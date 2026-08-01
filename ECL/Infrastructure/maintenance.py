from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PENDING_MAINTENANCE_FILE = ".pending_debug_maintenance.json"

DEBUG_MAINTENANCE_TARGETS: dict[str, tuple[str, ...]] = {
    "reset_launcher_data": (
        "setting.json",
        "accounts",
        "info_card.json",
        "notice.json",
    ),
    "clear_plugins": (
        "plugins",
        "plugin_config",
    ),
}


class DebugMaintenanceError(ValueError):
    """调试维护请求无效。"""


def _get_data_root(data_path: Path | str) -> Path:
    root = Path(data_path).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _get_safe_target(root: Path, relative_path: str) -> Path:
    target = (root / relative_path).resolve()
    if target == root or root not in target.parents:
        raise DebugMaintenanceError(f"维护目标超出数据目录: {relative_path}")
    return target


def _read_pending_actions(marker_path: Path) -> list[str]:
    if not marker_path.is_file():
        return []
    try:
        data = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return []
    actions = data.get("actions") if isinstance(data, dict) else None
    if not isinstance(actions, list):
        return []
    return [action for action in actions if isinstance(action, str) and action in DEBUG_MAINTENANCE_TARGETS]


def schedule_debug_maintenance(data_path: Path | str, action: str) -> dict[str, Any]:
    """安排一次仅在下次启动时执行的受限调试维护操作。"""
    if action not in DEBUG_MAINTENANCE_TARGETS:
        raise DebugMaintenanceError(f"不支持的维护操作: {action}")

    root = _get_data_root(data_path)
    marker_path = root / PENDING_MAINTENANCE_FILE
    actions = _read_pending_actions(marker_path)
    if action not in actions:
        actions.append(action)

    marker_data = {
        "actions": actions,
        "scheduled_at": datetime.now(UTC).isoformat(),
    }
    temporary_path = marker_path.with_suffix(".json.tmp")
    temporary_path.write_text(json.dumps(marker_data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary_path.replace(marker_path)

    return {
        "action": action,
        "restart_required": True,
        "targets": list(DEBUG_MAINTENANCE_TARGETS[action]),
        "backup_root": str(root / "backups"),
    }


def apply_pending_debug_maintenance(data_path: Path | str) -> list[dict[str, Any]]:
    """执行已安排的调试维护操作，并把原数据移动到可恢复备份中。"""
    root = _get_data_root(data_path)
    marker_path = root / PENDING_MAINTENANCE_FILE
    if not marker_path.exists():
        return []

    actions = _read_pending_actions(marker_path)
    if not actions:
        invalid_marker_path = marker_path.with_suffix(".invalid.json")
        marker_path.replace(invalid_marker_path)
        return []

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    backup_root = root / "backups" / f"debug-maintenance-{timestamp}"
    results: list[dict[str, Any]] = []

    for action in actions:
        moved_targets: list[str] = []
        for relative_path in DEBUG_MAINTENANCE_TARGETS[action]:
            target = _get_safe_target(root, relative_path)
            if not target.exists():
                continue
            destination = backup_root / action / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(target), str(destination))
            moved_targets.append(relative_path)

        results.append(
            {
                "action": action,
                "moved_targets": moved_targets,
                "backup_path": str(backup_root / action) if moved_targets else None,
            }
        )

    marker_path.unlink(missing_ok=True)
    return results
