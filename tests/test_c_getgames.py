import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from ECL.game.Core.C_GetGames import GetGames


class FakeResponse:
    def __init__(self, text: str, json_data: dict | None = None):
        self._text = text
        self._json_data = json_data or {}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._json_data

    @property
    def text(self) -> str:
        return self._text


class DummyFilesChecker:
    def __init__(self) -> None:
        self.api_url = type("ApiUrl", (), {"FabricMeta": "https://fabric", "Meta": "https://meta"})()
        self.check_files = MagicMock()


class GetGamesFabricInstallTests(unittest.TestCase):
    def test_download_fabric_uses_game_version_type_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game_path = Path(tmpdir)
            checker = DummyFilesChecker()
            game = GetGames(files_checker=checker)

            def fake_get(url: str, *args, **kwargs):
                if "fabric" in url:
                    return FakeResponse('{"id": "fabric-profile"}', {"version": "0.11.2"})
                return FakeResponse("", {
                    "latest": {"release": "1.20.1", "snapshot": "1.20.1"},
                    "versions": [{"id": "1.20.1", "type": "release"}],
                })

            with patch("ECL.game.Core.C_GetGames.requests.get", side_effect=fake_get):
                result = game.download_fabric(game_path, "1.20.1", "0.11.2", download_vanilla=False)

            self.assertTrue(result)
            versions_info_path = game_path / "versions" / "VersionsInfo.json"
            self.assertTrue(versions_info_path.exists())
            data = json.loads(versions_info_path.read_text(encoding="utf-8"))
            self.assertIn("fabric-loader-0.11.2-1.20.1", data)
            self.assertEqual(data["fabric-loader-0.11.2-1.20.1"]["VanillaType"], "release")


if __name__ == "__main__":
    unittest.main()
