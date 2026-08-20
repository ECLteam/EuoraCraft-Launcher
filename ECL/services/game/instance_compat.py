from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ECL.utils import get_logger


@dataclass(slots=True)
class ExternalInstanceMetadata:
    """
    保存一个第三方启动器针对单个实例提供的只读元数据。
    """

    source: str
    modified_ns: int
    fields: dict[str, Any] = field(default_factory=dict)
    stats: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _read_text(path: Path) -> str:
    last_error: UnicodeDecodeError | None = None
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    return path.read_text(encoding="utf-8")


def _parse_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().casefold()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    return None


def _non_negative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return None


def _path_key(path: Path | str) -> str:
    return os.path.normcase(os.path.normpath(str(Path(path).expanduser().resolve(strict=False))))


def _find_key(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        for current_key, current_value in value.items():
            if str(current_key).casefold() == key.casefold():
                return current_value
        for current_value in value.values():
            result = _find_key(current_value, key)
            if result is not None:
                return result
    elif isinstance(value, list):
        for current_value in value:
            result = _find_key(current_value, key)
            if result is not None:
                return result
    return None


class InstanceCompatibilityReader:
    """
    读取第三方启动器的实例元数据，不对第三方文件执行任何写入。

    解析失败会转换为来源级警告，使单个损坏配置不会阻断整个版本扫描。
    """

    _IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")
    _HMCL_ICON_MAP = {
        "grass": "grass",
        "chest": "chest",
        "command": "command",
        "forge": "forge",
        "neo_forge": "neoforge",
        "neoforge": "neoforge",
        "fabric": "fabric",
        "quilt": "quilt",
        "optifine": "optifine",
        "furnace": "iron",
        "craft_table": "quartz",
    }

    def __init__(self) -> None:
        self._logger = get_logger("InstanceCompatibilityReader")
        self._qomicex_cache: dict[
            str,
            tuple[tuple[int, int], list[dict[str, Any]] | None, str | None],
        ] = {}

    @staticmethod
    def resolve_qomicex_path(manual_path: str | Path | None = None) -> Path | None:
        """
        按手动配置、环境变量、引导文件和默认目录顺序查找 Qomicex 数据文件。

        :param manual_path: 设置页指定的 ``instances.json`` 或其父目录
        :return: 首个存在的数据文件；未找到时返回 ``None``
        """
        candidates: list[Path] = []
        if manual_path and str(manual_path).strip():
            candidates.append(Path(str(manual_path).strip()).expanduser())
        env_home = os.environ.get("QOMICEX_HOME", "").strip()
        if env_home:
            candidates.append(Path(env_home).expanduser())

        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        if local_app_data:
            base = Path(local_app_data) / "qomicex-launcher"
            bootstrap = base / ".qomicex-bootstrap"
            if bootstrap.is_file():
                try:
                    bootstrap_value = _read_text(bootstrap).strip()
                    try:
                        parsed = json.loads(bootstrap_value)
                    except ValueError:
                        parsed = bootstrap_value
                    if isinstance(parsed, dict):
                        parsed = parsed.get("dataDir") or parsed.get("path") or parsed.get("home")
                    if isinstance(parsed, str) and parsed.strip():
                        candidates.append(Path(parsed.strip()).expanduser())
                except (OSError, UnicodeDecodeError):
                    pass
            candidates.extend((base, base / "data"))

        for candidate in candidates:
            file_path = candidate if candidate.name.casefold() == "instances.json" else candidate / "instances.json"
            if file_path.is_file():
                return file_path.resolve(strict=False)
        return None

    @staticmethod
    def _parse_pcl_ini(path: Path) -> dict[str, str]:
        values: dict[str, str] = {}
        for raw_line in _read_text(path).splitlines():
            line = raw_line.strip()
            if not line or line.startswith(("#", ";", "[")) or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip().casefold()] = value.strip()
        return values

    def _read_pcl(self, instance_path: Path) -> ExternalInstanceMetadata | None:
        setup_path = instance_path / "PCL" / "Setup.ini"
        if not setup_path.is_file():
            return None
        metadata = ExternalInstanceMetadata(source="pcl", modified_ns=setup_path.stat().st_mtime_ns)
        try:
            values = self._parse_pcl_ini(setup_path)
            description = values.get("custominfo", "").strip()
            if description:
                metadata.fields["description"] = description
            if "isstar" in values:
                favorite = _parse_bool(values["isstar"])
                if favorite is not None:
                    metadata.fields["favorite"] = favorite

            display_type = _non_negative_int(values.get("displaytype"))
            if display_type is not None:
                metadata.fields["hidden"] = display_type == 1
                category = {2: "modpack", 3: "vanilla", 5: "test"}.get(display_type)
                if category:
                    metadata.fields["categoryId"] = category

            custom_logo = instance_path / "PCL" / "Logo.png"
            if custom_logo.is_file() and _parse_bool(values.get("logocustom")) is not False:
                metadata.fields["icon"] = {"type": "external", "value": str(custom_logo), "source": "pcl"}
                metadata.modified_ns = max(metadata.modified_ns, custom_logo.stat().st_mtime_ns)
            else:
                logo_name = values.get("logo", "").casefold()
                logo_map = {
                    "grass": ("builtin", "grass"),
                    "chest": ("builtin", "chest"),
                    "command": ("builtin", "command"),
                    "neoforge": ("loader", "neoforge"),
                    "forge": ("loader", "forge"),
                    "fabric": ("loader", "fabric"),
                    "quilt": ("loader", "quilt"),
                    "optifine": ("loader", "optifine"),
                }
                matched_logo = next((value for key, value in logo_map.items() if key in logo_name), None)
                if matched_logo is not None:
                    metadata.fields["icon"] = {
                        "type": matched_logo[0],
                        "value": matched_logo[1],
                        "source": "pcl",
                    }
            launch_count = _non_negative_int(values.get("versionlaunchcount"))
            if launch_count is not None:
                metadata.stats["launchCount"] = launch_count
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            metadata.warnings.append(f"PCL 配置读取失败: {exc}")
            self._logger.warning("读取 PCL 实例配置失败 %s: %s", setup_path, exc)
        return metadata

    def _read_hmcl(self, instance_path: Path) -> ExternalInstanceMetadata | None:
        settings_path = instance_path / ".hmcl" / "config" / "instance-game-settings.json"
        icon_paths = [instance_path / f"icon{extension}" for extension in self._IMAGE_EXTENSIONS]
        local_icon = next((path for path in icon_paths if path.is_file()), None)
        if not settings_path.is_file() and local_icon is None:
            return None
        modified_ns = max(
            [path.stat().st_mtime_ns for path in (settings_path, local_icon) if path is not None and path.is_file()],
            default=0,
        )
        metadata = ExternalInstanceMetadata(source="hmcl", modified_ns=modified_ns)
        try:
            icon_name = "default"
            if settings_path.is_file():
                data = json.loads(_read_text(settings_path))
                raw_icon = _find_key(data, "icon")
                if isinstance(raw_icon, str) and raw_icon.strip():
                    icon_name = raw_icon.strip().casefold()
            if local_icon is not None and icon_name == "default":
                metadata.fields["icon"] = {"type": "external", "value": str(local_icon), "source": "hmcl"}
            elif icon_name in self._HMCL_ICON_MAP:
                icon_value = self._HMCL_ICON_MAP[icon_name]
                icon_type = "loader" if icon_value in {"forge", "neoforge", "fabric", "quilt", "optifine"} else "builtin"
                metadata.fields["icon"] = {"type": icon_type, "value": icon_value, "source": "hmcl"}
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            metadata.warnings.append(f"HMCL 配置读取失败: {exc}")
            self._logger.warning("读取 HMCL 实例配置失败 %s: %s", settings_path, exc)
        return metadata

    @staticmethod
    def _qomicex_instances(data: Any) -> list[dict[str, Any]]:
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            for key in ("instances", "data", "items"):
                value = data.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
        return []

    @staticmethod
    def _match_qomicex_instance(
        instances: list[dict[str, Any]],
        instance_path: Path,
        version_id: str,
        vanilla_name: str,
        primary_loader: str,
    ) -> list[dict[str, Any]]:
        exact = [item for item in instances if item.get("gameDir") and _path_key(item["gameDir"]) == _path_key(instance_path)]
        if exact:
            return exact
        version_key = version_id.casefold()
        vanilla_key = vanilla_name.casefold()
        loader_key = primary_loader.casefold()
        matched = [
            item
            for item in instances
            if str(item.get("name") or "").casefold() == version_key
            and str(item.get("gameVersion") or "").casefold() in {"", vanilla_key}
            and str(item.get("loader") or "vanilla").casefold() in {"", loader_key}
        ]
        if len(matched) > 1:
            _logger = get_logger("EuoraCraft-Launcher.InstanceCompatibilityReader")
            _logger.debug(
                "Qomicex 模糊匹配: instance_path=%s, version_id=%s, vanilla_name=%s, "
                "loader=%s, matched_count=%d, candidates=[%s]",
                instance_path,
                version_id,
                vanilla_name,
                primary_loader,
                len(matched),
                ", ".join(
                    f"name={m.get('name','?')},gameDir={m.get('gameDir','?')},"
                    f"gameVersion={m.get('gameVersion','?')},loader={m.get('loader','?')}"
                    for m in matched
                ),
            )
        return matched

    def _load_qomicex_instances(
        self,
        data_path: Path,
    ) -> tuple[list[dict[str, Any]] | None, int, str | None]:
        """
        按文件签名缓存 Qomicex 实例索引，避免一次扫描中为每个版本重复解析 JSON。

        :param data_path: Qomicex ``instances.json`` 路径
        :return: 实例列表、文件修改时间和可选错误文本
        """
        try:
            stat = data_path.stat()
        except OSError as exc:
            return None, 0, str(exc)
        signature = (stat.st_mtime_ns, stat.st_size)
        cache_key = _path_key(data_path)
        cached = self._qomicex_cache.get(cache_key)
        if cached is not None and cached[0] == signature:
            return cached[1], stat.st_mtime_ns, cached[2]
        try:
            instances = self._qomicex_instances(json.loads(_read_text(data_path)))
            error = None
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            instances = None
            error = str(exc)
            self._logger.warning("读取 Qomicex 实例索引失败 %s: %s", data_path, exc)
        self._qomicex_cache[cache_key] = (signature, instances, error)
        return instances, stat.st_mtime_ns, error

    def _read_qomicex(
        self,
        instance_path: Path,
        version_id: str,
        vanilla_name: str,
        primary_loader: str,
        configured_path: str | Path | None,
    ) -> ExternalInstanceMetadata | None:
        data_path = self.resolve_qomicex_path(configured_path)
        if data_path is None:
            return None
        instances, modified_ns, error = self._load_qomicex_instances(data_path)
        if instances is None:
            return ExternalInstanceMetadata(
                source="qomicex",
                modified_ns=modified_ns,
                warnings=[f"Qomicex 配置读取失败: {error}"],
            )

        matches = self._match_qomicex_instance(
            instances,
            instance_path,
            version_id,
            vanilla_name,
            primary_loader,
        )
        if len(matches) != 1:
            if len(matches) > 1:
                self._logger.warning(
                    "Qomicex 实例匹配存在歧义: instance_path=%s, version_id=%s, vanilla_name=%s, "
                    "primary_loader=%s, matched_count=%d, matched_names=[%s]",
                    instance_path,
                    version_id,
                    vanilla_name,
                    primary_loader,
                    len(matches),
                    ", ".join(str(m.get("name", "?")) for m in matches),
                )
            return None

        item = matches[0]
        metadata = ExternalInstanceMetadata(source="qomicex", modified_ns=modified_ns)
        description = str(item.get("modpackSummary") or "").strip()
        if description:
            metadata.fields["description"] = description
        if isinstance(item.get("isHidden"), bool):
            metadata.fields["hidden"] = item["isHidden"]
        if isinstance(item.get("isDefault"), bool):
            metadata.fields["pinned"] = item["isDefault"]

        icon_data = item.get("iconData")
        icon_name = str(item.get("icon") or "").strip().casefold()
        if isinstance(icon_data, str) and icon_data.startswith("data:image/"):
            metadata.fields["icon"] = {"type": "data", "value": icon_data, "source": "qomicex"}
        elif icon_name:
            icon_type = "loader" if icon_name in {"forge", "neoforge", "fabric", "quilt", "optifine"} else "builtin"
            metadata.fields["icon"] = {"type": icon_type, "value": icon_name, "source": "qomicex"}

        play_time_minutes = _non_negative_int(item.get("playTime"))
        if play_time_minutes is not None:
            metadata.stats["totalRunDurationSeconds"] = play_time_minutes * 60
        last_played = item.get("lastPlayed")
        if isinstance(last_played, str) and last_played.strip():
            metadata.stats["lastLaunchedAt"] = last_played.strip()
        return metadata

    def read_instance(
        self,
        game_path: Path,
        version_id: str,
        *,
        vanilla_name: str,
        primary_loader: str,
        qomicex_path: str | Path | None = None,
    ) -> list[ExternalInstanceMetadata]:
        """
        汇总指定实例可用的第三方元数据来源。

        :param game_path: Minecraft 游戏根目录
        :param version_id: 版本目录名称
        :param vanilla_name: 扫描得到的原版版本号
        :param primary_loader: 扫描得到的主加载器
        :param qomicex_path: 可选的 Qomicex 手动数据路径
        :return: 按来源分离的只读元数据
        """
        instance_path = game_path / "versions" / version_id
        sources = [
            self._read_pcl(instance_path),
            self._read_hmcl(instance_path),
            self._read_qomicex(instance_path, version_id, vanilla_name, primary_loader, qomicex_path),
        ]
        return [source for source in sources if source is not None]


__all__ = ["ExternalInstanceMetadata", "InstanceCompatibilityReader"]
