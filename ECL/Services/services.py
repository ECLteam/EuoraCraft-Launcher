from __future__ import annotations

from contextlib import suppress
from pathlib import Path

from ECL.Events import EventBus
from ECL.Services.accounts import AccountManager
from ECL.Services.avatars import AvatarManager
from ECL.Services.game import GameService
from ECL.Services.info_card import InfoCardManager

__all__ = ["register_services"]


def register_services(
    data_path: Path | str,
    resource_path: Path | str,
) -> tuple[AccountManager, AvatarManager, InfoCardManager, GameService]:
    """实例化 Services 模块内的服务并统一注册到总线。"""
    account_manager: AccountManager | None = None
    avatar_manager: AvatarManager | None = None
    game_service: GameService | None = None
    bus = EventBus()
    env_manager = bus.get("env")
    microsoft_client_id = None
    if env_manager is not None:
        microsoft_client_id = env_manager.get_value("MICROSOFT_CLIENT_ID")

    try:
        account_manager = AccountManager(data_path, microsoft_client_id=microsoft_client_id)
        avatar_manager = AvatarManager(
            resource_path,
            authlib_manager=account_manager.authlib_manager,
        )
        info_card_manager = InfoCardManager(data_path)
        game_service = GameService(account_manager, data_path=data_path)
    except Exception:
        if account_manager is not None:
            with suppress(Exception):
                account_manager.close()
        if avatar_manager is not None:
            with suppress(Exception):
                avatar_manager.close()
        if game_service is not None:
            with suppress(Exception):
                game_service.close()
        raise

    bus.register("accounts", account_manager)
    bus.register("avatars", avatar_manager)
    bus.register("info_card", info_card_manager)
    bus.register("game", game_service)
    return account_manager, avatar_manager, info_card_manager, game_service
