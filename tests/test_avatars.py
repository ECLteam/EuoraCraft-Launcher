import base64
from io import BytesIO

import pytest
from PIL import Image

from ECL.Services import AvatarError, AvatarManager


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
