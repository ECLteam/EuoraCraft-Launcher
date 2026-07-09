from __future__ import annotations

import json
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..common.build_env import MICROSOFT_CLIENT_ID as BUILD_CLIENT_ID
from ..common.env import get_env_loader
from ..common.logger import get_logger
from .authlib import AuthlibInjectorAccount, AuthlibInjectorManager
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
        self.client_id = BUILD_CLIENT_ID or get_env_loader().get("MICROSOFT_CLIENT_ID", "")
        self._auth: MultiAccountMinecraftAuth | None = None
        self.output_log: Callable[[str], None] | None = None
        # Authlib 外置登录
        self._authlib_accounts: dict[str, AuthlibInjectorAccount] = {}
        self._authlib_current_account: AuthlibInjectorAccount | None = None
        self._authlib_data_dir = Path("~/.ECLAuth").expanduser()
        self._authlib_accounts_file = self._authlib_data_dir / "authlib_accounts.json"
        self._authlib_injector_manager = AuthlibInjectorManager(self._authlib_data_dir / "authlib")
        self._load_authlib_accounts()
        AccountManager._initialized = True

    def initialize(self) -> dict[str, Any]:
        if self._auth is not None and self._auth._initialized:
            return {"success": True, "needs_password": False}
        try:
            self._auth = MultiAccountMinecraftAuth(self.client_id)
            if self.output_log:
                self._auth.set_output_log(self.output_log)
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

    def set_output_log(self, callback: Callable[[str], None]) -> None:
        self.output_log = callback
        if self._auth:
            self._auth.set_output_log(callback)

    def _ensure_initialized(self) -> bool:
        if self._auth is not None:
            return True
        result = self.initialize()
        if isinstance(result, dict):
            if result.get("error"):
                return False
            return bool(result.get("success", False) or result.get("needs_password", False))
        return bool(result)

    def get_account_by_id(self, account_id: str) -> dict | None:
        # 检查 Authlib 账户
        if account_id in self._authlib_accounts:
            acc = self._authlib_accounts[account_id]
            return {
                "id": acc.account_id,
                "alias": acc.get_display_name(),
                "type": "authlib",
                "email": acc.email,
                "uuid": acc.get_uuid(),
                "auth_server": acc.auth_server,
            }
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
        if not self.client_id:
            return {"status": "error", "message": "needs_client_id", "needs_client_id": True}
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

    def refresh_account_profile(self, account_id: str) -> dict[str, Any]:
        # 检查 Authlib 账户
        if account_id in self._authlib_accounts:
            acc = self._authlib_accounts[account_id]
            if acc.refresh():
                return {"message": f"Authlib 账户 '{acc.get_display_name()}' 档案已刷新"}
            raise RuntimeError(f"刷新 Authlib 账户 '{acc.get_display_name()}' 档案失败")
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

    # ── Authlib 外置登录 ─────────────────────────────────────────────────

    def _load_authlib_accounts(self) -> None:
        """从文件加载 Authlib 账户。"""
        if not self._authlib_accounts_file.is_file():
            return
        try:
            with self._authlib_accounts_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            for acc_data in data.get("accounts", []):
                acc = AuthlibInjectorAccount.from_dict(acc_data)
                self._authlib_accounts[acc.account_id] = acc
            current_id = data.get("current_account_id")
            if current_id and current_id in self._authlib_accounts:
                self._authlib_current_account = self._authlib_accounts[current_id]
            logger.debug(f"加载了 {len(self._authlib_accounts)} 个 Authlib 账户")
        except (json.JSONDecodeError, OSError, KeyError, ValueError) as e:
            logger.error(f"加载 Authlib 账户失败: {e}")

    def _save_authlib_accounts(self) -> None:
        """保存 Authlib 账户到文件。"""
        try:
            self._authlib_data_dir.mkdir(parents=True, exist_ok=True)
            data = {
                "accounts": [acc.to_dict() for acc in self._authlib_accounts.values()],
                "current_account_id": self._authlib_current_account.account_id
                if self._authlib_current_account
                else None,
            }
            with self._authlib_accounts_file.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except (OSError, ValueError, TypeError) as e:
            logger.error(f"保存 Authlib 账户失败: {e}")

    def add_authlib_account(self, server_url: str, email: str, password: str) -> dict[str, Any]:
        """添加一个外置登录（Authlib-Injector）账户。"""
        if not server_url or not email or not password:
            return {"success": False, "message": "服务器地址、邮箱和密码不能为空"}
        # 检查是否已存在
        for acc in self._authlib_accounts.values():
            if acc.email == email and acc.auth_server == server_url.rstrip("/"):
                return {"success": False, "message": f"邮箱 '{email}' 在该服务器上已存在"}
        account = AuthlibInjectorAccount(
            auth_server=server_url,
            email=email,
            password=password,
        )
        logger.info(f"尝试登录 Authlib 账户: {email} @ {server_url}")
        if not account.login():
            return {"success": False, "message": "登录失败，请检查服务器地址和账号密码"}
        self._authlib_accounts[account.account_id] = account
        if not self._authlib_current_account:
            self._authlib_current_account = account
        self._save_authlib_accounts()
        # 如果有微软账户系统，将其当前账户清掉（避免冲突）
        if self._auth is not None and self._auth.current_account is not None:
            self._auth.current_account = None
        return {
            "success": True,
            "message": f"外置登录账户 '{email}' 添加成功",
            "account": {
                "id": account.account_id,
                "alias": account.get_display_name(),
                "type": "authlib",
                "email": account.email,
                "uuid": account.get_uuid(),
                "auth_server": account.auth_server,
            },
        }

    def get_authlib_injector_manager(self) -> AuthlibInjectorManager:
        return self._authlib_injector_manager

    def is_authlib_current(self) -> bool:
        return self._authlib_current_account is not None

    def get_authlib_current_account(self) -> AuthlibInjectorAccount | None:
        return self._authlib_current_account

    def get_authlib_launch_args(self) -> list[str]:
        if self._authlib_current_account is not None:
            return self._authlib_injector_manager.get_launch_args(self._authlib_current_account.auth_server)
        return []

    # ── 覆盖方法以支持 Authlib ─────────────────────────────────────────

    def get_all_accounts(self) -> list[dict]:
        """获取所有账户（包含微软/离线/Authlib）。"""
        accounts = []
        if self._ensure_initialized() and self._auth is not None:
            accounts = self._auth.get_all_accounts_info()
        # 添加 Authlib 账户
        for acc in self._authlib_accounts.values():
            accounts.append(
                {
                    "id": acc.account_id,
                    "alias": acc.get_display_name(),
                    "type": "authlib",
                    "email": acc.email,
                    "uuid": acc.get_uuid(),
                    "isCurrent": acc.account_id == self._authlib_current_account.account_id
                    if self._authlib_current_account
                    else False,
                    "auth_server": acc.auth_server,
                }
            )
        return accounts

    def get_current_account(self) -> dict | None:
        """获取当前选中的账户。"""
        # 优先检查 Authlib 当前账户
        if self._authlib_current_account is not None:
            return {
                "id": self._authlib_current_account.account_id,
                "alias": self._authlib_current_account.get_display_name(),
                "type": "authlib",
                "email": self._authlib_current_account.email,
                "uuid": self._authlib_current_account.get_uuid(),
                "auth_server": self._authlib_current_account.auth_server,
            }
        if self._ensure_initialized() and self._auth is not None:
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
        return None

    def get_current_account_token(self) -> str | None:
        """获取当前账户的 access token。"""
        if self._authlib_current_account is not None:
            return self._authlib_current_account.get_token()
        if not self._ensure_initialized() or self._auth is None:
            return None
        return self._auth.get_current_account_token()

    def switch_account(self, account_id: str) -> dict[str, Any]:
        """切换账户（支持 Authlib）。"""
        # 先检查 Authlib 账户
        if account_id in self._authlib_accounts:
            self._authlib_current_account = self._authlib_accounts[account_id]
            self._save_authlib_accounts()
            # 清除微软账户的当前状态
            if self._auth is not None and self._auth._initialized:
                self._auth.current_account = None
            return {"message": f"已切换到 Authlib 账户: {self._authlib_current_account.get_display_name()}"}
        if not self._ensure_initialized():
            raise RuntimeError("账户管理器未初始化")
        result = self._auth.switch_account(account_id)
        if result:
            self._authlib_current_account = None
            account = self._auth.get_account_by_id(account_id)
            return {"message": f"已切换到账户: {account.alias if account else account_id}"}
        raise RuntimeError(f"未找到账户: {account_id}")

    def remove_account(self, account_id: str) -> dict[str, Any]:
        """移除账户（支持 Authlib）。"""
        if account_id in self._authlib_accounts:
            account = self._authlib_accounts[account_id]
            alias = account.get_display_name()
            del self._authlib_accounts[account_id]
            if self._authlib_current_account and self._authlib_current_account.account_id == account_id:
                self._authlib_current_account = None
            self._save_authlib_accounts()
            return {"message": f"Authlib 账户 '{alias}' 已移除"}
        if not self._ensure_initialized():
            raise RuntimeError("账户管理器未初始化")
        account = self._auth.get_account_by_id(account_id)
        alias = account.alias if account else account_id
        result = self._auth.remove_account(account_id)
        if result:
            return {"message": f"账户 '{alias}' 已移除"}
        raise RuntimeError(f"移除账户 '{alias}' 失败")


_account_manager: AccountManager | None = None
