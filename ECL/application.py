from __future__ import annotations

import asyncio
import inspect
import logging
import os
import ssl
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from time import perf_counter
from typing import TYPE_CHECKING, Any

import httpx

from ECL.common import __version__, __version_type__
from ECL.common.runtime import RuntimeInfo
from ECL.events import EventBus
from ECL.game import InstancesManager
from ECL.plugins import PluginManager
from ECL.services.accounts import AccountManager
from ECL.services.game import GameService
from ECL.services.info_card import InfoCardManager
from ECL.services.processes import ProcessService
from ECL.services.wardrobe import WardrobeStore
from ECL.utils import ConfigStore, Environment

if TYPE_CHECKING:
    from ECL.services.connector import ConnectorService

logger = logging.getLogger("EuoraCraft-Launcher.Application")


def _apply_ssl_verify(ssl_context: ssl.SSLContext, verify: bool) -> None:
    """设置 SSL 上下文的证书校验开关，供共享 HTTP 客户端运行时热切换。"""
    if verify:
        ssl_context.verify_mode = ssl.CERT_REQUIRED
        ssl_context.check_hostname = True
    else:
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE


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
    wardrobe: WardrobeStore
    info_card: InfoCardManager
    game: GameService
    connector: ConnectorService
    plugins: PluginManager
    processes: ProcessService
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
            for resource in (self.plugins, self.processes, self.game, self.accounts, self.http):
                try:
                    close = resource.close
                    if inspect.iscoroutinefunction(close):
                        # 账户等资源的异步关闭需要在独立事件循环中完成
                        asyncio.run(close())
                    else:
                        close()
                except Exception:
                    logger.exception("关闭后端资源失败: %s", type(resource).__name__)
            self.events.clear()
            logger.debug("应用上下文已关闭")


def create_application(
    runtime_info: RuntimeInfo,
    *,
    on_state_ready: Callable[[ApplicationState], None] | None = None,
) -> ApplicationContext:
    """
    构造一次应用运行所需的完整后端依赖图。

    初始化中途失败时，本函数会按逆序释放已经创建的资源，再将原始异常抛给启动器。

    :param runtime_info: 运行目录、资源目录和打包状态
    :param on_state_ready: 配置读取后、服务构造前的可选回调，用于提前应用日志级别
    :return: 负责后端依赖与资源生命周期的应用上下文
    """
    startup_started = perf_counter()
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
    if on_state_ready is not None:
        on_state_ready(state)
    logger.debug(
        "正在构造后端依赖图: data_path=%s, frozen=%s, debug=%s",
        state.data_path,
        state.is_frozen,
        state.debug,
    )

    created: list[Any] = []
    try:
        phase_started = perf_counter()
        logger.debug("正在创建共享 HTTP 客户端")
        disable_ssl_verify = bool((state.config.get("launcher") or {}).get("disable_ssl_verify", False))
        ignore_proxy = bool((state.config.get("launcher") or {}).get("ignore_proxy", True))
        if ignore_proxy:
            # httpx 默认通过 urllib 读取系统/环境代理，代理异常时所有请求都会失败，
            # 这里统一置 NO_PROXY=* 让全部网络请求直连，规避坏代理的影响。
            os.environ["NO_PROXY"] = "*"
            os.environ["no_proxy"] = "*"
        ssl_verify_context = ssl.create_default_context()
        _apply_ssl_verify(ssl_verify_context, disable_ssl_verify)
        http = httpx.Client(
            timeout=httpx.Timeout(15, connect=10),
            follow_redirects=True,
            headers={"User-Agent": "EuoraCraft-Launcher"},
            verify=ssl_verify_context,
        )
        created.append(http)
        logger.debug("共享 HTTP 客户端已创建，duration=%.2fs", perf_counter() - phase_started)

        phase_started = perf_counter()
        logger.info("正在初始化账户服务")
        accounts = AccountManager(
            state.data_path,
            microsoft_client_id=environment.get_value("MICROSOFT_CLIENT_ID"),
            event_bus=events,
            disable_ssl_verify=disable_ssl_verify,
            resource_path=state.resource_path,
        )
        created.append(accounts)
        logger.info(
            "账户服务初始化完成，duration=%.2fs，Microsoft 登录可用=%s",
            perf_counter() - phase_started,
            accounts.microsoft_login_config()["available"],
        )

        phase_started = perf_counter()
        wardrobe = WardrobeStore(state.data_path)
        logger.debug(
            "本地衣柜已创建，条目数=%s，duration=%.2fs",
            len(wardrobe.list_items()),
            perf_counter() - phase_started,
        )
        info_card = InfoCardManager(state.data_path, http_client=http)

        phase_started = perf_counter()
        logger.info("正在初始化游戏服务")
        # 共享进程管理器，使实例终端能同时展示插件与 Minecraft 实例的输出。
        shared_instances = InstancesManager()
        game = GameService(
            accounts,
            data_path=state.data_path,
            resource_path=state.resource_path,
            curseforge_api_key=environment.get_value("CURSEFORGE_API_KEY"),
            event_bus=events,
            instances_manager=shared_instances,
        )
        created.append(game)
        logger.info("游戏服务初始化完成，duration=%.2fs", perf_counter() - phase_started)

        phase_started = perf_counter()
        logger.debug("正在初始化联机服务 ConnectorService")
        from ECL.services.connector import ConnectorService
        current_account = accounts.current_account()
        connector = ConnectorService(
            player_name=(current_account or {}).get("alias") or "Player",
            http_client=http,
        )
        logger.debug(
            "联机服务状态: available=%s, easytier_available=%s, easytier_version=%s",
            connector.available,
            connector.easytier_available,
            connector.easytier_version,
        )
        created.append(connector)
        logger.debug("联机服务 ConnectorService 已初始化，duration=%.2fs", perf_counter() - phase_started)

        phase_started = perf_counter()
        logger.debug("正在初始化子进程实例服务")
        processes = ProcessService(event_bus=events, instances_manager=shared_instances)
        created.append(processes)
        logger.debug("子进程实例服务已初始化，duration=%.2fs", perf_counter() - phase_started)

        plugins = PluginManager(events, processes=processes)
        created.append(plugins)
        plugins.initialize(state.data_path, state.resource_path)
        logger.debug("插件管理器已初始化，duration=%.2fs", perf_counter() - phase_started)
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
        wardrobe=wardrobe,
        info_card=info_card,
        game=game,
        connector=connector,
        plugins=plugins,
        processes=processes,
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
        _apply_ssl_verify(
            ssl_verify_context,
            bool((data or {}).get("disable_ssl_verify", False)),
        )
        logger.debug("运行配置已刷新: debug=%s", state.debug)

    events.subscribe("config:updated", update_runtime_config)
    logger.info("后端依赖图构造完成，total=%.2fs", perf_counter() - startup_started)
    return context


__all__ = ["ApplicationContext", "ApplicationState", "create_application"]
