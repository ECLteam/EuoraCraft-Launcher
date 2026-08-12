import base64
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from anyio import to_thread
from pydantic import ValidationError
from pytauri_plugins.dialog import DialogExt

from ECL.api.models import (
    AccountTextureRequest,
    MicrosoftCapeRequest,
    WardrobeApplySkinRequest,
    WardrobeImportRequest,
    WardrobeItemRequest,
    WardrobeUpdateRequest,
)
from ECL.services.wardrobe import MAX_TEXTURE_BYTES, WardrobeError
from ECL.utils import atomic_write_bytes

from .bridge import _FrontendState, _ipc_handler, _normalize_image_url


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

    @_ipc_handler("ACCOUNT_TEXTURE_FAILED")
    async def accounts_texture_urls(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        返回账户完整皮肤与当前披风地址，图片裁切和渲染由前端完成。

        :param body: 包含账户稳定标识的 IPC 请求数据
        :return: 可用的皮肤和披风 URL
        """
        try:
            request = AccountTextureRequest.model_validate(body)
        except ValidationError as exc:
            return self._invalid_request(exc)
        textures = await to_thread.run_sync(self.accounts.texture_urls, request.account_id)
        return {"success": True, "data": textures}

    async def wardrobe_list(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        返回本地衣柜元数据，不包含纹理字节或本地绝对路径。

        :param body: 空 IPC 请求数据
        :return: 按最近更新时间排序的衣柜条目
        """
        return {"success": True, "data": self.wardrobe.list_items()}

    @_ipc_handler("WARDROBE_SYNC_FAILED")
    async def wardrobe_sync_account_skin(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        将账户当前穿戴的远程皮肤下载到本地衣柜，重复纹理沿用已有条目。

        :param body: 包含账户稳定标识的 IPC 请求数据
        :return: 本地衣柜条目与哈希去重标记
        """
        try:
            request = AccountTextureRequest.model_validate(body)
        except ValidationError as exc:
            return self._invalid_request(exc)
        account_data = await to_thread.run_sync(self.accounts.list_accounts)
        account = next(
            (candidate for candidate in account_data["accounts"] if candidate["id"] == request.account_id),
            None,
        )
        if account is None or account.get("type") == "offline":
            raise WardrobeError("该账户没有可同步的在线皮肤", "WARDROBE_SKIN_UNAVAILABLE")
        textures = await to_thread.run_sync(self.accounts.texture_urls, request.account_id)
        skin_url = _normalize_image_url(textures.get("skinUrl"))
        if skin_url is None:
            raise WardrobeError("该账户没有可同步的在线皮肤", "WARDROBE_SKIN_UNAVAILABLE")
        texture = await to_thread.run_sync(self._download_account_skin, skin_url)
        item, deduplicated = await to_thread.run_sync(
            self.wardrobe.import_bytes,
            texture,
            "skin",
            f"{account.get('alias') or 'Minecraft'} 当前皮肤",
            textures.get("skinModel") or "classic",
        )
        self.logger.info(
            "账户当前皮肤已同步到衣柜: account=%s, item=%s, deduplicated=%s",
            request.account_id,
            item["id"],
            deduplicated,
        )
        return {"success": True, "data": {"item": item, "deduplicated": deduplicated}}

    def _download_account_skin(self, url: str) -> bytes:
        """
        使用应用共享客户端流式下载账户皮肤，在写入衣柜前限制响应大小。

        :param url: 由账户服务返回并完成 HTTP(S) 格式校验的皮肤地址
        :return: 不超过衣柜上限的 PNG 原始字节
        """
        data = bytearray()
        with self.http.stream("GET", url) as response:
            response.raise_for_status()
            for chunk in response.iter_bytes(64 * 1024):
                data.extend(chunk)
                if len(data) > MAX_TEXTURE_BYTES:
                    raise WardrobeError("账户皮肤超过 5 MiB", "WARDROBE_FILE_TOO_LARGE")
        return bytes(data)

    @_ipc_handler("WARDROBE_IMPORT_FAILED")
    async def wardrobe_import(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        将用户选择的 PNG 复制到启动器衣柜，并返回去重结果。

        :param body: 包含源路径、素材类型和可选模型的 IPC 请求数据
        :return: 导入后的条目与去重标记
        """
        try:
            request = WardrobeImportRequest.model_validate(body)
        except ValidationError as exc:
            return self._invalid_request(exc)
        item, deduplicated = await to_thread.run_sync(
            self.wardrobe.import_file,
            request.path,
            request.kind.value,
            request.name,
            request.model.value if request.model else None,
        )
        return {"success": True, "data": {"item": item, "deduplicated": deduplicated}}

    @_ipc_handler("WARDROBE_UPDATE_FAILED")
    async def wardrobe_update(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        修改衣柜条目的名称或皮肤模型，不转换原始图片。

        :param body: 包含条目标识及待修改字段的 IPC 请求数据
        :return: 更新后的衣柜条目
        """
        try:
            request = WardrobeUpdateRequest.model_validate(body)
        except ValidationError as exc:
            return self._invalid_request(exc)
        item = await to_thread.run_sync(
            self.wardrobe.update_item,
            request.item_id,
            request.name,
            request.model.value if request.model else None,
            request.favorite,
        )
        return {"success": True, "data": item}

    @_ipc_handler("WARDROBE_DELETE_FAILED")
    async def wardrobe_delete(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        删除本地收藏；已经上传到外部账户的皮肤不受影响。

        :param body: 包含衣柜条目标识的 IPC 请求数据
        """
        try:
            request = WardrobeItemRequest.model_validate(body)
        except ValidationError as exc:
            return self._invalid_request(exc)
        await to_thread.run_sync(self.wardrobe.delete_item, request.item_id)
        return {"success": True}

    @_ipc_handler("WARDROBE_TEXTURE_FAILED")
    async def wardrobe_texture(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        将衣柜中的小型 PNG 原样编码为 Data URL 供 WebView 渲染。

        :param body: 包含衣柜条目标识的 IPC 请求数据
        :return: PNG Data URL 和 MIME 类型
        """
        try:
            request = WardrobeItemRequest.model_validate(body)
        except ValidationError as exc:
            return self._invalid_request(exc)
        _, texture = await to_thread.run_sync(self.wardrobe.read_texture, request.item_id)
        encoded = base64.b64encode(texture).decode("ascii")
        return {"success": True, "data": {"dataUrl": f"data:image/png;base64,{encoded}", "mime": "image/png"}}

    @_ipc_handler("WARDROBE_EXPORT_FAILED")
    async def wardrobe_export(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        通过原生保存对话框导出衣柜中的原始 PNG，不经过前端 Base64 往返传输。

        :param body: 包含衣柜条目标识的 IPC 请求数据
        :return: 用户选择的保存路径；取消时路径为空
        """
        try:
            request = WardrobeItemRequest.model_validate(body)
        except ValidationError as exc:
            return self._invalid_request(exc)
        if self._webview is None:
            raise WardrobeError("窗口尚未就绪", "WEBVIEW_NOT_READY")
        item, texture = await to_thread.run_sync(self.wardrobe.read_texture, request.item_id)
        safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", item["name"]).strip(" .")[:80] or "skin"
        picked = await to_thread.run_sync(
            lambda: DialogExt.file(self._webview).blocking_save_file(
                add_filter=("PNG 图片", ["png"]),
                set_file_name=f"{safe_name}.png",
                set_title="另存为皮肤",
            )
        )
        if not picked:
            return {"success": True, "data": {"path": None}}
        target = Path(str(picked))
        await to_thread.run_sync(atomic_write_bytes, target, texture)
        self.logger.info("衣柜纹理已导出: item=%s, kind=%s", item["id"], item["kind"])
        return {"success": True, "data": {"path": str(target)}}

    @_ipc_handler("SKIN_UPDATE_FAILED")
    async def wardrobe_apply_skin(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        将衣柜中的标准 64×64 皮肤上传到指定 Microsoft 账户。

        :param body: 包含衣柜条目和目标账户标识的 IPC 请求数据
        :return: 上传后刷新得到的账户资料
        """
        try:
            request = WardrobeApplySkinRequest.model_validate(body)
        except ValidationError as exc:
            return self._invalid_request(exc)
        item, texture = await to_thread.run_sync(self.wardrobe.read_texture, request.item_id)
        if item["kind"] != "skin" or (item["width"], item["height"]) != (64, 64):
            return {
                "success": False,
                "message": "只有标准 64×64 皮肤可以上传到 Microsoft",
                "errorCode": "WARDROBE_UNSUPPORTED_UPLOAD",
            }
        account = await to_thread.run_sync(
            self.accounts.upload_skin,
            request.account_id,
            item["model"] or "classic",
            texture,
        )
        self.logger.info("衣柜皮肤已上传: item=%s, model=%s", item["id"], item["model"])
        return {"success": True, "data": account}

    @_ipc_handler("SKIN_UPDATE_FAILED")
    async def microsoft_reset_skin(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        将正版账户皮肤重置为默认。

        :param body: 经过边界校验的 IPC 请求数据
        """
        try:
            request = AccountTextureRequest.model_validate(body)
        except ValidationError as exc:
            return self._invalid_request(exc)
        account = await to_thread.run_sync(self.accounts.reset_skin, request.account_id)
        return {"success": True, "data": account}

    @_ipc_handler("SKIN_UPDATE_FAILED")
    async def microsoft_set_cape(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        为正版账户选择已解锁的披风。

        :param body: 经过边界校验的 IPC 请求数据
        """
        try:
            request = MicrosoftCapeRequest.model_validate(body)
        except ValidationError as exc:
            return self._invalid_request(exc)
        account = await to_thread.run_sync(self.accounts.set_cape, request.account_id, request.cape_id)
        return {"success": True, "data": account}

    @_ipc_handler("SKIN_UPDATE_FAILED")
    async def microsoft_reset_cape(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        取消正版账户当前佩戴的披风。

        :param body: 经过边界校验的 IPC 请求数据
        """
        try:
            request = AccountTextureRequest.model_validate(body)
        except ValidationError as exc:
            return self._invalid_request(exc)
        account = await to_thread.run_sync(self.accounts.reset_cape, request.account_id)
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
