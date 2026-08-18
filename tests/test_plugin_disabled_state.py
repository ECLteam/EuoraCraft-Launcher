"""插件禁用状态持久化测试。"""

import json
from pathlib import Path

from ECL.plugins import PluginFramework


def _write_plugin(plugin_dir: Path, metadata: dict, source: str) -> None:
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "plugin.json").write_text(json.dumps(metadata), encoding="utf-8")
    (plugin_dir / "main.py").write_text(source, encoding="utf-8")


def test_disabled_plugin_is_skipped_on_initialize(tmp_path) -> None:
    """被禁用的插件不应被实例化，状态应为 disabled。"""
    data_path = tmp_path / "data"
    resource_path = tmp_path / "resources"
    _write_plugin(
        data_path / "plugins" / "disabled_plugin",
        {
            "name": "disabled_plugin",
            "version": "1.0.0",
            "entry_point": "main:DisabledPlugin",
            "permissions": [
                {"scope": "events", "action": "emit", "resource": "disabled_plugin:*"},
                {"scope": "commands", "action": "execute", "resource": "*"},
            ],
        },
        "from ECL.plugins import Plugin\n"
        "class DisabledPlugin(Plugin):\n"
        "    @Plugin.on_command('hello')\n"
        "    def cmd_hello(self): return {'ok': True}\n",
    )
    # 预置禁用状态
    state_path = data_path / "plugin_state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({"disabled": ["disabled_plugin"]}), encoding="utf-8")

    framework = PluginFramework()
    framework.initialize(data_path, resource_path)

    assert framework._status.get("disabled_plugin") == "disabled"
    assert framework.get_plugin("disabled_plugin") is None
    info = {p["name"]: p for p in framework.list_plugins()}
    disabled_info = info["disabled_plugin"]
    assert disabled_info["status"] == "disabled"
    assert disabled_info["version"] == "1.0.0"
    assert disabled_info["title"] == "disabled_plugin"
    assert disabled_info["author"] == ""
    assert disabled_info["dependencies"] == {}
    assert len(disabled_info["permissions"]) == 2


def test_disabled_plugin_shows_metadata_from_plugin_json(tmp_path) -> None:
    """被禁用且未实例化的插件，list_plugins 仍应从 plugin.json 读取元数据。"""
    data_path = tmp_path / "data"
    resource_path = tmp_path / "resources"
    _write_plugin(
        data_path / "plugins" / "meta_plugin",
        {
            "name": "meta_plugin",
            "title": "元数据展示插件",
            "version": "2.3.4",
            "description": "测试禁用后仍可读取元数据",
            "author": "ECLTest",
            "entry_point": "main:MetaPlugin",
            "dependencies": {"dep": ">=1.0.0"},
            "permissions": [
                {"scope": "events", "action": "emit", "resource": "meta_plugin:*"},
            ],
        },
        "from ECL.plugins import Plugin\n"
        "class MetaPlugin(Plugin):\n"
        "    @Plugin.on_command('hello')\n"
        "    def cmd_hello(self): return {'ok': True}\n",
    )
    state_path = data_path / "plugin_state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({"disabled": ["meta_plugin"]}), encoding="utf-8")

    framework = PluginFramework()
    framework.initialize(data_path, resource_path)

    assert framework.get_plugin("meta_plugin") is None
    info = {p["name"]: p for p in framework.list_plugins()}["meta_plugin"]
    assert info["status"] == "disabled"
    assert info["title"] == "元数据展示插件"
    assert info["version"] == "2.3.4"
    assert info["description"] == "测试禁用后仍可读取元数据"
    assert info["author"] == "ECLTest"
    assert info["dependencies"] == {"dep": ">=1.0.0"}
    assert len(info["permissions"]) == 1
    assert info["is_system"] is False


def test_disable_persists_to_state_file(tmp_path) -> None:
    """从前端禁用插件后，状态应写入 plugin_state.json。"""
    data_path = tmp_path / "data"
    resource_path = tmp_path / "resources"
    _write_plugin(
        data_path / "plugins" / "demo",
        {
            "name": "demo",
            "version": "1.0.0",
            "entry_point": "main:DemoPlugin",
            "permissions": [
                {"scope": "events", "action": "emit", "resource": "demo:*"},
                {"scope": "commands", "action": "execute", "resource": "*"},
            ],
        },
        "from ECL.plugins import Plugin\n"
        "class DemoPlugin(Plugin):\n"
        "    @Plugin.on_command('hello')\n"
        "    def cmd_hello(self): return {'ok': True}\n",
    )

    framework = PluginFramework()
    framework.initialize(data_path, resource_path)

    assert framework._status.get("demo") == "enabled"
    assert framework.disable("demo").success is True
    state_path = data_path / "plugin_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert "demo" in state.get("disabled", [])


def test_enable_removes_from_state_file(tmp_path) -> None:
    """启用已禁用插件后，应从 plugin_state.json 中移除。"""
    data_path = tmp_path / "data"
    resource_path = tmp_path / "resources"
    _write_plugin(
        data_path / "plugins" / "demo",
        {
            "name": "demo",
            "version": "1.0.0",
            "entry_point": "main:DemoPlugin",
            "permissions": [
                {"scope": "events", "action": "emit", "resource": "demo:*"},
                {"scope": "commands", "action": "execute", "resource": "*"},
            ],
        },
        "from ECL.plugins import Plugin\n"
        "class DemoPlugin(Plugin):\n"
        "    @Plugin.on_command('hello')\n"
        "    def cmd_hello(self): return {'ok': True}\n",
    )
    state_path = data_path / "plugin_state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({"disabled": ["demo"]}), encoding="utf-8")

    framework = PluginFramework()
    framework.initialize(data_path, resource_path)

    assert framework._status.get("demo") == "disabled"
    success, _ = framework._enable("demo")
    assert success is True
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert "demo" not in state.get("disabled", [])


def test_frontend_ready_is_idempotent_and_reenabled_plugins_get_hook(tmp_path) -> None:
    """on_frontend_ready 重复调用只生效一次；前端就绪后重新启用的插件单独补调。"""
    data_path = tmp_path / "data"
    resource_path = tmp_path / "resources"
    _write_plugin(
        data_path / "plugins" / "demo",
        {
            "name": "demo",
            "version": "1.0.0",
            "entry_point": "main:DemoPlugin",
            "permissions": [
                {"scope": "events", "action": "emit", "resource": "demo:*"},
                {"scope": "commands", "action": "execute", "resource": "*"},
            ],
        },
        "from ECL.plugins import Plugin\n"
        "class DemoPlugin(Plugin):\n"
        "    def __init__(self, *args, **kwargs):\n"
        "        super().__init__(*args, **kwargs)\n"
        "        self.ready_count = 0\n"
        "    def on_frontend_ready(self):\n"
        "        self.ready_count += 1\n",
    )

    framework = PluginFramework()
    framework.initialize(data_path, resource_path)

    plugin = framework.get_plugin("demo")
    assert plugin is not None
    assert plugin.ready_count == 0

    framework.on_frontend_ready()
    assert plugin.ready_count == 1

    framework.on_frontend_ready()
    assert plugin.ready_count == 1  # 重复调用不生效

    assert framework.disable("demo").success is True
    assert plugin.ready_count == 1

    success, _ = framework._enable("demo")
    assert success is True
    assert plugin.ready_count == 2  # 前端就绪后重新启用补调


def test_register_route_is_idempotent(tmp_path) -> None:
    """同一插件重复注册相同路径时，路由列表中只保留一条。"""
    data_path = tmp_path / "data"
    resource_path = tmp_path / "resources"
    _write_plugin(
        data_path / "plugins" / "demo",
        {
            "name": "demo",
            "version": "1.0.0",
            "entry_point": "main:DemoPlugin",
            "permissions": [
                {"scope": "ui", "action": "write", "resource": "*"},
                {"scope": "events", "action": "emit", "resource": "demo:*"},
                {"scope": "commands", "action": "execute", "resource": "*"},
            ],
        },
        "from ECL.plugins import Plugin\n"
        "class DemoPlugin(Plugin):\n"
        "    def on_enable(self):\n"
        "        super().on_enable()\n"
        "        self.register_route('/page', 'Page', 'plugin')\n"
        "        self.register_route('/page', 'Page', 'plugin')\n",
    )

    framework = PluginFramework()
    framework.initialize(data_path, resource_path)

    routes = [r for r in framework.get_routes() if r["plugin"] == "demo"]
    assert len(routes) == 1
    assert routes[0]["path"] == "/page"


def test_close_does_not_mark_all_plugins_disabled(tmp_path) -> None:
    """框架关闭时不应把已加载插件全部写入 plugin_state.json。"""
    data_path = tmp_path / "data"
    resource_path = tmp_path / "resources"
    _write_plugin(
        data_path / "plugins" / "demo",
        {
            "name": "demo",
            "version": "1.0.0",
            "entry_point": "main:DemoPlugin",
            "permissions": [
                {"scope": "events", "action": "emit", "resource": "demo:*"},
                {"scope": "commands", "action": "execute", "resource": "*"},
            ],
        },
        "from ECL.plugins import Plugin\n"
        "class DemoPlugin(Plugin):\n"
        "    @Plugin.on_command('hello')\n"
        "    def cmd_hello(self): return {'ok': True}\n",
    )

    framework = PluginFramework()
    framework.initialize(data_path, resource_path)
    assert framework._status.get("demo") == "enabled"

    state_path = data_path / "plugin_state.json"
    # 确保已有状态文件，模拟用户之前禁用过某个插件的场景
    state_path.write_text(json.dumps({"disabled": ["other_plugin"]}), encoding="utf-8")

    framework.close()

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert "demo" not in state.get("disabled", [])
    assert "other_plugin" in state.get("disabled", [])
