import base64
from io import BytesIO
from typing import Any
from urllib.parse import urlsplit

from anyio import to_thread
from PIL import Image

from .bridge import _FrontendState, _ipc_handler


class AccountHandlers(_FrontendState):
    async def accounts_list(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        获取账户列表。

        :param body: 经过边界校验的 IPC 请求数据
        """
        return {"success": True, "data": self.accounts.list_accounts()}

    async def accounts_current(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        获取当前账户。

        :param body: 经过边界校验的 IPC 请求数据
        """
        return {"success": True, "data": self.accounts.current_account()}

    @_ipc_handler("ACCOUNT_OPERATION_FAILED")
    async def accounts_add_offline(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        添加离线账户。

        :param body: 经过边界校验的 IPC 请求数据
        """
        account_data = self.accounts.add_offline(body.get("username"), body.get("uuid"))
        return {"success": True, "data": account_data}

    @_ipc_handler("AUTHLIB_LOGIN_FAILED")
    async def accounts_add_authlib(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        添加外置登录账户。

        :param body: 经过边界校验的 IPC 请求数据
        """
        server_url = self._normalize_authlib_server_url(body.get("server_url"))
        if server_url is None:
            return {"success": False, "message": "外置登录服务器地址无效", "errorCode": "INVALID_AUTHLIB_SERVER"}
        email = body.get("email")
        if not isinstance(email, str) or not email.strip():
            return {"success": False, "message": "外置登录邮箱不能为空", "errorCode": "INVALID_AUTHLIB_USERNAME"}
        email = email.strip()
        account = await to_thread.run_sync(
            self.accounts.add_authlib,
            server_url,
            email,
            body.get("password"),
        )
        self._remember_authlib_login(account.get("auth_server") or server_url, email)
        return {"success": True, "data": account}

    @_ipc_handler("AUTHLIB_PROFILE_SELECT_FAILED")
    async def accounts_select_authlib_profile(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        为多角色外置账户选择本次登录使用的单个角色。

        :param body: 经过边界校验的 IPC 请求数据
        """
        account = await to_thread.run_sync(
            self.accounts.select_authlib_profile,
            body.get("account_id"),
            body.get("profile_id"),
        )
        return {"success": True, "data": account}

    @_ipc_handler("AUTHLIB_SERVER_RESOLVE_FAILED")
    async def authlib_resolve_server(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        解析外置登录网站实际使用的 API 地址。

        :param body: 经过边界校验的 IPC 请求数据
        """
        server_url = self._normalize_authlib_server_url(body.get("server_url"))
        if server_url is None:
            return {"success": False, "message": "外置登录服务器地址无效", "errorCode": "INVALID_AUTHLIB_SERVER"}
        resolved_url = await to_thread.run_sync(self.accounts.resolve_authlib_server, server_url)
        return {"success": True, "data": resolved_url}

    @_ipc_handler("ACCOUNT_OPERATION_FAILED")
    async def accounts_start_microsoft_login(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        开始微软登录。

        :param body: 经过边界校验的 IPC 请求数据
        """
        login_data = await to_thread.run_sync(self.accounts.start_microsoft_login)
        return {"success": True, "data": login_data}

    async def accounts_microsoft_login_config(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        获取微软登录配置。

        :param body: 经过边界校验的 IPC 请求数据
        """
        return {"success": True, "data": self.accounts.microsoft_login_config()}

    async def accounts_poll_microsoft_login(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        获取微软登录状态。

        :param body: 经过边界校验的 IPC 请求数据
        """
        return {"success": True, "data": self.accounts.poll_microsoft_login()}

    async def accounts_cancel_microsoft_login(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        取消微软登录。

        :param body: 经过边界校验的 IPC 请求数据
        """
        return {"success": True, "data": {"cancelled": self.accounts.cancel_microsoft_login()}}

    @_ipc_handler("ACCOUNT_OPERATION_FAILED")
    async def accounts_complete_microsoft_login(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        完成微软登录。

        :param body: 经过边界校验的 IPC 请求数据
        """
        login_result = self.accounts.complete_microsoft_login()
        return {"success": True, "data": login_result}

    @_ipc_handler("ACCOUNT_OPERATION_FAILED")
    async def accounts_switch(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        切换账户。

        :param body: 经过边界校验的 IPC 请求数据
        """
        self.accounts.switch_account(body.get("account_id"))
        return {"success": True}

    @_ipc_handler("ACCOUNT_OPERATION_FAILED")
    async def accounts_remove(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        删除账户。

        :param body: 经过边界校验的 IPC 请求数据
        """
        self.accounts.remove_account(body.get("account_id"))
        return {"success": True}

    @_ipc_handler("ACCOUNT_OPERATION_FAILED")
    async def accounts_refresh_profile(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        刷新账户信息。

        :param body: 经过边界校验的 IPC 请求数据
        """
        refresh_result = await to_thread.run_sync(self.accounts.refresh_account, body.get("account_id"))
        return {"success": True, "data": refresh_result}

    @staticmethod
    def _decode_skin_image(image: Any) -> bytes | None:
        """
        将前端皮肤图片数据(base64 data URL 或纯 base64)解码并校验为可读图片。

        :param image: 需要上传或保存的图像数据
        """
        if not isinstance(image, str) or not image:
            return None
        encoded = image
        if image.startswith("data:"):
            try:
                _, encoded = image.split(",", 1)
            except ValueError:
                return None
        try:
            payload = base64.b64decode(encoded)
        except (ValueError, base64.binascii.Error):
            return None
        try:
            with Image.open(BytesIO(payload)) as image_reader:
                image_reader.load()
        except Exception:
            return None
        return payload

    @_ipc_handler("SKIN_UPDATE_FAILED")
    async def microsoft_upload_skin(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        上传皮肤到正版(Microsoft)账户。

        :param body: 经过边界校验的 IPC 请求数据
        """
        png_bytes = self._decode_skin_image(body.get("image"))
        if png_bytes is None:
            return {"success": False, "message": "无效的皮肤图片数据", "errorCode": "INVALID_SKIN_IMAGE"}
        account = await to_thread.run_sync(
            self.accounts.upload_skin,
            body.get("account_id"),
            body.get("variant"),
            png_bytes,
        )
        return {"success": True, "data": account}

    @_ipc_handler("SKIN_UPDATE_FAILED")
    async def microsoft_reset_skin(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        将正版账户皮肤重置为默认。

        :param body: 经过边界校验的 IPC 请求数据
        """
        account = await to_thread.run_sync(self.accounts.reset_skin, body.get("account_id"))
        return {"success": True, "data": account}

    @_ipc_handler("SKIN_UPDATE_FAILED")
    async def microsoft_set_cape(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        为正版账户选择已解锁的披风。

        :param body: 经过边界校验的 IPC 请求数据
        """
        account = await to_thread.run_sync(
            self.accounts.set_cape,
            body.get("account_id"),
            body.get("cape_id"),
        )
        return {"success": True, "data": account}

    @_ipc_handler("SKIN_UPDATE_FAILED")
    async def microsoft_reset_cape(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        取消正版账户当前佩戴的披风。

        :param body: 经过边界校验的 IPC 请求数据
        """
        account = await to_thread.run_sync(self.accounts.reset_cape, body.get("account_id"))
        return {"success": True, "data": account}

    async def authlib_servers(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        获取外置登录服务器。

        :param body: 经过边界校验的 IPC 请求数据
        """
        authlib_server_list = []
        for server in self._get_authlib_servers():
            server_url = server["url"]
            hostname = urlsplit(server_url).hostname or server_url
            authlib_server_list.append(
                {"name": hostname, "url": server_url, "email": server["email"], "description": server_url}
            )
        return {"success": True, "data": authlib_server_list}
