"""验证 ECL_data/plugins 下的测试插件本身能够正常加载。"""

import shutil
from pathlib import Path

from ECL.events import EventBus
from ECL.plugins import PluginFramework


def _reset_runtime() -> None:
    EventBus._instance = None
    EventBus._initialized = False
    PluginFramework._instance = None
    PluginFramework._initialized = False


# 需要验证的测试插件名称列表
_TEST_PLUGIN_NAMES = [
    "test_basic",
    "test_events",
    "test_crash",
    "test_dependencies",
    "test_permissions",
    "test_frontend",
    "test_timeout",
    "test_settings",
]


def _copy_plugins(source_dir: Path, target_dir: Path) -> None:
    """将源目录下的测试插件复制到临时目标目录。"""
    target_dir.mkdir(parents=True, exist_ok=True)
    for name in _TEST_PLUGIN_NAMES:
        src = source_dir / name
        if src.is_dir():
            shutil.copytree(src, target_dir / name, dirs_exist_ok=True)


def test_all_test_plugins_load_without_unexpected_permission_errors(tmp_path) -> None:
    """测试插件加载结果符合预期：7 个正常启用，test_permissions 因故意测试越权命令而权限拒绝。"""
    _reset_runtime()
    data_path = tmp_path / "data"
    resource_path = tmp_path / "resources"
    source_plugins = Path(__file__).parent.parent / "ECL_data" / "plugins"
    _copy_plugins(source_plugins, data_path / "plugins")

    framework = PluginFramework()
    framework.initialize(data_path, resource_path)

    # test_permissions 插件内部故意声明了越权命令，用于测试权限拒绝场景
    expected_enabled = [name for name in _TEST_PLUGIN_NAMES if name != "test_permissions"]
    for name in expected_enabled:
        assert framework._status.get(name) == "enabled", f"插件 {name} 未启用"
        assert framework.get_plugin(name) is not None, f"插件 {name} 未实例化"

    assert framework._status.get("test_permissions") == "permission_denied"
    info = {p["name"]: p for p in framework.list_plugins()}
    assert info["test_permissions"]["status"] == "permission_denied"
    assert info["test_permissions"]["error"] is not None
    assert "commands:execute:try_denied_cmd" in info["test_permissions"]["error"]

    for name in expected_enabled:
        assert info[name]["status"] == "enabled", f"list_plugins 中 {name} 状态异常"
