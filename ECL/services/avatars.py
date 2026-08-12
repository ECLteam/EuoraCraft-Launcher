import base64
import hashlib
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx
from PIL import Image

from ECL.services.authlib import AuthlibAccountManager
from ECL.utils import get_logger


class AvatarError(Exception):
    def __init__(self, message: str, error_code: str = "AVATAR_ERROR"):
        super().__init__(message)
        self.error_code = error_code


class AvatarManager:
    ONLINE_AVATAR_URLS = (
        "https://api.mcheads.org/head/{uuid}/{size}",
        "https://crafatar.com/avatars/{uuid}?size={size}&overlay=true",
    )
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

    def __init__(
        self,
        resource_path: Path | str,
        authlib_manager: AuthlibAccountManager | None = None,
        http_client: httpx.Client | None = None,
    ):
        self.logger = get_logger("AvatarManager")
        self.skin_path = Path(resource_path) / "resources" / "Skins"
        self.authlib_manager = authlib_manager
        self._owns_client = http_client is None
        self.client = http_client or httpx.Client(
            timeout=httpx.Timeout(10, connect=5), follow_redirects=True, headers={"User-Agent": "EuoraCraft-Launcher"}
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
        last_error = None
        for url in self.ONLINE_AVATAR_URLS:
            try:
                response = self.client.get(url.format(uuid=account_uuid, size=size))
                response.raise_for_status()
                with Image.open(BytesIO(response.content)) as image:
                    avatar = image.convert("RGBA").resize((size, size), Image.Resampling.NEAREST)
                    return self._encode_image(avatar)
            except (httpx.HTTPError, OSError, ValueError) as exc:
                last_error = exc

        if last_error is not None:
            raise last_error
        raise AvatarError("没有可用的在线头像源", "AVATAR_PROVIDER_UNAVAILABLE")

    def render_avatar(
        self,
        account_uuid: Any,
        size: Any = 64,
        use_default_skin: bool = False,
        account_type: Any = None,
        account_id: Any = None,
    ) -> dict[str, str]:
        """
        渲染在线或默认皮肤头像，并返回 data URL 与 Base64 数据。

        :param account_uuid: 账户 UUID
        :param size: 目标图像尺寸
        :param use_default_skin: 是否在自定义皮肤缺失时使用默认皮肤
        :param account_type: 账户提供者类型
        :param account_id: 账户的稳定标识
        """
        normalized_size = self._validate_size(size)
        normalized_uuid = self._normalize_uuid(account_uuid)
        identifier = normalized_uuid or str(account_uuid or "Player")

        if use_default_skin or not normalized_uuid:
            return self._render_default_avatar(identifier, normalized_size)

        is_authlib = str(account_type or "").casefold() == "authlib"
        if is_authlib and (self.authlib_manager is None or not isinstance(account_id, str) or not account_id):
            return self._render_default_avatar(normalized_uuid, normalized_size)

        try:
            if is_authlib:
                avatar_source = self.authlib_manager.get_avatar(account_id, normalized_size)
                if avatar_source is None:
                    return self._render_default_avatar(normalized_uuid, normalized_size)
                with Image.open(BytesIO(avatar_source.data)) as image:
                    if avatar_source.is_skin:
                        avatar = self._render_skin_head(image, normalized_size)
                    else:
                        avatar = image.convert("RGBA").resize(
                            (normalized_size, normalized_size),
                            Image.Resampling.NEAREST,
                        )
                    return self._encode_image(avatar)
            return self._render_online_avatar(normalized_uuid, normalized_size)
        except (httpx.HTTPError, OSError, ValueError) as exc:
            if isinstance(exc, httpx.HTTPStatusError):
                reason = f"HTTP {exc.response.status_code}"
                if exc.response.reason_phrase:
                    reason += f" {exc.response.reason_phrase}"
            else:
                reason = str(exc)
            source = "外置登录皮肤" if is_authlib else "在线头像源"
            self.logger.warning("%s不可用，使用默认皮肤: %s", source, reason)
            return self._render_default_avatar(normalized_uuid, normalized_size)

    def close(self) -> None:
        """
        关闭头像下载客户端。
        """
        if self._owns_client:
            self.client.close()
