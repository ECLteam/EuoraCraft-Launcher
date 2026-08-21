from __future__ import annotations

import base64
import copy
import hashlib
import json
import mimetypes
import re
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from threading import RLock
from typing import Any
from uuid import uuid4
from xml.etree import ElementTree as ET

from ECL.plugins.permissions import Permission, PermissionAction, PermissionScope
from ECL.utils.files import atomic_write_bytes, atomic_write_text

THEME_SCHEMA_VERSION = 1
MAX_ARCHIVE_BYTES = 50 * 1024 * 1024
MAX_UNPACKED_BYTES = 100 * 1024 * 1024
MAX_ARCHIVE_FILES = 128
ALLOWED_ASSET_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".woff2", ".svg"}
EDITABLE_ROOTS = {
    "meta",
    "schemes",
    "tokens",
    "background",
    "componentOverrides",
    "nodeOverrides",
    "instanceOverrides",
    "effects",
    "extensions",
}
SAFE_STYLE_PROPERTIES = {
    "background",
    "backgroundColor",
    "backgroundImage",
    "color",
    "borderColor",
    "borderWidth",
    "borderStyle",
    "borderRadius",
    "boxShadow",
    "opacity",
    "filter",
    "backdropFilter",
    "fontFamily",
    "fontSize",
    "fontWeight",
    "lineHeight",
    "letterSpacing",
    "outlineColor",
    "outlineStyle",
    "outlineWidth",
    "outlineOffset",
    "padding",
    "gap",
    "transform",
    "transition",
    "animation",
}
SAFE_EFFECT_TYPES = {"shadow", "glass", "gradient", "texture", "border", "filter", "motion"}
_THEME_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}$")
_DANGEROUS_SVG_STYLE_RE = re.compile(r"url\s*\(\s*['\"]?(?:https?:|data:|//)", re.IGNORECASE)


def _default_preset() -> dict[str, Any]:
    return {
        "schemaVersion": THEME_SCHEMA_VERSION,
        "id": "builtin.default",
        "meta": {
            "name": "ECL Default",
            "description": "EuoraCraft Launcher built-in theme",
            "author": "ECLTeam",
        },
        "schemes": {
            "light": {
                "canvas": "#f4f6fa",
                "surface": "rgba(255,255,255,0.88)",
                "text": "#1d2433",
            },
            "dark": {
                "canvas": "#171a21",
                "surface": "rgba(34,38,48,0.88)",
                "text": "#f1f3f7",
            },
        },
        "tokens": {
            "primary": "#5b6ff5",
            "radiusControl": "6px",
            "radiusCard": "8px",
            "radiusDialog": "10px",
            "shadowSurface": "0 1px 2px rgba(29,36,51,0.04)",
            "fontBody": "HarmonyOS Sans SC",
        },
        "background": {"type": "none", "opacity": 1, "blur": 0},
        "componentOverrides": {},
        "nodeOverrides": {},
        "effects": [],
        "assets": {},
        "pluginDependencies": [],
        "extensions": {},
    }


def _folia_preset() -> dict[str, Any]:
    """The bundled Folia visual skin.

    The rendering assets live in the frontend bundle; the preset only selects the
    skin and provides its portable token defaults.  Keeping it a regular v1
    preset means a copy made in the theme studio remains editable and exportable.
    """
    preset = _default_preset()
    preset["id"] = "builtin.folia"
    preset["uiSkin"] = "folia"
    preset["meta"] = {
        "name": "Folia",
        "description": "Folia glass and aurora interface skin",
        "author": "ECLTeam",
    }
    preset["schemes"] = {
        "light": {
            "canvas": "#f4f6fa",
            "surface": "rgba(255,255,255,0.62)",
            "surfaceMuted": "rgba(248,249,252,0.72)",
            "text": "#1d2433",
            "textSecondary": "#596275",
            "border": "rgba(29,36,51,0.12)",
            "primary": "#5b6ff5",
        },
        "dark": {
            "canvas": "#1a1c23",
            "surface": "rgba(32,36,46,0.62)",
            "surfaceMuted": "rgba(41,46,57,0.72)",
            "text": "#e8e9eb",
            "textSecondary": "#a0a3a8",
            "border": "rgba(255,255,255,0.10)",
            "primary": "#8291ff",
        },
    }
    preset["tokens"].update(
        {
            "primary": "#5b6ff5",
            "radiusControl": "6px",
            "radiusCard": "8px",
            "radiusDialog": "10px",
            "shadowSurface": "0 1px 2px rgba(29,36,51,0.04)",
        }
    )
    return preset


def _builtin_presets() -> dict[str, dict[str, Any]]:
    """
    Return fresh copies so no caller can mutate a process-wide preset.
    """
    return {"builtin.default": _default_preset(), "builtin.folia": _folia_preset()}


def _json_clone(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False))


def _validate_theme_id(value: Any) -> str:
    if not isinstance(value, str) or not _THEME_ID_RE.fullmatch(value):
        raise ValueError("主题 ID 只能包含字母、数字、点、短横线和下划线")
    return value


def normalize_preset(value: Any, *, forced_id: str | None = None) -> dict[str, Any]:  # noqa: C901
    if not isinstance(value, dict):
        raise ValueError("主题预设根节点必须是对象")
    if value.get("schemaVersion") != THEME_SCHEMA_VERSION:
        raise ValueError(f"不支持的主题协议版本: {value.get('schemaVersion')}")
    preset = _json_clone(value)
    preset["id"] = _validate_theme_id(forced_id or preset.get("id"))
    skin = preset.get("uiSkin", "classic")
    if skin not in {"classic", "folia"}:
        raise ValueError("主题 UI skin 不受支持")
    # Persist the default too: copied/exported legacy presets become explicit,
    # while older on-disk presets remain accepted during migration.
    preset["uiSkin"] = skin
    meta = preset.setdefault("meta", {})
    if not isinstance(meta, dict) or not isinstance(meta.get("name"), str) or not meta["name"].strip():
        raise ValueError("主题名称不能为空")
    if len(meta["name"].strip()) > 120:
        raise ValueError("主题名称不能超过 120 个字符")
    for key, default in (
        ("schemes", {}),
        ("tokens", {}),
        ("background", {}),
        ("componentOverrides", {}),
        ("nodeOverrides", {}),
        ("instanceOverrides", {}),
        ("assets", {}),
        ("extensions", {}),
    ):
        current = preset.setdefault(key, copy.deepcopy(default))
        if not isinstance(current, dict):
            raise ValueError(f"主题字段 {key} 必须是对象")
    for key in ("effects", "pluginDependencies"):
        current = preset.setdefault(key, [])
        if not isinstance(current, list):
            raise ValueError(f"主题字段 {key} 必须是数组")
    _validate_style_values(preset["tokens"], "tokens")
    for root in ("componentOverrides", "nodeOverrides", "instanceOverrides"):
        if len(preset[root]) > 2048:
            raise ValueError(f"主题字段 {root} 包含过多覆盖项")
        for target, override in preset[root].items():
            if not isinstance(target, str) or not target or len(target) > 240 or not isinstance(override, dict):
                raise ValueError(f"主题字段 {root} 包含无效目标")
            _validate_override(override, f"{root}.{target}")
    for recipe in preset["effects"]:
        recipe_type = recipe.get("type") if isinstance(recipe, dict) else None
        if not isinstance(recipe_type, str) or (
            recipe_type not in SAFE_EFFECT_TYPES
            and re.fullmatch(r"[a-zA-Z0-9_-]+\.[a-zA-Z0-9._-]+", recipe_type) is None
        ):
            raise ValueError("主题包含不支持的效果配方")
        _validate_style_values(recipe, "effects", allow_nested=True)
    return preset


def _validate_style_values(values: dict[str, Any], field: str, *, allow_nested: bool = False) -> None:
    if len(values) > 512:
        raise ValueError(f"主题字段 {field} 包含过多属性")
    for key, value in values.items():
        if not isinstance(key, str) or len(key) > 120:
            raise ValueError(f"主题字段 {field} 包含无效属性名")
        if isinstance(value, dict) and allow_nested:
            _validate_style_values(value, field, allow_nested=True)
        elif isinstance(value, list) and allow_nested:
            if len(value) > 120:
                raise ValueError(f"主题字段 {field} 包含过长数组")
            for item in value:
                if isinstance(item, dict):
                    _validate_style_values(item, field, allow_nested=True)
        elif value is not None and not isinstance(value, (str, int, float, bool)):
            raise ValueError(f"主题字段 {field} 包含无效属性值")
        elif isinstance(value, str) and (
            len(value) > 2048 or any(char in value for char in "{};") or "url(" in value.lower()
        ):
            raise ValueError(f"主题字段 {field} 包含不安全属性值")


def _validate_override(override: dict[str, Any], field: str) -> None:
    properties = override.get("properties", override)
    if not isinstance(properties, dict):
        raise ValueError(f"主题覆盖 {field} 的 properties 必须是对象")
    for name in properties:
        if name in {"states", "effects"} and properties is override:
            continue
        if name not in SAFE_STYLE_PROPERTIES:
            raise ValueError(f"主题属性不允许修改: {name}")
    _validate_style_values({key: value for key, value in properties.items() if key in SAFE_STYLE_PROPERTIES}, field)
    states = override.get("states", {})
    if not isinstance(states, dict) or not set(states).issubset({"hover", "active", "focus", "focusVisible", "disabled"}):
        raise ValueError(f"主题覆盖 {field} 包含无效状态")
    for state, state_properties in states.items():
        if not isinstance(state_properties, dict) or not set(state_properties).issubset(SAFE_STYLE_PROPERTIES):
            raise ValueError(f"主题状态 {state} 包含危险属性")
        _validate_style_values(state_properties, f"{field}.{state}")


def sanitize_svg(data: bytes) -> bytes:
    """
    Return a static, local-only SVG or reject malformed/dangerous input.
    """
    if len(data) > 5 * 1024 * 1024:
        raise ValueError("SVG 文件超过 5 MiB 限制")
    lowered = data.lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise ValueError("SVG 不允许包含 DTD 或实体声明")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValueError("SVG XML 格式无效") from exc
    if root.tag.rsplit("}", 1)[-1].lower() != "svg":
        raise ValueError("资源不是有效的 SVG 文档")

    blocked_tags = {"script", "foreignobject", "iframe", "object", "embed", "audio", "video"}
    for parent in list(root.iter()):
        for child in list(parent):
            if child.tag.rsplit("}", 1)[-1].lower() in blocked_tags:
                parent.remove(child)
        for attr, raw_value in list(parent.attrib.items()):
            local_attr = attr.rsplit("}", 1)[-1].lower()
            value = raw_value.strip()
            if local_attr.startswith("on"):
                del parent.attrib[attr]
                continue
            if local_attr in {"href", "src"} and value and not value.startswith("#"):
                del parent.attrib[attr]
                continue
            if local_attr == "style" and _DANGEROUS_SVG_STYLE_RE.search(value):
                del parent.attrib[attr]
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _safe_archive_name(name: str) -> PurePosixPath:
    path = PurePosixPath(name.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError("主题包包含不安全路径")
    return path


@dataclass
class ThemeDesignSession:
    session_id: str
    preset_id: str
    draft: dict[str, Any]
    base: dict[str, Any]
    revision: int = 0
    selection: dict[str, Any] | None = None
    dirty: bool = False
    show_slots: bool = False
    slot_hosts: list[dict[str, Any]] = field(default_factory=list)
    undo_stack: list[dict[str, Any]] = field(default_factory=list)
    redo_stack: list[dict[str, Any]] = field(default_factory=list)


class ThemeService:
    def __init__(self, data_path: Path, config: Any, events: Any, plugins: Any | None = None) -> None:
        self.data_path = Path(data_path)
        self.theme_dir = self.data_path / "themes"
        self.draft_dir = self.data_path / "theme_drafts"
        self.config = config
        self.events = events
        self.plugins = plugins
        self._sessions: dict[str, ThemeDesignSession] = {}
        self._lock = RLock()
        self.theme_dir.mkdir(parents=True, exist_ok=True)
        self.draft_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_active_theme()

    def _ensure_active_theme(self) -> None:
        ui = self.config.get_config("ui") or {}
        theme_config = dict(ui.get("theme") or {})
        if theme_config.get("active_preset_id"):
            return
        legacy = _default_preset()
        legacy["id"] = "user.migrated"
        legacy["meta"] = {
            "name": "Migrated appearance",
            "description": "Migrated from the legacy launcher appearance settings",
            "author": "EuoraCraft Launcher",
        }
        if theme_config.get("primary_color"):
            legacy["tokens"]["primary"] = theme_config["primary_color"]
        background = dict(ui.get("background") or {})
        legacy["background"] = {
            "type": background.get("type", "none"),
            "path": background.get("path", ""),
            "opacity": background.get("opacity", theme_config.get("background_opacity", 1)),
            "blur": background.get("blur", theme_config.get("blur_amount", 0)),
        }
        self.save_preset(legacy)
        theme_config["active_preset_id"] = legacy["id"]
        ui["theme"] = theme_config
        self.config.save_config("ui", ui)

    def _preset_path(self, preset_id: str) -> Path:
        return self.theme_dir / _validate_theme_id(preset_id) / "theme.json"

    def list_presets(self) -> list[dict[str, Any]]:
        items = [self._summary(preset, source="builtin", readonly=True) for preset in _builtin_presets().values()]
        for path in sorted(self.theme_dir.glob("*/theme.json")):
            try:
                preset = normalize_preset(json.loads(path.read_text(encoding="utf-8")))
                items.append(self._summary(preset, source="user", readonly=False))
            except (OSError, ValueError, json.JSONDecodeError):
                continue
        for plugin_name, preset in self._plugin_presets():
            summary = self._summary(preset, source="plugin", readonly=True)
            summary["plugin"] = plugin_name
            items.append(summary)
        return items

    def _enabled_plugins(self) -> list[tuple[str, Any]]:
        if self.plugins is None:
            return []
        result = []
        for entry in self.plugins.list_plugins():
            if entry.get("status") != "enabled":
                continue
            name = entry.get("name")
            plugin = self.plugins.get_plugin(name) if isinstance(name, str) else None
            if plugin is not None:
                result.append((name, plugin))
        return result

    def _has_theme_permission(self, plugin_name: str, resource: str) -> bool:
        manager = getattr(self.plugins, "_permission_manager", None)
        if manager is None:
            return False
        return manager.has_permission(
            plugin_name,
            Permission(PermissionScope.THEME, PermissionAction.READ, resource),
        )

    @staticmethod
    def _read_plugin_json(plugin: Any, raw: Any) -> Any:
        if isinstance(raw, (dict, list)):
            return _json_clone(raw)
        if not isinstance(raw, str):
            raise ValueError("插件主题贡献必须是对象或相对 JSON 路径")
        root = Path(plugin.plugin_dir).resolve()
        path = (root / raw).resolve()
        if root not in path.parents or path.suffix.lower() != ".json":
            raise ValueError("插件主题贡献路径越界或格式无效")
        return json.loads(path.read_text(encoding="utf-8"))

    def _plugin_presets(self) -> list[tuple[str, dict[str, Any]]]:
        presets: list[tuple[str, dict[str, Any]]] = []
        for plugin_name, plugin in self._enabled_plugins():
            if not self._has_theme_permission(plugin_name, "preset:*"):
                continue
            contributes = plugin.metadata.get("contributes") or {}
            raw_items = contributes.get("themePresets", []) if isinstance(contributes, dict) else []
            if not isinstance(raw_items, list):
                continue
            for raw in raw_items[:64]:
                try:
                    preset = normalize_preset(self._read_plugin_json(plugin, raw))
                    if not preset["id"].startswith(f"plugin.{plugin_name}."):
                        continue
                    presets.append((plugin_name, preset))
                except (OSError, ValueError, json.JSONDecodeError):
                    continue
        return presets

    def extension_catalog(self) -> dict[str, Any]:
        result: dict[str, list[dict[str, Any]]] = {"effects": [], "tokens": [], "nodes": [], "windows": []}
        mapping = {
            "themeEffects": ("effects", "effect:*"),
            "themeTokens": ("tokens", "token:*"),
            "themeNodes": ("nodes", "node:*"),
        }
        for plugin_name, plugin in self._enabled_plugins():
            contributes = plugin.metadata.get("contributes") or {}
            if not isinstance(contributes, dict):
                continue
            for manifest_key, (result_key, permission) in mapping.items():
                if not self._has_theme_permission(plugin_name, permission):
                    continue
                raw_items = contributes.get(manifest_key, [])
                if not isinstance(raw_items, list):
                    continue
                for raw in raw_items[:128]:
                    try:
                        value = self._read_plugin_json(plugin, raw)
                    except (OSError, ValueError, json.JSONDecodeError):
                        continue
                    values = value if isinstance(value, list) else [value]
                    result[result_key].extend(
                        {**item, "plugin": plugin_name}
                        for item in values
                        if isinstance(item, dict) and str(item.get("id", "")).startswith(f"{plugin_name}.")
                    )
            windows = contributes.get("windows", [])
            if isinstance(windows, list):
                result["windows"].extend({**item, "plugin": plugin_name} for item in windows if isinstance(item, dict))
        return result

    @staticmethod
    def _summary(preset: dict[str, Any], *, source: str, readonly: bool) -> dict[str, Any]:
        return {
            "id": preset["id"],
            "name": preset.get("meta", {}).get("name", preset["id"]),
            "description": preset.get("meta", {}).get("description", ""),
            "author": preset.get("meta", {}).get("author", ""),
            "source": source,
            "readonly": readonly,
            "pluginDependencies": preset.get("pluginDependencies", []),
        }

    def get_preset(self, preset_id: str) -> dict[str, Any]:
        builtin = _builtin_presets().get(preset_id)
        if builtin is not None:
            return builtin
        for _, preset in self._plugin_presets():
            if preset["id"] == preset_id:
                return preset
        path = self._preset_path(preset_id)
        if not path.is_file():
            raise ValueError(f"主题不存在: {preset_id}")
        return normalize_preset(json.loads(path.read_text(encoding="utf-8")))

    def save_preset(self, preset: dict[str, Any]) -> dict[str, Any]:
        normalized = normalize_preset(preset)
        if normalized["id"].startswith("builtin."):
            raise ValueError("内置主题不可覆盖")
        path = self._preset_path(normalized["id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, json.dumps(normalized, ensure_ascii=False, indent=2))
        self.events.emit("theme:library_changed", {"presetId": normalized["id"], "action": "saved"})
        return normalized

    def asset_data_url(self, preset_id: str, asset_path: str) -> dict[str, str]:
        _validate_theme_id(preset_id)
        archive_path = _safe_archive_name(asset_path)
        if not archive_path.parts or archive_path.parts[0] != "assets":
            raise ValueError("主题资源必须位于 assets 目录")
        path = (self._preset_path(preset_id).parent / Path(*archive_path.parts)).resolve()
        root = self._preset_path(preset_id).parent.resolve()
        if root not in path.parents or not path.is_file() or path.suffix.lower() not in ALLOWED_ASSET_EXTENSIONS:
            raise ValueError("主题资源不存在或类型不受支持")
        data = path.read_bytes()
        if len(data) > 10 * 1024 * 1024:
            raise ValueError("单个主题资源超过 10 MiB 限制")
        if path.suffix.lower() == ".svg":
            data = sanitize_svg(data)
            mime = "image/svg+xml"
        elif path.suffix.lower() == ".woff2":
            mime = "font/woff2"
        else:
            mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        encoded = base64.b64encode(data).decode("ascii")
        return {"mime": mime, "dataUrl": f"data:{mime};base64,{encoded}"}

    def delete_preset(self, preset_id: str) -> None:
        if preset_id.startswith("builtin."):
            raise ValueError("内置主题不可删除")
        ui = self.config.get_config("ui") or {}
        if (ui.get("theme") or {}).get("active_preset_id") == preset_id:
            raise ValueError("当前正在使用的主题不可删除")
        directory = self._preset_path(preset_id).parent
        if not directory.is_dir():
            raise ValueError(f"主题不存在: {preset_id}")
        shutil.rmtree(directory)
        self.events.emit("theme:library_changed", {"presetId": preset_id, "action": "deleted"})

    def activate(self, preset_id: str) -> dict[str, Any]:
        preset = self.get_preset(preset_id)
        ui = self.config.get_config("ui") or {}
        theme_config = dict(ui.get("theme") or {})
        theme_config["active_preset_id"] = preset_id
        ui["theme"] = theme_config
        self.config.save_config("ui", ui)
        self.events.emit("theme:activated", {"presetId": preset_id, "preset": preset})
        return preset

    def active_preset(self) -> dict[str, Any]:
        ui = self.config.get_config("ui") or {}
        preset_id = (ui.get("theme") or {}).get("active_preset_id") or "builtin.default"
        try:
            return self.get_preset(preset_id)
        except ValueError:
            return _default_preset()

    def start_session(self, preset_id: str | None = None, *, restore: bool = True) -> dict[str, Any]:
        preset = self.get_preset(preset_id) if preset_id else self.active_preset()
        if preset["id"].startswith(("builtin.", "plugin.")):
            preset = _json_clone(preset)
            preset["id"] = f"user.{uuid4().hex[:12]}"
            preset["meta"]["name"] = f"{preset['meta']['name']} Copy"
        base_preset = _json_clone(preset)
        session_id = uuid4().hex
        if restore:
            recoveries = sorted(self.draft_dir.glob(f"*--{preset['id']}.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            if recoveries:
                try:
                    recovered = json.loads(recoveries[0].read_text(encoding="utf-8"))
                    preset = normalize_preset(recovered["draft"])
                except (OSError, ValueError, json.JSONDecodeError, KeyError):
                    pass
        session = ThemeDesignSession(session_id=session_id, preset_id=preset["id"], draft=preset, base=base_preset)
        with self._lock:
            self._sessions[session_id] = session
        self._checkpoint(session)
        snapshot = self._snapshot(session)
        self.events.emit("theme:design_changed", snapshot)
        return snapshot

    def get_session(self, session_id: str) -> dict[str, Any]:
        return self._snapshot(self._require_session(session_id))

    def select(self, session_id: str, selection: dict[str, Any] | None) -> dict[str, Any]:
        session = self._require_session(session_id)
        session.selection = _json_clone(selection) if selection is not None else None
        session.revision += 1
        snapshot = self._snapshot(session)
        self.events.emit("theme:selection_changed", snapshot)
        return snapshot

    def set_overlay(
        self,
        session_id: str,
        *,
        show_slots: bool,
        slot_hosts: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Update transient design overlays without dirtying the preset or its history.
        """
        session = self._require_session(session_id)
        session.show_slots = show_slots
        if slot_hosts is not None:
            session.slot_hosts = _json_clone(slot_hosts)
        snapshot = self._snapshot(session)
        self.events.emit("theme:overlay_changed", snapshot)
        return snapshot

    def patch(self, session_id: str, expected_revision: int, operations: list[dict[str, Any]]) -> dict[str, Any]:
        session = self._require_session(session_id)
        if session.revision != expected_revision:
            raise ThemeRevisionConflict(self._snapshot(session))
        previous = _json_clone(session.draft)
        next_draft = _json_clone(session.draft)
        for operation in operations:
            self._apply_operation(next_draft, operation)
        session.draft = normalize_preset(next_draft)
        session.undo_stack.append(previous)
        if len(session.undo_stack) > 100:
            session.undo_stack.pop(0)
        session.redo_stack.clear()
        session.revision += 1
        session.dirty = True
        self._checkpoint(session)
        snapshot = self._snapshot(session)
        self.events.emit("theme:preview_changed", snapshot)
        return snapshot

    def undo(self, session_id: str, expected_revision: int) -> dict[str, Any]:
        session = self._require_revision(session_id, expected_revision)
        if session.undo_stack:
            session.redo_stack.append(_json_clone(session.draft))
            session.draft = session.undo_stack.pop()
            session.revision += 1
            session.dirty = True
            self._checkpoint(session)
        snapshot = self._snapshot(session)
        self.events.emit("theme:preview_changed", snapshot)
        return snapshot

    def redo(self, session_id: str, expected_revision: int) -> dict[str, Any]:
        session = self._require_revision(session_id, expected_revision)
        if session.redo_stack:
            session.undo_stack.append(_json_clone(session.draft))
            session.draft = session.redo_stack.pop()
            session.revision += 1
            session.dirty = True
            self._checkpoint(session)
        snapshot = self._snapshot(session)
        self.events.emit("theme:preview_changed", snapshot)
        return snapshot

    def commit(self, session_id: str) -> dict[str, Any]:
        session = self._require_session(session_id)
        preset = self.save_preset(session.draft)
        self.activate(preset["id"])
        session.dirty = False
        session.base = _json_clone(preset)
        session.revision += 1
        self._remove_checkpoint(session)
        snapshot = self._snapshot(session)
        self.events.emit("theme:design_committed", snapshot)
        return snapshot

    def save_as(self, session_id: str, name: str) -> dict[str, Any]:
        session = self._require_session(session_id)
        previous_checkpoint = self._checkpoint_path(session)
        preset = _json_clone(session.draft)
        preset["id"] = f"user.{uuid4().hex[:12]}"
        preset["meta"]["name"] = name.strip()
        preset = self.save_preset(preset)
        self.activate(preset["id"])
        session.preset_id = preset["id"]
        session.draft = _json_clone(preset)
        session.base = _json_clone(preset)
        session.dirty = False
        session.revision += 1
        previous_checkpoint.unlink(missing_ok=True)
        snapshot = self._snapshot(session)
        self.events.emit("theme:design_committed", snapshot)
        return snapshot

    def discard(self, session_id: str, *, keep_recovery: bool = False) -> None:
        session = self._require_session(session_id)
        if not keep_recovery:
            self._remove_checkpoint(session)
        with self._lock:
            self._sessions.pop(session_id, None)
        self.events.emit("theme:design_discarded", {"sessionId": session_id, "keepRecovery": keep_recovery})

    def _require_session(self, session_id: str) -> ThemeDesignSession:
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            raise ValueError("主题设计会话不存在或已结束")
        return session

    def _require_revision(self, session_id: str, expected_revision: int) -> ThemeDesignSession:
        session = self._require_session(session_id)
        if session.revision != expected_revision:
            raise ThemeRevisionConflict(self._snapshot(session))
        return session

    @staticmethod
    def _apply_operation(target: dict[str, Any], operation: dict[str, Any]) -> None:  # noqa: C901
        if operation.get("op") not in {"set", "remove"}:
            raise ValueError("主题补丁只支持 set/remove")
        raw_path = operation.get("path")
        if not isinstance(raw_path, str) or not raw_path.startswith("/"):
            raise ValueError("主题补丁路径无效")
        parts = [part.replace("~1", "/").replace("~0", "~") for part in raw_path[1:].split("/") if part]
        if not parts or parts[0] not in EDITABLE_ROOTS:
            raise ValueError("主题补丁试图修改只读字段")
        if parts[0] == "meta" and (len(parts) < 2 or parts[1] not in {"name", "description", "author"}):
            raise ValueError("主题元数据字段不可修改")
        cursor: Any = target
        for key in parts[:-1]:
            if isinstance(cursor, dict):
                cursor = cursor.setdefault(key, {})
            elif isinstance(cursor, list) and key.isdigit() and int(key) < len(cursor):
                cursor = cursor[int(key)]
            else:
                raise ValueError("主题补丁路径不存在")
        last = parts[-1]
        if operation["op"] == "remove":
            if isinstance(cursor, dict):
                cursor.pop(last, None)
            elif isinstance(cursor, list) and last.isdigit() and int(last) < len(cursor):
                cursor.pop(int(last))
            return
        value = _json_clone(operation.get("value"))
        if isinstance(cursor, dict):
            cursor[last] = value
        elif isinstance(cursor, list) and last.isdigit() and int(last) <= len(cursor):
            index = int(last)
            if index == len(cursor):
                cursor.append(value)
            else:
                cursor[index] = value
        else:
            raise ValueError("主题补丁路径不可写")

    def _snapshot(self, session: ThemeDesignSession) -> dict[str, Any]:
        enabled_plugins = {name for name, _ in self._enabled_plugins()}
        dependencies = []
        for raw in session.draft.get("pluginDependencies", []):
            if isinstance(raw, dict):
                dependency = _json_clone(raw)
                dependency["available"] = dependency.get("id") in enabled_plugins
                dependencies.append(dependency)
        return {
            "sessionId": session.session_id,
            "presetId": session.preset_id,
            "draft": _json_clone(session.draft),
            "basePreset": _json_clone(session.base),
            "selection": _json_clone(session.selection),
            "revision": session.revision,
            "dirty": session.dirty,
            "canUndo": bool(session.undo_stack),
            "canRedo": bool(session.redo_stack),
            "pluginDependencies": dependencies,
            "showSlots": session.show_slots,
            "slotHosts": _json_clone(session.slot_hosts),
        }

    def _checkpoint_path(self, session: ThemeDesignSession) -> Path:
        return self.draft_dir / f"{session.session_id}--{session.preset_id}.json"

    def _checkpoint(self, session: ThemeDesignSession) -> None:
        payload = {"sessionId": session.session_id, "presetId": session.preset_id, "draft": session.draft}
        atomic_write_text(self._checkpoint_path(session), json.dumps(payload, ensure_ascii=False, indent=2))

    def _remove_checkpoint(self, session: ThemeDesignSession) -> None:
        self._checkpoint_path(session).unlink(missing_ok=True)

    def export_preset(self, preset_id: str, output_path: Path, *, include_instance_overrides: bool = False) -> Path:
        preset = self.get_preset(preset_id)
        if not include_instance_overrides:
            preset = _json_clone(preset)
            preset.pop("instanceOverrides", None)
        output_path = Path(output_path)
        if output_path.suffix.lower() != ".ecltheme":
            output_path = output_path.with_suffix(".ecltheme")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        source_dir = self._preset_path(preset_id).parent if not preset_id.startswith("builtin.") else None
        files: dict[str, bytes] = {
            "theme.json": json.dumps(preset, ensure_ascii=False, indent=2).encode("utf-8")
        }
        if source_dir and (source_dir / "assets").is_dir():
            for asset in (source_dir / "assets").rglob("*"):
                if not asset.is_file() or asset.suffix.lower() not in ALLOWED_ASSET_EXTENSIONS:
                    continue
                relative = PurePosixPath("assets") / PurePosixPath(asset.relative_to(source_dir / "assets").as_posix())
                files[str(relative)] = sanitize_svg(asset.read_bytes()) if asset.suffix.lower() == ".svg" else asset.read_bytes()
        manifest = {
            "format": "euoracraft-theme",
            "schemaVersion": THEME_SCHEMA_VERSION,
            "presetId": preset["id"],
            "checksums": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
        }
        files["manifest.json"] = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
        temp = output_path.with_suffix(output_path.suffix + ".tmp")
        with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in files.items():
                archive.writestr(name, data)
        temp.replace(output_path)
        return output_path

    def import_preset(self, archive_path: Path, *, replace: bool = False) -> dict[str, Any]:
        archive_path = Path(archive_path)
        if not archive_path.is_file() or archive_path.stat().st_size > MAX_ARCHIVE_BYTES:
            raise ValueError("主题包不存在或超过 50 MiB")
        with zipfile.ZipFile(archive_path) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ARCHIVE_FILES or sum(info.file_size for info in infos) > MAX_UNPACKED_BYTES:
                raise ValueError("主题包文件数量或解压体积超过限制")
            names = {_safe_archive_name(info.filename): info for info in infos if not info.is_dir()}
            theme_info = names.get(PurePosixPath("theme.json"))
            manifest_info = names.get(PurePosixPath("manifest.json"))
            if theme_info is None or manifest_info is None:
                raise ValueError("主题包缺少 manifest.json 或 theme.json")
            manifest = json.loads(archive.read(manifest_info))
            preset = normalize_preset(json.loads(archive.read(theme_info)))
            checksums = manifest.get("checksums") if isinstance(manifest, dict) else None
            if not isinstance(checksums, dict):
                raise ValueError("主题包缺少资源校验和")
            raw_files: dict[PurePosixPath, bytes] = {}
            for name, info in names.items():
                data = archive.read(info)
                expected = checksums.get(str(name))
                if name != PurePosixPath("manifest.json") and expected != hashlib.sha256(data).hexdigest():
                    raise ValueError(f"主题包文件校验失败: {name}")
                if name.parts[0] == "assets":
                    if name.suffix.lower() not in ALLOWED_ASSET_EXTENSIONS:
                        raise ValueError(f"主题包包含不支持的资源: {name}")
                    if name.suffix.lower() == ".svg":
                        data = sanitize_svg(data)
                    raw_files[name] = data
        original_id = preset["id"]
        # Builtins are exportable but can never be restored over the bundled
        # definition.  Importing one produces the same editable local copy as
        # opening it in the theme studio.
        if original_id.startswith("builtin.") or (self._preset_path(original_id).exists() and not replace):
            preset["id"] = f"user.{uuid4().hex[:12]}"
            preset["meta"]["name"] = f"{preset['meta']['name']} (Imported)"
        target_dir = self._preset_path(preset["id"]).parent
        target_dir.mkdir(parents=True, exist_ok=True)
        for name, data in raw_files.items():
            destination = target_dir.joinpath(*name.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_bytes(destination, data)
        saved = self.save_preset(preset)
        return {"preset": saved, "originalId": original_id, "importedId": saved["id"]}


class ThemeRevisionConflict(ValueError):
    def __init__(self, snapshot: dict[str, Any]) -> None:
        super().__init__("主题草稿已在另一个窗口更新")
        self.snapshot = snapshot


__all__ = [
    "ALLOWED_ASSET_EXTENSIONS",
    "THEME_SCHEMA_VERSION",
    "ThemeRevisionConflict",
    "ThemeService",
    "normalize_preset",
    "sanitize_svg",
]
