from ECL.utils import EnvManager


def test_env_manager_reads_microsoft_client_id_from_dotenv(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("MICROSOFT_CLIENT_ID", raising=False)
    (tmp_path / ".env").write_text("MICROSOFT_CLIENT_ID=dotenv-client-id\n", encoding="utf-8")

    manager = EnvManager(tmp_path)

    assert manager.get_value("MICROSOFT_CLIENT_ID") == "dotenv-client-id"


def test_system_microsoft_client_id_overrides_dotenv(tmp_path, monkeypatch) -> None:
    (tmp_path / ".env").write_text("MICROSOFT_CLIENT_ID=dotenv-client-id\n", encoding="utf-8")
    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "system-client-id")

    manager = EnvManager(tmp_path)

    assert manager.get_value("MICROSOFT_CLIENT_ID") == "system-client-id"


def test_env_manager_reads_system_variables_without_dotenv(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "system-only-client-id")

    manager = EnvManager(tmp_path)

    assert manager.get_value("MICROSOFT_CLIENT_ID") == "system-only-client-id"
