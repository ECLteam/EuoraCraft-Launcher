from __future__ import annotations

import functools
from typing import Any

from anyio import to_thread

from ECL.api.contracts import ApiResponse, failure, success
from ECL.api.models import InstanceTarget, KickRequest, PortRequest, PortsRequest, RoomCodeRequest
from ECL.services.connector import ConnectorError, ConnectorNotAvailableError

from .bridge import _FrontendState, _ipc_handler


def _connector_guard(error_code: str):
    """
    为联机 IPC 处理器统一映射 Connector 异常到稳定失败响应。

    依赖缺失映射为 ``CONNECTOR_NOT_AVAILABLE``，其余业务错误映射为命令专属错误码。

    :param error_code: 除依赖缺失外的兜底错误码
    """

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(self, body, *args, **kwargs):
            try:
                return await func(self, body, *args, **kwargs)
            except ConnectorNotAvailableError as exc:
                return failure(str(exc), "CONNECTOR_NOT_AVAILABLE")
            except ConnectorError as exc:
                return failure(str(exc), error_code)

        return wrapper

    return decorator


class ConnectorHandlers(_FrontendState):
    """
    联机功能的 IPC 命令处理器。
    """

    @_ipc_handler("CONNECTOR_NOT_AVAILABLE")
    async def connector_status(self, body: dict[str, Any]) -> ApiResponse:
        """查询联机服务的当前状态。"""
        return success(self.connector.get_status())

    @_ipc_handler("CONNECTOR_HOST_PORT_FAILED")
    @_connector_guard("CONNECTOR_HOST_PORT_FAILED")
    async def connector_host_port(self, body: dict[str, Any]) -> ApiResponse:
        """在联机服务中对外开放并托管指定端口。"""
        port = PortRequest.model_validate(body).port
        result = await to_thread.run_sync(self.connector.host_port, port)
        return success(result)

    @_ipc_handler("CONNECTOR_HOST_INSTANCE_FAILED")
    @_connector_guard("CONNECTOR_HOST_INSTANCE_FAILED")
    async def connector_host_instance(self, body: dict[str, Any]) -> ApiResponse:
        """在联机服务中托管一个指定的本地游戏实例。"""
        target = InstanceTarget.model_validate(body)
        result = await to_thread.run_sync(self.connector.host_instance, target.game_path, target.version_id)
        return success(result)

    @_ipc_handler("CONNECTOR_JOIN_FAILED")
    @_connector_guard("CONNECTOR_JOIN_FAILED")
    async def connector_join(self, body: dict[str, Any]) -> ApiResponse:
        """通过房间码加入他人托管的联机房间。"""
        code = RoomCodeRequest.model_validate(body).code
        result = await to_thread.run_sync(self.connector.join, code)
        return success(result)

    @_ipc_handler("CONNECTOR_LEAVE_FAILED")
    @_connector_guard("CONNECTOR_LEAVE_FAILED")
    async def connector_leave(self, body: dict[str, Any]) -> ApiResponse:
        """从当前联机房间退出。"""
        result = self.connector.leave()
        return success(result)

    @_ipc_handler("CONNECTOR_KICK_FAILED")
    @_connector_guard("CONNECTOR_KICK_FAILED")
    async def connector_kick(self, body: dict[str, Any]) -> ApiResponse:
        """从当前房间踢出指定的参与机器。"""
        machine_id = KickRequest.model_validate(body).machine_id
        result = self.connector.kick(machine_id)
        return success(result)

    @_ipc_handler("CONNECTOR_MATCH_FAILED")
    async def connector_match_instances(self, body: dict[str, Any]) -> ApiResponse:
        """匹配可用的联机实例，当前返回空占位。"""
        return success({"mods": [], "instances": []})

    @_ipc_handler("CONNECTOR_EASYTIER_STATUS_FAILED")
    async def connector_easytier_status(self, body: dict[str, Any]) -> ApiResponse:
        """查询 EasyTier 组网状态。"""
        return success(self.connector.get_easytier_status())

    @_ipc_handler("CONNECTOR_EASYTIER_DOWNLOAD_FAILED")
    async def connector_easytier_download(self, body: dict[str, Any]) -> ApiResponse:
        """请求 EasyTier 组网组件下载，返回其当前状态。"""
        return success(self.connector.get_easytier_status())

    @_ipc_handler("CONNECTOR_SCAN_PORTS_FAILED")
    async def connector_detect_ports(self, body: dict[str, Any]) -> ApiResponse:
        """探测本机 Java 进程开放的候选端口。"""
        return success(self.connector.detect_ports())

    @_ipc_handler("CONNECTOR_SCAN_PORTS_FAILED")
    async def connector_search_mc_port(self, body: dict[str, Any]) -> ApiResponse:
        """在候选端口中搜索确认 Minecraft 服务端口。"""
        ports = PortsRequest.model_validate(body).ports
        return success(self.connector.search_mc_port(ports))

    @_ipc_handler("CONNECTOR_NAT_TYPE_FAILED")
    async def connector_nat_type(self, body: dict[str, Any]) -> ApiResponse:
        """查询本机网络的 NAT 类型。"""
        return success(self.connector.get_nat_type())
