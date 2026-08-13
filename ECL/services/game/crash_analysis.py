from __future__ import annotations

import json
import os
import re
import shutil
import stat
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from threading import RLock
from typing import Any, Literal
from uuid import uuid4
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile, ZipInfo

from ECL.utils import get_logger

from .base import GameServiceError

# 分析流程参考 HMCL 的 CrashReportAnalyzer（GNU GPL v3）：
# https://github.com/HMCL-dev/HMCL/blob/main/HMCLCore/src/main/java/org/jackhuang/hmcl/game/CrashReportAnalyzer.java
# 本模块针对 ECL 的进程模型重新设计并以 Python 独立实现。

Confidence = Literal["certain", "likely", "possible"]

_MAX_SOURCE_BYTES = 16 * 1024 * 1024
_MAX_ARCHIVE_FILES = 100
_MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
_MAX_ANALYSIS_CHARS = 6 * 1024 * 1024
_MAX_EVIDENCE_LENGTH = 320
_STALE_SESSION_SECONDS = 24 * 60 * 60
_LOG_SETTLE_SECONDS = 2.0

_TEXT_SUFFIXES = frozenset({".log", ".txt"})
_CRASH_FILE_NAMES = frozenset({"latest.log", "debug.log"})
_REDACTION_PATTERNS = (
    re.compile(r"(?i)(--accessToken\s+)(\S+)"),
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)(\S+)"),
    re.compile(r"(?i)((?:access[_-]?token|client[_-]?token|password|session)\s*[:=]\s*)([^\s,;]+)"),
)


@dataclass(frozen=True)
class _Rule:
    code: str
    confidence: Confidence
    priority: int
    patterns: tuple[re.Pattern[str], ...]


@dataclass
class _ReportRecord:
    result: dict[str, Any]
    output: str
    directory: Path


def _patterns(*values: str) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(value, re.IGNORECASE) for value in values)


# 规则只匹配 Minecraft、JVM 与主流加载器的公开输出；原因代码和前端文案均为 ECL 自有定义。
_RULES = (
    _Rule("jvm.invalid_arguments", "certain", 0, _patterns(r"unrecognized (?:vm )?option", r"could not create the java virtual machine")),
    _Rule("memory.out_of_memory", "certain", 0, _patterns(r"outofmemoryerror", r"out of physical ram", r"out of memory error", r"could not reserve enough space")),
    _Rule("java.incompatible_version", "certain", 0, _patterns(r"unsupported class file (?:major|minor) version", r"compiled by a more recent version of the java runtime", r"level is not supported by the active jre")),
    _Rule("java.module_access", "likely", 0, _patterns(r"module java\.base does not (?:export|open)", r"inaccessibleobjectexception", r"java\.lang\.nosuchfieldexception: ucp")),
    _Rule("java.legacy_forge", "likely", 0, _patterns(r"manifestentryverifier", r"unable to make protected final java\.lang\.class")),
    _Rule("java.openj9", "certain", 0, _patterns(r"openj9 is (?:not supported|incompatible)", r"j9vminternals")),
    _Rule("java.32bit_heap", "likely", 0, _patterns(r"invalid maximum heap size", r"unable to allocate .* object heap")),
    _Rule("java.architecture_mismatch", "likely", 0, _patterns(r"can.t load (?:amd )?64-bit .* on a 32-bit platform", r"wrong elf class", r"%1 is not a valid win32 application")),
    _Rule("graphics.opengl_unsupported", "certain", 0, _patterns(r"driver does not appear to support opengl", r"pixel format not accelerated", r"couldn.t set pixel format")),
    _Rule("graphics.driver_crash", "likely", 0, _patterns(r"exception_access_violation", r"problematic frame:.*(?:nvoglv|atio|ig\w*)")),
    _Rule("jvm.native_crash", "likely", 0, _patterns(r"a fatal error has been detected by the java runtime environment", r"internal error \(.*?\), pid=\d+", r"sigsegv")),
    _Rule("native.library_missing", "likely", 0, _patterns(r"unsatisfiedlinkerror", r"failed to locate library", r"no .* in java\.library\.path")),
    _Rule("files.integrity_failure", "likely", 0, _patterns(r"signer information does not match", r"invalid or corrupt jarfile", r"zip error:.*invalid")),
    _Rule("loader.install_incomplete", "likely", 0, _patterns(r"cannot find launch target fmlclient", r"invalid paths argument.*fmlcore", r"classnotfoundexception:.*(?:modlauncher|fabricloader)")),
    _Rule("mod.extracted_jar", "certain", 0, _patterns(r"extracted mod jars? found", r"directories below appear to be extracted jar files")),
    _Rule("mod.duplicate", "certain", 0, _patterns(r"duplicatemodsfoundexception", r"found duplicate mods?", r"modresolutionexception:\s*duplicate")),
    _Rule("mod.missing_dependency", "certain", 0, _patterns(r"missing or unsupported mandatory dependencies", r"depends on .* which is missing", r"requires version .* of .* but only")),
    _Rule("mod.incompatible", "certain", 0, _patterns(r"incompatible mods found", r"some of your mods are incompatible", r"mod resolution encountered an incompatible mod set")),
    _Rule("mod.mixin_failure", "likely", 1, _patterns(r"mixin (?:prepare|apply|transform) failed", r"mixinbootstrap.*(?:not found|missing)", r"invalidmixinexception")),
    _Rule("mod.config_failure", "likely", 1, _patterns(r"failed loading config file", r"parsingexception", r"failed to load config .* for mod")),
    _Rule("mod.initialization_failure", "likely", 1, _patterns(r"failed to create mod instance", r"caught exception from ", r"exception during mod loading")),
    _Rule("mod.loader_reported", "likely", 1, _patterns(r"failure message:", r"a potential solution has been determined", r"mod loading has failed")),
    _Rule("mod.optifine_conflict", "likely", 1, _patterns(r"optifine.*(?:incompatible|not compatible)", r"shaders mod detected.*optifine", r"optifine.*nosuchmethoderror")),
    _Rule("resource.render_failure", "likely", 1, _patterns(r"1282:\s*invalid operation", r"lower resolution resourcepack", r"texture.*(?:too large|out of memory)")),
    _Rule("world.block_failure", "likely", 1, _patterns(r"block location:\s*world:", r"ticking block")),
    _Rule("world.entity_failure", "likely", 1, _patterns(r"entity.s exact location:", r"ticking entity")),
    _Rule("game.manual_debug_crash", "certain", 1, _patterns(r"manually triggered debug crash")),
    _Rule("game.crash_report", "likely", 2, _patterns(r"crash report saved to", r"this crash report has been saved to", r"could not save crash report")),
)

_IGNORED_STACK_PREFIXES = (
    "java.",
    "javax.",
    "jdk.",
    "sun.",
    "com.mojang.",
    "net.minecraft.",
    "net.minecraftforge.",
    "net.fabricmc.",
    "org.spongepowered.",
    "org.lwjgl.",
    "com.google.",
    "org.apache.",
)


class CrashAnalyzer:
    """
    分析 Minecraft 与 JVM 日志，并管理一次启动器会话内的临时报告。

    分析流程参考 GPL-3.0 项目 HMCL 的规则表与堆栈降级思路，但规则表达、原因代码、
    证据抽取和报告格式均为 EuoraCraft Launcher 的独立实现。临时目录由本对象独占，
    关闭后不保留分析历史。

    :param data_path: 启动器数据目录，用于临时报告和默认导出位置
    """

    def __init__(self, data_path: Path | str):
        self.logger = get_logger("CrashAnalyzer")
        self.data_path = Path(data_path).resolve(strict=False)
        self._sessions_root = self.data_path / "temp" / "crash-analysis"
        self._sessions_root.mkdir(parents=True, exist_ok=True)
        self._cleanup_stale_sessions()
        self._temporary = TemporaryDirectory(
            prefix=f"{os.getpid()}-",
            dir=self._sessions_root,
            ignore_cleanup_errors=True,
        )
        self.session_path = Path(self._temporary.name)
        self._reports: dict[str, _ReportRecord] = {}
        self._lock = RLock()
        self._closed = False

    def _cleanup_stale_sessions(self) -> None:
        cutoff = time.time() - _STALE_SESSION_SECONDS
        for path in self._sessions_root.iterdir():
            try:
                if path.is_dir() and path.stat().st_mtime < cutoff:
                    shutil.rmtree(path, ignore_errors=True)
            except OSError:
                self.logger.warning("清理过期崩溃分析目录失败: %s", path, exc_info=True)

    @staticmethod
    def _redact(value: str) -> str:
        redacted = value
        for pattern in _REDACTION_PATTERNS:
            redacted = pattern.sub(r"\1***", redacted)
        try:
            home = str(Path.home())
            if home:
                redacted = redacted.replace(home, "%USERPROFILE%").replace(home.replace("\\", "/"), "%USERPROFILE%")
        except RuntimeError:
            pass
        return redacted

    @staticmethod
    def _read_bounded(path: Path, *, reject_oversize: bool = False) -> str:
        with path.open("rb") as stream:
            data = stream.read(_MAX_SOURCE_BYTES + 1)
        if len(data) > _MAX_SOURCE_BYTES:
            if reject_oversize:
                raise GameServiceError("崩溃分析文件过大", "CRASH_FILE_TOO_LARGE")
            head = data[: _MAX_SOURCE_BYTES // 3]
            tail = data[-(_MAX_SOURCE_BYTES * 2 // 3) :]
            data = head + b"\n[ECL: oversized log truncated]\n" + tail
        if b"\0" in data[:4096]:
            raise GameServiceError("崩溃分析文件不是文本日志", "CRASH_FILE_NOT_TEXT")
        return data.decode("utf-8", errors="replace")

    @staticmethod
    def _safe_member(info: ZipInfo) -> PurePosixPath:
        """
        验证压缩成员不是路径穿越、符号链接、嵌套压缩包或二进制文件。

        :param info: ZIP 中尚未解压的成员元数据
        :return: 可安全用于扁平化目标名称的 POSIX 路径
        """
        member = PurePosixPath(info.filename.replace("\\", "/"))
        if member.is_absolute() or ".." in member.parts or not member.name:
            raise GameServiceError("压缩包包含不安全路径", "CRASH_ARCHIVE_UNSAFE")
        mode = info.external_attr >> 16
        if stat.S_ISLNK(mode):
            raise GameServiceError("压缩包包含符号链接", "CRASH_ARCHIVE_UNSAFE")
        if member.suffix.casefold() not in _TEXT_SUFFIXES:
            raise GameServiceError("压缩包包含不支持的文件类型", "CRASH_ARCHIVE_UNSUPPORTED")
        return member

    def _import_archive(self, source: Path, destination: Path) -> list[Path]:
        """
        在文件数和总解压量限制内提取可分析文本。

        :param source: 用户选择的 ZIP 文件
        :param destination: 当前会话报告独占的提取目录
        :return: 已提取并等待脱敏的文本文件
        """
        imported: list[Path] = []
        total_size = 0
        try:
            with ZipFile(source) as archive:
                members = [entry for entry in archive.infolist() if not entry.is_dir()]
                if len(members) > _MAX_ARCHIVE_FILES:
                    raise GameServiceError("崩溃报告压缩包文件数量过多", "CRASH_ARCHIVE_TOO_LARGE")
                for index, info in enumerate(members):
                    member = self._safe_member(info)
                    if info.file_size > _MAX_SOURCE_BYTES:
                        raise GameServiceError("压缩包中的单个日志过大", "CRASH_ARCHIVE_TOO_LARGE")
                    total_size += info.file_size
                    if total_size > _MAX_ARCHIVE_BYTES:
                        raise GameServiceError("崩溃报告压缩包解压后过大", "CRASH_ARCHIVE_TOO_LARGE")
                    target = destination / f"{index:03d}-{member.name}"
                    target.write_bytes(archive.read(info))
                    imported.append(target)
        except BadZipFile as exc:
            raise GameServiceError("崩溃报告压缩包已损坏", "CRASH_ARCHIVE_INVALID") from exc
        return imported

    def _copy_text(self, source: Path, destination: Path, *, reject_oversize: bool = False) -> str:
        content = self._redact(self._read_bounded(source, reject_oversize=reject_oversize))
        destination.write_text(content, encoding="utf-8")
        return content

    @staticmethod
    def _candidate_files(game_path: Path, version_id: str, game_directory: Path) -> list[Path]:
        version_path = game_path / "versions" / version_id
        directories = {
            game_path,
            version_path,
            game_directory,
            game_path / "logs",
            version_path / "logs",
            game_directory / "logs",
            game_path / "crash-reports",
            version_path / "crash-reports",
            game_directory / "crash-reports",
        }
        candidates: set[Path] = set()
        for directory in directories:
            if not directory.is_dir():
                continue
            try:
                for path in directory.iterdir():
                    name = path.name.casefold()
                    if not path.is_file():
                        continue
                    if (
                        name in _CRASH_FILE_NAMES
                        or name.startswith("crash-")
                        or name.startswith("hs_err_pid")
                    ) and path.suffix.casefold() in _TEXT_SUFFIXES:
                        candidates.add(path.resolve(strict=False))
            except OSError:
                continue
        return sorted(candidates, key=lambda item: str(item).casefold())

    def _collect_runtime_sources(
        self,
        report_dir: Path,
        *,
        game_path: Path,
        version_id: str,
        game_directory: Path,
        started_wall_time: float,
        output_lines: list[str],
    ) -> tuple[list[Path], str]:
        """
        等待日志短暂落盘，并收集本次进程启动后更新的候选文本。

        :return: 报告内的来源文件和脱敏后的实时输出
        """
        sources_dir = report_dir / "sources"
        sources_dir.mkdir()
        output = self._redact("\n".join(output_lines[-500:]))
        output_path = sources_dir / "game-output.log"
        output_path.write_text(output, encoding="utf-8")
        collected = [output_path]
        deadline = time.monotonic() + _LOG_SETTLE_SECONDS
        candidates: list[Path] = []
        while True:
            candidates = []
            for source in self._candidate_files(game_path, version_id, game_directory):
                try:
                    if source.stat().st_mtime >= started_wall_time - 5:
                        candidates.append(source)
                except OSError:
                    continue
            if candidates or time.monotonic() >= deadline:
                break
            time.sleep(0.1)
        for index, source in enumerate(candidates):
            try:
                target = sources_dir / f"{index:03d}-{source.name}"
                self._copy_text(source, target)
                collected.append(target)
            except (OSError, GameServiceError):
                self.logger.warning("读取崩溃候选日志失败: %s", source, exc_info=True)
        return collected, output

    @staticmethod
    def _sanitize_metadata(value: Any) -> Any:
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                folded = str(key).casefold().replace("_", "").replace("-", "")
                if any(secret in folded for secret in ("token", "password", "credential", "session")):
                    result[key] = "***"
                else:
                    result[key] = CrashAnalyzer._sanitize_metadata(item)
            return result
        if isinstance(value, list):
            return [CrashAnalyzer._sanitize_metadata(item) for item in value]
        return value

    def _collect_context(self, report_dir: Path, game_path: Path, version_id: str) -> None:
        """
        收集脱敏版本元数据和最近的启动器日志。

        上下文文件仅用于用户主动导出的诊断包；任何读取失败都记录警告但不阻止分析。
        """
        metadata_dir = report_dir / "metadata"
        metadata_dir.mkdir(exist_ok=True)
        version_json = game_path / "versions" / version_id / f"{version_id}.json"
        try:
            if version_json.is_file() and version_json.stat().st_size <= _MAX_SOURCE_BYTES:
                raw = json.loads(version_json.read_text(encoding="utf-8"))
                sanitized = self._sanitize_metadata(raw)
                (metadata_dir / "version.json").write_text(
                    json.dumps(sanitized, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
            self.logger.warning("收集崩溃报告版本元数据失败: %s", version_json, exc_info=True)

        launcher_logs = self.data_path / "logs"
        if not launcher_logs.is_dir():
            return
        try:
            candidates = sorted(
                (path for path in launcher_logs.iterdir() if path.is_file() and path.suffix.casefold() == ".log"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )[:2]
        except OSError:
            self.logger.warning("枚举启动器日志失败", exc_info=True)
            return
        target_dir = report_dir / "launcher-logs"
        for source in candidates:
            try:
                target_dir.mkdir(exist_ok=True)
                self._copy_text(source, target_dir / source.name)
            except (OSError, GameServiceError):
                self.logger.warning("收集启动器日志失败: %s", source, exc_info=True)

    def _collect_manual_sources(self, report_dir: Path, source: Path) -> tuple[list[Path], str]:
        sources_dir = report_dir / "sources"
        sources_dir.mkdir()
        if source.suffix.casefold() == ".zip":
            imported = self._import_archive(source, sources_dir)
            collected = []
            for index, path in enumerate(imported):
                target = sources_dir / f"manual-{index:03d}-{path.name}"
                self._copy_text(path, target, reject_oversize=True)
                path.unlink(missing_ok=True)
                collected.append(target)
        elif source.suffix.casefold() in _TEXT_SUFFIXES:
            target = sources_dir / f"manual-{source.name}"
            self._copy_text(source, target, reject_oversize=True)
            collected = [target]
        else:
            raise GameServiceError("仅支持 .log、.txt 或 .zip 崩溃报告", "CRASH_FILE_UNSUPPORTED")
        output_path = next((path for path in collected if path.name.casefold().endswith(("latest.log", "debug.log"))), None)
        if output_path is None:
            output_path = collected[0] if collected else None
        output = output_path.read_text(encoding="utf-8", errors="replace") if output_path else ""
        return collected, output

    @staticmethod
    def _evidence(text: str, pattern: re.Pattern[str]) -> list[str]:
        evidence: list[str] = []
        for line in text.splitlines():
            if pattern.search(line):
                normalized = " ".join(line.strip().split())[:_MAX_EVIDENCE_LENGTH]
                if normalized and normalized not in evidence:
                    evidence.append(normalized)
                if len(evidence) == 3:
                    break
        return evidence

    @staticmethod
    def _parameters(code: str, evidence: list[str]) -> dict[str, Any]:
        joined = "\n".join(evidence)
        result: dict[str, Any] = {}
        jar_names = sorted(set(re.findall(r"[\w .+@()\[\]-]+\.jar", joined, re.IGNORECASE)))
        if jar_names:
            result["files"] = [name.strip() for name in jar_names[:8]]
        if code == "world.block_failure":
            match = re.search(r"(?:Block|ticking block)[^\n]{0,80}", joined, re.IGNORECASE)
            if match:
                result["block"] = match.group(0).strip()
        elif code == "world.entity_failure":
            match = re.search(r"(?:Entity|ticking entity)[^\n]{0,100}", joined, re.IGNORECASE)
            if match:
                result["entity"] = match.group(0).strip()
        return result

    def _match_rules(self, text: str) -> list[dict[str, Any]]:
        matches: list[tuple[_Rule, list[str]]] = []
        for rule in _RULES:
            evidence: list[str] = []
            for pattern in rule.patterns:
                evidence.extend(item for item in self._evidence(text, pattern) if item not in evidence)
            if evidence:
                matches.append((rule, evidence[:3]))
        if not matches:
            return []
        selected_priority = min(rule.priority for rule, _ in matches)
        return [
            {
                "code": rule.code,
                "confidence": rule.confidence,
                "evidence": evidence,
                "parameters": self._parameters(rule.code, evidence),
            }
            for rule, evidence in matches
            if rule.priority == selected_priority
        ]

    @staticmethod
    def _stack_candidates(text: str) -> list[str]:
        candidates: list[str] = []
        for match in re.finditer(r"\bat\s+([A-Za-z_$][\w$]*(?:\.[\w$]+){2,})", text):
            class_name = match.group(1)
            if class_name.startswith(_IGNORED_STACK_PREFIXES):
                continue
            package = ".".join(class_name.split(".")[:3])
            if package not in candidates:
                candidates.append(package)
            if len(candidates) == 12:
                break
        return candidates

    @staticmethod
    def _mod_display_name(archive: ZipFile, fallback: str) -> str:
        try:
            if "fabric.mod.json" in archive.namelist():
                metadata = json.loads(archive.read("fabric.mod.json")[: 512 * 1024].decode("utf-8", errors="replace"))
                if isinstance(metadata, dict):
                    name = metadata.get("name") or metadata.get("id")
                    if isinstance(name, str) and name.strip():
                        return name.strip()[:120]
            for metadata_name in ("META-INF/neoforge.mods.toml", "META-INF/mods.toml"):
                if metadata_name not in archive.namelist():
                    continue
                content = archive.read(metadata_name)[: 512 * 1024].decode("utf-8", errors="replace")
                match = re.search(r'(?m)^\s*(?:displayName|modId)\s*=\s*["\']([^"\']+)', content)
                if match:
                    return match.group(1).strip()[:120]
        except (BadZipFile, KeyError, OSError, UnicodeError, json.JSONDecodeError):
            pass
        return fallback

    @staticmethod
    def _mod_package_map(mods_dirs: list[Path]) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for mods_dir in mods_dirs:
            if not mods_dir.is_dir():
                continue
            for jar in mods_dir.iterdir():
                if not jar.is_file() or jar.suffix.casefold() != ".jar":
                    continue
                try:
                    with ZipFile(jar) as archive:
                        display_name = CrashAnalyzer._mod_display_name(archive, jar.stem)
                        names = archive.namelist()
                        for name in names[:5000]:
                            if not name.endswith(".class") or name.startswith(("net/minecraft/", "java/", "com/mojang/")):
                                continue
                            parts = PurePosixPath(name).parts
                            if len(parts) >= 4:
                                mapping.setdefault(".".join(parts[:3]), display_name)
                except (BadZipFile, OSError):
                    continue
        return mapping

    def _stack_reason(self, text: str, game_path: Path, game_directory: Path) -> dict[str, Any] | None:
        candidates = self._stack_candidates(text)
        if not candidates:
            return None
        package_map = self._mod_package_map([game_path / "mods", game_directory / "mods"])
        mods = sorted({name for package in candidates for prefix, name in package_map.items() if package.startswith(prefix)})
        if mods:
            return {
                "code": "stack.suspected_mod",
                "confidence": "possible",
                "evidence": candidates[:5],
                "parameters": {"mods": mods[:8]},
            }
        return {
            "code": "stack.suspected_component",
            "confidence": "possible",
            "evidence": candidates[:5],
            "parameters": {"packages": candidates[:8]},
        }

    def _analyze_text(self, texts: list[str], game_path: Path, game_directory: Path) -> list[dict[str, Any]]:
        combined = "\n".join(texts)
        if len(combined) > _MAX_ANALYSIS_CHARS:
            combined = combined[: _MAX_ANALYSIS_CHARS // 2] + "\n" + combined[-(_MAX_ANALYSIS_CHARS // 2) :]
        reasons = self._match_rules(combined)
        if reasons:
            return reasons
        stack_reason = self._stack_reason(combined, game_path, game_directory)
        if stack_reason:
            return [stack_reason]
        code = "unknown.no_logs" if not combined.strip() else "unknown.unclassified"
        return [{"code": code, "confidence": "possible", "evidence": [], "parameters": {}}]

    def _save_report(
        self,
        *,
        report_id: str,
        report_dir: Path,
        version_id: str,
        exit_code: int | None,
        detected_by: list[str],
        sources: list[Path],
        output: str,
        game_path: Path,
        game_directory: Path,
    ) -> dict[str, Any]:
        self._collect_context(report_dir, game_path, version_id)
        texts = [path.read_text(encoding="utf-8", errors="replace") for path in sources]
        reasons = self._analyze_text(texts, game_path, game_directory)
        result: dict[str, Any] = {
            "reportId": report_id,
            "versionId": version_id,
            "exitCode": exit_code,
            "detectedBy": list(dict.fromkeys(detected_by)),
            "reasons": reasons,
            "sourceFiles": [path.name for path in sources],
            "hasOutput": bool(output.strip()),
        }
        (report_dir / "analysis.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        readable = [f"EuoraCraft Minecraft crash report {report_id}", f"Version: {version_id}"]
        if exit_code is not None:
            readable.append(f"Exit code: {exit_code}")
        readable.append(f"Detected by: {', '.join(result['detectedBy']) or 'manual'}")
        for reason in reasons:
            readable.append(f"- {reason['code']} ({reason['confidence']})")
            readable.extend(f"  {line}" for line in reason["evidence"])
        (report_dir / "analysis.txt").write_text("\n".join(readable), encoding="utf-8")
        with self._lock:
            if self._closed:
                raise GameServiceError("崩溃分析服务已关闭", "CRASH_ANALYZER_CLOSED")
            self._reports[report_id] = _ReportRecord(result=result, output=output, directory=report_dir)
        return dict(result)

    def analyze_runtime(
        self,
        *,
        version_id: str,
        game_path: Path,
        game_directory: Path,
        started_wall_time: float,
        output_lines: list[str],
        exit_code: int,
        detected_by: list[str],
    ) -> dict[str, Any]:
        """
        收集一次已退出游戏的相关日志并生成会话报告。

        :param version_id: 版本目录名称
        :param game_path: Minecraft 根目录
        :param game_directory: 启动参数实际使用的游戏目录
        :param started_wall_time: 本次进程创建时的墙上时钟时间戳
        :param output_lines: 进程退出前保留的输出行
        :param exit_code: Java 进程退出码
        :param detected_by: 触发崩溃判定的稳定信号名称
        :return: 可发送到前端的结构化分析结果
        """
        report_id = uuid4().hex
        report_dir = self.session_path / report_id
        report_dir.mkdir()
        sources, output = self._collect_runtime_sources(
            report_dir,
            game_path=game_path,
            version_id=version_id,
            game_directory=game_directory,
            started_wall_time=started_wall_time,
            output_lines=output_lines,
        )
        return self._save_report(
            report_id=report_id,
            report_dir=report_dir,
            version_id=version_id,
            exit_code=exit_code,
            detected_by=detected_by,
            sources=sources,
            output=output,
            game_path=game_path,
            game_directory=game_directory,
        )

    def analyze_file(self, file_path: Path, game_path: Path, version_id: str) -> dict[str, Any]:
        """
        导入用户选择的文本日志或 ZIP 并生成会话报告。

        :param file_path: 用户明确选择的日志或压缩包
        :param game_path: 用于关联模组目录的 Minecraft 根目录
        :param version_id: 用于结果展示和版本元数据关联的版本名称
        :return: 可发送到前端的结构化分析结果
        """
        source = file_path.expanduser().resolve(strict=False)
        if not source.is_file():
            raise GameServiceError("崩溃分析文件不存在", "CRASH_FILE_NOT_FOUND")
        report_id = uuid4().hex
        report_dir = self.session_path / report_id
        report_dir.mkdir()
        try:
            sources, output = self._collect_manual_sources(report_dir, source)
            return self._save_report(
                report_id=report_id,
                report_dir=report_dir,
                version_id=version_id,
                exit_code=None,
                detected_by=["manual"],
                sources=sources,
                output=output,
                game_path=game_path,
                game_directory=game_path / "versions" / version_id,
            )
        except Exception:
            shutil.rmtree(report_dir, ignore_errors=True)
            raise

    def output(self, report_id: str) -> dict[str, str]:
        """
        返回报告对应的已脱敏游戏输出。

        :param report_id: 当前会话内的崩溃报告编号
        :return: 输出名称与内容
        """
        with self._lock:
            record = self._reports.get(report_id)
        if record is None:
            raise GameServiceError("崩溃报告不存在或已过期", "CRASH_REPORT_NOT_FOUND")
        return {"name": "game-output.log", "content": record.output}

    def export(self, report_id: str, output_path: Path | None = None) -> dict[str, str]:
        """
        将当前会话中的单个报告原子导出为 ZIP。

        :param report_id: 当前会话内的崩溃报告编号
        :param output_path: 可选目标路径；缺失时写入启动器 exports 目录
        :return: 导出 ZIP 的绝对路径
        """
        with self._lock:
            record = self._reports.get(report_id)
        if record is None:
            raise GameServiceError("崩溃报告不存在或已过期", "CRASH_REPORT_NOT_FOUND")
        if output_path is None:
            safe_version = re.sub(r"[^A-Za-z0-9._-]+", "-", str(record.result["versionId"]))[:48] or "Minecraft"
            target = self.data_path / "exports" / f"EuoraCraft-crash-{safe_version}-{report_id[:8]}.zip"
        else:
            target = output_path.expanduser().resolve(strict=False)
            if target.suffix.casefold() != ".zip":
                target = target.with_suffix(".zip")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
        try:
            with ZipFile(temporary, "w", compression=ZIP_DEFLATED) as archive:
                for path in sorted(record.directory.rglob("*")):
                    if path.is_file():
                        archive.write(path, arcname=path.relative_to(record.directory).as_posix())
            temporary.replace(target)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        return {"path": str(target)}

    def close(self) -> None:
        """
        清空报告索引并删除本次会话创建的全部临时文件。
        """
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._reports.clear()
        self._temporary.cleanup()


__all__ = ["CrashAnalyzer"]
