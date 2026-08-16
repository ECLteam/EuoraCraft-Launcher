from __future__ import annotations

from typing import Any

from anyio import to_thread

from ECL.api.contracts import ApiResponse, failure, success
from ECL.api.models import InstanceTarget, KickRequest, PortRequest, RoomCodeRequest
from ECL.services.connector import ConnectorError, ConnectorNotAvailableError

from .bridge import _FrontendState, _ipc_handler


class ConnectorHandlers(_FrontendState):
    """
    联机功能的 IPC 命令处理器。
    """

    @_ipc_handler("CONNECTOR_NOT_AVAILABLE")
    async def connector_status(self, body: dict[str, Any]) -> ApiResponse:
        return success(self.connector.get_status())

    @_ipc_handler("CONNECTOR_HOST_PORT_FAILED")
    async def connector_host_port(self, body: dict[str, Any]) -> ApiResponse:
        try:
            port = PortRequest.model_validate(body).port
            result = await to_thread.run_sync(self.connector.host_port, port)
            return success(result)
        except ConnectorNotAvailableError as exc:
            return failure(str(exc), "CONNECTOR_NOT_AVAILABLE")
        except ConnectorError as exc:
            return failure(str(exc), "CONNECTOR_HOST_PORT_FAILED")

    @_ipc_handler("CONNECTOR_HOST_INSTANCE_FAILED")
    async def connector_host_instance(self, body: dict[str, Any]) -> ApiResponse:
        try:
            target = InstanceTarget.model_validate(body)
            result = await to_thread.run_sync(self.connector.host_instance, target.game_path, target.version_id)
            return success(result)
        except ConnectorNotAvailableError as exc:
            return failure(str(exc), "CONNECTOR_NOT_AVAILABLE")
        except ConnectorError as exc:
            return failure(str(exc), "CONNECTOR_HOST_INSTANCE_FAILED")

    @_ipc_handler("CONNECTOR_JOIN_FAILED")
    async def connector_join(self, body: dict[str, Any]) -> ApiResponse:
        try:
            code = RoomCodeRequest.model_validate(body).code
            result = await to_thread.run_sync(self.connector.join, code)
            return success(result)
        except ConnectorNotAvailableError as exc:
            return failure(str(exc), "CONNECTOR_NOT_AVAILABLE")
        except ConnectorError as exc:
            return failure(str(exc), "CONNECTOR_JOIN_FAILED")

    @_ipc_handler("CONNECTOR_LEAVE_FAILED")
    async def connector_leave(self, body: dict[str, Any]) -> ApiResponse:
        try:
            result = self.connector.leave()
            return success(result)
        except ConnectorError as exc:
            return failure(str(exc), "CONNECTOR_LEAVE_FAILED")

    @_ipc_handler("CONNECTOR_KICK_FAILED")
    async def connector_kick(self, body: dict[str, Any]) -> ApiResponse:
        try:
            machine_id = KickRequest.model_validate(body).machine_id
            result = self.connector.kick(machine_id)
            return success(result)
        except ConnectorError as exc:
            return failure(str(exc), "CONNECTOR_KICK_FAILED")

    @_ipc_handler("CONNECTOR_MATCH_FAILED")
    async def connector_match_instances(self, body: dict[str, Any]) -> ApiResponse:
        return success({"mods": [], "instances": []})

    @_ipc_handler("CONNECTOR_EASYTIER_STATUS_FAILED")
    async def connector_easytier_status(self, body: dict[str, Any]) -> ApiResponse:
        return success(self.connector.get_easytier_status())

    @_ipc_handler("CONNECTOR_EASYTIER_DOWNLOAD_FAILED")
    async def connector_easytier_download(self, body: dict[str, Any]) -> ApiResponse:
        return success(self.connector.get_easytier_status())

    @_ipc_handler("CONNECTOR_SCAN_PORTS_FAILED")
    async def connector_scan_ports(self, body: dict[str, Any]) -> ApiResponse:
        return success(self.connector.scan_ports())

    @_ipc_handler("CONNECTOR_NAT_TYPE_FAILED")
    async def connector_nat_type(self, body: dict[str, Any]) -> ApiResponse:
        return success(self.connector.get_nat_type())
