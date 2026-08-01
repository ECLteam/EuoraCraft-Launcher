import base64
import hashlib
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx
from PIL import Image

from ECL.Infrastructure import get_logger


class AvatarError(Exception):
    def __init__(self, message: str, error_code: str = "AVATAR_ERROR"):
        super().__init__(message)
        self.error_code = error_code


class AvatarManager:
    DEFAULT_SKINS = (
        "Alex.png",
        "Ari.png",
        "Efe.png",
        "Kai.png",
        "Makena.png",
        "Noor.png",
        "Steve.png",
        "Sunny.png",
        "Zuri.png",
    )

    def __init__(self, resource_path: Path | str):
        self.logger = get_logger("AvatarManager")
        self.skin_path = Path(resource_path) / "resources" / "Skins"
        self.client = httpx.Client(
            timeout=httpx.Timeout(10, connect=5),
            follow_redirects=True,
            headers={"User-Agent": "EuoraCraft-Launcher"},
        )

    @staticmethod
    def _validate_size(size: Any) -> int:
        try:
            normalized = int(size)
        except (TypeError, ValueError) as exc:
            raise AvatarError("头像尺寸无效", "INVALID_AVATAR_SIZE") from exc
        if not 8 <= normalized <= 512:
            raise AvatarError("头像尺寸必须在 8 到 512 之间", "INVALID_AVATAR_SIZE")
        return normalized

    @staticmethod
    def _normalize_uuid(value: Any) -> str:
        normalized = str(value or "").replace("-", "").strip().lower()
        if len(normalized) != 32:
            return ""
        try:
            int(normalized, 16)
        except ValueError:
            return ""
        return normalized

    def _default_skin_path(self, identifier: str) -> Path:
        digest = hashlib.sha256(identifier.encode("utf-8")).digest()
        skin_name = self.DEFAULT_SKINS[int.from_bytes(digest[:2], "big") % len(self.DEFAULT_SKINS)]
        skin_path = self.skin_path / skin_name
        if not skin_path.is_file():
            raise AvatarError("默认皮肤资源不存在", "DEFAULT_SKIN_NOT_FOUND")
        return skin_path

    @staticmethod
    def _render_skin_head(image: Image.Image, size: int) -> Image.Image:
        source = image.convert("RGBA")
        scale = source.width // 64
        if scale < 1 or source.width != 64 * scale or source.height < 32 * scale:
            raise AvatarError("皮肤图片尺寸无效", "INVALID_SKIN_IMAGE")

        face = source.crop((8 * scale, 8 * scale, 16 * scale, 16 * scale))
        overlay = source.crop((40 * scale, 8 * scale, 48 * scale, 16 * scale))
        face.alpha_composite(overlay)
        return face.resize((size, size), Image.Resampling.NEAREST)

    @staticmethod
    def _encode_image(image: Image.Image) -> dict[str, str]:
        output = BytesIO()
        image.save(output, format="PNG")
        encoded = base64.b64encode(output.getvalue()).decode("ascii")
        return {
            "dataUrl": f"data:image/png;base64,{encoded}",
            "base64": encoded,
        }

    def _render_default_avatar(self, identifier: str, size: int) -> dict[str, str]:
        with Image.open(self._default_skin_path(identifier)) as image:
            return self._encode_image(self._render_skin_head(image, size))

    def _render_online_avatar(self, account_uuid: str, size: int) -> dict[str, str]:
        response = self.client.get(
            f"https://crafatar.com/avatars/{account_uuid}",
            params={"size": size, "overlay": "true", "default": "MHF_Steve"},
        )
        response.raise_for_status()
        with Image.open(BytesIO(response.content)) as image:
            avatar = image.convert("RGBA").resize((size, size), Image.Resampling.NEAREST)
            return self._encode_image(avatar)

    def render_avatar(
        self,
        account_uuid: Any,
        size: Any = 64,
        use_default_skin: bool = False,
    ) -> dict[str, str]:
        normalized_size = self._validate_size(size)
        normalized_uuid = self._normalize_uuid(account_uuid)
        identifier = normalized_uuid or str(account_uuid or "Player")

        if use_default_skin or not normalized_uuid:
            return self._render_default_avatar(identifier, normalized_size)

        try:
            return self._render_online_avatar(normalized_uuid, normalized_size)
        except (httpx.HTTPError, OSError, ValueError) as exc:
            self.logger.warning("在线头像获取失败，使用默认皮肤: %s", exc)
            return self._render_default_avatar(normalized_uuid, normalized_size)

    def close(self) -> None:
        self.client.close()
