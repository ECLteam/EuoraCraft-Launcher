from __future__ import annotations

import json
import os
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from ECL.utils import atomic_write_text, get_logger

# 待应用更新的状态标记文件名，位于启动器数据目录下。
PENDING_UPDATE_FILE = ".pending_update.json"

# 自动更新通道白名单；alpha（预发布通道）与 dev（源码运行）不开放自更新。
_SELF_UPDATE_CHANNELS = frozenset({"beta", "rc", "release"})

# 下载写入缓冲区大小（字节）。
_DOWNLOAD_CHUNK_BYTES = 64 * 1024

# 需要同步复制到新启动器旁的配套文件（仅打包目录形态存在时启用）。
_COMPANION_FILE_NAMES = frozenset({"version.json"})

# 平台对应的安装包特征词；命中即视为该平台使用的文件。
_WINDOWS_KEYWORDS = ("windows", "win", "win32", "amd64", "x64", "x86_64")
_LINUX_KEYWORDS = ("linux", "linux-x86_64", "appimage")
_DARWIN_KEYWORDS = ("macos", "mac", "darwin", "dmg", "app")

# 各种打包旁路文件，不参与安装包挑选。
_SIDECAR_PATTERNS = (
    ".sha256",
    ".sha512",
    ".md5",
    ".pdb",
    ".debug",
    "-symbols.",
    "checksums",
    "latest.",
)

# 可执行文件后缀；单文件优先，其次 zip 包。
_EXECUTABLE_SUFFIXES = (".exe", ".appimage", ".deb", ".rpm", ".bin")


class AppUpdateError(ValueError):
    """
    启动器自动更新流程中的用户可感知错误。

    :param message: 面向用户的错误描述
    :param error_code: 稳定错误码，供前端区分呈现形式
    :param phase: 发生错误的阶段（select / download / verify / stage / apply）
    """

    def __init__(self, message: str, *, error_code: str = "APP_UPDATE_FAILED", phase: str = "stage") -> None:
        super().__init__(message)
        self.error_code = error_code
        self.phase = phase


@dataclass(frozen=True, slots=True)
class UpdateAsset:
    """
    Release 中与当前平台匹配的安装包。

    :param name: 资产文件名
    :param url: 资产下载地址
    :param size: 期望字节数，未知时为 0
    """

    name: str
    url: str
    size: int = 0


@dataclass(frozen=True, slots=True)
class StagedUpdate:
    """
    一次已下载并待应用的新版本替换计划。

    :param version: 目标版本号
    :param new_binary: 待替换的新启动器可执行文件
    :param target: 当前运行的启动器可执行文件（sys.executable）
    :param backup: 替换前的旧文件备份路径
    """

    version: str
    new_binary: Path
    target: Path
    backup: Path


def _is_http_url(url: str) -> bool:
    # 校验地址是否为带主机的 HTTP(S) URL。
    try:
        parsed = urlsplit(url)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.hostname)


def _name_tokens(name: str) -> list[str]:
    # 把资产文件名拆成小写关键词，用于平台匹配。
    import re

    text = name.lower()
    tokens = set(re.split(r"[._\-\s]+", text))
    tokens.add(text)
    return list(tokens)


def _is_sidecar(name: str) -> bool:
    # 判断文件是否为校验和、符号等非安装包旁路文件。
    lowered = name.lower()
    return any(pattern in lowered for pattern in _SIDECAR_PATTERNS) and not lowered.endswith(".exe")


def _is_platform_asset(name: str, platform: str) -> bool:
    # 按平台特征词判断资产是否属于当前平台。
    tokens = _name_tokens(name)
    keywords = (
        _WINDOWS_KEYWORDS
        if platform == "win32"
        else (_DARWIN_KEYWORDS if platform == "darwin" else (_LINUX_KEYWORDS if platform.startswith("linux") else ()))
    )
    if any(token in keywords for token in tokens):
        return True
    # 跨平台资产通常带架构但不带系统词，仅当无任何系统特征时视为通用包。
    return not any(token in (_WINDOWS_KEYWORDS + _LINUX_KEYWORDS + _DARWIN_KEYWORDS) for token in tokens)


def _binary_suffix(name: str) -> bool:
    # 判断资产是否为可直接执行的单文件包。
    lowered = name.lower()
    return any(lowered.endswith(ext) for ext in _EXECUTABLE_SUFFIXES) or lowered.endswith(".zip")


def _peer_digest_asset(release: dict[str, Any], name: str) -> str | None:
    # 查找与新包同名的 .sha256 校验清单；GitHub 资产页会生成 digest 资产。
    base = Path(name).name
    digest_candidates = [f"{base}.sha256", f"{base}.sha512"]
    for item in release.get("assets") or []:
        if not isinstance(item, dict):
            continue
        asset_name = str(item.get("name") or "")
        if asset_name in digest_candidates:
            return str(item.get("browser_download_url") or "") or None
    return None


def _find_exe_inside(directory: Path) -> Path:
    # 在解压目录中定位当前平台的可执行文件，找不到时抛出错误。
    for path in sorted(directory.rglob("*.exe")) if sys.platform == "win32" else sorted(directory.iterdir()):
        if path.is_file():
            return path
    raise AppUpdateError("请升级包未包含可执行文件，无法应用", error_code="UPDATE_PACKAGE_INVALID", phase="verify")


class UpdateApplier:
    """
    执行启动器自动更新：挑选安装包、下载校验、落盘替换计划并拉起重启。

    运行中的启动器无法直接覆盖自身，因此采用「先写好替换计划，再退出由独立
    引导脚本完成替换并重启」的延迟替换策略。alpha 与源码运行（dev）不开放。

    :param app_path: 启动器可执行文件所在目录
    :param data_path: 启动器持久化数据目录
    :param is_frozen: 是否运行于打包后的可执行文件
    :param version_type: 当前版本类型（alpha / beta / rc / release）
    :param current_version: 当前版本号
    :param http: 共享的启动器通道 HTTP 客户端
    :param event_bus: 应用事件总线，用于上报下载进度
    :param platform: 目标平台（默认取当前系统）
    """

    def __init__(
        self,
        *,
        app_path: Path | str,
        data_path: Path | str,
        is_frozen: bool,
        version_type: str,
        current_version: str,
        http: Any | None = None,
        event_bus: Any | None = None,
        platform: str | None = None,
    ) -> None:
        self.logger = get_logger("UpdateApplier")
        self.app_path = Path(app_path)
        self.data_path = Path(data_path)
        self.is_frozen = bool(is_frozen)
        self.version_type = version_type or "release"
        self.current_version = current_version
        self.http = http
        self.events = event_bus
        self._platform = platform or sys.platform
        self.updates_dir = self.data_path / "updates"
        self.pending_file = self.data_path / PENDING_UPDATE_FILE

    def enabled(self) -> bool:
        """
        判断当前运行形态是否允许自更新。

        :return: 打包运行且版本通道在 beta / rc / release 白名单内时为 True
        """
        return self.is_frozen and self.version_type in _SELF_UPDATE_CHANNELS

    def matching_asset(self, release: dict[str, Any]) -> UpdateAsset | None:
        """
        从版本 Release 中挑选与当前平台匹配的安装包。

        :param release: GitHub Release 对象
        :return: 匹配的安装包，无可用资产时返回 None
        """
        assets = release.get("assets") if isinstance(release, dict) else None
        if not isinstance(assets, list):
            return None
        candidates: list[UpdateAsset] = []
        for item in assets:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "")
            url = str(item.get("browser_download_url") or "")
            if not name or not url or not _is_http_url(url) or _is_sidecar(name):
                continue
            if not _is_platform_asset(name, self._platform):
                continue
            candidates.append(
                UpdateAsset(name=name, url=url, size=int(item.get("size") or 0))
            )
        if not candidates:
            return None
        executable = [candidate for candidate in candidates if candidate.name.lower().endswith(_EXECUTABLE_SUFFIXES)]
        return (executable or candidates)[0]

    def stage(
        self,
        release: dict[str, Any],
        *,
        asset: UpdateAsset | None = None,
        downloaded: Path | None = None,
        stage_dir: Path | None = None,
        target: Path | None = None,
    ) -> tuple[StagedUpdate, Path]:
        """
        为新版本准备可替换的二进制并落盘替换计划标记。

        :param release: GitHub Release 对象
        :param asset: 已选定的安装包，缺省时自动匹配
        :param downloaded: 已下载的安装包路径，缺省时自动下载
        :param stage_dir: 工作目录，缺省使用数据目录下的 updates 子目录
        :param target: 待替换的当前可执行文件路径，缺省取 sys.executable
        :return: 替换计划与已下载/解压后二进制路径
        :raises AppUpdateError: 挑选、下载或校验失败时抛出
        """
        asset = asset or self.matching_asset(release)
        if asset is None:
            raise AppUpdateError("未找到与当前系统匹配的安装包", error_code="UPDATE_ASSET_NOT_FOUND", phase="select")

        version = str(release.get("tag_name") or "unknown").lstrip("vV")
        stage_root = stage_dir or self.updates_dir / version
        stage_root.mkdir(parents=True, exist_ok=True)
        if downloaded is None:
            self._download_asset(asset, stage_root)
            downloaded = stage_root / asset.name
        if not downloaded.exists():
            raise AppUpdateError("请升级包下载失败，请重试", error_code="UPDATE_ASSET_MISSING", phase="verify")
        if asset.size > 0 and downloaded.stat().st_size != asset.size:
            raise AppUpdateError("请升级包下载不完整，请重试", error_code="UPDATE_VERIFY_FAILED", phase="verify")
        new_binary = self._prepare_binary(downloaded, stage_root)

        resolve_target = Path(target).resolve() if target else self._default_target()
        staged = StagedUpdate(
            version=version,
            new_binary=new_binary.resolve(),
            target=resolve_target,
            backup=stage_root / "launcher.old.exe" if self._platform == "win32" else stage_root / "launcher.old",
        )
        self._write_pending(staged)
        return staged, new_binary.resolve()

    def _default_target(self) -> Path:
        # 确定当前运行的可执行文件路径；源码运行不受支持。
        if sys.executable and Path(sys.executable).is_file():
            return Path(sys.executable).resolve()
        raise AppUpdateError("无法定位启动器可执行文件", error_code="UPDATE_TARGET_INVALID", phase="stage")

    def _download_asset(self, asset: UpdateAsset, stage_root: Path) -> None:
        # 流式下载安装包到临时文件，并通过事件总线上报进度。
        if self.http is None:
            raise AppUpdateError("更新通道不可用", error_code="UPDATE_CHANNEL_UNAVAILABLE", phase="download")
        temporary = stage_root / f"{asset.name}.part"
        received = 0
        try:
            with self.http.stream("GET", asset.url, follow_redirects=True) as response:
                response.raise_for_status()
                with temporary.open("wb") as handle:
                    for chunk in response.iter_bytes(_DOWNLOAD_CHUNK_BYTES):
                        handle.write(chunk)
                        received += len(chunk)
                        self._emit_progress(asset, received)
        except Exception as exc:
            temporary.unlink(missing_ok=True)
            self.logger.warning("安装包下载失败: %s", exc)
            raise AppUpdateError("请升级包下载失败，请检查网络后重试", error_code="UPDATE_DOWNLOAD_FAILED", phase="download") from exc
        self._emit_progress(asset, received, phase="complete")
        if asset.size > 0 and received != asset.size:
            temporary.unlink(missing_ok=True)
            raise AppUpdateError("请升级包下载不完整，请重试", error_code="UPDATE_VERIFY_FAILED", phase="verify")
        temporary.replace(stage_root / asset.name)

    def _emit_progress(self, asset: UpdateAsset, received: int, *, phase: str = "download") -> None:
        # 上报下载进度事件；事件总线缺失时静默跳过。
        if self.events is None:
            return
        self.events.emit(
            "update:progress",
            {"phase": phase, "name": asset.name, "received": received, "total": asset.size},
        )

    def _prepare_binary(self, downloaded: Path, stage_root: Path) -> Path:
        # 把安装包整理为可直接替换的可执行文件；压缩包先解压再定位。
        if downloaded.name.lower().endswith(".zip"):
            extract_dir = stage_root / "extract"
            extract_dir.mkdir(parents=True, exist_ok=True)
            try:
                with zipfile.ZipFile(downloaded) as archive:
                    archive.extractall(extract_dir)
            except (zipfile.BadZipFile, OSError) as exc:
                raise AppUpdateError("请升级包格式异常，无法应用", error_code="UPDATE_PACKAGE_INVALID", phase="verify") from exc
            return _find_exe_inside(extract_dir)
        return downloaded

    def _write_pending(self, staged: StagedUpdate) -> None:
        # 原子写入待应用更新的状态标记，供引导脚本与启动时清理读取。
        stage_root = staged.backup.parent
        marker = {
            "version": staged.version,
            "new_binary": str(staged.new_binary),
            "target": str(staged.target),
            "backup": str(staged.backup),
            "scheduled_at": datetime.now(UTC).isoformat(),
        }
        stage_root.mkdir(parents=True, exist_ok=True)
        atomic_write_text(self.pending_file, json.dumps(marker, ensure_ascii=False, indent=2))

    def bootstrap_script(self, staged: StagedUpdate, pid: int) -> tuple[str, str]:
        """
        生成在当前平台执行延迟替换的引导脚本内容。

        :param staged: 待应用的替换计划
        :param pid: 当前启动器进程号，供脚本等待其退出
        :return: ``(文件名, 脚本内容)``
        """
        if self._platform == "win32":
            return "apply_update.cmd", _win_bootstrap(
                pid=pid,
                target=str(staged.target),
                backup=str(staged.backup),
                new_binary=str(staged.new_binary),
                pending=str(self.pending_file),
            )
        return "apply_update.sh", _posix_bootstrap(
            pid=pid,
            target=str(staged.target),
            backup=str(staged.backup),
            new_binary=str(staged.new_binary),
            pending=str(self.pending_file),
        )

    def apply(self, staged: StagedUpdate, *, pid: int | None = None, bootstrap_path: Path | None = None) -> Path:
        """
        写入引导脚本并脱离当前进程拉起，随后由调用方请求退出重启。

        :param staged: 待应用的替换计划
        :param pid: 当前进程号，缺省取 os.getpid()
        :param bootstrap_path: 引导脚本写入位置，缺省放在数据目录
        :return: 已拉起引导脚本的路径
        """
        stage_root = staged.backup.parent
        stage_root.mkdir(parents=True, exist_ok=True)
        bootstrap_path = bootstrap_path or stage_root / ("apply_update.cmd" if self._platform == "win32" else "apply_update.sh")
        _, content = self.bootstrap_script(staged, pid if pid is not None else os.getpid())
        bootstrap_path.write_text(content, encoding="utf-8")
        self._run_detached(bootstrap_path)
        self.logger.info("已拉起更新引导脚本: %s", bootstrap_path)
        return bootstrap_path

    def _run_detached(self, script: Path) -> None:
        # 以脱离当前进程会话的方式启动引导脚本，使其在启动器退出后仍能执行。
        if self._platform == "win32":
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
            command: list[str] = ["cmd", "/c", str(script)]
        else:
            flags = 0
            command = ["/bin/sh", str(script)]
        subprocess.Popen(command, close_fds=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)

    def clear_pending(self) -> bool:
        """
        清理遗留的待更新标记，并尽可能删除未应用的旧备份。

        :return: 是否存在并被清理的待更新标记
        """
        return clear_stale_pending_update(self.data_path)

    def load_pending(self) -> StagedUpdate | None:
        """
        读取已落盘的待应用替换计划。

        :return: 替换计划；标记缺失或损坏时返回 None
        """
        if not self.pending_file.is_file():
            return None
        try:
            data = json.loads(self.pending_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        version = data.get("version")
        new_binary = data.get("new_binary")
        target = data.get("target")
        backup = data.get("backup")
        if not all(isinstance(field, str) and field for field in (version, new_binary, target, backup)):
            return None
        return StagedUpdate(
            version=str(version),
            new_binary=Path(str(new_binary)),
            target=Path(str(target)),
            backup=Path(str(backup)),
        )


def clear_stale_pending_update(data_path: Path | str) -> bool:
    """
    清理遗留的待更新标记，并尽可能删除未应用的旧备份。

    :param data_path: 启动器数据目录
    :return: 是否存在并被清理的待更新标记
    """
    pending_file = Path(data_path) / PENDING_UPDATE_FILE
    if not pending_file.is_file():
        return False
    try:
        data = json.loads(pending_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pending_file.unlink(missing_ok=True)
        return True
    backup = data.get("backup") if isinstance(data, dict) else None
    if isinstance(backup, str) and backup:
        Path(backup).unlink(missing_ok=True)
    pending_file.unlink(missing_ok=True)
    return True


def _win_bootstrap(*, pid: int, target: str, backup: str, new_binary: str, pending: str) -> str:
    # 生成 Windows 单文件 aborted 引导脚本：等待进程退出后备份、替换并重启。
    return "\r\n".join(
        [
            "@echo off",
            "setlocal",
            "rem 等待启动器进程退出，避免文件占用导致替换失败",
            ":wait",
            f'tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul',
            "if %errorlevel%==0 (",
            "  timeout /t 1 /nobreak >nul",
            "  goto wait",
            ")",
            f'move /y "{target}" "{backup}" >nul 2>&1',
            f'move /y "{new_binary}" "{target}" >nul 2>&1',
            f'start "" "{target}"',
            f'del /f /q "{backup}" >nul 2>&1',
            f'del /f /q "{pending}" >nul 2>&1',
            "exit /b 0",
        ]
    ) + "\r\n"


def _posix_bootstrap(*, pid: int, target: str, backup: str, new_binary: str, pending: str) -> str:
    # 生成 POSIX shell 引导脚本：等待进程退出后备份、替换并重启。
    import shlex

    return "\n".join(
        [
            "#!/bin/sh",
            f'while kill -0 {pid} 2>/dev/null; do sleep 1; done',
            f'mv {shlex.quote(target)} {shlex.quote(backup)}',
            f'mv {shlex.quote(new_binary)} {shlex.quote(target)}',
            f'rm -f {shlex.quote(backup)} {shlex.quote(pending)}',
            f'{shlex.quote(target)} "$@" &',
        ]
    ) + "\n"


__all__ = [
    "PENDING_UPDATE_FILE",
    "AppUpdateError",
    "StagedUpdate",
    "UpdateApplier",
    "UpdateAsset",
    "clear_stale_pending_update",
]
