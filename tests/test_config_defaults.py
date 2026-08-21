from ECL.utils.config import default_config


def test_ui_defaults_start_collapsed_with_full_background_brightness() -> None:
    ui_config = default_config["ui"]

    assert ui_config["theme"]["sidebar_collapsed"] is True
    assert ui_config["theme"]["background_opacity"] == 1.0
    assert ui_config["background"]["opacity"] == 1.0


def test_launcher_network_defaults_are_bounded() -> None:
    launcher_config = default_config["launcher"]

    assert launcher_config["request_timeout"] == 15
    assert launcher_config["request_retries"] == 2
