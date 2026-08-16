from __future__ import annotations

import asyncio
import json
import logging
import socket
import struct
import sys
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from ipaddress import IPv4Address
from threading import Thread
from typing import Any

import easytier_pyo3
import httpx
import psutil

from ECL.services.florolding import Florolding, find_free_port, machine_id, validate_code
from ECL.services.florolding.Florolding.F_Client import AsyncFloroldingClient

logger = logging.getLogger("EuoraCraft-Launcher.Connector")

# ── 节点服务 ──────────────────────────────────────────────────────────

_NODE_LIST_URL = "https://api.qomicex.top/api/nodes"
_NODE_UA = "ECL"
_DEFAULT_NODES = ["tcp://public.easytier.cn:11010"]
_EASYTIER_SCHEMES = ("tcp://", "udp://", "quic://", "faketcp://", "ws://", "wss://")


class _LoggerWriter:
    """
    把写往 stdout 的文本按行转发到日志记录器。

    florolding 库内部用 ``print()`` 输出（忽略传入的 log_callback），改动子模块
    会影响其独立使用，因此这里从外部把 stdout 重定向到日志，避免污染终端。
    """

    def __init__(self, level: int = logging.INFO) -> None:
        self._level = level
        self._buffer = ""

    def write(self, text: str) -> int:
        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if line.strip():
                logger.log(self._level, line)
        return len(text)

    def flush(self) -> None:
        if self._buffer.strip():
            logger.log(self._level, self._buffer)
            self._buffer = ""

    def isatty(self) -> bool:
        return False

    def fileno(self) -> int | None:
        return None


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
        player_name: str | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._launcher_info = launcher_info
        self._player_name = player_name or "Player"
        self._http = http_client
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
        self._nodes: list[str] = list(_DEFAULT_NODES)
        self._error: str | None = None
        self._started: bool = False

        # florolding 库 stdout 捕获（转发到日志记录器）
        self._stdout_capture: _LoggerWriter | None = None
        self._saved_stdout: Any = None

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

    def fetch_nodes(self) -> list[str]:
        """
        获取可用的 EasyTier 中继节点 URI 列表。

        从 Qomicex 节点服务拉取节点，聚合的 ``https://`` 节点会二次请求解析出实际 URI。
        失败时回退到内置默认节点，保证建房/加入不会因取节点失败而中断。

        :returns: 去重保序的节点 URI 列表
        """
        if self._http is None:
            return list(_DEFAULT_NODES)
        try:
            response = self._http.get(
                _NODE_LIST_URL,
                headers={"User-Agent": _NODE_UA},
                timeout=10.0,
            )
            response.raise_for_status()
            items = response.json()
            if not isinstance(items, list):
                logger.warning("节点服务返回了非数组结构，使用默认节点")
                return list(_DEFAULT_NODES)

            nodes: list[str] = []
            aggregate_urls: list[str] = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                url = str(item.get("url") or "").strip()
                if not url:
                    continue
                if self._is_easytier_peer(url):
                    nodes.append(url)
                elif url.startswith("https://"):
                    aggregate_urls.append(url)

            if aggregate_urls:
                with ThreadPoolExecutor(max_workers=min(len(aggregate_urls), 8)) as pool:
                    for resolved in pool.map(self._resolve_aggregate_node, aggregate_urls):
                        nodes.extend(resolved)
            resolved = list(dict.fromkeys(nodes)) or list(_DEFAULT_NODES)
            logger.debug("联机节点列表: %s", resolved)
            return resolved
        except Exception as exc:
            logger.warning("拉取联机节点列表失败，使用默认节点: %s", exc)
            return list(_DEFAULT_NODES)

    def _resolve_aggregate_node(self, url: str) -> list[str]:
        """
        解析一个聚合节点地址，得到可用的 EasyTier URI。

        :param url: 以 ``https://`` 开头的聚合节点地址
        :returns: 解析出的节点 URI 列表（可能为空）
        """
        try:
            response = self._http.get(
                url,
                headers={"User-Agent": _NODE_UA},
                timeout=10.0,
            )
            response.raise_for_status()
            text = response.text.strip()
            if not text:
                return []
            try:
                payload = response.json()
                if isinstance(payload, list):
                    return [
                        str(node.get("url")).strip()
                        for node in payload
                        if isinstance(node, dict) and self._is_easytier_peer(str(node.get("url") or ""))
                    ]
            except Exception:
                pass
            if self._is_easytier_peer(text):
                return [text]
            return []
        except Exception as exc:
            logger.debug("解析聚合节点失败: %s", exc)
            return []

    @staticmethod
    def _is_easytier_peer(value: str) -> bool:
        """
        判断一个字符串是否为 easytier 原生支持的节点 URI。

        :param value: 待判断的字符串
        :returns: 是原生节点 URI 时返回 True
        """
        return value.startswith(_EASYTIER_SCHEMES)

    # ── florolding stdout 捕获 ─────────────────────────────────────

    def _begin_stdout_capture(self) -> None:
        """
        把 sys.stdout 重定向到日志记录器，捕获 florolding 库的 print 输出。

        幂等：已捕获时直接返回。
        """
        if self._stdout_capture is not None:
            return
        stdout = sys.stdout
        if stdout is None:
            return
        self._saved_stdout = stdout
        self._stdout_capture = _LoggerWriter()
        sys.stdout = self._stdout_capture

    def _end_stdout_capture(self) -> None:
        """
        恢复原始的 sys.stdout。

        幂等：未捕获时直接返回。
        """
        if self._stdout_capture is None:
            return
        try:
            self._stdout_capture.flush()
        finally:
            sys.stdout = self._saved_stdout
            self._saved_stdout = None
            self._stdout_capture = None

    # ── 状态查询 ────────────────────────────────────────────────────

    @staticmethod
    def _to_frontend_player(player: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": player.get("name", ""),
            "vendor": player.get("vendor", ""),
            "iconBase64": None,
            "kind": "host" if str(player.get("kind", "")).upper() == "HOST" else "guest",
            "machineId": player.get("machine_id"),
        }

    def _current_players(self) -> list[dict[str, Any]]:
        if self._mode == "host" and self._room_server is not None:
            try:
                raw = self._room_server.sync_get_player_list()
                return [self._to_frontend_player(p) for p in raw if isinstance(p, dict)]
            except Exception:
                return []
        if self._mode == "guest" and self._client is not None:
            loop = getattr(self._client, "loop", None)
            writer = getattr(self._client, "writer", None)
            if loop is not None and writer is not None:
                try:
                    status, body = asyncio.run_coroutine_threadsafe(
                        self._client.send_request("c:player_profiles_list", b""),
                        loop,
                    ).result(timeout=5)
                    if status == 0:
                        raw = json.loads(body.decode("utf-8"))
                        return [self._to_frontend_player(p) for p in raw if isinstance(p, dict)]
                except Exception:
                    pass
            # 列表获取失败时至少展示自己，避免玩家列表为空
            return [
                {
                    "name": self._client.player_name,
                    "vendor": self._client.vendor,
                    "iconBase64": None,
                    "kind": "guest",
                    "machineId": self._client.machine_id,
                }
            ]
        return self._players

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
            "players": self._current_players(),
            "nodes": self._nodes,
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
        self._begin_stdout_capture()
        try:
            florolding = Florolding(
                launcher_info=self._launcher_info,
                log_callback=self._log_callback,
            )
            logger.debug("Florolding 实例已创建")

            # 设置 EasyTier 节点列表
            self._nodes = self.fetch_nodes()
            florolding.set_nodes(self._nodes)
            logger.debug("已设置 EasyTier 节点列表")

            room_code, server, easy_tier_node = florolding.create_room(
                player_name=self._player_name,
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
            self._end_stdout_capture()
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

        self._begin_stdout_capture()
        try:
            florolding = Florolding(
                launcher_info=self._launcher_info,
                log_callback=self._log_callback,
            )
            self._nodes = self.fetch_nodes()
            florolding.set_nodes(self._nodes)
            logger.debug("开始加入联机房间: room_code=%s, player_name=%s", code, self._player_name)

            node, mc_port = self._join_room(florolding, code, self._player_name)
            self._mc_host = "127.0.0.1"
            self._mc_port = mc_port
            self._easy_tier_node = node
            self._mode = "guest"
            self._error = None

            logger.info("已加入联机房间: room_code=%s, mc_port=%s", code, mc_port)
            return {"mcHost": self._mc_host, "mcPort": self._mc_port}
        except Exception as exc:
            self._mode = "idle"
            self._error = str(exc)
            self._stop_async_thread_client()
            self._end_stdout_capture()
            logger.exception("加入联机房间失败: %s", exc)
            raise ConnectorError(f"加入房间失败: {exc}") from exc

    def _join_room(
        self,
        florolding: Florolding,
        room_code: str,
        player_name: str,
        conn_timeout: int = 30,
    ) -> tuple[Any, int]:
        """
        执行加入房间的握手流程，返回 EasyTier 节点和本地 Minecraft 映射端口。

        florolding 的 ``join_room`` 只返回 EasyTier 节点，不暴露本地映射端口，而启动器
        需要它向前端展示连接地址，因此这里复刻其握手流程并保留端口。

        :param florolding: Florolding 实例
        :param room_code: 房间码
        :param player_name: 玩家昵称
        :param conn_timeout: 发现房主大厅的超时秒数
        :returns: (easytier_node, 本地 Minecraft 映射端口)
        """
        machine_idv = machine_id()
        easytier_config: dict = deepcopy(florolding.easytier_config)
        easytier_config.update({
            "network_identity": {
                "network_name": f"scaffolding-mc-{room_code[2:11]}",
                "network_secret": room_code[12:21],
            },
            "peer": florolding.nodes,
        })

        node = easytier_pyo3.Node(easytier_config)
        node.start()

        host_node_info: dict = {}
        start_time = time.time()
        while not host_node_info:
            for info in node.routes():
                if info["hostname"].lower().startswith("scaffolding-mc-server-") and (
                    info.get("ipv4_addr", {}).get("address", {}).get("addr")
                ):
                    host_node_info = info
                    break
            if host_node_info:
                break
            time.sleep(1)
            if time.time() - start_time > conn_timeout:
                raise TimeoutError("连接超时，无法找到联机大厅")

        server_port = host_node_info["hostname"].replace("scaffolding-mc-server-", "")
        if not server_port.isnumeric() or not (0 < int(server_port) <= 65535):
            raise ValueError("联机大厅端口不合规")

        host_virtual_ip = IPv4Address(host_node_info["ipv4_addr"]["address"]["addr"]).exploded
        bind_server_port = find_free_port()
        node.apply_config({
            "port_forward": [
                {
                    "bind_addr": f"127.0.0.1:{bind_server_port}",
                    "dst_addr": f"{host_virtual_ip}:{server_port}",
                    "proto": "tcp",
                }
            ]
        })

        client = AsyncFloroldingClient(
            machine_id=machine_idv,
            easytier_id=node.peer_id(),
            player_name=player_name,
            server_port=bind_server_port,
            vendor=florolding.vendor,
            log_callback=self._log_callback,
        )
        self._client = client
        Thread(target=client.start, daemon=True).start()
        while not client.writer:
            time.sleep(1)

        client.sync_c_protocols()
        mc_port = client.sync_server_port()
        bind_mc_port = find_free_port()
        node.apply_config({
            "port_forward": [
                {
                    "bind_addr": f"127.0.0.1:{bind_mc_port}",
                    "dst_addr": f"{host_virtual_ip}:{mc_port}",
                    "proto": "tcp",
                }
            ]
        })

        return node, bind_mc_port

    def leave(self) -> dict[str, Any]:
        """
        退出联机房间。

        :returns: 包含 status 的字典
        """
        self._stop_async_thread_client()
        server = self._room_server
        if server is not None and hasattr(server, "sync_stop"):
            try:
                server.sync_stop()
            except Exception:
                logger.debug("停止联机服务端失败", exc_info=True)

        node = self._easy_tier_node
        if node is not None and hasattr(node, "stop"):
            try:
                node.stop()
            except Exception:
                logger.debug("停止 EasyTier 节点失败", exc_info=True)

        self._end_stdout_capture()
        self._mode = "idle"
        self._room_code = None
        self._mc_host = None
        self._mc_port = None
        self._room_server = None
        self._easy_tier_node = None
        self._client = None
        self._error = None
        return {"status": "left"}

    def _stop_async_thread_client(self) -> None:
        """
        停止 florolding 客户端线程：取消心跳并断开连接。

        florolding 的 ``AsyncFloroldingClient`` 以守护线程运行，若不在退出房间时
        停止，解释器关闭时其心跳仍会写 stdout，引发 ``_enter_buffered_busy`` 死锁。
        这里通过事件循环安全地取消心跳并断开，不修改子模块。
        """
        client = self._client
        if client is None:
            return
        loop = getattr(client, "loop", None)
        if loop is None:
            return
        async def _stop() -> None:
            task = getattr(client, "heartbeat_task", None)
            if task is not None:
                task.cancel()
            if getattr(client, "writer", None) is not None:
                await client.disconnect()
        try:
            asyncio.run_coroutine_threadsafe(_stop(), loop)
        except (RuntimeError, TypeError):
            logger.debug("停止 florolding 客户端失败", exc_info=True)
        finally:
            self._client = None

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
        扫描本机 Java 进程开放的 Minecraft 服务端口。

        Minecraft 的“对局域网开放”会分配随机端口，不能依赖 25565 等固定端口。
        此处先从 Java 进程的监听套接字缩小范围，再发送无副作用的状态请求确认
        对端确实是 Minecraft 服务端，避免把其他应用的开放端口误用于联机。

        :returns: 包含 port 的字典（未找到时 port 为 None）
        """
        candidates = self._minecraft_listener_ports()
        logger.debug("开始扫描本地 Minecraft 端口: candidates=%s", candidates)
        for port in candidates:
            if self._is_minecraft_server(port):
                logger.info("发现本地 Minecraft 服务端口: %s", port)
                return {"port": port}
        logger.debug("未发现本地 Minecraft 服务端口")
        return {"port": None}

    # ── 辅助方法 ────────────────────────────────────────────────────

    @staticmethod
    def _minecraft_listener_ports() -> list[int]:
        """
        获取 Java 进程正在监听的 TCP 端口。

        psutil 在无管理员权限时可能无法读取其他用户进程；这种情况下返回已能读取到的
        结果而不是中断扫描。Minecraft 客户端与启动器通常属于当前用户，仍可正常发现。

        :returns: 去重、升序排列的候选端口
        """
        java_pids: set[int] = set()
        try:
            for process in psutil.process_iter(["pid", "name", "exe"]):
                info = process.info
                executable = " ".join(str(info.get(key) or "") for key in ("name", "exe")).lower()
                if "java" in executable and isinstance(info.get("pid"), int):
                    java_pids.add(info["pid"])
        except (psutil.AccessDenied, psutil.Error) as exc:
            logger.debug("枚举 Java 进程失败: %s", exc)

        if not java_pids:
            return []

        try:
            connections = psutil.net_connections(kind="tcp")
        except (psutil.AccessDenied, psutil.Error) as exc:
            logger.debug("读取本地监听端口失败: %s", exc)
            return []

        ports = {
            connection.laddr.port
            for connection in connections
            if connection.pid in java_pids
            and connection.status == psutil.CONN_LISTEN
            and connection.laddr
            and isinstance(connection.laddr.port, int)
            and 0 < connection.laddr.port <= 65535
        }
        return sorted(ports)

    @staticmethod
    def _is_minecraft_server(port: int, timeout: float = 0.5) -> bool:
        """
        通过 Minecraft Status 协议确认本地端口的服务类型。

        :param port: 待确认的本地 TCP 端口
        :param timeout: 建连与读取的最大等待秒数
        :returns: 收到合法 Minecraft 状态 JSON 时返回 True，其他网络服务返回 False
        """
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=timeout) as connection:
                connection.settimeout(timeout)
                handshake = b"\x00" + ConnectorService._encode_varint(758) + ConnectorService._encode_varint(9)
                handshake += b"localhost" + struct.pack(">H", port) + b"\x01"
                connection.sendall(ConnectorService._encode_varint(len(handshake)) + handshake)
                connection.sendall(b"\x01\x00")

                packet_length = ConnectorService._read_varint(connection)
                if packet_length is None or not 1 <= packet_length <= 1_048_576:
                    return False
                packet = ConnectorService._read_exact(connection, packet_length)
                if packet is None:
                    return False

            packet_id, offset = ConnectorService._decode_varint(packet)
            if packet_id != 0:
                return False
            json_length, offset = ConnectorService._decode_varint(packet, offset)
            if json_length is None or json_length < 2 or offset + json_length != len(packet):
                return False
            status = json.loads(packet[offset : offset + json_length].decode("utf-8"))
            return isinstance(status, dict) and isinstance(status.get("version"), dict)
        except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError, struct.error):
            return False

    @staticmethod
    def _encode_varint(value: int) -> bytes:
        """
        将非负 Minecraft VarInt 编码为字节串。

        :param value: 待编码的非负整数
        :returns: 可直接写入 Minecraft TCP 数据包的 VarInt 字节串
        """
        encoded = bytearray()
        while True:
            current = value & 0x7F
            value >>= 7
            encoded.append(current | (0x80 if value else 0))
            if not value:
                return bytes(encoded)

    @staticmethod
    def _read_varint(connection: socket.socket) -> int | None:
        """
        从套接字读取一个至多五字节的 Minecraft VarInt。

        :param connection: 已建立连接并配置读取超时的 TCP 套接字
        :returns: 读取成功的整数；连接关闭或格式无效时返回 None
        """
        encoded = bytearray()
        for _ in range(5):
            byte = ConnectorService._read_exact(connection, 1)
            if byte is None:
                return None
            encoded.extend(byte)
            if not byte[0] & 0x80:
                value, _ = ConnectorService._decode_varint(encoded)
                return value
        return None

    @staticmethod
    def _decode_varint(data: bytes | bytearray, offset: int = 0) -> tuple[int | None, int]:
        """
        解析内存中的 Minecraft VarInt，并返回值与下一个偏移量。

        :param data: 包含 VarInt 的原始字节数据
        :param offset: VarInt 在 data 内的起始偏移量
        :returns: (解析值, 下一个偏移量)；不完整或超长时解析值为 None
        """
        value = 0
        for index in range(5):
            if offset + index >= len(data):
                return None, offset
            byte = data[offset + index]
            value |= (byte & 0x7F) << (7 * index)
            if not byte & 0x80:
                return value, offset + index + 1
        return None, offset

    @staticmethod
    def _read_exact(connection: socket.socket, length: int) -> bytes | None:
        """
        读取定长响应，连接提前关闭时返回 None。

        :param connection: 已建立连接并配置读取超时的 TCP 套接字
        :param length: 必须读取的字节数
        :returns: 完整响应；连接提前关闭时返回 None
        """
        chunks = bytearray()
        while len(chunks) < length:
            chunk = connection.recv(length - len(chunks))
            if not chunk:
                return None
            chunks.extend(chunk)
        return bytes(chunks)
