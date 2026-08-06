from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

PENDING_MAINTENANCE_FILE = ".pending_debug_maintenance.json"

DEBUG_MAINTENANCE_TARGETS: dict[str, tuple[str, ...]] = {
    "reset_launcher_data": ("setting.json", "accounts", "info_card.json", "notice.json"),
    "clear_plugins": ("plugins", "plugin_config"),
}


class DebugMaintenanceError(ValueError):
    """调试维护请求无效。"""


@dataclass(frozen=True, slots=True)
class ScheduledMaintenance:
    """待执行的维护任务。"""

    action: str
    targets: tuple[str, ...]
    backup_root: Path
    restart_required: bool = True

@dataclass(frozen=True, slots=True)
class MaintenanceResult:
    """维护结果。"""

    action: str
    moved_targets: tuple[str, ...]
    backup_path: Path | None

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
    except (OSError, json.JSONDecodeError):
        return []
    actions = data.get("actions") if isinstance(data, dict) else None
    if not isinstance(actions, list):
        return []
    return [action for action in actions if isinstance(action, str) and action in DEBUG_MAINTENANCE_TARGETS]


def schedule_debug_maintenance(data_path: Path | str, action: str) -> ScheduledMaintenance:
    """安排一次仅在下次启动时执行的受限调试维护操作。"""
    if action not in DEBUG_MAINTENANCE_TARGETS:
        raise DebugMaintenanceError(f"不支持的维护操作: {action}")
    root = _get_data_root(data_path)
    marker_path = root / PENDING_MAINTENANCE_FILE
    actions = _read_pending_actions(marker_path)
    if action not in actions:
        actions.append(action)
    marker_data = {"actions": actions, "scheduled_at": datetime.now(UTC).isoformat()}
    temporary_path = marker_path.with_suffix(".json.tmp")
    temporary_path.write_text(json.dumps(marker_data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary_path.replace(marker_path)
    return ScheduledMaintenance(action, DEBUG_MAINTENANCE_TARGETS[action], root / "backups")


def apply_pending_debug_maintenance(data_path: Path | str) -> list[MaintenanceResult]:
    """执行已安排的调试维护操作，并把原数据移动到可恢复备份中。"""
    root = _get_data_root(data_path)
    marker_path = root / PENDING_MAINTENANCE_FILE
    if not marker_path.exists():
        return []
    actions = _read_pending_actions(marker_path)
    if not actions:
        marker_path.replace(marker_path.with_suffix(".invalid.json"))
        return []

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    backup_root = root / "backups" / f"debug-maintenance-{timestamp}"
    results: list[MaintenanceResult] = []
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
        backup_path = backup_root / action if moved_targets else None
        results.append(MaintenanceResult(action, tuple(moved_targets), backup_path))
    marker_path.unlink(missing_ok=True)
    return results
