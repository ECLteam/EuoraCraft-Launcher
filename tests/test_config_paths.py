import json

from ECL.utils import ConfigStore
from ECL.utils.config import default_config


def test_new_config_uses_absolute_minecraft_path_and_creates_directory(tmp_path) -> None:
    data_path = tmp_path / "ECL_data"
    manager = ConfigStore(data_path)

    config = manager.get_config()
    minecraft_path = (tmp_path / ".minecraft").resolve()

    assert config["game"]["minecraft_paths"] == [{"name": "默认路径", "path": str(minecraft_path)}]
    assert config["game"]["last_install_path"] == str(minecraft_path)
    assert config["game"]["last_manage_path"] == str(minecraft_path)
    assert minecraft_path.is_dir()
    assert minecraft_path.is_absolute()

    saved_config = json.loads((data_path / "setting.json").read_text(encoding="utf-8"))
    assert saved_config["game"]["minecraft_paths"] == [{"name": "默认路径", "path": str(minecraft_path)}]


def test_existing_empty_game_paths_are_initialized(tmp_path) -> None:
    data_path = tmp_path / "ECL_data"
    data_path.mkdir()
    (data_path / "setting.json").write_text(
        json.dumps(default_config, ensure_ascii=False),
        encoding="utf-8",
    )

    config = ConfigStore(data_path).get_config()
    minecraft_path = (tmp_path / ".minecraft").resolve()

    assert config["game"]["minecraft_paths"] == [{"name": "默认路径", "path": str(minecraft_path)}]
    assert config["game"]["last_install_path"] == str(minecraft_path)
    assert config["game"]["last_manage_path"] == str(minecraft_path)
    assert minecraft_path.is_dir()
