import base64
from io import BytesIO

import httpx
import pytest
from PIL import Image

from ECL.Services import AuthlibAccountManager, AuthlibAvatar, AvatarError, AvatarManager


class OfflineAuthClient:
    def close(self):
        pass


def _create_skin_resources(resource_path) -> None:
    skin_path = resource_path / "resources" / "Skins"
    skin_path.mkdir(parents=True)
    skin = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    for x in range(8, 16):
        for y in range(8, 16):
            skin.putpixel((x, y), (180, 120, 80, 255))
    skin.putpixel((40, 8), (20, 90, 210, 255))
    for name in AvatarManager.DEFAULT_SKINS:
        skin.save(skin_path / name)


def test_default_avatar_renders_face_and_overlay(tmp_path) -> None:
    _create_skin_resources(tmp_path)
    manager = AvatarManager(tmp_path)

    result = manager.render_avatar("offline-player", 16, True)

    assert result["dataUrl"] == f"data:image/png;base64,{result['base64']}"
    image = Image.open(BytesIO(base64.b64decode(result["base64"]))).convert("RGBA")
    assert image.size == (16, 16)
    assert image.getpixel((0, 0)) == (20, 90, 210, 255)
    assert image.getpixel((4, 4)) == (180, 120, 80, 255)
    manager.close()


def test_avatar_size_is_validated(tmp_path) -> None:
    _create_skin_resources(tmp_path)
    manager = AvatarManager(tmp_path)

    with pytest.raises(AvatarError) as exc_info:
        manager.render_avatar("offline-player", 2, True)

    assert exc_info.value.error_code == "INVALID_AVATAR_SIZE"
    manager.close()


def test_online_avatar_uses_second_source_when_primary_is_unavailable(tmp_path) -> None:
    _create_skin_resources(tmp_path)
    manager = AvatarManager(tmp_path)
    requested_hosts = []

    image_data = BytesIO()
    Image.new("RGBA", (32, 32), (20, 90, 210, 255)).save(image_data, format="PNG")

    def handle_request(request: httpx.Request) -> httpx.Response:
        requested_hosts.append(request.url.host)
        if request.url.host == "api.mcheads.org":
            return httpx.Response(503, request=request)
        return httpx.Response(200, request=request, content=image_data.getvalue())

    manager.client.close()
    manager.client = httpx.Client(transport=httpx.MockTransport(handle_request))

    result = manager.render_avatar("1cb5a9d2f3454fe5bf576e33138a2992", 32)

    image = Image.open(BytesIO(base64.b64decode(result["base64"]))).convert("RGBA")
    assert requested_hosts == ["api.mcheads.org", "crafatar.com"]
    assert image.getpixel((0, 0)) == (20, 90, 210, 255)
    manager.close()


def test_blessing_skin_avatar_uses_player_endpoint(tmp_path) -> None:
    requested_urls = []
    avatar_data = BytesIO()
    Image.new("RGBA", (32, 32), (120, 70, 190, 255)).save(avatar_data, format="PNG")

    def handle_request(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(200, request=request, content=avatar_data.getvalue())

    manager = AuthlibAccountManager(
        tmp_path,
        OfflineAuthClient(),
        httpx.Client(transport=httpx.MockTransport(handle_request)),
    )
    manager.accounts["account"] = {
        "YggdrasilAPI": "https://skin.example.com/api/yggdrasil",
        "Profiles": {
            "selectedProfile": {
                "name": "Player Name",
                "id": "1cb5a9d2f3454fe5bf576e33138a2992",
            }
        },
    }

    result = manager.get_avatar("account", 32)

    assert requested_urls == ["https://skin.example.com/avatar/player/Player%20Name?size=32&png=true"]
    assert result is not None
    assert result.is_skin is False
    image = Image.open(BytesIO(result.data)).convert("RGBA")
    assert image.getpixel((0, 0)) == (120, 70, 190, 255)
    manager.close()


def test_authlib_avatar_uses_its_yggdrasil_skin(tmp_path) -> None:
    requested_urls = []
    skin_data = BytesIO()
    skin = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    for x in range(8, 16):
        for y in range(8, 16):
            skin.putpixel((x, y), (40, 160, 80, 255))
    skin.save(skin_data, format="PNG")
    texture_data = base64.b64encode(b'{"textures":{"SKIN":{"url":"https://textures.example.com/player.png"}}}').decode(
        "ascii"
    )

    def handle_request(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        if request.url.host == "skin.example.com":
            return httpx.Response(
                200,
                request=request,
                json={"properties": [{"name": "textures", "value": texture_data}]},
            )
        return httpx.Response(200, request=request, content=skin_data.getvalue())

    manager = AuthlibAccountManager(
        tmp_path,
        OfflineAuthClient(),
        httpx.Client(transport=httpx.MockTransport(handle_request)),
    )
    manager.accounts["account"] = {
        "YggdrasilAPI": "https://skin.example.com/yggdrasil",
        "Profiles": {
            "selectedProfile": {
                "name": "Player",
                "id": "1cb5a9d2f3454fe5bf576e33138a2992",
            }
        },
    }

    result = manager.get_avatar("account", 32)

    assert requested_urls == [
        "https://skin.example.com/yggdrasil/sessionserver/session/minecraft/profile/"
        "1cb5a9d2f3454fe5bf576e33138a2992?unsigned=true",
        "https://textures.example.com/player.png",
    ]
    assert result is not None
    assert result.is_skin is True
    image = Image.open(BytesIO(result.data)).convert("RGBA")
    assert image.getpixel((8, 8)) == (40, 160, 80, 255)
    manager.close()


def test_authlib_avatar_without_skin_returns_none(tmp_path) -> None:
    requested_hosts = []
    texture_data = base64.b64encode(b'{"textures":{}}').decode("ascii")

    def handle_request(request: httpx.Request) -> httpx.Response:
        requested_hosts.append(request.url.host)
        return httpx.Response(
            200,
            request=request,
            json={"properties": [{"name": "textures", "value": texture_data}]},
        )

    manager = AuthlibAccountManager(
        tmp_path,
        OfflineAuthClient(),
        httpx.Client(transport=httpx.MockTransport(handle_request)),
    )
    manager.accounts["account"] = {
        "YggdrasilAPI": "https://skin.example.com/yggdrasil",
        "Profiles": {
            "selectedProfile": {
                "name": "Player",
                "id": "1cb5a9d2f3454fe5bf576e33138a2992",
            }
        },
    }

    result = manager.get_avatar("account", 32)

    assert result is None
    assert requested_hosts == ["skin.example.com"]
    manager.close()


def test_avatar_manager_delegates_authlib_avatar_to_authlib_service(tmp_path) -> None:
    _create_skin_resources(tmp_path)
    avatar_data = BytesIO()
    Image.new("RGBA", (32, 32), (120, 70, 190, 255)).save(avatar_data, format="PNG")

    class FakeAuthlibManager:
        def __init__(self):
            self.request = None

        def get_avatar(self, account_id: str, size: int) -> AuthlibAvatar:
            self.request = (account_id, size)
            return AuthlibAvatar(avatar_data.getvalue(), False)

    authlib_manager = FakeAuthlibManager()
    manager = AvatarManager(tmp_path, authlib_manager=authlib_manager)

    result = manager.render_avatar(
        "1cb5a9d2f3454fe5bf576e33138a2992",
        32,
        account_type="authlib",
        account_id="authlib-account",
    )

    assert authlib_manager.request == ("authlib-account", 32)
    image = Image.open(BytesIO(base64.b64decode(result["base64"]))).convert("RGBA")
    assert image.getpixel((0, 0)) == (120, 70, 190, 255)
    manager.close()
