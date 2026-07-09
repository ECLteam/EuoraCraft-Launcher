import asyncio
import os
import platform
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..common.logger import get_logger
from .models import JavaInfo

logger = get_logger("java")


class JavaDetector:
    _executor: ThreadPoolExecutor | None = None

    def __init__(self) -> None:
        self.java_list: list[JavaInfo] = []
        self._candidate_cache: dict[str, tuple[Path, str]] = {}
        self.is_windows: bool = platform.system() == "Windows"
        self.is_macos: bool = platform.system() == "Darwin"

    @classmethod
    def __get_executor(cls) -> ThreadPoolExecutor:
        if cls._executor is None:
            cls._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="java_detect")
        return cls._executor

    @classmethod
    def shutdown_executor(cls) -> None:
        if cls._executor is not None:
            cls._executor.shutdown(wait=False)
            cls._executor = None

    def detect_all(self) -> list[JavaInfo]:
        logger.debug("开始扫描 Java...")

        if self.is_windows:
            self._scan_registry()

        self._scan_environment()

        if not self.is_windows:
            self._scan_unix_tools()

        self._validate_and_deduplicate()
        self.java_list.sort(key=lambda x: x.major_version, reverse=True)

        logger.info(f"扫描完成，共找到 {len(self.java_list)} 个有效 Java")
        return self.java_list

    async def detect_all_parallel(self):
        logger.debug("开始并行扫描 Java...")
        loop = asyncio.get_running_loop()

        async def _run_scan(fn):
            return await loop.run_in_executor(self.__get_executor(), fn)

        scan_tasks = [_run_scan(self._scan_environment)]
        if self.is_windows:
            scan_tasks.append(_run_scan(self._scan_registry))
        if not self.is_windows:
            scan_tasks.append(_run_scan(self._scan_unix_tools))

        results = await asyncio.gather(*scan_tasks, return_exceptions=True)
        for i, r in enumerate(results):
            if isinstance(r, BaseException):
                logger.error(f"Java 扫描子任务 {i} 失败: {r}")

        self._validate_and_deduplicate()
        self.java_list.sort(key=lambda x: x.major_version, reverse=True)
        logger.info(f"并行扫描完成，共找到 {len(self.java_list)} 个有效 Java")
        return self.java_list

    def _add_candidate(self, path: Path, source: str) -> None:
        if not path.exists():
            return

        normalized = path.resolve()
        bin_dir = str(normalized.parent).lower()

        if bin_dir in self._candidate_cache:
            _existing_path, _ = self._candidate_cache[bin_dir]
            if self.is_windows and "javaw" in normalized.name.lower():
                self._candidate_cache[bin_dir] = (normalized, source)
        else:
            self._candidate_cache[bin_dir] = (normalized, source)

    def _scan_registry(self) -> None:
        if not self.is_windows:
            return

        try:
            import winreg
        except ImportError:
            return

        logger.debug("正在读取注册表...")

        registry_configs = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\JavaSoft\Java Runtime Environment", "JRE"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\JavaSoft\Java Development Kit", "JDK"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\JavaSoft\JDK", "JDK"),
        ]

        if platform.machine().endswith("64"):
            registry_configs.extend(
                [
                    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\JavaSoft\Java Runtime Environment", "JRE"),
                    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\JavaSoft\Java Development Kit", "JDK"),
                    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\JavaSoft\JDK", "JDK"),
                ]
            )

        for hkey, sub_path, java_type in registry_configs:
            try:
                with winreg.OpenKey(hkey, sub_path) as key:
                    index = 0
                    while True:
                        try:
                            version_name = winreg.EnumKey(key, index)
                            version_key_path = f"{sub_path}\\{version_name}"

                            with winreg.OpenKey(hkey, version_key_path) as version_key:
                                java_home, _ = winreg.QueryValueEx(version_key, "JavaHome")
                                if not java_home or not Path(java_home).exists():
                                    index += 1
                                    continue

                                java_home_path = Path(java_home)
                                javaw = java_home_path / "bin" / "javaw.exe"
                                java = java_home_path / "bin" / "java.exe"

                                target = javaw if javaw.exists() else java
                                if target.exists():
                                    self._add_candidate(target, f"registry_{java_type}")
                            index += 1
                        except OSError:
                            break
            except FileNotFoundError:
                pass
            except (OSError, ValueError, TypeError, KeyError, RuntimeError) as e:
                logger.error(f"注册表读取错误: {e}")

    def _scan_environment(self) -> None:
        logger.debug("正在检查环境变量...")

        java_home = os.environ.get("JAVA_HOME")
        if java_home:
            base = Path(java_home) / "bin"
            for exe in ["javaw.exe", "java.exe"] if self.is_windows else ["java"]:
                if (full := base / exe).exists():
                    self._add_candidate(full, "env_java_home")
                    break

        path_env = os.environ.get("PATH", "")
        for path_dir in path_env.split(os.pathsep):
            path_dir = path_dir.strip('"')
            if not path_dir:
                continue
            for exe in ["javaw.exe", "java.exe"] if self.is_windows else ["java"]:
                if (full := Path(path_dir) / exe).exists():
                    self._add_candidate(full, "env_path")

    def _scan_unix_tools(self) -> None:
        logger.debug("正在扫描 Unix 工具链...")

        try:
            result = subprocess.run(["which", "java"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0 and (path := Path(result.stdout.strip())).exists():
                real_path = path.resolve()
                self._add_candidate(real_path, "which_java")
        except (OSError, subprocess.TimeoutExpired, ValueError, TypeError):
            pass

        if not self.is_macos:
            try:
                result = subprocess.run(
                    ["update-alternatives", "--list", "java"], capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    for line in result.stdout.strip().split("\n"):
                        if line and (path := Path(line)).exists():
                            self._add_candidate(path.resolve(), "update_alternatives")
            except (OSError, subprocess.TimeoutExpired, ValueError, TypeError):
                pass

    def _validate_and_deduplicate(self) -> None:
        logger.debug(f"发现 {len(self._candidate_cache)} 个唯一目录，开始验证...")

        validated: dict[str, JavaInfo] = {}

        for path, source in self._candidate_cache.values():
            info = self._validate_java(path, source)
            if not info:
                continue

            if info._unique_key in validated:
                validated[info._unique_key].sources.extend(info.sources)
            else:
                validated[info._unique_key] = info

        self.java_list = list(validated.values())

    def _validate_java(self, path: Path, source: str) -> JavaInfo | None:
        exec_path = path.with_name("java.exe") if self.is_windows and "javaw" in path.name.lower() else path

        try:
            result = subprocess.run(
                [str(exec_path), "-version"], capture_output=True, timeout=10, encoding="utf-8", errors="ignore"
            )
        except (OSError, subprocess.TimeoutExpired):
            return None

        output = result.stderr or result.stdout
        if not output:
            return None

        return self._parse_version_output(path, output, source, exec_path)

    def _is_jdk(self, java_home: Path, output: str) -> bool:
        if (java_home / "jmods").exists():
            return True
        if (java_home / "lib" / "tools.jar").exists():
            return True
        return "jdk" in output.lower() or "development" in output.lower()

    def _parse_version_output(self, path: Path, output: str, source: str, exec_path: Path) -> JavaInfo | None:
        version_match = re.search(r'version\s+"(\d+[\.\d]*[_\+]?\d*)"', output, re.IGNORECASE)
        if not version_match:
            return None

        version_str = version_match.group(1)
        major = int(version_str.split(".")[1]) if version_str.startswith("1.") else int(version_str.split(".")[0])

        java_home = exec_path.parent.parent
        java_type = "JDK" if self._is_jdk(java_home, output) else "JRE"

        arch = "64-bit"
        if any(x in output for x in ["32-Bit", "i586", "i686", "x86"]):
            arch = "32-bit"

        return JavaInfo(
            path=path, version=version_str, major_version=major, java_type=java_type, arch=arch, sources=[source]
        )
