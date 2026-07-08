import base64
import contextlib
import hashlib
import os
from collections.abc import Callable
from pathlib import Path

import keyring
import keyring.errors
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from ..common.logger import get_logger

logger = get_logger("auth.crypto")


class SmartKeyringManager:
    def __init__(self, service_name: str = "ECLAuth", log_callback: Callable[[str], None] | None = None):
        self.service_name = service_name
        self.backend_type: str = "unknown"
        self.log_callback = log_callback or print
        self._setup_smart_keyring()

    def _log(self, msg: str) -> None:
        self.log_callback(msg)

    def _setup_smart_keyring(self) -> None:
        backends = [
            self._try_system_keyring,
            self._try_encrypted_file_keyring,
            self._try_json_file_keyring,
            self._try_custom_fallback,
        ]
        for backend in backends:
            if backend():
                self._log(f"密钥环后端: {self.backend_type}")
                return
        raise RuntimeError("无法初始化任何密钥环后端")

    def _try_system_keyring(self) -> bool:
        try:
            test_key = f"test_key_{hashlib.md5(self.service_name.encode()).hexdigest()}"
            keyring.set_password(self.service_name, test_key, "test_value")
            result = keyring.get_password(self.service_name, test_key)
            keyring.delete_password(self.service_name, test_key)
            if result == "test_value":
                self.backend_type = "system"
                self._log("使用系统密钥环")
                return True
        except (keyring.errors.KeyringError, OSError, ValueError, TypeError) as e:
            self._log(f"系统密钥环不可用: {e}")
        return False

    def _try_encrypted_file_keyring(self) -> bool:
        try:
            from keyrings.alt.file import EncryptedKeyring

            keyring_obj = EncryptedKeyring()
            test_key = "test_encrypted"
            keyring_obj.set_password(self.service_name, test_key, "test")
            result = keyring_obj.get_password(self.service_name, test_key)
            keyring_obj.delete_password(self.service_name, test_key)
            if result == "test":
                keyring.set_keyring(keyring_obj)
                self.backend_type = "encrypted_file"
                self._log("使用加密文件密钥环")
                return True
        except (ImportError, OSError, ValueError, TypeError, KeyError, RuntimeError) as e:
            self._log(f"加密文件密钥环失败: {e}")
        return False

    def _try_json_file_keyring(self) -> bool:
        try:
            from keyrings.alt.file import JSONKeyring

            keyring_obj = JSONKeyring()
            test_key = "test_json"
            keyring_obj.set_password(self.service_name, test_key, "test")
            result = keyring_obj.get_password(self.service_name, test_key)
            keyring_obj.delete_password(self.service_name, test_key)
            if result == "test":
                keyring.set_keyring(keyring_obj)
                self.backend_type = "json_file"
                self._log("使用 JSON 密钥环")
                return True
        except (ImportError, OSError, ValueError, TypeError, KeyError, RuntimeError) as e:
            self._log(f"JSON 密钥环失败: {e}")
        return False

    def _try_custom_fallback(self) -> bool:
        try:

            class CustomFallbackKeyring:
                def __init__(self):
                    self.storage_file = Path("~/.ECLAuth/custom_keyring.bin").expanduser()
                    self.storage_file.parent.mkdir(parents=True, exist_ok=True)
                    self.key_file = Path.home() / ".euoracraft" / "keyring.key"
                    self.key_file.parent.mkdir(parents=True, exist_ok=True)
                    if self.key_file.exists():
                        self.key = self.key_file.read_bytes()
                    else:
                        self.key = Fernet.generate_key()
                        self.key_file.write_bytes(self.key)
                        with contextlib.suppress(OSError):
                            self.key_file.chmod(0o600)
                    self.fernet = Fernet(self.key)

                def set_password(self, service: str, username: str, password: str) -> None:
                    entries = []
                    target_key = f"{service}|{username}"
                    if self.storage_file.exists():
                        with self.storage_file.open("rb") as f:
                            for line in f:
                                line = line.strip()
                                if not line:
                                    continue
                                try:
                                    decrypted = self.fernet.decrypt(line).decode()
                                    s, u, _ = decrypted.split("|", 2)
                                    if f"{s}|{u}" != target_key:
                                        entries.append(line)
                                except (InvalidToken, ValueError, KeyError, TypeError):
                                    entries.append(line)
                    new_data = f"{service}|{username}|{password}"
                    encrypted = self.fernet.encrypt(new_data.encode())
                    entries.append(encrypted)
                    with self.storage_file.open("wb") as f:
                        for entry in entries:
                            f.write(entry + b"\n")

                def get_password(self, service: str, username: str) -> str | None:
                    try:
                        with self.storage_file.open("rb") as f:
                            for line in f:
                                try:
                                    decrypted = self.fernet.decrypt(line.strip()).decode()
                                    s, u, p = decrypted.split("|", 2)
                                    if s == service and u == username:
                                        return p
                                except (InvalidToken, ValueError, KeyError, TypeError):
                                    continue
                    except FileNotFoundError:
                        pass
                    return None

            keyring.set_keyring(CustomFallbackKeyring())
            self.backend_type = "custom_fallback"
            self._log("使用自定义回退密钥环")
            return True
        except (OSError, ValueError, TypeError) as e:
            self._log(f"自定义回退失败: {e}")
        return False

    def get_backend_info(self) -> dict:
        return {
            "type": self.backend_type,
            "service": self.service_name,
            "secure": self.backend_type not in ["plaintext_file", "custom_fallback"],
        }


class EncryptionManager:
    def __init__(
        self,
        service_name: str = "ECLAuth",
        log_callback: Callable[[str], None] | None = None,
    ):
        self.service_name = service_name
        self.data_dir = Path("~/.ECLAuth").expanduser()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.salt_file = self.data_dir / "encryption_salt.bin"
        self.log_callback = log_callback or print
        self.keyring_manager = SmartKeyringManager(service_name, self._log)
        self.fernet = None
        self._needs_password = False
        self._ensure_encryption_key()

    def _log(self, msg: str) -> None:
        self.log_callback(msg)

    def _ensure_encryption_key(self) -> None:
        encryption_key = keyring.get_password(self.service_name, "encryption_key")
        if encryption_key:
            self.fernet = Fernet(encryption_key.encode())
            return
        self._needs_password = True

    def needs_password(self) -> bool:
        return self._needs_password

    def set_password(self, password: str) -> None:
        if len(password) < 8:
            raise ValueError("密码长度至少8位")
        self._generate_and_store_key(password)
        self._needs_password = False

    def change_password(self, new_password: str) -> Fernet:
        if not self.fernet:
            raise RuntimeError("加密管理器未初始化")
        old_fernet = self.fernet
        salt = self.salt_file.read_bytes() if self.salt_file.exists() else os.urandom(16)
        if not self.salt_file.exists():
            self.salt_file.write_bytes(salt)
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=600000)
        new_key = base64.urlsafe_b64encode(kdf.derive(new_password.encode()))
        keyring.set_password(self.service_name, "encryption_key", new_key.decode())
        self.fernet = Fernet(new_key)
        self._log("主密码已更新")
        return old_fernet

    def _generate_and_store_key(self, password: str) -> None:
        if self.salt_file.exists():
            salt = self.salt_file.read_bytes()
        else:
            salt = os.urandom(16)
            self.salt_file.write_bytes(salt)
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=600000)
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        keyring.set_password(self.service_name, "encryption_key", key.decode())
        self.fernet = Fernet(key)
        backend_info = self.keyring_manager.get_backend_info()
        self._log("加密设置完成")
        if not backend_info["secure"]:
            self._log("当前使用安全性较低的后端")

    def encrypt_data(self, data: str) -> str:
        if not self.fernet:
            raise RuntimeError("加密管理器未初始化")
        encrypted = self.fernet.encrypt(data.encode())
        return base64.urlsafe_b64encode(encrypted).decode()

    def decrypt_data(self, encrypted_data: str) -> str:
        if not self.fernet:
            raise RuntimeError("加密管理器未初始化")
        try:
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_data.encode())
            decrypted = self.fernet.decrypt(encrypted_bytes)
            return decrypted.decode()
        except (InvalidToken, ValueError, TypeError) as e:
            raise ValueError(f"解密失败: {e}") from e
