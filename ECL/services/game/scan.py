import json
import re
from copy import deepcopy
from pathlib import Path
from threading import Thread
from time import monotonic
from typing import Any

from ECL.utils import atomic_write_text

from .base import GameServiceError, VersionScanError, _GameState


class ScanCoordinator(_GameState):
    @staticmethod
    def _normalize_scan_paths(value: Any) -> list[Path]:
        if isinstance(value, (str, Path)):
            raw_paths = [value]
        elif isinstance(value, list):
            raw_paths = value
        else:
            raise VersionScanError("实例路径必须是字符串或字符串数组", "INVALID_GAME_PATH")

        paths: list[Path] = []
        seen: set[str] = set()
        for raw_path in raw_paths:
            if not isinstance(raw_path, (str, Path)):
                raise VersionScanError("实例路径数组只能包含字符串", "INVALID_GAME_PATH")
            path_value = str(raw_path).strip()
            if not path_value:
                continue
            path = Path(path_value).expanduser()
            if path.name.casefold() == "versions":
                path = path.parent
            path_key = str(path.resolve(strict=False)).casefold()
            if path_key in seen:
                continue
            seen.add(path_key)
            paths.append(path)
        if not paths:
            raise VersionScanError("至少需要一个有效的实例路径", "INVALID_GAME_PATH")
        return paths

    @staticmethod
    def _normalize_scanned_loader(value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            return "Vanilla"
        return value.strip()

    @staticmethod
    def _normalize_scanned_version(
        game_path: Path,
        version_name: str,
        raw_info: Any,
    ) -> dict[str, Any]:
        info = raw_info if isinstance(raw_info, dict) else {}
        version_path_value = info.get("VersionPath")
        version_path = (
            Path(version_path_value)
            if isinstance(version_path_value, str) and version_path_value.strip()
            else game_path / "versions" / version_name
        )
        json_path = version_path / f"{version_name}.json"
        vanilla_version = info.get("VanillaVersion")
        vanilla_name = (
            vanilla_version.strip()
            if isinstance(vanilla_version, str) and vanilla_version.strip() and vanilla_version != "Unknown"
            else version_name
        )
        version_type = str(info.get("VanillaType") or "").strip() or "release"
        primary_loader = ScanCoordinator._normalize_scanned_loader(info.get("LoaderType"))
        loader_key = primary_loader.casefold()
        has_optifine = loader_key == "optifine"
        loader_version = str(info.get("LoaderVersion") or "").strip()
        if loader_version == "Unknown":
            loader_version = ""
        required_java_value = str(info.get("RequestJava") or "").strip()
        required_java = int(required_java_value) if required_java_value.isdigit() else None
        return {
            "id": version_name,
            "versionId": version_name,
            "versionType": version_type,
            "path": str(game_path),
            "displayName": version_name,
            "primaryLoader": primary_loader,
            "loaderVersion": loader_version,
            "vanillaName": vanilla_name,
            "requiredJava": required_java,
            "hasForge": loader_key == "forge",
            "hasNeoForge": "neoforged" in loader_key or loader_key == "neoforge",
            "hasFabric": loader_key in {"fabric", "legacyfabric", "babric"},
            "hasQuilt": loader_key == "quilt",
            "hasOptiFine": has_optifine,
            "isBroken": not json_path.is_file(),
            "jsonPath": str(json_path),
            "sourceName": game_path.name or str(game_path),
        }

    @staticmethod
    def _version_path_key(game_path: Path) -> str:
        return str(game_path.resolve(strict=False)).casefold()

    @staticmethod
    def _version_directory_snapshot(game_path: Path) -> tuple[tuple[str, int, int], ...]:
        """
        生成轻量版本目录快照，只跟踪目录项和直接 JSON 文件。

        :param game_path: Minecraft 游戏根目录
        """
        versions_path = game_path / "versions"
        records: list[tuple[str, int, int]] = []

        def append_stat(relative_path: str, path: Path) -> None:
            try:
                stat = path.stat()
            except OSError:
                return
            records.append((relative_path, stat.st_mtime_ns, stat.st_size))

        if not versions_path.is_dir():
            return ()
        append_stat(".", versions_path)
        try:
            version_directories = [entry for entry in versions_path.iterdir() if entry.is_dir()]
        except OSError:
            return tuple(records)
        for version_directory in version_directories:
            append_stat(f"{version_directory.name}/", version_directory)
            try:
                json_files = version_directory.glob("*.json")
                for json_file in json_files:
                    if json_file.is_file():
                        append_stat(f"{version_directory.name}/{json_file.name}", json_file)
            except OSError:
                continue
        return tuple(sorted(records))

    def _watch_version_path(self, game_path: Path) -> str:
        key = self._version_path_key(game_path)
        snapshot = self._version_directory_snapshot(game_path)
        thread: Thread | None = None
        with self._lock:
            previous_snapshot = self._version_watch_snapshots.get(key)
            self._version_watch_paths[key] = game_path
            self._version_watch_snapshots[key] = snapshot
            if previous_snapshot is not None and previous_snapshot != snapshot:
                self._version_scan_cache.pop(key, None)
                self._version_watch_pending[key] = monotonic()
            if self._version_watcher_enabled and (
                self._version_watch_thread is None or not self._version_watch_thread.is_alive()
            ):
                self._version_watch_stop.clear()
                thread = Thread(target=self._version_watch_loop, name="ECL-VersionWatcher", daemon=True)
                self._version_watch_thread = thread
        if thread is not None:
            thread.start()
        return key

    def _poll_version_changes(self, now: float | None = None) -> list[str]:
        current_time = monotonic() if now is None else now
        with self._lock:
            watched_paths = list(self._version_watch_paths.items())

        changed_paths: list[str] = []
        for key, game_path in watched_paths:
            snapshot = self._version_directory_snapshot(game_path)
            with self._lock:
                if key not in self._version_watch_paths:
                    continue
                previous_snapshot = self._version_watch_snapshots.get(key)
                if previous_snapshot != snapshot:
                    self._version_watch_snapshots[key] = snapshot
                    self._version_scan_cache.pop(key, None)
                    self._version_watch_pending[key] = current_time
                pending_since = self._version_watch_pending.get(key)
                if pending_since is None or current_time - pending_since < self._version_watch_debounce:
                    continue
                self._version_watch_pending.pop(key, None)
                changed_paths.append(str(game_path.resolve(strict=False)))

        for game_path in changed_paths:
            self.events.emit("game:versions_changed", {"gamePath": game_path})
        return changed_paths

    def _version_watch_loop(self) -> None:
        while not self._version_watch_stop.wait(self._version_watch_interval):
            try:
                self._poll_version_changes()
            except Exception:
                self.logger.exception("监视 Minecraft 版本目录失败")

    def _scan_game_path(self, game_path: Path) -> list[dict[str, Any]]:
        versions_path = game_path / "versions"
        if not versions_path.is_dir():
            self.logger.debug("跳过不存在的版本目录: %s", versions_path)
            return []
        try:
            versions = self._search_factory(game_path).search_minecraft()
        except (OSError, TypeError, ValueError) as exc:
            self.logger.exception("扫描 Minecraft 版本失败: %s", game_path)
            raise VersionScanError(f"扫描游戏目录失败: {game_path}: {exc}") from exc
        if not isinstance(versions, dict):
            raise VersionScanError(f"版本扫描器返回了无效数据: {game_path}")
        return [
            self._normalize_scanned_version(game_path, version_name.strip(), info)
            for version_name, info in versions.items()
            if isinstance(version_name, str) and version_name.strip()
        ]

    def scan_versions(self, paths: Any, *, force: bool = False) -> list[dict[str, Any]]:
        """
        扫描 Minecraft 目录；目录未变化时复用缓存结果。

        :param paths: 用户指定的扫描路径列表
        :param force: 是否忽略有效缓存并重新扫描
        """
        scanned_versions: list[dict[str, Any]] = []
        normalized_paths = list(self._normalize_scan_paths(paths))
        self.logger.debug("开始扫描版本目录，共 %d 个路径，force=%s", len(normalized_paths), force)
        for game_path in normalized_paths:
            key = self._watch_version_path(game_path)
            # 确保每个游戏路径下都有 ecl.json
            self._ensure_ecl_config(game_path)
            with self._lock:
                cached_versions = None if force else self._version_scan_cache.get(key)
            if cached_versions is None:
                self.logger.debug("扫描版本目录: %s", game_path)
                versions = self._scan_game_path(game_path)
                with self._lock:
                    self._version_scan_cache[key] = deepcopy(versions)
                    self._version_watch_snapshots[key] = self._version_directory_snapshot(game_path)
                    self._version_watch_pending.pop(key, None)
            else:
                self.logger.debug("扫描版本目录: %s，共 %d 个版本", game_path, len(cached_versions))
                versions = deepcopy(cached_versions)
            scanned_versions.extend(versions)
        self.logger.debug("版本扫描完成，共 %d 个实例", len(scanned_versions))
        return sorted(
            scanned_versions,
            key=lambda item: (str(item["sourceName"]).casefold(), str(item["displayName"]).casefold()),
        )

    def _ecl_json_path(self, game_path: Any) -> Path:
        path = self._normalize_game_path(game_path)
        return path / self._ECL_JSON_NAME

    def _ensure_ecl_config(self, game_path: Any) -> None:
        """
        如果游戏路径下不存在 ecl.json，则创建默认配置文件。

        :param game_path: Minecraft 游戏根目录
        """
        ecl_path = self._ecl_json_path(game_path)
        if ecl_path.is_file():
            return
        try:
            ecl_path.parent.mkdir(parents=True, exist_ok=True)
            default_config = {
                "activeVersion": "",
                "lastLaunched": "",
            }
            atomic_write_text(ecl_path, json.dumps(default_config, ensure_ascii=False, indent=2))
            self.logger.debug("初始化默认 ecl.json: %s", ecl_path)
        except OSError as exc:
            self.logger.warning("初始化 ecl.json 失败 %s: %s", ecl_path, exc)

    def read_ecl_config(self, game_path: Any) -> dict[str, Any]:
        """
        读取指定游戏路径下的 ecl.json，文件不存在或损坏时返回空字典。

        :param game_path: Minecraft 游戏根目录
        """
        ecl_path = self._ecl_json_path(game_path)
        if not ecl_path.is_file():
            self.logger.debug("ecl.json 不存在，返回空配置: %s", ecl_path)
            return {}
        try:
            raw = ecl_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            result = data if isinstance(data, dict) else {}
            self.logger.debug("读取 ecl.json 成功: %s，activeVersion=%s", ecl_path, result.get("activeVersion", ""))
            return result
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            self.logger.warning("读取 ecl.json 失败 %s: %s", ecl_path, exc)
            return {}

    def write_ecl_config(self, game_path: Any, data: dict[str, Any]) -> None:
        """
        写入 ecl.json 到指定游戏路径。

        :param game_path: Minecraft 游戏根目录
        :param data: 需要处理或持久化的数据
        """
        if not isinstance(data, dict):
            raise GameServiceError("ecl.json 数据必须是字典", "INVALID_ECL_CONFIG")
        ecl_path = self._ecl_json_path(game_path)
        self.logger.debug("写入 ecl.json: %s，activeVersion=%s", ecl_path, data.get("activeVersion", ""))
        try:
            ecl_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(ecl_path, json.dumps(data, ensure_ascii=False, indent=2))
        except OSError as exc:
            raise GameServiceError(f"写入 ecl.json 失败: {exc}", "ECL_CONFIG_WRITE_FAILED") from exc

    def patch_ecl_config(self, game_path: Any, patch: dict[str, Any]) -> dict[str, Any]:
        """
        合并更新 ecl.json 中的部分字段，返回更新后的完整配置。

        :param game_path: Minecraft 游戏根目录
        :param patch: 需要合并到原配置的字段
        """
        if not isinstance(patch, dict):
            raise GameServiceError("ecl.json 增量数据必须是字典", "INVALID_ECL_CONFIG")
        self.logger.debug("增量更新 ecl.json: %s，字段=%s", self._ecl_json_path(game_path), list(patch.keys()))
        current = self.read_ecl_config(game_path)
        current.update(patch)
        self.write_ecl_config(game_path, current)
        return current

    def get_active_version(self, game_path: Any) -> str | None:
        """
        从 ecl.json 读取当前路径下的启动版本；没有则返回 None。

        :param game_path: Minecraft 游戏根目录
        """
        config = self.read_ecl_config(game_path)
        version_id = config.get("activeVersion") or config.get("active_version")
        result = str(version_id).strip() if isinstance(version_id, str) and version_id.strip() else None
        self.logger.debug("获取当前路径启动版本: %s -> %s", game_path, result)
        return result

    def set_active_version(self, game_path: Any, version_id: Any) -> None:
        """
        把当前路径的启动版本写入 ecl.json。

        :param game_path: Minecraft 游戏根目录
        :param version_id: Minecraft 版本或实例标识
        """
        name = self._normalize_version_name(version_id, "实例名称")
        self.logger.debug("设置当前路径启动版本: %s -> %s", game_path, name)
        self.patch_ecl_config(game_path, {"activeVersion": name})

    @staticmethod
    def _java_major_version(version: Any) -> int:
        value = str(version or "").strip()
        if value.startswith("1."):
            value = value[2:]
        match = re.match(r"\d+", value)
        return int(match.group()) if match else 0

    def scan_java(self, user_java_paths: list[str] | None = None) -> list[dict[str, Any]]:
        """
        扫描 Java 运行时。

        :param user_java_paths: 用户配置的 Java 搜索路径
        """
        user_paths = [path for path in user_java_paths or [] if isinstance(path, str) and path.strip()]
        self.logger.debug("开始扫描 Java 运行时，用户自定义路径: %s", user_paths)
        scanner = self._java_scanner_factory(
            cache_file=self._java_cache_file,
            user_java_paths=user_paths,
        )
        self._java_runtimes = scanner.scan()
        self.logger.debug("Java 扫描完成，共发现 %d 个运行时", len(self._java_runtimes))
        installations = []
        for runtime in self._java_runtimes:
            architecture = str(runtime.architecture or "unknown").lower()
            architecture = {
                "amd64": "x64",
                "x86_64": "x64",
                "aarch64": "arm64",
                "i386": "x86",
                "i686": "x86",
            }.get(architecture, architecture)
            path = str(runtime.path)
            installations.append(
                {
                    "path": path,
                    "version": str(runtime.version),
                    "major_version": self._java_major_version(runtime.version),
                    "java_type": runtime.vendor or ("JDK" if runtime.is_jdk else "JRE"),
                    "arch": architecture,
                    "sources": ["user" if path in user_paths else "system"],
                }
            )
        return sorted(
            installations,
            key=lambda item: (-item["major_version"], item["java_type"].casefold(), item["path"].casefold()),
        )
