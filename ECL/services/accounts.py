from __future__ import annotations

import json
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from threading import Event, RLock, Thread
from time import perf_counter
from typing import Any
from uuid import UUID

import httpx

from ECL.common import MICROSOFT_CLIENT_ID
from ECL.events import EventBus
from ECL.game import MicrosoftAuthManager, name_to_uuid
from ECL.services.authlib import AuthlibAccountManager, AuthlibError
from ECL.utils import get_logger

MICROSOFT_LOGIN_POLL_INTERVAL_SECONDS = 2


class _ProgressMinecraftClient:
    """
    为 Minecraft 账户客户端补充登录阶段进度通知。

    :param client: 实际执行令牌和档案请求的 Minecraft 客户端
    :param on_progress: 登录阶段发生变化时调用的回调函数
    """

    def __init__(self, client: Any, on_progress: Callable[[str], None]) -> None:
        self.client = client
        self.on_progress = on_progress
        # 只有设备代码登录期间才发送阶段事件，日常皮肤操作不应污染登录状态。
        self.login_active = False

    def get_minecraft_token(self, token: str):
        """
        获取 Minecraft 访问令牌并报告授权阶段。

        :param token: Xbox XSTS 令牌
        :return: 底层客户端返回的 Minecraft 令牌响应
        """
        if self.login_active:
            self.on_progress("authorization_confirmed")
        result = self.client.get_minecraft_token(token)
        if self.login_active:
            self.on_progress("minecraft_token")
        return result

    def get_profile(self, token: str):
        """
        获取 Minecraft 档案并报告保存阶段。

        :param token: Minecraft 访问令牌
        :return: 底层客户端返回的玩家档案
        """
        if self.login_active:
            self.on_progress("profile")
        result = self.client.get_profile(token)
        if self.login_active:
            self.on_progress("saving")
        return result

    def upload_skin(self, token: str, variant: str, image: bytes):
        return self.client.upload_skin(token, variant, image)

    def reset_skin(self, token: str):
        return self.client.reset_skin(token)

    def set_cape(self, token: str, cape_id: str):
        return self.client.set_cape(token, cape_id)

    def reset_cape(self, token: str):
        return self.client.reset_cape(token)

    def set_profile_name(self, token: str, name: str):
        return self.client.set_profile_name(token, name)

    def close(self) -> None:
        self.client.close()


class LauncherMicrosoftAccountManager(MicrosoftAuthManager):
    """
    将底层 Microsoft 认证流程适配为启动器账户管理流程。

    :param client_id: Microsoft OAuth 应用客户端 ID
    :param on_device_code: 收到设备代码后调用的回调函数
    :param on_progress: 登录阶段发生变化时调用的回调函数
    :param cache_path: Microsoft 令牌缓存目录
    """

    def __init__(
        self,
        client_id: str,
        on_device_code: Callable[[dict[str, str]], None],
        on_progress: Callable[[str], None],
        cache_path: Path | str | None = None,
        verify: bool = True,
    ) -> None:
        super().__init__(client_id, cache_path, on_device_code, verify=verify)
        self._progress_client = _ProgressMinecraftClient(self.minecraft_client, on_progress)
        self.minecraft_client = self._progress_client

    def add_microsoft_account(self) -> str:
        """
        完成 Microsoft 登录并保存可用于启动游戏的账户。

        :return: 新增账户的稳定标识
        """
        self._progress_client.login_active = True
        try:
            return super().add_microsoft_account()
        finally:
            self._progress_client.login_active = False


class AccountError(Exception):
    """
    表示可安全转换为稳定 IPC 错误码的账户操作失败。

    :param message: 面向用户的错误说明
    :param error_code: 供前端识别的稳定错误码
    """

    def __init__(self, message: str, error_code: str = "ACCOUNT_ERROR"):
        super().__init__(message)
        self.error_code = error_code


class AccountManager:
    """
    聚合离线、Microsoft 与 Authlib 账户，并维护当前账户选择。

    Microsoft 设备码登录的线程状态也由本类统一拥有，确保同一时间只有一个登录流程。
    Authlib 协议和头像渲染保留独立实现文件，因为它们具有独立的协议与图像处理边界。

    :param data_path: 启动器数据目录
    :param microsoft_manager: 测试或定制环境提供的 Microsoft 认证管理器
    :param microsoft_client_id: Microsoft OAuth 客户端 ID
    :param authlib_manager: 测试或定制环境提供的 Authlib 管理器
    :param event_bus: 当前应用上下文拥有的事件总线
    """

    def __init__(
        self,
        data_path: Path | str,
        microsoft_manager: MicrosoftAuthManager | None = None,
        microsoft_client_id: str | None = None,
        authlib_manager: AuthlibAccountManager | None = None,
        event_bus: EventBus | None = None,
        disable_ssl_verify: bool = False,
    ):
        """
        加载持久化账户，并连接两种在线认证提供者。

        :param data_path: 启动器数据目录
        :param microsoft_manager: 可选的 Microsoft 认证管理器
        :param microsoft_client_id: Microsoft OAuth 客户端 ID
        :param authlib_manager: 可选的 Authlib 账户管理器
        :param event_bus: 当前应用上下文拥有的事件总线
        :param disable_ssl_verify: 是否关闭 Microsoft 登录服务器的 SSL 证书校验
        """
        self.logger = get_logger("AccountManager")
        self.events = event_bus or EventBus()
        self.data_path = Path(data_path) / "accounts"
        self.data_path.mkdir(parents=True, exist_ok=True)
        self.state_path = self.data_path / "accounts.json"
        # 持久化状态和登录线程会被 IPC 轮询并发访问，统一使用一把可重入锁保护。
        self._lock = RLock()
        # 登录事件表示设备码流程已经推进；取消事件用于请求后台线程尽快终止。
        self._login_event = Event()
        self._login_cancel_event = Event()
        self._login_thread: Thread | None = None
        # 登录流只在需要向前端展示设备码时存在，状态字典则始终可供轮询。
        self._login_flow: dict[str, Any] | None = None
        self._login_state: dict[str, Any] = {"status": "idle"}
        # 离线账户和当前选择由本类持久化；在线账户数据由对应提供者保存。
        self._offline_accounts: dict[str, dict[str, Any]] = {}
        self._current_account_id: str | None = None
        # 账户偏好（收藏/置顶）独立存储，覆盖离线、微软与外置账户。
        self._account_prefs: dict[str, dict[str, bool]] = {}
        phase_started = perf_counter()
        self._load_state()
        self.logger.debug("账户聚合状态读取完成，duration=%.2fs", perf_counter() - phase_started)

        manager_was_provided = microsoft_manager is not None
        effective_client_id = (microsoft_client_id or MICROSOFT_CLIENT_ID).strip()
        self._microsoft_login_available = manager_was_provided or bool(effective_client_id)
        if microsoft_manager is None:
            phase_started = perf_counter()
            self.logger.debug("正在创建 Microsoft 认证管理器")
            microsoft_manager = LauncherMicrosoftAccountManager(
                client_id=effective_client_id,
                on_device_code=self._on_device_code,
                on_progress=self._on_microsoft_progress,
                verify=not disable_ssl_verify,
            )
            self.logger.debug("Microsoft 认证管理器已创建，duration=%.2fs", perf_counter() - phase_started)
        else:
            microsoft_manager.on_device_code = self._on_device_code
        self.microsoft_manager = microsoft_manager
        if authlib_manager is None:
            phase_started = perf_counter()
            self.logger.debug("正在创建 Authlib 账户管理器")
            authlib_manager = AuthlibAccountManager()
            self.logger.debug("Authlib 账户管理器已创建，duration=%.2fs", perf_counter() - phase_started)
        self.authlib_manager = authlib_manager
        phase_started = perf_counter()
        self._deduplicate_microsoft_accounts()
        self._ensure_current_account()
        self.logger.debug(
            "账户服务已加载: offline=%d, microsoft=%d, authlib=%d, current_selected=%s, finalize=%.2fs",
            len(self._offline_accounts),
            len(self.microsoft_manager.get_microsoft_accounts()),
            len(self.authlib_manager.list_accounts()),
            self._current_account_id is not None,
            perf_counter() - phase_started,
        )

    def microsoft_login_config(self) -> dict[str, bool]:
        """
        返回微软设备代码登录是否具备有效客户端配置。

        """
        return {
            "available": self._microsoft_login_available,
            "needs_client_id": not self._microsoft_login_available,
        }

    def _load_state(self) -> None:
        if not self.state_path.exists():
            return
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
            offline_accounts = state.get("offline_accounts", {})
            if isinstance(offline_accounts, dict):
                self._offline_accounts = offline_accounts
            current_account_id = state.get("current_account_id")
            if isinstance(current_account_id, str) and current_account_id:
                self._current_account_id = current_account_id
            account_prefs = state.get("account_prefs", {})
            if isinstance(account_prefs, dict):
                self._account_prefs = {
                    str(account_id): flags
                    for account_id, flags in account_prefs.items()
                    if isinstance(flags, dict) and isinstance(account_id, (str, int))
                }
            self.logger.debug(
                "已读取账户聚合状态: offline=%d, current_selected=%s",
                len(self._offline_accounts),
                self._current_account_id is not None,
            )
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            self.logger.warning("读取账号状态失败，将使用空账号列表: %s", exc)

    def _save_state(self) -> None:
        state = {
            "offline_accounts": self._offline_accounts,
            "current_account_id": self._current_account_id,
            "account_prefs": self._account_prefs,
        }
        temporary_path = self.state_path.with_suffix(".json.tmp")
        try:
            serialized = json.dumps(state, ensure_ascii=False, indent=2)
            temporary_path.write_text(serialized, encoding="utf-8")
            temporary_path.replace(self.state_path)
        except (OSError, TypeError, ValueError) as exc:
            temporary_path.unlink(missing_ok=True)
            raise AccountError("保存账号数据失败", "ACCOUNT_SAVE_FAILED") from exc

    @staticmethod
    def _validate_username(username: Any) -> str:
        if not isinstance(username, str):
            raise AccountError("离线用户名不能为空", "INVALID_OFFLINE_USERNAME")
        normalized = username.strip()
        if not normalized:
            raise AccountError("离线用户名不能为空", "INVALID_OFFLINE_USERNAME")
        if len(normalized) > 16 or any(character.isspace() for character in normalized):
            raise AccountError("离线用户名必须为 1 到 16 个不含空格的字符", "INVALID_OFFLINE_USERNAME")
        return normalized

    def _microsoft_account(self, account_id: str, info: dict[str, Any]) -> dict[str, Any]:
        profile = info.get("Profile") or {}
        account = {
            "id": account_id,
            "alias": profile.get("name") or info.get("Email") or account_id,
            "type": "microsoft",
            "email": info.get("Email") or "",
            "uuid": profile.get("id") or "",
            "isCurrent": account_id == self._current_account_id,
        }

        skins = profile.get("skins") or []
        if skins and isinstance(skins[0], dict):
            skin_url = skins[0].get("url")
            if isinstance(skin_url, str) and skin_url:
                account["skinUrl"] = skin_url

        capes = profile.get("capes") or []
        if isinstance(capes, list):
            valid_capes = []
            for cape in capes:
                if isinstance(cape, dict) and cape.get("id"):
                    valid_capes.append(
                        {
                            "id": str(cape.get("id")),
                            "name": str(cape.get("alias") or cape.get("name") or cape.get("id")),
                            "state": str(cape.get("state") or ""),
                            "url": str(cape.get("url") or ""),
                        }
                    )
            if valid_capes:
                account["capes"] = valid_capes

        return account

    @staticmethod
    def _microsoft_identity(info: dict[str, Any]) -> str | None:
        profile = info.get("Profile") or {}
        account_uuid = profile.get("id")
        if isinstance(account_uuid, str) and account_uuid.strip():
            return f"uuid:{account_uuid.replace('-', '').strip().lower()}"

        email = info.get("Email")
        if isinstance(email, str) and email.strip():
            return f"email:{email.strip().casefold()}"
        return None

    def _authlib_account(self, account_id: str, info: dict[str, Any]) -> dict[str, Any]:
        profiles = info.get("Profiles") or {}
        profile = profiles.get("selectedProfile") or {}
        account = {
            "id": account_id,
            "alias": profile.get("name") or "请选择角色",
            "type": "authlib",
            "email": info.get("Username") or "",
            "uuid": profile.get("id") or "",
            "auth_server": info.get("YggdrasilAPI") or "",
            "isCurrent": account_id == self._current_account_id,
        }
        available_profiles = profiles.get("availableProfiles") or []
        if not profile and isinstance(available_profiles, list):
            account["profile_selection_required"] = True
            account["available_profiles"] = deepcopy(available_profiles)
        return account

    def _deduplicate_microsoft_accounts(self, preferred_id: str | None = None) -> str | None:
        accounts = self.microsoft_manager.get_microsoft_accounts()
        canonical_by_identity: dict[str, str] = {}
        replacements: dict[str, str] = {}

        for account_id, info in accounts.items():
            identity = self._microsoft_identity(info)
            if identity is None:
                continue

            existing_id = canonical_by_identity.get(identity)
            if existing_id is None:
                canonical_by_identity[identity] = account_id
                continue

            candidate_ids = {existing_id, account_id}
            if preferred_id in candidate_ids:
                canonical_id = preferred_id
            elif self._current_account_id in candidate_ids:
                canonical_id = self._current_account_id
            else:
                canonical_id = account_id

            duplicate_id = existing_id if canonical_id == account_id else account_id
            canonical_by_identity[identity] = canonical_id
            replacements[duplicate_id] = canonical_id

        for duplicate_id in replacements:
            self.microsoft_manager.del_microsoft_account(duplicate_id)

        def resolve_account_id(account_id: str | None) -> str | None:
            while account_id in replacements:
                account_id = replacements[account_id]
            return account_id

        current_account_id = resolve_account_id(self._current_account_id)
        if current_account_id != self._current_account_id:
            self._current_account_id = current_account_id
            if self.state_path.exists():
                self._save_state()

        if replacements:
            self.logger.info("已合并 %s 个重复 Microsoft 账户", len(replacements))
        return resolve_account_id(preferred_id)

    def _all_accounts(self) -> list[dict[str, Any]]:
        offline_accounts = [deepcopy(account) for account in self._offline_accounts.values()]
        microsoft_accounts = [
            self._microsoft_account(account_id, info)
            for account_id, info in self.microsoft_manager.get_microsoft_accounts().items()
        ]
        authlib_accounts = [
            self._authlib_account(account_id, info) for account_id, info in self.authlib_manager.list_accounts().items()
        ]
        accounts = offline_accounts + microsoft_accounts + authlib_accounts
        for account in accounts:
            account["isCurrent"] = account["id"] == self._current_account_id
            self._apply_account_prefs(account)
        # 置顶账户优先，其次是收藏账户，组内保持原有顺序。
        accounts.sort(key=lambda account: (not account.get("pinned", False), not account.get("favorite", False)))
        return accounts

    def _ensure_current_account(self) -> None:
        with self._lock:
            accounts = self._all_accounts()
            account_ids = {account["id"] for account in accounts}
            if self._current_account_id in account_ids:
                return
            self._current_account_id = accounts[0]["id"] if accounts else None
            if accounts or self.state_path.exists():
                self._save_state()


    def _apply_account_prefs(self, account: dict[str, Any]) -> None:
        """
        在账户数据中注入收藏/置顶标记。

        :param account: 单个账户字典，会被原地修改。
        """
        prefs = self._account_prefs.get(account["id"], {})
        account["favorite"] = bool(prefs.get("favorite"))
        account["pinned"] = bool(prefs.get("pinned"))

    def set_favorite(self, account_id: Any, favorite: bool) -> dict[str, Any]:
        """
        设置账户是否收藏。

        :param account_id: 账户的稳定标识
        :param favorite: 是否收藏
        :returns: 刷新后的完整账户列表
        """
        return self._set_account_flag(account_id, "favorite", favorite)

    def set_pinned(self, account_id: Any, pinned: bool) -> dict[str, Any]:
        """
        设置账户是否置顶。

        :param account_id: 账户的稳定标识
        :param pinned: 是否置顶
        :returns: 刷新后的完整账户列表
        """
        return self._set_account_flag(account_id, "pinned", pinned)

    def _set_account_flag(self, account_id: Any, flag: str, value: bool) -> dict[str, Any]:
        """
        设置账户的布尔标记（收藏/置顶）并持久化。

        :param account_id: 账户的稳定标识
        :param flag: 标记名（"favorite" 或 "pinned"）
        :param value: 标记值
        :returns: 刷新后的完整账户列表
        """
        if not isinstance(account_id, str) or not account_id:
            raise AccountError("账号 ID 不能为空", "INVALID_ACCOUNT_ID")
        self._validate_account_prefs(account_id)
        with self._lock:
            prefs = self._account_prefs.setdefault(account_id, {})
            prefs[flag] = bool(value)
            self._save_state()
        self._emit_changed()
        return self.list_accounts()

    def _validate_account_prefs(self, account_id: str) -> None:
        """
        验证账户是否存在，不存在时抛出 ``AccountError``。

        :param account_id: 账户的稳定标识
        """
        with self._lock:
            account_ids = {account["id"] for account in self._all_accounts()}
        if account_id not in account_ids:
            raise AccountError("账号不存在，无法设置偏好", "ACCOUNT_NOT_FOUND")

    def list_accounts(self) -> dict[str, Any]:
        """
        返回所有账户以及当前账户标识。

        """
        with self._lock:
            accounts = self._all_accounts()
            current = next((account for account in accounts if account["isCurrent"]), None)
            return {"accounts": accounts, "current": current}

    def current_account(self) -> dict[str, Any] | None:
        """
        获取当前账户。

        """
        return self.list_accounts()["current"]

    def get_launch_credentials(self) -> dict[str, str]:
        """
        返回启动游戏所需的当前账户凭据。

        """
        with self._lock:
            current = next(
                (account for account in self._all_accounts() if account["id"] == self._current_account_id),
                None,
            )
        if current is None:
            raise AccountError("请先选择一个游戏账户", "ACCOUNT_REQUIRED")

        account_uuid = str(current.get("uuid") or "").replace("-", "")
        player_name = str(current.get("alias") or "").strip()
        if not account_uuid or not player_name:
            raise AccountError("当前账户资料不完整", "ACCOUNT_PROFILE_INVALID")
        if current.get("type") == "offline":
            return {
                "player_name": player_name,
                "uuid": account_uuid,
                "user_type": "legacy",
                "access_token": "None",
            }
        if current.get("type") == "microsoft":
            token = self.microsoft_manager.get_minecraft_token(current["id"])
            return {
                "player_name": player_name,
                "uuid": account_uuid,
                "user_type": "msa",
                "access_token": token,
            }
        if current.get("type") == "authlib":
            try:
                token = self.authlib_manager.get_token(current["id"])
            except (AuthlibError, httpx.HTTPError, OSError, KeyError, TypeError, ValueError) as exc:
                raise AccountError(f"刷新外置登录令牌失败: {exc}", "AUTHLIB_TOKEN_FAILED") from exc
            return {
                "player_name": player_name,
                "uuid": account_uuid,
                "user_type": "yggdrasil",
                "access_token": token["AccessToken"],
                "auth_server": token["YggdrasilAPI"],
            }
        raise AccountError("当前账户类型暂不支持启动游戏", "ACCOUNT_TYPE_UNSUPPORTED")

    @staticmethod
    def _resolve_offline_uuid(username: str, custom_uuid: Any = None) -> str:
        if custom_uuid is None or custom_uuid == "":
            return str(name_to_uuid(username))
        if not isinstance(custom_uuid, str):
            raise AccountError("自定义 UUID 必须是字符串", "INVALID_OFFLINE_UUID")

        value = custom_uuid.strip()
        compact_value = value.replace("-", "")
        if len(compact_value) != 32 or any(character not in "0123456789abcdefABCDEF" for character in compact_value):
            raise AccountError("自定义 UUID 格式无效", "INVALID_OFFLINE_UUID")
        try:
            return str(UUID(value))
        except ValueError as exc:
            raise AccountError("自定义 UUID 格式无效", "INVALID_OFFLINE_UUID") from exc

    def add_offline(self, username: Any, custom_uuid: Any = None) -> dict[str, Any]:
        """
        添加离线账户。

        :param username: 登录或离线账户用户名
        :param custom_uuid: 可选的离线账户 UUID
        """
        normalized = self._validate_username(username)
        account_uuid = self._resolve_offline_uuid(normalized, custom_uuid)
        account_id = f"offline:{account_uuid}"
        with self._lock:
            account = {
                "id": account_id,
                "alias": normalized,
                "type": "offline",
                "uuid": account_uuid,
                "isCurrent": True,
            }
            self._offline_accounts[account_id] = account
            self._current_account_id = account_id
            self._save_state()
        self._emit_changed()
        return deepcopy(account)

    def add_authlib(self, server_url: Any, username: Any, password: Any) -> dict[str, Any]:
        """
        添加外置登录账户。

        :param server_url: Authlib 认证服务器地址
        :param username: 登录或离线账户用户名
        :param password: 仅用于本次认证且不会写入日志的密码
        """
        if not isinstance(server_url, str) or not server_url.strip():
            raise AccountError("外置登录服务器不能为空", "INVALID_AUTHLIB_SERVER")
        if not isinstance(username, str) or not username.strip():
            raise AccountError("外置登录用户名不能为空", "INVALID_AUTHLIB_USERNAME")
        if not isinstance(password, str) or not password:
            raise AccountError("外置登录密码不能为空", "INVALID_AUTHLIB_PASSWORD")
        try:
            account_id, info = self.authlib_manager.add_account(
                server_url.strip(),
                username.strip(),
                password,
            )
        except httpx.HTTPStatusError as exc:
            try:
                error = exc.response.json()
            except json.JSONDecodeError:
                error = {}

            message = None
            if isinstance(error, dict):
                message = error.get("errorMessage") or error.get("error")
            if not isinstance(message, str) or not message.strip():
                message = f"认证服务器返回 {exc.response.status_code} {exc.response.reason_phrase}"
            raise AccountError(f"外置登录失败: {message.strip()}", "AUTHLIB_LOGIN_FAILED") from exc
        except (AuthlibError, httpx.RequestError, OSError, KeyError, TypeError, ValueError) as exc:
            raise AccountError(f"外置登录失败: {exc}", "AUTHLIB_LOGIN_FAILED") from exc
        with self._lock:
            selection_required = not bool((info.get("Profiles") or {}).get("selectedProfile"))
            if not selection_required:
                self._current_account_id = account_id
                self._save_state()
            account = self._authlib_account(account_id, info)
        if not account.get("profile_selection_required"):
            self._emit_changed()
        return account

    def select_authlib_profile(self, account_id: Any, profile_id: Any) -> dict[str, Any]:
        """
        完成多角色外置登录，只保存用户选中的一个角色。

        :param account_id: 账户的稳定标识
        :param profile_id: Authlib 玩家档案标识
        """
        if not isinstance(account_id, str) or not account_id:
            raise AccountError("账号 ID 不能为空", "INVALID_ACCOUNT_ID")
        if not isinstance(profile_id, str) or not profile_id:
            raise AccountError("请选择要登录的角色", "INVALID_AUTHLIB_PROFILE")
        try:
            selected_account_id, info = self.authlib_manager.select_profile(account_id, profile_id)
        except httpx.HTTPStatusError as exc:
            try:
                error = exc.response.json()
            except json.JSONDecodeError:
                error = {}
            message = error.get("errorMessage") if isinstance(error, dict) else None
            if not isinstance(message, str) or not message.strip():
                message = f"认证服务器返回 {exc.response.status_code} {exc.response.reason_phrase}"
            raise AccountError(f"选择外置登录角色失败: {message.strip()}", "AUTHLIB_PROFILE_SELECT_FAILED") from exc
        except (AuthlibError, httpx.RequestError, OSError, KeyError, TypeError, ValueError) as exc:
            raise AccountError(f"选择外置登录角色失败: {exc}", "AUTHLIB_PROFILE_SELECT_FAILED") from exc
        with self._lock:
            self._current_account_id = selected_account_id
            self._save_state()
            account = self._authlib_account(selected_account_id, info)
        self._emit_changed()
        return account

    def resolve_authlib_server(self, server_url: Any) -> str:
        """
        返回外置登录地址对应的 Yggdrasil API 地址。

        :param server_url: Authlib 认证服务器地址
        """
        if not isinstance(server_url, str) or not server_url.strip():
            raise AccountError("外置登录服务器不能为空", "INVALID_AUTHLIB_SERVER")
        try:
            return self.authlib_manager.resolve_server(server_url.strip())
        except httpx.HTTPError as exc:
            raise AccountError(f"无法识别外置登录服务器: {exc}", "AUTHLIB_SERVER_RESOLVE_FAILED") from exc

    def switch_account(self, account_id: Any) -> None:
        """
        切换当前账户；账户不存在时抛出 ``AccountError``。

        :param account_id: 账户的稳定标识
        """
        if not isinstance(account_id, str) or not account_id:
            raise AccountError("账号 ID 不能为空", "INVALID_ACCOUNT_ID")
        with self._lock:
            account_ids = {account["id"] for account in self._all_accounts()}
            if account_id not in account_ids:
                raise AccountError("账号不存在", "ACCOUNT_NOT_FOUND")
            self._current_account_id = account_id
            self._save_state()
        self._emit_changed()

    def remove_account(self, account_id: Any) -> None:
        """
        移除账户并自动选择剩余账户。

        :param account_id: 账户的稳定标识
        """
        if not isinstance(account_id, str) or not account_id:
            raise AccountError("账号 ID 不能为空", "INVALID_ACCOUNT_ID")
        with self._lock:
            if account_id in self._offline_accounts:
                self._offline_accounts.pop(account_id)
            elif account_id in self.microsoft_manager.get_microsoft_accounts():
                self.microsoft_manager.del_microsoft_account(account_id)
            elif account_id in self.authlib_manager.list_accounts():
                self.authlib_manager.delete_account(account_id)
            else:
                raise AccountError("账号不存在", "ACCOUNT_NOT_FOUND")

            if self._current_account_id == account_id:
                remaining_accounts = self._all_accounts()
                self._current_account_id = remaining_accounts[0]["id"] if remaining_accounts else None
            self._account_prefs.pop(account_id, None)
            self._save_state()
        self._emit_changed()

    def refresh_account(self, account_id: Any) -> dict[str, Any]:
        """
        刷新账户信息。

        :param account_id: 账户的稳定标识
        """
        if not isinstance(account_id, str) or not account_id:
            raise AccountError("账号 ID 不能为空", "INVALID_ACCOUNT_ID")
        with self._lock:
            if account_id in self._offline_accounts:
                account = deepcopy(self._offline_accounts[account_id])
            elif account_id in self.microsoft_manager.get_microsoft_accounts():
                self.microsoft_manager.refresh_profile(account_id)
                info = self.microsoft_manager.get_microsoft_accounts()[account_id]
                account = self._microsoft_account(account_id, info)
            elif account_id in self.authlib_manager.list_accounts():
                info = self.authlib_manager.refresh_account(account_id)
                account = self._authlib_account(account_id, info)
            else:
                raise AccountError("账号不存在", "ACCOUNT_NOT_FOUND")
        self._emit_changed()
        return account

    def texture_urls(self, account_id: str) -> dict[str, str]:
        """
        返回账户完整皮肤与当前披风的远程纹理地址，供前端统一渲染。

        离线账户没有远程材质；Microsoft 直接使用缓存档案，Authlib 只解析会话服务器
        返回的材质元数据，不在后端下载图片。

        :param account_id: 账户的稳定标识
        :return: 可用的 ``skinUrl``、``skinModel`` 与 ``capeUrl``；离线或无材质时返回空字典
        """
        if not isinstance(account_id, str) or not account_id:
            raise AccountError("账号 ID 不能为空", "INVALID_ACCOUNT_ID")
        with self._lock:
            microsoft = self.microsoft_manager.get_microsoft_accounts().get(account_id)
            if microsoft is not None:
                profile = microsoft.get("Profile") or {}
                result: dict[str, str] = {}
                skins = profile.get("skins") or []
                if skins and isinstance(skins[0], dict) and isinstance(skins[0].get("url"), str):
                    result["skinUrl"] = skins[0]["url"]
                    variant = str(skins[0].get("variant") or "classic").lower()
                    result["skinModel"] = "slim" if variant == "slim" else "classic"
                active_cape = next(
                    (
                        cape
                        for cape in profile.get("capes") or []
                        if isinstance(cape, dict) and str(cape.get("state") or "").upper() == "ACTIVE"
                    ),
                    None,
                )
                if active_cape and isinstance(active_cape.get("url"), str):
                    result["capeUrl"] = active_cape["url"]
                return result
            if account_id in self._offline_accounts:
                return {}
            is_authlib = account_id in self.authlib_manager.list_accounts()
        if is_authlib:
            return self.authlib_manager.get_texture_urls(account_id)
        raise AccountError("账号不存在", "ACCOUNT_NOT_FOUND")

    def _require_microsoft_account(self, account_id: Any) -> None:
        """
        校验 account_id 是否为正版(Microsoft)账户。

        :param account_id: 账户的稳定标识
        """
        if not isinstance(account_id, str) or not account_id:
            raise AccountError("账号 ID 不能为空", "INVALID_ACCOUNT_ID")
        if account_id not in self.microsoft_manager.get_microsoft_accounts():
            raise AccountError("账号不存在或不是正版账户", "ACCOUNT_NOT_FOUND")

    def upload_skin(self, account_id: Any, variant: Any, image: bytes) -> dict[str, Any]:
        """
        上传皮肤到 Mojang 服务器并刷新账户信息。

        :param account_id: 账户的稳定标识
        :param variant: Minecraft 皮肤模型类型
        :param image: 需要上传或保存的图像数据
        """
        self._require_microsoft_account(account_id)
        normalized_variant = "slim" if str(variant or "").lower() == "slim" else "classic"
        self.microsoft_manager.upload_skin(account_id, normalized_variant, image)
        return self.refresh_account(account_id)

    def reset_skin(self, account_id: Any) -> dict[str, Any]:
        """
        将正版账户皮肤重置为默认。

        :param account_id: 账户的稳定标识
        """
        self._require_microsoft_account(account_id)
        self.microsoft_manager.reset_skin(account_id)
        return self.refresh_account(account_id)

    def set_cape(self, account_id: Any, cape_id: Any) -> dict[str, Any]:
        """
        为正版账户选择已解锁的披风。

        :param account_id: 账户的稳定标识
        :param cape_id: 需要启用的披风标识
        """
        self._require_microsoft_account(account_id)
        if not isinstance(cape_id, str) or not cape_id.strip():
            raise AccountError("披风 ID 不能为空", "INVALID_CAPE_ID")
        self.microsoft_manager.set_cape(account_id, cape_id.strip())
        return self.refresh_account(account_id)

    def reset_cape(self, account_id: Any) -> dict[str, Any]:
        """
        取消正版账户当前佩戴的披风。

        :param account_id: 账户的稳定标识
        """
        self._require_microsoft_account(account_id)
        self.microsoft_manager.reset_cape(account_id)
        return self.refresh_account(account_id)

    def _on_device_code(self, flow: dict[str, Any]) -> None:
        with self._lock:
            self._login_flow = flow
            if self._login_cancel_event.is_set():
                flow["expires_at"] = 0
                self._login_state = {"status": "cancelled"}
                self._login_event.set()
                return
            flow["interval"] = MICROSOFT_LOGIN_POLL_INTERVAL_SECONDS
            self._login_state = {
                "status": "pending",
                "userCode": flow.get("user_code", ""),
                "verificationUri": flow.get("verification_uri", ""),
                "message": flow.get("message", ""),
                "interval": MICROSOFT_LOGIN_POLL_INTERVAL_SECONDS,
            }
            self._login_event.set()

    def _on_microsoft_progress(self, stage: str) -> None:
        self.logger.debug("Microsoft 登录阶段已更新: %s", stage)
        with self._lock:
            self._login_state = {"status": "progress", "stage": stage}
        self.events.emit(
            "accounts:microsoft_login_status",
            {
                "status": "progress",
                "stage": stage,
                "focus": stage == "authorization_confirmed",
            },
        )

    def _run_microsoft_login(self) -> None:
        frontend_event: dict[str, Any] | None = None
        try:
            account_id = self.microsoft_manager.add_microsoft_account()
            with self._lock:
                account_id = self._deduplicate_microsoft_accounts(preferred_id=account_id) or account_id
                self._current_account_id = account_id
                self._save_state()
                self._login_state = {"status": "ready", "account_id": account_id}
                frontend_event = {"status": "ready"}
        except Exception as exc:
            with self._lock:
                if self._login_cancel_event.is_set():
                    self.logger.info("Microsoft 登录已取消")
                    self._login_state = {"status": "cancelled"}
                else:
                    self.logger.exception("Microsoft 登录失败")
                    self._login_state = {"status": "error", "message": str(exc)}
                    frontend_event = {"status": "error", "message": str(exc)}
        finally:
            with self._lock:
                self._login_flow = None
                self._login_event.set()
        if frontend_event is not None:
            self.events.emit("accounts:microsoft_login_status", frontend_event)

    def start_microsoft_login(self) -> dict[str, Any]:
        """
        开始微软登录。

        """
        if not self._microsoft_login_available:
            raise AccountError(
                "需要配置 MICROSOFT_CLIENT_ID 后才能使用正版登录",
                "MICROSOFT_CLIENT_ID_REQUIRED",
            )
        with self._lock:
            if self._login_thread and self._login_thread.is_alive():
                if self._login_cancel_event.is_set():
                    raise AccountError("Microsoft 登录正在取消，请稍后重试", "MICROSOFT_LOGIN_CANCELLING")
                state = deepcopy(self._login_state)
            elif self._login_state.get("status") == "ready":
                self._login_state = {"status": "idle"}
                self._login_thread = None
                return {"status": "completed"}
            else:
                self._login_state = {"status": "starting"}
                self._login_flow = None
                self._login_cancel_event.clear()
                self._login_event.clear()
                self._login_thread = Thread(target=self._run_microsoft_login, name="MicrosoftLogin", daemon=True)
                self._login_thread.start()
                self.logger.debug("Microsoft 设备码登录线程已启动")
                state = deepcopy(self._login_state)

        if state.get("status") == "starting":
            self._login_event.wait(timeout=15)
            with self._lock:
                state = deepcopy(self._login_state)

        if state.get("status") == "error":
            raise AccountError(state.get("message") or "Microsoft 登录启动失败", "MICROSOFT_LOGIN_FAILED")
        if state.get("status") == "cancelled":
            raise AccountError("Microsoft 登录已取消", "MICROSOFT_LOGIN_CANCELLED")
        if state.get("status") == "starting":
            self.cancel_microsoft_login()
            raise AccountError("获取 Microsoft 设备代码超时，请重试", "MICROSOFT_LOGIN_TIMEOUT")
        if state.get("status") == "ready":
            return {"status": "completed"}
        if state.get("status") == "progress":
            return {"status": "progress", "stage": state.get("stage")}
        return {
            "status": "pending",
            "userCode": state.get("userCode", ""),
            "verificationUri": state.get("verificationUri", ""),
            "message": state.get("message", ""),
            "interval": state.get("interval", 5),
        }

    def poll_microsoft_login(self) -> dict[str, Any]:
        """
        获取微软登录状态。

        """
        with self._lock:
            state = deepcopy(self._login_state)
        status = state.get("status")
        if status == "ready":
            return {"status": "ready"}
        if status == "error":
            return {"status": "error", "message": state.get("message") or "Microsoft 登录失败"}
        if status == "cancelled":
            return {"status": "error", "message": "Microsoft 登录已取消"}
        if status in {"starting", "pending", "progress"}:
            result = {
                "status": "progress" if status == "progress" else "pending",
                "retry_after": state.get("interval", 5),
            }
            if state.get("stage"):
                result["stage"] = state["stage"]
            return result
        return {"status": "error", "message": "当前没有进行中的 Microsoft 登录"}

    def complete_microsoft_login(self) -> dict[str, Any]:
        """
        完成已授权的微软登录并返回保存后的账户。

        """
        with self._lock:
            state = deepcopy(self._login_state)
            if state.get("status") == "error":
                raise AccountError(state.get("message") or "Microsoft 登录失败", "MICROSOFT_LOGIN_FAILED")
            if state.get("status") == "cancelled":
                raise AccountError("Microsoft 登录已取消", "MICROSOFT_LOGIN_CANCELLED")
            if state.get("status") in {"starting", "pending", "progress"}:
                result = {
                    "status": "pending",
                    "retry_after": state.get("interval", 5),
                }
                if state.get("stage"):
                    result["stage"] = state["stage"]
                return result
            if state.get("status") != "ready":
                raise AccountError("当前没有可完成的 Microsoft 登录", "MICROSOFT_LOGIN_NOT_STARTED")

            account_id = state["account_id"]
            info = self.microsoft_manager.get_microsoft_accounts().get(account_id)
            if info is None:
                raise AccountError("Microsoft 账号数据不存在", "ACCOUNT_NOT_FOUND")
            account = self._microsoft_account(account_id, info)
            self._login_state = {"status": "idle"}
            self._login_thread = None
        self._emit_changed()
        return {"status": "completed", "account": account}

    def cancel_microsoft_login(self) -> bool:
        """
        取消登录流程；返回本次调用是否实际取消了任务。

        """
        with self._lock:
            login_thread = self._login_thread
            is_active = bool(login_thread and login_thread.is_alive())
            if not is_active and self._login_state.get("status") not in {"starting", "pending"}:
                return False

            self._login_cancel_event.set()
            if self._login_flow is not None:
                self._login_flow["expires_at"] = 0
            self._login_state = {"status": "cancelled"}
            self._login_event.set()
        self.events.emit("accounts:microsoft_login_status", {"status": "cancelled"})
        return True

    def _emit_changed(self) -> None:
        self.events.emit("accounts:changed", self.list_accounts())

    def close(self) -> None:
        """
        取消仍在运行的认证任务并释放认证客户端。
        """
        cancelled = self.cancel_microsoft_login()
        self.logger.debug("正在关闭账户服务: login_cancelled=%s", cancelled)
        self.microsoft_manager.close()
        self.authlib_manager.close()
