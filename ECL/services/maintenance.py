from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ECL.utils import DebugMaintenanceError, atomic_write_text

PENDING_MAINTENANCE_FILE = ".pending_debug_maintenance.json"

DEBUG_MAINTENANCE_TARGETS: dict[str, tuple[str, ...]] = {
    "reset_launcher_data": ("setting.json", "info_card.json", "notice.json"),
    "clear_plugins": ("plugins", "plugin_config"),
}

# 账户数据已迁移到用户主目录；还原启动器数据时按相对主目录的路径一并删除。
HOME_MAINTENANCE_TARGETS: dict[str, tuple[str, ...]] = {
    "reset_launcher_data": (".ECL/accounts",),
}


@dataclass(frozen=True, slots=True)
class ScheduledMaintenance:
    """
    待执行的维护任务。
    """

    action: str
    targets: tuple[str, ...]
    restart_required: bool = True


@dataclass(frozen=True, slots=True)
class MaintenanceResult:
    """
    维护结果。
    """

    action: str
    removed_targets: tuple[str, ...]


def _get_data_root(data_path: Path | str) -> Path:
    root = Path(data_path).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _get_safe_target(root: Path, relative_path: str) -> Path:
    target = (root / relative_path).resolve()
    if target == root or root not in target.parents:
        raise DebugMaintenanceError(f"维护目标超出数据目录: {relative_path}")
    return target


def _get_safe_home_target(home_root: Path, relative_path: str) -> Path:
    target = (home_root / relative_path).resolve()
    if target == home_root or home_root not in target.parents:
        raise DebugMaintenanceError(f"维护目标超出主目录: {relative_path}")
    return target


def _delete_target(target: Path) -> None:
    # 统一删除文件或目录，存在性由调用方判断。
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()


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
    """
    安排一次仅在下次启动时执行的受限调试维护操作。

    :param data_path: 启动器数据目录
    :param action: 需要执行的操作类型
    """
    if action not in DEBUG_MAINTENANCE_TARGETS:
        raise DebugMaintenanceError(f"不支持的维护操作: {action}")
    root = _get_data_root(data_path)
    marker_path = root / PENDING_MAINTENANCE_FILE
    actions = _read_pending_actions(marker_path)
    if action not in actions:
        actions.append(action)
    marker_data = {"actions": actions, "scheduled_at": datetime.now(UTC).isoformat()}
    atomic_write_text(marker_path, json.dumps(marker_data, ensure_ascii=False, indent=2))
    return ScheduledMaintenance(action, DEBUG_MAINTENANCE_TARGETS[action])


def apply_pending_debug_maintenance(
    data_path: Path | str, home_dir: Path | str | None = None
) -> list[MaintenanceResult]:
    """
    执行已安排的调试维护操作，并直接删除原数据（不再保留备份）。

    :param data_path: 启动器数据目录
    :param home_dir: 用户主目录；仅测试环境传入隔离目录，生产默认为 ``Path.home()``
    """
    root = _get_data_root(data_path)
    marker_path = root / PENDING_MAINTENANCE_FILE
    if not marker_path.exists():
        return []
    actions = _read_pending_actions(marker_path)
    if not actions:
        marker_path.replace(marker_path.with_suffix(".invalid.json"))
        return []

    home_root = Path(home_dir).resolve() if home_dir is not None else Path.home()
    results: list[MaintenanceResult] = []
    for action in actions:
        removed_targets: list[str] = []
        for relative_path in DEBUG_MAINTENANCE_TARGETS[action]:
            target = _get_safe_target(root, relative_path)
            if not target.exists():
                continue
            _delete_target(target)
            removed_targets.append(relative_path)
        for relative_path in HOME_MAINTENANCE_TARGETS.get(action, ()):
            target = _get_safe_home_target(home_root, relative_path)
            if not target.exists():
                continue
            _delete_target(target)
            removed_targets.append(str(target))
        results.append(MaintenanceResult(action, tuple(removed_targets)))
    marker_path.unlink(missing_ok=True)
    return results
