from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from threading import Event, RLock, Thread
from typing import Any
from uuid import UUID

from ECL.Common import MICROSOFT_CLIENT_ID
from ECL.Events import EventBus
from ECL.Game.Core.Libs import name_to_uuid
from ECL.Game.Core.MicrosoftAuth import MicrosoftAuthManager
from ECL.Infrastructure import get_logger

MICROSOFT_LOGIN_POLL_INTERVAL_SECONDS = 2 # 轮询间隔秒


class AccountError(Exception):
    def __init__(self, message: str, error_code: str = "ACCOUNT_ERROR"):
        super().__init__(message)
        self.error_code = error_code


class AccountManager:
    def __init__(
        self,
        data_path: Path | str,
        microsoft_manager: MicrosoftAuthManager | None = None,
        microsoft_client_id: str | None = None,
    ):
        self.logger = get_logger("AccountManager")
        self.data_path = Path(data_path) / "accounts"
        self.data_path.mkdir(parents=True, exist_ok=True)
        self.state_path = self.data_path / "accounts.json"
        self._lock = RLock()
        self._login_event = Event()
        self._login_cancel_event = Event()
        self._login_thread: Thread | None = None
        self._login_flow: dict[str, Any] | None = None
        self._login_state: dict[str, Any] = {"status": "idle"}
        self._offline_accounts: dict[str, dict[str, Any]] = {}
        self._current_account_id: str | None = None
        self._load_state()

        manager_was_provided = microsoft_manager is not None
        effective_client_id = (microsoft_client_id or MICROSOFT_CLIENT_ID).strip()
        self._microsoft_login_available = manager_was_provided or bool(effective_client_id)
        if microsoft_manager is None:
            microsoft_options = {
                "cache_path": self.data_path / "microsoft",
                "on_device_code": self._on_device_code,
            }
            if effective_client_id:
                microsoft_options["client_id"] = effective_client_id
            microsoft_manager = MicrosoftAuthManager(**microsoft_options)
        else:
            microsoft_manager.on_device_code = self._on_device_code
        self.microsoft_manager = microsoft_manager
        self._deduplicate_microsoft_accounts()
        self._ensure_current_account()

    def microsoft_login_config(self) -> dict[str, bool]:
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
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            self.logger.warning("读取账号状态失败，将使用空账号列表: %s", exc)

    def _save_state(self) -> None:
        state = {
            "offline_accounts": self._offline_accounts,
            "current_account_id": self._current_account_id,
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

    @staticmethod
    def _microsoft_skin_url(info: dict[str, Any]) -> str | None:
        profile = info.get("Profile") or {}
        skins = profile.get("skins") or []
        if skins and isinstance(skins[0], dict):
            skin_url = skins[0].get("url")
            if isinstance(skin_url, str) and skin_url:
                return skin_url

        skin_info = info.get("Skin") or {}
        for item in skin_info.get("properties") or []:
            if item.get("name") != "textures" or not isinstance(item.get("value"), dict):
                continue
            texture = ((item["value"].get("textures") or {}).get("SKIN") or {}).get("url")
            if isinstance(texture, str) and texture:
                return texture
        return None

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
        skin_url = self._microsoft_skin_url(info)
        if skin_url:
            account["skinUrl"] = skin_url
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
        accounts = offline_accounts + microsoft_accounts
        for account in accounts:
            account["isCurrent"] = account["id"] == self._current_account_id
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

    def list_accounts(self) -> dict[str, Any]:
        with self._lock:
            accounts = self._all_accounts()
            current = next((account for account in accounts if account["isCurrent"]), None)
            return {"accounts": accounts, "current": current}

    def current_account(self) -> dict[str, Any] | None:
        return self.list_accounts()["current"]

    def get_launch_credentials(self) -> dict[str, str]:
        """返回当前账户用于启动 Minecraft 的最小凭据集合。"""
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

    def switch_account(self, account_id: Any) -> None:
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
        if not isinstance(account_id, str) or not account_id:
            raise AccountError("账号 ID 不能为空", "INVALID_ACCOUNT_ID")
        with self._lock:
            if account_id in self._offline_accounts:
                self._offline_accounts.pop(account_id)
            elif account_id in self.microsoft_manager.get_microsoft_accounts():
                self.microsoft_manager.del_microsoft_account(account_id)
            else:
                raise AccountError("账号不存在", "ACCOUNT_NOT_FOUND")

            if self._current_account_id == account_id:
                remaining_accounts = self._all_accounts()
                self._current_account_id = remaining_accounts[0]["id"] if remaining_accounts else None
            self._save_state()
        self._emit_changed()

    def refresh_account(self, account_id: Any) -> dict[str, Any]:
        if not isinstance(account_id, str) or not account_id:
            raise AccountError("账号 ID 不能为空", "INVALID_ACCOUNT_ID")
        with self._lock:
            if account_id in self._offline_accounts:
                account = deepcopy(self._offline_accounts[account_id])
            elif account_id in self.microsoft_manager.get_microsoft_accounts():
                self.microsoft_manager.refresh_profile(account_id)
                info = self.microsoft_manager.get_microsoft_accounts()[account_id]
                account = self._microsoft_account(account_id, info)
            else:
                raise AccountError("账号不存在", "ACCOUNT_NOT_FOUND")
        self._emit_changed()
        return account

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
            EventBus().emit("accounts:microsoft_login_status", frontend_event)

    def start_microsoft_login(self) -> dict[str, Any]:
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
        return {
            "status": "pending",
            "userCode": state.get("userCode", ""),
            "verificationUri": state.get("verificationUri", ""),
            "message": state.get("message", ""),
            "interval": state.get("interval", 5),
        }

    def poll_microsoft_login(self) -> dict[str, Any]:
        with self._lock:
            state = deepcopy(self._login_state)
        status = state.get("status")
        if status == "ready":
            return {"status": "ready"}
        if status == "error":
            return {"status": "error", "message": state.get("message") or "Microsoft 登录失败"}
        if status == "cancelled":
            return {"status": "error", "message": "Microsoft 登录已取消"}
        if status in {"starting", "pending"}:
            return {"status": "pending", "retry_after": state.get("interval", 5)}
        return {"status": "error", "message": "当前没有进行中的 Microsoft 登录"}

    def complete_microsoft_login(self) -> dict[str, Any]:
        with self._lock:
            state = deepcopy(self._login_state)
            if state.get("status") == "error":
                raise AccountError(state.get("message") or "Microsoft 登录失败", "MICROSOFT_LOGIN_FAILED")
            if state.get("status") == "cancelled":
                raise AccountError("Microsoft 登录已取消", "MICROSOFT_LOGIN_CANCELLED")
            if state.get("status") in {"starting", "pending"}:
                return {
                    "status": "pending",
                    "retry_after": state.get("interval", 5),
                }
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
        EventBus().emit("accounts:microsoft_login_status", {"status": "cancelled"})
        return True

    def _emit_changed(self) -> None:
        EventBus().emit("accounts:changed", self.list_accounts())

    def close(self) -> None:
        self.cancel_microsoft_login()
        self.microsoft_manager.close()
