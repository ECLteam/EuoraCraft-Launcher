from pathlib import Path
from typing import Any
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

import psutil
from anyio import to_thread

from ECL.api.contracts import success
from ECL.services.maintenance import schedule_debug_maintenance

from .bridge import _FrontendState, _ipc_handler


class SystemHandlers(_FrontendState):
    """提供启动器信息、严重错误、用户协议、日志导出与调试维护的正式 IPC 边界。"""

    async def launcher_errors_pending(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        返回尚未被前端确认呈现的严重错误。

        :param body: 必须为空的请求对象
        :return: 当前启动器会话内待呈现的错误事件列表
        """
        if body:
            return {"success": False, "message": "launcher_errors_pending 不接受参数", "errorCode": "INVALID_REQUEST"}
        with self._frontend_event_lock:
            pending = list(self._pending_error_presentations.values())
        return success(pending)

    async def launcher_errors_ack(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        确认前端已经接收一批严重错误并释放其内存副本。

        :param body: 包含一个或多个 ``error_ids`` 的请求对象
        :return: 已确认移除的错误数量
        """
        error_ids = body.get("error_ids")
        if not isinstance(error_ids, list) or not error_ids or any(not isinstance(item, str) or not item for item in error_ids):
            return {"success": False, "message": "错误编号列表无效", "errorCode": "INVALID_REQUEST"}
        removed = 0
        with self._frontend_event_lock:
            for error_id in error_ids:
                if self._pending_error_presentations.pop(error_id, None) is not None:
                    removed += 1
        return success({"removed": removed})

    async def system_ping(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        检查连接。

        :param body: 经过边界校验的 IPC 请求数据
        """
        return {"success": True, "data": {"status": "ok", "message": "正常"}}

    @_ipc_handler("SYSTEM_MEMORY_FAILED")
    async def system_memory(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        获取内存信息。

        :param body: 经过边界校验的 IPC 请求数据
        """
        mem = psutil.virtual_memory()
        to_mb = 1 / (1024 * 1024)
        return {
            "success": True,
            "data": {
                "totalMb": round(mem.total * to_mb),
                "usedMb": round(mem.used * to_mb),
                "freeMb": round(mem.available * to_mb),
                "percentUsed": mem.percent,
            },
        }

    async def launcher_info(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        获取启动器信息。

        :param body: 经过边界校验的 IPC 请求数据
        """
        launcher_config = self._get_effective_config().get("launcher") or {}
        return {
            "success": True,
            "data": {
                "version": launcher_config.get("version", ""),
                "version_type": launcher_config.get("version_type", "release"),
                "debug": bool(launcher_config.get("debug", False)),
            },
        }

    async def info_card_get(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        获取信息卡片。

        :param body: 经过边界校验的 IPC 请求数据
        """
        data = await to_thread.run_sync(self.info_card.get_info_card)
        return {"success": True, "data": data}

    async def user_agreement_get(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        读取当前用户协议接受状态。

        :param body: 必须为空的请求对象
        :return: 接受状态和本地匿名标识
        """
        if body:
            return {"success": False, "message": "user_agreement_get 不接受参数", "errorCode": "INVALID_REQUEST"}
        state = self.config.get_config("user_agreement") or {}
        return {
            "success": True,
            "data": {"accepted": bool(state.get("accepted", False)), "uuid": str(state.get("uuid") or "")},
        }

    async def user_agreement_save(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        保存用户已接受协议的本地状态。

        :param body: 可选包含既有匿名 ``uuid`` 的请求数据
        :return: 保存后的接受状态和匿名标识
        """
        existing = self.config.get_config("user_agreement") or {}
        agreement_id = body.get("uuid") or existing.get("uuid") or uuid4().hex
        if not isinstance(agreement_id, str):
            return {"success": False, "message": "协议标识格式无效", "errorCode": "INVALID_REQUEST"}
        state = {"accepted": True, "uuid": agreement_id}
        self.config.save_config("user_agreement", state)
        return {"success": True, "data": state}

    async def user_agreement_clear(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        清除用户协议接受状态，但保留匿名标识供再次确认。

        :param body: 必须为空的请求对象
        :return: 空的成功响应
        """
        if body:
            return {"success": False, "message": "user_agreement_clear 不接受参数", "errorCode": "INVALID_REQUEST"}
        existing = self.config.get_config("user_agreement") or {}
        self.config.save_config("user_agreement", {"accepted": False, "uuid": str(existing.get("uuid") or "")})
        return {"success": True}

    @_ipc_handler("EXPORT_LOGS_FAILED")
    async def export_logs(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        将当前启动器日志打包为 ZIP 文件。

        :param body: 可选包含目标 ``output_path`` 的请求数据
        :return: 导出文件的绝对路径
        """
        output_path = body.get("output_path")
        if output_path is None:
            output_path = self.data_path / "exports" / "EuoraCraft-logs.zip"
        elif not isinstance(output_path, str) or not output_path.strip() or "\0" in output_path:
            return {"success": False, "message": "日志导出路径无效", "errorCode": "INVALID_PATH"}
        target = Path(output_path).expanduser().resolve(strict=False)
        temporary = target.with_suffix(f"{target.suffix}.tmp")
        log_dir = self.data_path / "logs"

        def write_archive() -> None:
            target.parent.mkdir(parents=True, exist_ok=True)
            with ZipFile(temporary, "w", compression=ZIP_DEFLATED) as archive:
                if log_dir.is_dir():
                    for path in sorted(log_dir.iterdir()):
                        if path.is_file():
                            archive.write(path, arcname=path.name)
            temporary.replace(target)

        try:
            await to_thread.run_sync(write_archive)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        return {"success": True, "data": {"path": str(target)}}

    def _schedule_debug_maintenance(self, action: str) -> dict[str, Any]:
        """在调试模式下排队一项启动器数据维护操作。"""
        if not bool(self.launcher.debug):
            return {"success": False, "message": "此操作仅在启动器调试模式下可用", "errorCode": "DEBUG_MODE_REQUIRED"}
        result = schedule_debug_maintenance(self.data_path, action)
        return success(
            {
                "action": result.action,
                "restart_required": result.restart_required,
                "targets": list(result.targets),
                "backup_root": str(result.backup_root),
            }
        )

    @_ipc_handler("DEBUG_MAINTENANCE_FAILED")
    async def debug_reset_launcher_data(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        重置启动器数据。

        :param body: 经过边界校验的 IPC 请求数据
        """
        return self._schedule_debug_maintenance("reset_launcher_data")

    @_ipc_handler("DEBUG_MAINTENANCE_FAILED")
    async def debug_clear_plugins(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        清理插件数据。

        :param body: 经过边界校验的 IPC 请求数据
        """
        return self._schedule_debug_maintenance("clear_plugins")

    async def debug_devtools_open(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        打开 WebView 开发者工具（F12 调试窗口）。

        :param body: 必须为空的请求对象
        :return: 包含 ``open`` 布尔值的响应
        """
        if self._webview is None:
            return {"success": False, "message": "窗口尚未就绪", "errorCode": "WEBVIEW_NOT_READY"}
        self._webview.open_devtools()
        return success({"open": True})
