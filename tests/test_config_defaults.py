# ============================================================
# EuoraCraft Launcher
# ECLTeam © 2026 GPL-3.0 License
# https://github.com/ECLTeam/EuoraCraft-Launcher
#
# 文件作用：针对 config_defaults 模块的自动化测试。
#
# 公开接口：
#   - test_ui_defaults_start_collapsed_with_full_background_brightness() -> None
#   - test_launcher_network_defaults_are_bounded() -> None
#   - test_game_defaults_use_full_instance_isolation() -> None
#   - test_loading_config_removes_legacy_launcher_metadata(tmp_path) -> None
# ============================================================

import json

from ECL.utils.config import ConfigStore, default_config


def test_ui_defaults_start_collapsed_with_full_background_brightness() -> None:
    ui_config = default_config["ui"]

    assert ui_config["theme"]["sidebar_collapsed"] is True
    assert ui_config["theme"]["primary_color"] == "#5B6FF5"
    assert ui_config["theme"]["background_opacity"] == 1.0
    assert ui_config["background"]["opacity"] == 1.0


def test_launcher_network_defaults_are_bounded() -> None:
    launcher_config = default_config["launcher"]

    assert launcher_config["request_timeout"] == 15
    assert launcher_config["request_retries"] == 2


def test_game_defaults_use_full_instance_isolation() -> None:
    game_config = default_config["game"]

    assert game_config["instance_isolation_policy"] == "all"
    assert game_config["jvm_args"] == []
    assert game_config["renderer"] == "default"
    assert game_config["game_args_tail"] == ""
    assert game_config["pre_launch_command"] == ""
    assert game_config["prefer_high_performance_gpu"] is False
    assert game_config["use_java_exe"] is False
    assert game_config["disable_crash_analysis"] is False


def test_loading_config_removes_legacy_launcher_metadata(tmp_path) -> None:
    setting_path = tmp_path / "setting.json"
    setting_path.write_text(
        json.dumps(
            {
                "launcher": {
                    "debug": False,
                    "version": "1.4.2-alpha.3+20260906",
                    "version_type": "alpha",
                },
                "game": {
                    "minecraft_paths": [{"name": "默认路径", "path": str(tmp_path / ".minecraft")}],
                },
            }
        ),
        encoding="utf-8",
    )

    loaded = ConfigStore(tmp_path).get_config()
    persisted = json.loads(setting_path.read_text(encoding="utf-8"))

    assert loaded["launcher"] == {"debug": False}
    assert persisted["launcher"] == {"debug": False}
