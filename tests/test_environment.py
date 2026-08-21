from ECL.utils import Environment


def test_env_manager_reads_microsoft_client_id_from_dotenv(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("MICROSOFT_CLIENT_ID", raising=False)
    (tmp_path / ".env").write_text("MICROSOFT_CLIENT_ID=dotenv-client-id\n", encoding="utf-8")

    manager = Environment(tmp_path)

    assert manager.get_value("MICROSOFT_CLIENT_ID") == "dotenv-client-id"


def test_system_microsoft_client_id_overrides_dotenv(tmp_path, monkeypatch) -> None:
    (tmp_path / ".env").write_text("MICROSOFT_CLIENT_ID=dotenv-client-id\n", encoding="utf-8")
    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "system-client-id")

    manager = Environment(tmp_path)

    assert manager.get_value("MICROSOFT_CLIENT_ID") == "system-client-id"


def test_env_manager_reads_system_variables_without_dotenv(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "system-only-client-id")

    manager = Environment(tmp_path)

    assert manager.get_value("MICROSOFT_CLIENT_ID") == "system-only-client-id"


def test_env_manager_reads_curseforge_api_key_from_dotenv(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("CURSEFORGE_API_KEY", raising=False)
    monkeypatch.delenv("ECL_CURSEFORGE_API_KEY", raising=False)
    (tmp_path / ".env").write_text("CURSEFORGE_API_KEY=dotenv-cf-key\n", encoding="utf-8")

    manager = Environment(tmp_path)

    assert manager.get_value("CURSEFORGE_API_KEY") == "dotenv-cf-key"


def test_system_curseforge_api_key_overrides_dotenv(tmp_path, monkeypatch) -> None:
    (tmp_path / ".env").write_text("CURSEFORGE_API_KEY=dotenv-cf-key\n", encoding="utf-8")
    monkeypatch.setenv("CURSEFORGE_API_KEY", "system-cf-key")

    manager = Environment(tmp_path)

    assert manager.get_value("CURSEFORGE_API_KEY") == "system-cf-key"


def test_env_manager_reads_curseforge_api_key_from_ecl_prefix(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("CURSEFORGE_API_KEY", raising=False)
    monkeypatch.setenv("ECL_CURSEFORGE_API_KEY", "ecl-prefix-cf-key")

    manager = Environment(tmp_path)

    assert manager.get_value("CURSEFORGE_API_KEY") == "ecl-prefix-cf-key"
