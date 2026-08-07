from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from ECL.Game.Core.MicrosoftAuth import MicrosoftAuthManager


class _ProgressMinecraftClient:
    def __init__(self, client: Any, on_progress: Callable[[str], None]) -> None:
        self.client = client
        self.on_progress = on_progress
        self.login_active = False

    def get_minecraft_token(self, token: str):
        if self.login_active:
            self.on_progress("authorization_confirmed")
        result = self.client.get_minecraft_token(token)
        if self.login_active:
            self.on_progress("minecraft_token")
        return result

    def get_profile(self, token: str):
        if self.login_active:
            self.on_progress("profile")
        result = self.client.get_profile(token)
        if self.login_active:
            self.on_progress("saving")
        return result

    def upload_skin(self, token: str, variant: str, image: bytes):
        return self.client.upload_skin(token, variant, image)

    def reset_skin(self, token: str):
        return self.client.reset_skin(token)

    def set_cape(self, token: str, cape_id: str):
        return self.client.set_cape(token, cape_id)

    def reset_cape(self, token: str):
        return self.client.reset_cape(token)

    def set_profile_name(self, token: str, name: str):
        return self.client.set_profile_name(token, name)

    def close(self) -> None:
        self.client.close()


class LauncherMicrosoftAccountManager(MicrosoftAuthManager):
    def __init__(
        self,
        client_id: str,
        on_device_code: Callable[[dict[str, str]], None],
        on_progress: Callable[[str], None],
        cache_path: Path | str | None = None,
    ) -> None:
        super().__init__(client_id, cache_path, on_device_code)
        self._progress_client = _ProgressMinecraftClient(self.minecraft_client, on_progress)
        self.minecraft_client = self._progress_client

    def add_microsoft_account(self) -> str:
        """登录并保存 Microsoft 账户。"""
        self._progress_client.login_active = True
        try:
            return super().add_microsoft_account()
        finally:
            self._progress_client.login_active = False
