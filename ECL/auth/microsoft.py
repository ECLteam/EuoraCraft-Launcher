import base64
import hashlib
import json
import time
import uuid
import webbrowser
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import msal
import requests

from ..common.logger import get_logger
from .crypto import EncryptionManager
from .models import MinecraftAccount

logger = get_logger("auth.microsoft")


class MultiAccountMinecraftAuth:
    def __init__(self, client_id: str, data_dir: str = "~/.ECLAuth"):
        self.client_id = client_id
        self.data_dir = Path(data_dir).expanduser()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._log_callback: Callable[[str], None] = logger.info
        self._login_log_callback: Callable[[str], None] = logger.info
        self._login_callback: Callable[[dict], None] = self._login_print
        self.encryption: EncryptionManager | None = None
        self.accounts: dict[str, MinecraftAccount] = {}
        self.current_account: MinecraftAccount | None = None
        self.accounts_file = self.data_dir / "accounts.json"
        self.current_account_file = self.data_dir / "current_account.txt"
        self._initialized: bool = False

        # pending login state
        self._pending_flow: dict | None = None
        self._pending_cache_file: str | None = None
        self._pending_app: msal.PublicClientApplication | None = None
        self._poll_interval: int = 5
        self._poll_expires_at: float = 0
        self._poll_result: dict | None = None
        self._poll_future: Any = None
        self._poll_executor: ThreadPoolExecutor | None = None

    def set_output_log(self, func: Callable[[str], None]) -> None:
        self._log_callback = func

    def set_output_login_log(self, func: Callable[[str], None]) -> None:
        self._login_log_callback = func

    def set_login_callback(self, func: Callable[[dict], None]) -> None:
        self._login_callback = func

    def _log(self, msg: str) -> None:
        self._log_callback(msg)

    @staticmethod
    def _login_print(flow: dict):
        print(flow)
        print(f"请在浏览器访问：{flow['verification_uri']}，并在其中输入：{flow['user_code']}")

    def initialize(self) -> bool:
        if self._initialized:
            self._log("已经初始化过，跳过")
            return True
        try:
            self.encryption = EncryptionManager(log_callback=self._log_callback)
            if self.encryption.needs_password():
                self._log("需要设置主密码")
                return False
            self._load_accounts()
            self._initialized = True
            self._log("初始化成功")
            return True
        except (OSError, json.JSONDecodeError, ValueError, KeyError, TypeError, RuntimeError) as e:
            self._log(f"初始化失败: {e}")
            return False

    def set_encryption_password(self, password: str) -> bool:
        if self.encryption is None:
            return False
        try:
            self.encryption.set_password(password)
            self._load_accounts()
            self._initialized = True
            return True
        except (OSError, json.JSONDecodeError, ValueError, KeyError, TypeError, RuntimeError) as e:
            self._log(f"设置密码失败: {e}")
            return False

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            raise RuntimeError("请先调用 initialize()")

    def _load_accounts(self) -> None:
        if not self.accounts_file.exists():
            logger.debug("账户文件不存在，跳过加载")
            return
        try:
            with self.accounts_file.open(encoding="utf-8") as f:
                accounts_data = json.load(f)
                logger.debug(f"账户文件原始数据包含 {len(accounts_data)} 个条目")
                for account_id, enc_data in accounts_data.items():
                    if isinstance(enc_data, str):
                        try:
                            decrypted_data = self.encryption.decrypt_data(enc_data)
                            account_dict = json.loads(decrypted_data)
                            self.accounts[account_id] = MinecraftAccount.from_dict(account_dict)
                            logger.debug(f"加载账户成功: {account_id}")
                        except (json.JSONDecodeError, ValueError, KeyError, TypeError) as item_err:
                            logger.warning(f"加载账户 {account_id} 失败: {item_err}")
                    else:
                        logger.warning(f"账户 {account_id} 数据格式异常，期望字符串，得到 {type(enc_data)}")
            self._log(f"已加载 {len(self.accounts)} 个账户")
        except (OSError, json.JSONDecodeError, ValueError, KeyError, TypeError) as e:
            logger.error(f"加载账户数据失败: {e}")
        if self.current_account_file.exists():
            try:
                with self.current_account_file.open(encoding="utf-8") as f:
                    current_id = f.read().strip()
                    if current_id in self.accounts:
                        self.current_account = self.accounts[current_id]
                        self._log(f"当前选中账户: {self.current_account.alias}")
            except (OSError, ValueError) as e:
                self._log(f"加载当前账户失败: {e}")

    def _save_accounts(self) -> None:
        accounts_data = {}
        for account_id, account in self.accounts.items():
            encrypted = self.encryption.encrypt_data(json.dumps(account.to_dict()))
            accounts_data[account_id] = encrypted
        try:
            with self.accounts_file.open("w", encoding="utf-8") as f:
                json.dump(accounts_data, f, indent=2)
        except (OSError, TypeError, ValueError, RuntimeError) as e:
            self._log(f"保存账户数据失败: {e}")

    def _set_current_account(self, account: MinecraftAccount) -> None:
        self.current_account = account
        try:
            with self.current_account_file.open("w", encoding="utf-8") as f:
                f.write(account.account_id)
        except (OSError, ValueError) as e:
            self._log(f"保存当前账户设置失败: {e}")

    def _build_persistence_cache(self, cache_file: str) -> msal.SerializableTokenCache:
        cache_path = self.data_dir / "cache" / f"{cache_file}.bin"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        token_cache = msal.SerializableTokenCache()
        if cache_path.exists():
            try:
                with cache_path.open(encoding="utf-8") as f:
                    encrypted = f.read()
                    decrypted = self.encryption.decrypt_data(encrypted)
                    token_cache.deserialize(decrypted)
            except (OSError, ValueError, KeyError, TypeError) as e:
                self._log(f"加载加密缓存失败: {e}")
        token_cache.cache_path = str(cache_path)
        return token_cache

    def _save_cache(self, token_cache: msal.SerializableTokenCache) -> None:
        if not hasattr(token_cache, "cache_path") or not token_cache.cache_path:
            return
        try:
            cache_data = token_cache.serialize()
            encrypted = self.encryption.encrypt_data(cache_data)
            with Path(token_cache.cache_path).open("w", encoding="utf-8") as f:
                f.write(encrypted)
        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as e:
            self._log(f"保存加密缓存失败: {e}")

    def _get_microsoft_token(self, cache_file: str) -> tuple[str | None, str | None, str | None]:
        scope = ["XboxLive.signin"]
        token_cache = self._build_persistence_cache(cache_file)
        app = msal.PublicClientApplication(
            client_id=self.client_id, authority="https://login.microsoftonline.com/consumers", token_cache=token_cache
        )
        accounts = app.get_accounts()
        result = None
        account_info = None
        email = None
        if accounts:
            self._login_log_callback("尝试静默获取令牌...")
            account_info = accounts[0]
            result = app.acquire_token_silent(scopes=scope, account=account_info)
        if not result:
            self._login_log_callback("开始设备代码流登录...")
            try:
                flow = app.initiate_device_flow(scopes=scope)
                if "user_code" not in flow:
                    raise ValueError("未能创建设备流")
                self._login_callback(flow)
                result = app.acquire_token_by_device_flow(flow)
                if result and "id_token_claims" in result:
                    id_claims = result["id_token_claims"]
                    email = id_claims.get("preferred_username") or id_claims.get("email")
            except (ValueError, KeyError, TypeError, json.JSONDecodeError, requests.exceptions.RequestException) as e:
                self._login_log_callback(f"设备代码流失败: {e}")
                return None, None, None
        if "access_token" in result:
            self._login_log_callback("微软令牌获取成功")
            self._save_cache(token_cache)
            account_id = account_info.get("home_account_id") if account_info else None
            return result["access_token"], account_id, email
        else:
            self._login_log_callback(f"认证失败: {result.get('error')}")
            return None, None, None

    def _get_xbox_chain_tokens(self, msft_access_token: str) -> tuple[str | None, str | None]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        try:
            resp = requests.post(
                "https://user.auth.xboxlive.com/user/authenticate",
                json={
                    "Properties": {
                        "AuthMethod": "RPS",
                        "SiteName": "user.auth.xboxlive.com",
                        "RpsTicket": f"d={msft_access_token}",
                    },
                    "RelyingParty": "http://auth.xboxlive.com",
                    "TokenType": "JWT",
                },
                headers=headers,
            )
            if resp.status_code != 200:
                self._login_log_callback(f"Xbox Live 令牌获取失败: {resp.status_code}")
                return None, None
            xbox_live_data = resp.json()
            xbox_live_token = xbox_live_data["Token"]
            user_hash = xbox_live_data["DisplayClaims"]["xui"][0]["uhs"]
            self._login_log_callback("Xbox Live 令牌获取成功")
            resp = requests.post(
                "https://xsts.auth.xboxlive.com/xsts/authorize",
                json={
                    "Properties": {"SandboxId": "RETAIL", "UserTokens": [xbox_live_token]},
                    "RelyingParty": "rp://api.minecraftservices.com/",
                    "TokenType": "JWT",
                },
                headers=headers,
            )
            if resp.status_code != 200:
                self._login_log_callback(f"XSTS 令牌获取失败: {resp.status_code}")
                return None, None
            xsts_token = resp.json()["Token"]
            self._login_log_callback("XSTS 令牌获取成功")
            return xsts_token, user_hash
        except (requests.exceptions.RequestException, KeyError, TypeError, json.JSONDecodeError, ValueError) as e:
            self._login_log_callback(f"Xbox 认证链失败: {e}")
            return None, None

    def _get_minecraft_token(self, xsts_token: str, user_hash: str) -> tuple[str | None, int]:
        try:
            resp = requests.post(
                "https://api.minecraftservices.com/authentication/login_with_xbox",
                json={"identityToken": f"XBL3.0 x={user_hash};{xsts_token}"},
                headers={"Content-Type": "application/json"},
            )
            if resp.status_code != 200:
                self._login_log_callback(f"Minecraft 令牌获取失败: {resp.status_code}")
                return None, 0
            data = resp.json()
            self._login_log_callback("Minecraft 令牌获取成功")
            return data["access_token"], data.get("expires_in", 86400)
        except (requests.exceptions.RequestException, KeyError, TypeError, json.JSONDecodeError, ValueError) as e:
            self._login_log_callback(f"Minecraft 令牌获取失败: {e}")
            return None, 0

    def _check_minecraft_ownership(self, mc_access_token: str) -> tuple[bool, dict | None]:
        try:
            resp = requests.get(
                "https://api.minecraftservices.com/minecraft/profile",
                headers={"Authorization": f"Bearer {mc_access_token}"},
            )
            if resp.status_code == 200:
                profile = resp.json()
                self._login_log_callback(f"Minecraft 所有权验证成功: {profile['name']}")
                return True, profile
            elif resp.status_code == 404:
                self._login_log_callback("该账户未购买 Minecraft Java 版")
                return False, None
            else:
                self._login_log_callback(f"验证失败: {resp.status_code}")
                return False, None
        except (requests.exceptions.RequestException, KeyError, TypeError, json.JSONDecodeError, ValueError) as e:
            self._login_log_callback(f"验证失败: {e}")
            return False, None

    def add_account(self) -> bool:
        self._ensure_initialized()
        cache_file = f"account_{uuid.uuid4().hex[:8]}"
        ms_token, account_id, email = self._get_microsoft_token(cache_file)
        if not ms_token:
            return False
        xsts_token, user_hash = self._get_xbox_chain_tokens(ms_token)
        if not xsts_token:
            return False
        mc_token, _expires_in = self._get_minecraft_token(xsts_token, user_hash)
        if not mc_token:
            return False
        has_minecraft, profile = self._check_minecraft_ownership(mc_token)
        if not has_minecraft:
            cache_path = self.data_dir / "cache" / f"{cache_file}.bin"
            if cache_path.exists():
                cache_path.unlink()
            return False
        alias = profile["name"]
        if not account_id:
            account_id = f"account_{len(self.accounts) + 1}"

        if account_id in self.accounts:
            self._log(f"微软账户 '{alias}' 已存在")
            cache_path = self.data_dir / "cache" / f"{cache_file}.bin"
            if cache_path.exists():
                cache_path.unlink()
            return False

        for existing_account in self.accounts.values():
            if existing_account.account_type == "microsoft" and existing_account.alias == alias:
                self._log(f"玩家名 '{alias}' 的微软账户已存在")
                cache_path = self.data_dir / "cache" / f"{cache_file}.bin"
                if cache_path.exists():
                    cache_path.unlink()
                return False

        account = MinecraftAccount(
            alias=alias, account_id=account_id, email=email or "未知", profile=profile, cache_file=cache_file
        )
        self.accounts[account_id] = account
        self._save_accounts()
        if len(self.accounts) == 1:
            self._set_current_account(account)
        self._log(f"账户 '{alias}' 添加成功")
        return True

    def add_offline_account(self, username: str) -> dict:
        self._ensure_initialized()
        if not username or not username.strip():
            self._log("用户名不能为空")
            return {"success": False, "message": "用户名不能为空"}
        username = username.strip()

        for account in self.accounts.values():
            if account.alias == username:
                if account.account_type == "offline":
                    msg = f"离线账户 '{username}' 已存在"
                else:
                    msg = f"玩家名 '{username}' 已被微软账户使用"
                self._log(msg)
                return {"success": False, "message": msg}

        offline_uuid_str = hashlib.md5(f"OfflinePlayer:{username}".encode()).hexdigest()
        formatted_uuid = f"{offline_uuid_str[:8]}-{offline_uuid_str[8:12]}-{offline_uuid_str[12:16]}-{offline_uuid_str[16:20]}-{offline_uuid_str[20:32]}"
        account_id = f"offline_{uuid.uuid4().hex[:8]}"
        profile = {"name": username, "id": formatted_uuid, "offline": True}
        account = MinecraftAccount(
            alias=username, account_id=account_id, email="", profile=profile, cache_file="", account_type="offline"
        )
        self.accounts[account_id] = account
        self._save_accounts()
        if len(self.accounts) == 1:
            self._set_current_account(account)
        self._log(f"离线账户 '{username}' 添加成功")
        return {"success": True, "message": f"离线账户 '{username}' 添加成功"}

    def list_accounts(self) -> list | None:
        self._ensure_initialized()
        if not self.accounts:
            self._log("暂无已保存的账户")
            return None
        return list(self.accounts.items())

    def get_current_account(self) -> MinecraftAccount | None:
        return self.current_account

    def switch_account(self, account_id: str) -> bool:
        self._ensure_initialized()
        if account_id in self.accounts:
            account = self.accounts[account_id]
            self._set_current_account(account)
            self._log(f"已切换到账户: {account.alias}")
            return True
        self._log(f"未找到账户: {account_id}")
        return False

    def remove_account(self, account_id: str) -> bool:
        self._ensure_initialized()
        if account_id not in self.accounts:
            self._log(f"未找到账户: {account_id}")
            return False
        target_account = self.accounts[account_id]
        if target_account.account_type == "microsoft" and target_account.cache_file:
            cache_path = self.data_dir / "cache" / f"{target_account.cache_file}.bin"
            if cache_path.exists():
                cache_path.unlink()
        del self.accounts[account_id]
        self._save_accounts()
        if self.current_account and self.current_account.account_id == account_id:
            self.current_account = None
            if self.current_account_file.exists():
                self.current_account_file.unlink()
        self._log(f"账户 '{target_account.alias}' 已移除")
        return True

    def get_account_id_by_alias(self, alias: str) -> str | None:
        self._ensure_initialized()
        for account_id, account in self.accounts.items():
            if account.alias == alias:
                return account_id
        return None

    def switch_account_by_alias(self, account_alias: str) -> bool:
        account_id = self.get_account_id_by_alias(account_alias)
        if account_id:
            return self.switch_account(account_id)
        self._log(f"未找到账户: {account_alias}")
        return False

    def remove_account_by_alias(self, account_alias: str) -> bool:
        account_id = self.get_account_id_by_alias(account_alias)
        if account_id:
            return self.remove_account(account_id)
        self._log(f"未找到账户: {account_alias}")
        return False

    def get_account_by_id(self, account_id: str) -> MinecraftAccount | None:
        self._ensure_initialized()
        return self.accounts.get(account_id)

    def get_current_account_token(self) -> str | None:
        self._ensure_initialized()
        if not self.current_account:
            self._log("未选择任何账户")
            return None
        if self.current_account.account_type == "offline":
            self._log(f"离线账户 '{self.current_account.alias}' 无需获取令牌")
            return "OFFLINE"

        # 检查缓存的 Minecraft 令牌是否仍然有效
        if self.current_account.mc_token and self.current_account.mc_token_expires > time.time():
            self._log(f"使用缓存的 Minecraft 令牌 (剩余 {self.current_account.mc_token_expires - time.time():.0f}s)")
            return self.current_account.mc_token

        self._log(f"正在为账户 {self.current_account.alias} 获取 Minecraft 令牌...")
        ms_token, _, _ = self._get_microsoft_token(self.current_account.cache_file)
        if not ms_token:
            self._login_log_callback("获取微软令牌失败")
            return None
        xsts_token, user_hash = self._get_xbox_chain_tokens(ms_token)
        if not xsts_token:
            self._login_log_callback("Xbox 认证链失败")
            return None
        mc_token, expires_in = self._get_minecraft_token(xsts_token, user_hash)
        if not mc_token:
            self._login_log_callback("获取 Minecraft 令牌失败")
            return None
        is_valid, profile = self._check_minecraft_ownership(mc_token)
        if not is_valid:
            self._login_log_callback("Minecraft 令牌验证失败")
            return None
        if profile and profile["name"] != self.current_account.alias:
            self._log(f"玩家 ID 变化: {self.current_account.alias} -> {profile['name']}")
            self.current_account.alias = profile["name"]
            self.current_account.profile = profile
        # 缓存令牌（提前 5 分钟过期）
        self.current_account.mc_token = mc_token
        self.current_account.mc_token_expires = time.time() + expires_in - 300
        self._save_accounts()
        return mc_token

    def refresh_account_profile(self, account_alias: str) -> bool:
        self._ensure_initialized()
        for account in self.accounts.values():
            if account.alias != account_alias:
                continue
            self._log(f"刷新账户档案: {account.alias}")
            ms_token, _, _ = self._get_microsoft_token(account.cache_file)
            if not ms_token:
                self._login_log_callback("获取微软令牌失败")
                return False
            xsts_token, user_hash = self._get_xbox_chain_tokens(ms_token)
            if not xsts_token:
                return False
            mc_token, _ = self._get_minecraft_token(xsts_token, user_hash)
            if not mc_token:
                return False
            is_valid, profile = self._check_minecraft_ownership(mc_token)
            if not is_valid:
                return False
            old_alias = account.alias
            account.profile = profile
            if profile["name"] != old_alias:
                self._log(f"更新账户别名: {old_alias} -> {profile['name']}")
                account.alias = profile["name"]
            self._save_accounts()
            self._log(f"{old_alias} 档案已更新")
            return True
        self._log(f"未找到账户: {account_alias}")
        return False

    def refresh_all_account_profiles(self) -> None:
        self._ensure_initialized()
        updated = 0
        for account in list(self.accounts.values()):
            self._log(f"刷新账户档案: {account.alias}")
            if self.refresh_account_profile(account.alias):
                updated += 1
            else:
                self._log(f"{account.alias} 档案刷新失败")
        self._log(f"档案刷新完成，成功更新 {updated}/{len(self.accounts)} 个账户")

    def change_master_password(self, new_password: str) -> bool:
        self._ensure_initialized()
        if len(new_password) < 8:
            self._log("密码长度至少8位")
            return False
        old_fernet = self.encryption.fernet
        try:
            new_fernet = self.encryption.change_password(new_password)
        except (RuntimeError, ValueError, KeyError, TypeError, OSError) as e:
            self._log(f"更改密码失败: {e}")
            return False
        self._log("重新加密缓存文件...")
        success = 0
        total = len(self.accounts)
        for account in self.accounts.values():
            cache_path = self.data_dir / "cache" / f"{account.cache_file}.bin"
            if cache_path.exists():
                try:
                    with cache_path.open(encoding="utf-8") as f:
                        encrypted_data = f.read()
                    decrypted_bytes = old_fernet.decrypt(base64.urlsafe_b64decode(encrypted_data.encode()))
                    decrypted_data = decrypted_bytes.decode()
                    new_encrypted = new_fernet.encrypt(decrypted_data.encode())
                    new_encrypted_b64 = base64.urlsafe_b64encode(new_encrypted).decode()
                    with cache_path.open("w", encoding="utf-8") as f:
                        f.write(new_encrypted_b64)
                    success += 1
                except (OSError, ValueError, KeyError, TypeError) as e:
                    self._log(f"重新加密账户 {account.alias} 的缓存失败: {e}")
        self._save_accounts()
        self._log(f"主密码更改完成，成功重新加密 {success}/{total} 个账户")
        return True

    def get_current_account_profile(self, refresh: bool = False) -> dict | None:
        self._ensure_initialized()
        if not self.current_account:
            self._log("未选择任何账户")
            return None
        if refresh:
            if self.refresh_account_profile(self.current_account.alias):
                return self.current_account.profile
            return None
        return self.current_account.profile

    def get_all_accounts_profiles(self, refresh: bool = False) -> dict[str, dict]:
        self._ensure_initialized()
        profiles = {}
        if refresh:
            self.refresh_all_account_profiles()
        for alias, account in self.accounts.items():
            profiles[alias] = account.profile
        return profiles

    def get_all_accounts_info(self) -> list[dict]:
        self._ensure_initialized()
        accounts_info = []
        current_id = self.current_account.account_id if self.current_account else None
        logger.debug(f"获取账户列表，内存中共有 {len(self.accounts)} 个账户")
        for account_id, account in self.accounts.items():
            info = {
                "id": account_id,
                "alias": account.alias,
                "type": account.account_type,
                "email": account.email if account.account_type == "microsoft" else "",
                "uuid": account.get_uuid(),
                "isCurrent": account_id == current_id,
                "skinUrl": account.get_skin_url(),
            }
            accounts_info.append(info)
            logger.debug(f"账户条目: {info}")
        accounts_info.sort(key=lambda x: (not x["isCurrent"], x["type"] == "offline", x["alias"].lower()))
        return accounts_info

    def start_microsoft_login(self) -> dict:
        self._ensure_initialized()
        cache_file = f"account_{uuid.uuid4().hex[:8]}"
        scope = ["XboxLive.signin"]
        token_cache = self._build_persistence_cache(cache_file)
        app = msal.PublicClientApplication(
            client_id=self.client_id, authority="https://login.microsoftonline.com/consumers", token_cache=token_cache
        )
        accounts = app.get_accounts()
        if accounts:
            result = app.acquire_token_silent(scopes=scope, account=accounts[0])
            if result and "access_token" in result:
                self._save_cache(token_cache)
                return {"status": "success", "cache_file": cache_file}
        flow = app.initiate_device_flow(scopes=scope)
        if "user_code" not in flow:
            return {"status": "error", "message": "创建设备流失败"}
        self._pending_flow = flow
        self._pending_cache_file = cache_file
        self._pending_app = app
        self._poll_interval = flow.get("interval", 5)
        self._poll_expires_at = float(flow.get("expires_at", 0))
        return {
            "status": "pending",
            "userCode": flow["user_code"],
            "verificationUri": flow["verification_uri"],
            "message": flow.get("message", ""),
            "interval": self._poll_interval,
        }

    def poll_microsoft_login(self) -> dict:
        self._ensure_initialized()
        if not self._pending_flow:
            return {"status": "error", "message": "没有待处理的登录流程"}

        if time.time() > self._poll_expires_at:
            self._cleanup_pending_login()
            return {"status": "error", "message": "登录超时，请重试"}

        if self._poll_result:
            return {"status": "ready", "message": "授权完成，等待完成登录"}

        if self._poll_future:
            if self._poll_future.done():
                try:
                    result = self._poll_future.result()
                    error = result.get("error")
                    if error == "authorization_pending":
                        self._poll_future = None
                        return {"status": "pending", "message": "等待用户授权..."}
                    elif error:
                        self._cleanup_poll()
                        return {"status": "error", "message": result.get("error_description", f"登录失败: {error}")}

                    if "access_token" in result:
                        self._poll_result = result
                        return {"status": "ready", "message": "授权完成，等待完成登录"}

                    self._poll_future = None
                    return {"status": "pending", "message": "等待用户授权..."}

                except (RuntimeError, KeyError, TypeError, ValueError) as e:
                    error_str = str(e)
                    if "authorization_pending" in error_str or "AADSTS70016" in error_str:
                        self._poll_future = None
                        return {"status": "pending", "message": "等待用户授权..."}
                    self._cleanup_poll()
                    return {"status": "error", "message": f"轮询出错: {error_str}"}
            else:
                return {"status": "pending", "message": "等待用户授权..."}

        try:
            if self._poll_executor is None:
                self._poll_executor = ThreadPoolExecutor(max_workers=1)

            self._poll_future = self._poll_executor.submit(
                self._pending_app.acquire_token_by_device_flow, self._pending_flow
            )
            return {"status": "pending", "message": "等待用户授权..."}

        except (RuntimeError, ValueError, TypeError) as e:
            error_str = str(e)
            logger.error(f"启动轮询任务失败: {error_str}")
            return {"status": "pending", "message": "等待用户授权..."}

    def _cleanup_poll(self) -> None:
        if self._poll_future and not self._poll_future.done():
            self._poll_future.cancel()
        self._poll_future = None
        if self._poll_executor is not None:
            self._poll_executor.shutdown(wait=False)
            self._poll_executor = None

    def _cleanup_pending_login(self) -> None:
        self._cleanup_poll()
        self._pending_flow = None
        self._pending_app = None
        self._poll_result = None
        self._pending_cache_file = None

    def shutdown(self) -> None:
        # 关闭所有资源：取消轮询、清理 pending 登录状态
        self._cleanup_pending_login()
        logger.debug("MultiAccountMinecraftAuth 资源已清理")

    def open_browser_for_auth(self, url: str) -> bool:
        try:
            webbrowser.open(url)
            return True
        except (OSError, ValueError, TypeError) as e:
            logger.error(f"打开浏览器失败: {e}")
            return False

    def complete_microsoft_login(self) -> dict:
        self._ensure_initialized()
        if not self._pending_flow:
            return {"success": False, "message": "没有待处理的登录流程"}
        try:
            if self._poll_result:
                result = self._poll_result
                self._poll_result = None
            else:
                result = self._pending_app.acquire_token_by_device_flow(self._pending_flow)

            if "access_token" not in result:
                return {"success": False, "message": f"登录失败: {result.get('error_description', '未知错误')}"}
            email = ""
            if "id_token_claims" in result:
                id_claims = result["id_token_claims"]
                email = id_claims.get("preferred_username") or id_claims.get("email", "")
            ms_token = result["access_token"]
            xsts_token, user_hash = self._get_xbox_chain_tokens(ms_token)
            if not xsts_token:
                return {"success": False, "message": "Xbox 认证失败"}
            mc_token = self._get_minecraft_token(xsts_token, user_hash)
            if not mc_token:
                return {"success": False, "message": "Minecraft 认证失败"}
            has_minecraft, profile = self._check_minecraft_ownership(mc_token)
            if not has_minecraft:
                cache_path = self.data_dir / "cache" / f"{self._pending_cache_file}.bin"
                if cache_path.exists():
                    cache_path.unlink()
                return {"success": False, "message": "该账户未购买 Minecraft Java 版"}
            alias = profile["name"]

            # 优先从 MSAL 账户列表获取 home_account_id 作为唯一标识
            msal_accounts = self._pending_app.get_accounts() if self._pending_app else []
            if msal_accounts:
                account_id = msal_accounts[0].get("home_account_id") or f"account_{len(self.accounts) + 1}"
            else:
                account_id = (
                    result.get("id_token_claims", {}).get("home_account_id") or f"account_{len(self.accounts) + 1}"
                )

            logger.debug(f"微软登录 account_id: {account_id}, 当前已有账户数: {len(self.accounts)}")

            if account_id in self.accounts:
                cache_path = self.data_dir / "cache" / f"{self._pending_cache_file}.bin"
                if cache_path.exists():
                    cache_path.unlink()
                self._cleanup_pending_login()
                return {"success": False, "message": f"微软账户 '{alias}' 已存在"}

            for existing_account in self.accounts.values():
                if existing_account.account_type == "microsoft" and existing_account.alias == alias:
                    cache_path = self.data_dir / "cache" / f"{self._pending_cache_file}.bin"
                    if cache_path.exists():
                        cache_path.unlink()
                    self._cleanup_pending_login()
                    return {"success": False, "message": f"玩家名 '{alias}' 的微软账户已存在"}

            account = MinecraftAccount(
                alias=alias,
                account_id=account_id,
                email=email or "未知",
                profile=profile,
                cache_file=self._pending_cache_file,
                account_type="microsoft",
            )
            self.accounts[account_id] = account
            self._save_accounts()
            self._save_cache(self._pending_app.token_cache)
            if len(self.accounts) == 1:
                self._set_current_account(account)
            self._cleanup_pending_login()
            return {
                "success": True,
                "message": f"账户 '{alias}' 添加成功",
                "account": {"id": account_id, "alias": alias, "type": "microsoft", "email": email},
            }
        except (
            OSError,
            json.JSONDecodeError,
            ValueError,
            KeyError,
            TypeError,
            RuntimeError,
            requests.exceptions.RequestException,
        ) as e:
            return {"success": False, "message": f"登录过程出错: {e}"}
