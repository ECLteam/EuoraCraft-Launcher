from __future__ import annotations

import asyncio
import logging
import socket
from collections.abc import Callable
from typing import Any

import easytier_pyo3

from ECL.services.florolding import Florolding, validate_code

logger = logging.getLogger("EuoraCraft-Launcher.Connector")


# ── 类型别名 ──────────────────────────────────────────────────────────

ConnectorMode = str  # "idle" | "starting" | "host" | "guest"
EasyTierPhase = str  # "idle" | "resolving" | "downloading" | "extracting" | "installed" | "failed"
NatTypeKind = str  # "cone" | "symmetric" | "blocked" | "unknown"


class ConnectorError(Exception):
    """
联机服务通用错误。
    """


class ConnectorNotAvailableError(ConnectorError):
    """
联机服务不可用（依赖缺失）。
    """


class ConnectorService:
    """
    联机服务，封装 Florolding + EasyTier 的多人联机能力。

    管理房间生命周期、玩家列表和网络连接状态。
    """

    def __init__(
        self,
        launcher_info: str = "EuoraCraft-Launcher",
        log_callback: Callable[[str, str], None] | None = None,
    ) -> None:
        self._launcher_info = launcher_info
        if log_callback is None:
            def _default_log(level: str, msg: str) -> None:
                log_func = getattr(logger, level.lower(), logger.info)
                log_func(msg)

            self._log_callback = _default_log
        else:
            self._log_callback = log_callback

        # 运行时状态
        self._mode: ConnectorMode = "idle"
        self._room_code: str | None = None
        self._mc_host: str | None = None
        self._mc_port: int | None = None
        self._room_server: Any = None  # AsyncFloroldingServer
        self._easy_tier_node: Any = None  # easytier_pyo3.Node
        self._client: Any = None  # AsyncFloroldingClient
        self._players: list[dict[str, Any]] = []
        self._error: str | None = None
        self._started: bool = False

        # 易用性
        self._loop: asyncio.AbstractEventLoop | None = None

    # ── 可用性 ──────────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        """
联机服务是否可用（依赖齐全）。
        """
        return True

    @property
    def easytier_available(self) -> bool:
        """
EasyTier 是否可用。
        """
        return True

    @property
    def easytier_version(self) -> str:
        """
EasyTier 版本号。
        """
        try:
            return easytier_pyo3.version()
        except Exception:
            return "unknown"

    # ── 状态查询 ────────────────────────────────────────────────────

    def get_status(self) -> dict[str, Any]:
        """
        获取当前联机状态。

        :returns: 包含 mode, roomCode, mcHost, mcPort, gameInfo, players, error 的字典
        """
        return {
            "mode": self._mode,
            "roomCode": self._room_code,
            "mcHost": self._mc_host,
            "mcPort": self._mc_port,
            "gameInfo": None,
            "players": self._players,
            "error": self._error,
        }

    def get_easytier_status(self) -> dict[str, Any]:
        """
        获取 EasyTier 安装状态。

        :returns: 包含 installed, status, progress, speed, error 的字典
        """
        return {
            "installed": True,
            "status": "installed",
            "progress": 100,
            "speed": 0,
            "error": None,
        }

    def get_nat_type(self) -> dict[str, Any]:
        """
        检测 NAT 类型（简易实现）。

        :returns: 包含 type, publicIp, publicPort 的字典
        """
        # 简易实现：仅标记为 unknown，实际 NAT 检测需要 STUN 协议
        return {
            "type": "unknown",
            "publicIp": None,
            "publicPort": None,
        }

    # ── 房间创建 ────────────────────────────────────────────────────

    def host_port(self, port: int) -> dict[str, Any]:
        """
        以指定端口创建联机房间。

        :param port: Minecraft 服务器端口
        :returns: 包含 roomCode 的字典
        :raises ConnectorNotAvailableError: 依赖缺失时抛出
        :raises ConnectorError: 房间创建失败时抛出
        """
        if self._mode != "idle":
            raise ConnectorError("当前已有活跃的房间，请先退出")

        logger.debug("开始创建联机房间: minecraft_port=%s, easytier=%s", port, self.easytier_available)
        try:
            florolding = Florolding(
                launcher_info=self._launcher_info,
                log_callback=self._log_callback,
            )
            logger.debug("Florolding 实例已创建")

            # 设置 EasyTier 节点列表
            florolding.set_nodes([])
            logger.debug("已清空 EasyTier 节点列表（使用默认节点）")

            room_code, server, easy_tier_node = florolding.create_room(
                player_name="Host",
                minecraft_port=port,
            )
            logger.debug(
                "房间已创建: room_code=%s, server=%s, easytier_id=%s",
                room_code, type(server).__name__, easy_tier_node.peer_id() if easy_tier_node else "N/A",
            )

            self._mode = "host"
            self._room_code = room_code
            self._mc_host = "127.0.0.1"
            self._mc_port = port
            self._room_server = server
            self._easy_tier_node = easy_tier_node
            self._error = None

            logger.info("联机房间创建成功: room_code=%s, minecraft_port=%s", room_code, port)
            return {"roomCode": room_code}
        except Exception as exc:
            self._mode = "idle"
            self._error = str(exc)
            logger.exception("创建联机房间失败: %s", exc)
            raise ConnectorError(f"创建房间失败: {exc}") from exc

    def host_instance(self, game_path: str, version_id: str) -> dict[str, Any]:
        """
        启动实例并创建联机房间。

        :param game_path: 游戏路径
        :param version_id: 版本 ID
        :returns: 包含 status 的字典
        """
        # 简易实现：先创建房间，后续通过启动器启动游戏服务端
        return self.host_port(25565)

    def join(self, code: str) -> dict[str, Any]:
        """
        加入联机房间。

        :param code: 房间码（格式 U/NNNN-NNNN-SSSS-SSSS）
        :returns: 包含 mcHost, mcPort 的字典
        :raises ConnectorNotAvailableError: 依赖缺失时抛出
        :raises ConnectorError: 加入失败时抛出
        """
        if self._mode != "idle":
            raise ConnectorError("当前已有活跃的房间，请先退出")

        if not validate_code(code):
            raise ConnectorError("无效的房间码格式")

        self._mode = "starting"
        self._room_code = code
        self._error = None

        # 简易实现：标记为已加入，实际连接需要完整的 EasyTier 网络发现
        # 这里模拟从前端输入的地址获取
        self._mode = "guest"
        # 从房间码中提取网络信息（简易实现，实际需要 EasyTier 网络发现）
        # 默认使用本地回环地址，实际联机需要通过 EasyTier 网络获取房主地址
        self._mc_host = "127.0.0.1"
        self._mc_port = 25565

        return {"mcHost": self._mc_host, "mcPort": self._mc_port}

    def leave(self) -> dict[str, Any]:
        """
        退出联机房间。

        :returns: 包含 status 的字典
        """
        self._mode = "idle"
        self._room_code = None
        self._mc_host = None
        self._mc_port = None
        self._room_server = None
        self._easy_tier_node = None
        self._client = None
        self._error = None
        return {"status": "left"}

    def kick(self, machine_id: str) -> dict[str, Any]:
        """
        移出玩家。

        :param machine_id: 目标玩家机器 ID
        :returns: 包含 status 的字典
        """
        self._players = [p for p in self._players if p.get("machineId") != machine_id]
        return {"status": "kicked"}

    # ── 端口扫描 ────────────────────────────────────────────────────

    def scan_ports(self) -> dict[str, Any]:
        """
        扫描本地 Minecraft 服务器端口。

        :returns: 包含 port 的字典（未找到时 port 为 None）
        """
        # 扫描常见端口
        common_ports = [25565, 25566, 25567, 25568, 25569, 25570]
        for port in common_ports:
            if self._check_port(port):
                return {"port": port}
        return {"port": None}

    # ── 辅助方法 ────────────────────────────────────────────────────

    @staticmethod
    def _check_port(port: int) -> bool:
        """
检查端口是否被占用（即是否有 Minecraft 服务器在运行）。
        """
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.settimeout(0.5)
                result = s.connect_ex(("127.0.0.1", port))
                return result == 0
            except Exception:
                return False
