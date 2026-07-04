from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from ..common.logger import get_logger
from .microsoft import MultiAccountMinecraftAuth

logger = get_logger("account")


class AccountManager:
    _instance: AccountManager | None = None
    _initialized: bool = False
    _lock = threading.Lock()

    def __new__(cls) -> AccountManager:
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance

    def __init__(self):
        if AccountManager._initialized:
            return
        self.client_id = "f1709935-df0b-400c-843a-530a77fb8d3c"
        self._auth: MultiAccountMinecraftAuth | None = None
        self._log_callback: Callable[[str], None] | None = None
        self._login_log_callback: Callable[[str], None] | None = None
        AccountManager._initialized = True

    def initialize(self) -> dict[str, Any]:
        if self._auth is not None and self._auth._initialized:
            return {"success": True, "needs_password": False}
        try:
            self._auth = MultiAccountMinecraftAuth(self.client_id)
            if self._log_callback:
                self._auth.set_output_log(self._log_callback)
            if self._login_log_callback:
                self._auth.set_output_login_log(self._login_log_callback)
            result = self._auth.initialize()
            if result:
                logger.info("账户管理器初始化成功")
                return {"success": True, "needs_password": False}
            if self._auth.encryption and self._auth.encryption.needs_password():
                logger.info("账户管理器需要主密码")
                return {"success": False, "needs_password": True}
            logger.error("账户管理器初始化失败")
            return {"success": False, "needs_password": False}
        except RuntimeError as e:
            logger.error(f"账户管理器初始化异常: {e}")
            return {"success": False, "needs_password": False}

    def set_master_password(self, password: str) -> bool:
        if self._auth is None:
            return False
        try:
            result = self._auth.set_encryption_password(password)
            if result:
                logger.info("主密码设置成功，账户管理器已初始化")
            return result
        except RuntimeError as e:
            logger.error(f"设置主密码失败: {e}")
            return False

    def set_log_callback(self, callback: Callable[[str], None]) -> None:
        self._log_callback = callback
        if self._auth:
            self._auth.set_output_log(callback)

    def set_login_log_callback(self, callback: Callable[[str], None]) -> None:
        self._login_log_callback = callback
        if self._auth:
            self._auth.set_output_login_log(callback)

    def _ensure_initialized(self) -> bool:
        if self._auth is not None:
            return True
        result = self.initialize()
        if isinstance(result, dict):
            if result.get("error"):
                return False
            return bool(result.get("success", False) or result.get("needs_password", False))
        return bool(result)

    def get_all_accounts(self) -> list[dict]:
        if not self._ensure_initialized():
            return []
        return self._auth.get_all_accounts_info()

    def get_current_account(self) -> dict | None:
        if not self._ensure_initialized():
            return None
        account = self._auth.get_current_account()
        if not account:
            return None
        return {
            "id": account.account_id,
            "alias": account.alias,
            "type": account.account_type,
            "email": account.email if account.account_type == "microsoft" else "",
            "uuid": account.get_uuid(),
            "skinUrl": account.get_skin_url(),
        }

    def get_account_by_id(self, account_id: str) -> dict | None:
        if not self._ensure_initialized():
            return None
        account = self._auth.get_account_by_id(account_id)
        if not account:
            return None
        return {
            "id": account.account_id,
            "alias": account.alias,
            "type": account.account_type,
            "email": account.email if account.account_type == "microsoft" else "",
            "uuid": account.get_uuid(),
            "skinUrl": account.get_skin_url(),
        }

    def add_offline_account(self, username: str) -> dict[str, Any]:
        if not self._ensure_initialized():
            raise RuntimeError("账户管理器未初始化")
        result = self._auth.add_offline_account(username)
        if not result:
            raise RuntimeError(f"添加离线账户 '{username}' 失败")
        if isinstance(result, dict) and not result.get("success"):
            raise RuntimeError(result.get("message", "添加离线账户失败"))
        accounts = self._auth.get_all_accounts_info()
        for acc in accounts:
            if acc["alias"] == username and acc["type"] == "offline":
                return {"account": acc, "message": f"离线账户 '{username}' 添加成功"}
        return {"message": f"离线账户 '{username}' 添加成功"}

    def start_microsoft_login(self) -> dict[str, Any]:
        if not self._ensure_initialized():
            raise RuntimeError("账户管理器未初始化")
        result = self._auth.start_microsoft_login()
        if result.get("status") == "error":
            raise RuntimeError(result.get("message", "启动登录失败"))
        if result.get("status") == "success":
            return {"status": "completed", "message": "登录成功"}
        return {
            "status": "pending",
            "userCode": result.get("userCode", ""),
            "verificationUri": result.get("verificationUri", ""),
            "message": result.get("message", "请在浏览器中完成授权"),
        }

    def poll_microsoft_login(self) -> dict[str, Any]:
        if not self._ensure_initialized():
            raise RuntimeError("账户管理器未初始化")
        return self._auth.poll_microsoft_login()

    def open_browser_for_auth(self, url: str) -> bool:
        if not self._ensure_initialized():
            return False
        return self._auth.open_browser_for_auth(url)

    def complete_microsoft_login(self) -> dict[str, Any]:
        if not self._ensure_initialized():
            raise RuntimeError("账户管理器未初始化")
        result = self._auth.complete_microsoft_login()
        if result.get("success"):
            return {"account": result.get("account"), "message": result.get("message", "登录成功")}
        raise RuntimeError(result.get("message", "登录失败"))

    def switch_account(self, account_id: str) -> dict[str, Any]:
        if not self._ensure_initialized():
            raise RuntimeError("账户管理器未初始化")
        result = self._auth.switch_account(account_id)
        if result:
            account = self._auth.get_account_by_id(account_id)
            return {"message": f"已切换到账户: {account.alias if account else account_id}"}
        raise RuntimeError(f"未找到账户: {account_id}")

    def remove_account(self, account_id: str) -> dict[str, Any]:
        if not self._ensure_initialized():
            raise RuntimeError("账户管理器未初始化")
        account = self._auth.get_account_by_id(account_id)
        alias = account.alias if account else account_id
        result = self._auth.remove_account(account_id)
        if result:
            return {"message": f"账户 '{alias}' 已移除"}
        raise RuntimeError(f"移除账户 '{alias}' 失败")

    def get_current_account_token(self) -> str | None:
        if not self._ensure_initialized():
            return None
        return self._auth.get_current_account_token()

    def refresh_account_profile(self, account_id: str) -> dict[str, Any]:
        if not self._ensure_initialized():
            raise RuntimeError("账户管理器未初始化")
        account = self._auth.get_account_by_id(account_id)
        if not account:
            raise RuntimeError(f"未找到账户: {account_id}")
        if account.account_type == "offline":
            return {"message": "离线账户无需刷新"}
        result = self._auth.refresh_account_profile(account.alias)
        if result:
            return {"message": f"账户 '{account.alias}' 档案已刷新"}
        raise RuntimeError(f"刷新账户 '{account.alias}' 档案失败")

    def shutdown(self) -> None:
        if self._auth is not None:
            self._auth.shutdown()
            logger.debug("AccountManager 资源已清理")


_account_manager: AccountManager | None = None


def get_account_manager() -> AccountManager:
    global _account_manager
    if _account_manager is None:
        _account_manager = AccountManager()
    return _account_manager
