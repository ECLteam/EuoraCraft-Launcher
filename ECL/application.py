from __future__ import annotations

import logging
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from typing import Any

import httpx

from ECL.common import __version__, __version_type__
from ECL.common.runtime import RuntimeInfo
from ECL.events import EventBus
from ECL.plugins import PluginManager
from ECL.services.accounts import AccountManager
from ECL.services.avatars import AvatarManager
from ECL.services.game import GameService
from ECL.services.info_card import InfoCardManager
from ECL.utils import ConfigStore, Environment

logger = logging.getLogger("EuoraCraft-Launcher.Application")


@dataclass
class ApplicationState:
    """
    保存一次应用运行期间会变化的后端状态。

    :param app_path: 启动器数据与运行文件所在目录
    :param resource_path: 打包资源或源码资源所在目录
    :param data_path: 后端持久化数据目录
    :param is_frozen: 当前是否运行于打包后的可执行文件
    """

    app_path: Path
    resource_path: Path
    data_path: Path
    is_frozen: bool
    launcher_version: str = __version__
    launcher_version_type: str = __version_type__
    debug: bool = False
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ApplicationContext:
    """
    显式保存后端依赖图，并统一管理共享资源的生命周期。

    上下文中的服务按字段顺序构造，关闭时按依赖的逆序释放。调用 ``close`` 多次不会
    重复关闭网络客户端或后台任务。
    """

    state: ApplicationState
    events: EventBus
    config: ConfigStore
    environment: Environment
    http: httpx.Client
    accounts: AccountManager
    avatars: AvatarManager
    info_card: InfoCardManager
    game: GameService
    plugins: PluginManager
    _closed: bool = field(default=False, init=False, repr=False, compare=False)
    _close_lock: RLock = field(default_factory=RLock, init=False, repr=False, compare=False)

    def close(self) -> None:
        """
        按依赖逆序关闭后端资源，并清空事件订阅。
        """
        with self._close_lock:
            if self._closed:
                logger.debug("忽略重复的应用上下文关闭请求")
                return
            object.__setattr__(self, "_closed", True)
            logger.debug("开始关闭应用上下文中的共享资源")
            for resource in (self.plugins, self.game, self.avatars, self.accounts, self.http):
                try:
                    resource.close()
                except Exception:
                    logger.exception("关闭后端资源失败: %s", type(resource).__name__)
            self.events.clear()
            logger.debug("应用上下文已关闭")


def create_application(runtime_info: RuntimeInfo) -> ApplicationContext:
    """
    构造一次应用运行所需的完整后端依赖图。

    初始化中途失败时，本函数会按逆序释放已经创建的资源，再将原始异常抛给启动器。

    :param runtime_info: 运行目录、资源目录和打包状态
    :return: 负责后端依赖与资源生命周期的应用上下文
    """

    state = ApplicationState(
        app_path=runtime_info["app_path"],
        resource_path=runtime_info["resource_path"],
        data_path=runtime_info["app_path"] / "ECL_data",
        is_frozen=runtime_info["is_frozen"],
    )
    events = EventBus()
    environment = Environment(state.app_path)
    config = ConfigStore(state.data_path, events)
    state.config = environment.apply_to_config(config.get_config())
    state.debug = bool((state.config.get("launcher") or {}).get("debug"))
    logger.debug(
        "正在构造后端依赖图: data_path=%s, frozen=%s, debug=%s",
        state.data_path,
        state.is_frozen,
        state.debug,
    )

    created: list[Any] = []
    try:
        http = httpx.Client(
            timeout=httpx.Timeout(30, connect=10),
            follow_redirects=True,
            headers={"User-Agent": "EuoraCraft-Launcher"},
        )
        created.append(http)
        logger.debug("共享 HTTP 客户端已创建")
        accounts = AccountManager(
            state.data_path,
            microsoft_client_id=environment.get_value("MICROSOFT_CLIENT_ID"),
            event_bus=events,
        )
        created.append(accounts)
        logger.debug("账户服务已创建，Microsoft 登录可用=%s", accounts.microsoft_login_config()["available"])
        avatars = AvatarManager(state.resource_path, authlib_manager=accounts.authlib_manager, http_client=http)
        created.append(avatars)
        logger.debug("头像服务已创建")
        info_card = InfoCardManager(state.data_path, http_client=http)
        game = GameService(accounts, data_path=state.data_path, event_bus=events)
        created.append(game)
        logger.debug("游戏服务已创建")
        plugins = PluginManager(events)
        created.append(plugins)
        plugins.initialize(state.data_path, state.resource_path)
        logger.debug("插件管理器已初始化")
    except Exception:
        logger.exception("后端依赖图构造失败，正在回收已创建的资源")
        for resource in reversed(created):
            close = getattr(resource, "close", None)
            if callable(close):
                with suppress(Exception):
                    close()
        raise

    context = ApplicationContext(
        state=state,
        events=events,
        config=config,
        environment=environment,
        http=http,
        accounts=accounts,
        avatars=avatars,
        info_card=info_card,
        game=game,
        plugins=plugins,
    )

    def update_runtime_config(section: str, data: Any) -> None:
        """
        在启动器设置变化后刷新运行状态和日志级别。

        :param section: 被修改的配置分区
        :param data: 分区更新后的配置数据
        """
        if section != "launcher":
            return
        state.config = environment.apply_to_config(config.get_config())
        state.debug = bool((data or {}).get("debug", False))
        logger.debug("运行配置已刷新: debug=%s", state.debug)

    events.subscribe("config:updated", update_runtime_config)
    return context


__all__ = ["ApplicationContext", "ApplicationState", "create_application"]
