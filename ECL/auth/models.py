from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class MinecraftAccount:
    alias: str
    account_id: str
    email: str
    profile: dict[str, Any]
    cache_file: str
    account_type: str = "microsoft"
    mc_token: str = ""
    mc_token_expires: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "alias": self.alias,
            "account_id": self.account_id,
            "email": self.email,
            "profile": self.profile,
            "cache_file": self.cache_file,
            "account_type": self.account_type,
            "mc_token": self.mc_token,
            "mc_token_expires": self.mc_token_expires,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MinecraftAccount:
        return cls(
            alias=data["alias"],
            account_id=data["account_id"],
            email=data.get("email", ""),
            profile=data["profile"],
            cache_file=data.get("cache_file", ""),
            account_type=data.get("account_type", "microsoft"),
            mc_token=data.get("mc_token", ""),
            mc_token_expires=data.get("mc_token_expires", 0.0),
        )

    def get_display_name(self) -> str:
        return self.alias or self.profile.get("name", "Unknown")

    def get_uuid(self) -> str:
        return self.profile.get("id", "")

    def get_skin_url(self) -> str | None:
        if self.account_type == "microsoft" and self.profile:
            skins = self.profile.get("skins", [])
            if skins:
                return skins[0].get("url")
        return None
