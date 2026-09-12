#!/usr/bin/env python3
"""Audit writes and deletions beneath the ECL account directory on Windows.

Run this tool from an elevated PowerShell:

    python tools/ecl_account_audit.py install
    python tools/ecl_account_audit.py watch
    python tools/ecl_account_audit.py uninstall

``install`` adds one inheritable SACL rule for the requested directory and enables
the Windows "Audit File System" policy. ``watch`` converts Security event 4663
records to JSONL. The log intentionally excludes file contents and credentials.
"""

from __future__ import annotations

import argparse
import base64
import csv
import ctypes
import json
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ElementTree
from collections import deque
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

FILE_SYSTEM_AUDIT_GUID = "{0CCE921D-69AE-11D9-BED3-505054503030}"
EVENT_ID_FILE_ACCESS = "4663"
STATE_FILE_NAME = "ecl-account-audit-state.json"
LOG_FILE_NAME = "ecl-account-audit.jsonl"
MAX_SEEN_EVENT_IDS = 10_000


@dataclass(frozen=True, slots=True)
class AuditPolicy:
    """The enabled success/failure flags for Windows File System auditing."""

    success: bool
    failure: bool


def _default_target() -> Path:
    return Path.home() / ".ECL"


def _default_log_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "ECL_data" / "audit"


def _is_windows() -> bool:
    return os.name == "nt"


def is_administrator() -> bool:
    """Return whether this process has an elevated Windows security token."""
    if not _is_windows():
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError:
        return False


def require_administrator() -> None:
    """Fail before attempting to touch the Security event log or a directory SACL."""
    if not is_administrator():
        raise PermissionError("需要使用“以管理员身份运行”的 PowerShell 执行此命令")


def normalize_path(path: Path | str) -> str:
    """Return a case-insensitive, absolute Windows path for reliable filtering."""
    return os.path.normcase(str(Path(path).resolve()))


def is_under_target(path: str, target: Path | str) -> bool:
    """Return whether an event object path is exactly the target or one of its children."""
    normalized_path = normalize_path(path)
    normalized_target = normalize_path(target)
    return normalized_path == normalized_target or normalized_path.startswith(normalized_target + os.sep)


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, check=False, encoding="utf-8", errors="replace", text=True)


def _require_success(result: subprocess.CompletedProcess[str], operation: str) -> str:
    if result.returncode == 0:
        return result.stdout
    detail = (result.stderr or result.stdout).strip()
    raise RuntimeError(f"{operation}失败（退出码 {result.returncode}）: {detail or '未知错误'}")


def _powershell(script: str, target: Path) -> str:
    """Execute a fixed PowerShell script with the target passed through an environment variable."""
    encoded_script = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    environment = os.environ.copy()
    environment["ECL_ACCOUNT_AUDIT_TARGET"] = str(target)
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-EncodedCommand",
            encoded_script,
        ],
        capture_output=True,
        check=False,
        encoding="utf-8",
        errors="replace",
        text=True,
        env=environment,
    )
    return _require_success(result, "修改目录审计规则")


def _audit_rule_script(*, remove: bool) -> str:
    method = "RemoveAuditRuleSpecific" if remove else "AddAuditRule"
    return f"""
$ErrorActionPreference = 'Stop'
$target = [Environment]::GetEnvironmentVariable('ECL_ACCOUNT_AUDIT_TARGET', 'Process')
$acl = Get-Acl -LiteralPath $target -Audit
$rights = [System.Security.AccessControl.FileSystemRights]::WriteData -bor `
    [System.Security.AccessControl.FileSystemRights]::AppendData -bor `
    [System.Security.AccessControl.FileSystemRights]::WriteExtendedAttributes -bor `
    [System.Security.AccessControl.FileSystemRights]::WriteAttributes -bor `
    [System.Security.AccessControl.FileSystemRights]::Delete -bor `
    [System.Security.AccessControl.FileSystemRights]::DeleteSubdirectoriesAndFiles -bor `
    [System.Security.AccessControl.FileSystemRights]::ChangePermissions -bor `
    [System.Security.AccessControl.FileSystemRights]::TakeOwnership
$inheritance = [System.Security.AccessControl.InheritanceFlags]::ContainerInherit -bor `
    [System.Security.AccessControl.InheritanceFlags]::ObjectInherit
$flags = [System.Security.AccessControl.AuditFlags]::Success -bor `
    [System.Security.AccessControl.AuditFlags]::Failure
$rule = [System.Security.AccessControl.FileSystemAuditRule]::new(
    'Everyone', $rights, $inheritance,
    [System.Security.AccessControl.PropagationFlags]::None, $flags
)
$acl.{method}($rule)
Set-Acl -LiteralPath $target -AclObject $acl
"""


def _parse_policy_report(report: str) -> AuditPolicy:
    """Parse auditpol CSV output without depending on its localized column headers."""
    rows = list(csv.reader(line for line in report.splitlines() if line.strip()))
    if not rows or not rows[-1]:
        raise ValueError("无法解析 auditpol 的文件系统审计状态")
    state = " ".join(rows[-1]).casefold()
    success = "success" in state or "成功" in state
    failure = "failure" in state or "失败" in state
    if "no auditing" in state or "无审核" in state or "无审计" in state:
        return AuditPolicy(success=False, failure=False)
    return AuditPolicy(success=success, failure=failure)


def get_audit_policy() -> AuditPolicy:
    """Read the current Windows File System audit flags using a locale-neutral GUID."""
    result = _run(["auditpol.exe", "/get", f"/subcategory:{FILE_SYSTEM_AUDIT_GUID}", "/r"])
    return _parse_policy_report(_require_success(result, "读取 Windows 文件系统审计策略"))


def set_audit_policy(policy: AuditPolicy) -> None:
    """Set only the success/failure flags for the File System audit subcategory."""
    result = _run(
        [
            "auditpol.exe",
            "/set",
            f"/subcategory:{FILE_SYSTEM_AUDIT_GUID}",
            f"/success:{'enable' if policy.success else 'disable'}",
            f"/failure:{'enable' if policy.failure else 'disable'}",
        ]
    )
    _require_success(result, "设置 Windows 文件系统审计策略")


def _state_path(log_dir: Path) -> Path:
    return log_dir / STATE_FILE_NAME


def load_state(log_dir: Path) -> dict[str, Any] | None:
    """Read this tool's installation state; malformed state is never silently accepted."""
    path = _state_path(log_dir)
    if not path.is_file():
        return None
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"审计工具状态文件无效: {path}") from error
    if not isinstance(state, dict):
        raise RuntimeError(f"审计工具状态文件格式无效: {path}")
    return state


def save_state(log_dir: Path, state: dict[str, Any]) -> None:
    """Persist only non-sensitive install metadata for a later safe uninstall."""
    log_dir.mkdir(parents=True, exist_ok=True)
    path = _state_path(log_dir)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def install(target: Path, log_dir: Path) -> None:
    """Enable auditing and add exactly one inheritable audit rule to ``target``."""
    require_administrator()
    target = target.resolve(strict=True)
    existing = load_state(log_dir)
    if existing is not None:
        raise RuntimeError(f"审计规则已由本工具安装；请先执行 uninstall: {_state_path(log_dir)}")

    original_policy = get_audit_policy()
    try:
        set_audit_policy(AuditPolicy(success=True, failure=True))
        _powershell(_audit_rule_script(remove=False), target)
    except Exception:
        set_audit_policy(original_policy)
        raise

    save_state(
        log_dir,
        {
            "schema_version": 1,
            "target": str(target),
            "installed_at": datetime.now(UTC).isoformat(),
            "policy_before": asdict(original_policy),
            "policy_after": asdict(AuditPolicy(success=True, failure=True)),
        },
    )
    print(f"已安装目录审计规则: {target}")
    print(f"运行 watch 后，日志会写入: {log_dir / LOG_FILE_NAME}")


def uninstall(target: Path, log_dir: Path) -> None:
    """Remove only this tool's exact SACL rule and conditionally restore audit policy flags."""
    require_administrator()
    state = load_state(log_dir)
    if state is None:
        raise RuntimeError("未找到本工具的安装状态，拒绝猜测并删除审计规则")
    if normalize_path(state.get("target", "")) != normalize_path(target):
        raise RuntimeError("目标目录与安装状态不一致，拒绝删除审计规则")

    target = target.resolve(strict=True)
    _powershell(_audit_rule_script(remove=True), target)
    before = AuditPolicy(**state["policy_before"])
    after = AuditPolicy(**state["policy_after"])
    current = get_audit_policy()
    if current == after:
        set_audit_policy(before)
    else:
        print("文件系统审计策略已在安装期间被其他程序修改，保留当前策略，不自动覆盖。")
    _state_path(log_dir).unlink(missing_ok=True)
    print(f"已移除本工具的目录审计规则: {target}")


def _event_value(event: ElementTree.Element, name: str) -> str:
    namespace = "{http://schemas.microsoft.com/win/2004/08/events/event}"
    for item in event.findall(f".//{namespace}Data"):
        if item.attrib.get("Name") == name:
            return item.text or ""
    return ""


def _system_value(event: ElementTree.Element, name: str) -> str:
    namespace = "{http://schemas.microsoft.com/win/2004/08/events/event}"
    item = event.find(f".//{namespace}{name}")
    return item.text if item is not None and item.text else ""


def _event_timestamp(event: ElementTree.Element) -> str:
    namespace = "{http://schemas.microsoft.com/win/2004/08/events/event}"
    item = event.find(f".//{namespace}TimeCreated")
    return item.attrib.get("SystemTime", "") if item is not None else ""


def access_actions(access_mask: str) -> list[str]:
    """Translate relevant FileSystemRights bits into compact, non-localized action labels."""
    try:
        value = int(access_mask, 0)
    except ValueError:
        return ["unknown"]
    flags = (
        (0x0002, "write_data"),
        (0x0004, "append_data"),
        (0x0010, "write_extended_attributes"),
        (0x0040, "delete_child"),
        (0x0100, "write_attributes"),
        (0x10000, "delete"),
        (0x40000, "change_permissions"),
        (0x80000, "take_ownership"),
    )
    return [label for bit, label in flags if value & bit] or ["other"]


def parse_security_events(raw_xml: str, target: Path | str) -> list[dict[str, Any]]:
    """Extract target-directory 4663 events from ``wevtutil`` RenderedXml output."""
    events: list[dict[str, Any]] = []
    for match in re.finditer(r"<Event(?:\s[^>]*)?>.*?</Event>", raw_xml, flags=re.DOTALL):
        try:
            event = ElementTree.fromstring(match.group())
        except ElementTree.ParseError:
            continue
        if _system_value(event, "EventID") != EVENT_ID_FILE_ACCESS:
            continue
        object_path = _event_value(event, "ObjectName")
        if not object_path or not is_under_target(object_path, target):
            continue
        process_id = _event_value(event, "ProcessId")
        try:
            parsed_process_id: int | None = int(process_id, 0) if process_id else None
        except ValueError:
            parsed_process_id = None
        user_name = _event_value(event, "SubjectUserName")
        domain = _event_value(event, "SubjectDomainName")
        events.append(
            {
                "record_id": _system_value(event, "EventRecordID"),
                "timestamp": _event_timestamp(event),
                "event_id": EVENT_ID_FILE_ACCESS,
                "path": object_path,
                "actions": access_actions(_event_value(event, "AccessMask")),
                "access_mask": _event_value(event, "AccessMask"),
                "user": f"{domain}\\{user_name}" if domain and user_name else user_name or None,
                "sid": _event_value(event, "SubjectUserSid") or None,
                "process_id": parsed_process_id,
                "process_path": _event_value(event, "ProcessName") or None,
            }
        )
    return events


def _read_security_events(limit: int) -> str:
    query = "*[System[(EventID=4663)]]"
    result = _run(["wevtutil.exe", "qe", "Security", f"/q:{query}", "/f:RenderedXml", "/rd:true", f"/c:{limit}"])
    return _require_success(result, "读取 Windows Security 审计日志")


def _append_events(log_path: Path, events: list[dict[str, Any]]) -> None:
    if not events:
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()


def watch(target: Path, log_dir: Path, interval: float, once: bool) -> None:
    """Continuously write new target-directory audit events to a JSONL file."""
    require_administrator()
    target = target.resolve(strict=True)
    log_path = log_dir / LOG_FILE_NAME
    seen: deque[str] = deque(maxlen=MAX_SEEN_EVENT_IDS)
    seen_ids: set[str] = set()
    print(f"正在监控 {target}；按 Ctrl+C 停止。日志: {log_path}")
    while True:
        events = parse_security_events(_read_security_events(MAX_SEEN_EVENT_IDS), target)
        new_events = []
        for event in reversed(events):
            record_id = str(event.get("record_id") or "")
            if not record_id or record_id in seen_ids:
                continue
            if len(seen) == seen.maxlen:
                seen_ids.discard(seen.popleft())
            seen.append(record_id)
            seen_ids.add(record_id)
            new_events.append(event)
        _append_events(log_path, new_events)
        if once:
            return
        time.sleep(interval)


def status(target: Path, log_dir: Path) -> None:
    """Print readiness information without changing security configuration."""
    print(f"目标目录: {target}")
    print(f"管理员权限: {'是' if is_administrator() else '否'}")
    print(f"安装状态: {'已安装' if load_state(log_dir) else '未安装'}")
    try:
        policy = get_audit_policy()
    except RuntimeError as error:
        print(f"文件系统审计策略: 无法读取（{error}）")
    else:
        print(f"文件系统审计策略: success={policy.success}, failure={policy.failure}")
    print(f"日志文件: {log_dir / LOG_FILE_NAME}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="审计 ECL 账户目录的 Windows 文件操作与进程归因")
    parser.add_argument("--target", type=Path, default=_default_target(), help="要审计的目录，默认为 ~/.ECL")
    parser.add_argument("--log-dir", type=Path, default=_default_log_dir(), help="JSONL 与安装状态的保存目录")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("install", help="安装目标目录的审计规则（需要管理员）")
    subparsers.add_parser("uninstall", help="移除本工具安装的审计规则（需要管理员）")
    subparsers.add_parser("status", help="查看权限、安装状态和审计策略")
    watch_parser = subparsers.add_parser("watch", help="持续读取 Security 4663 事件（需要管理员）")
    watch_parser.add_argument("--interval", type=float, default=1.0, help="轮询间隔秒数，默认 1")
    watch_parser.add_argument("--once", action="store_true", help="读取一次后退出，适合诊断")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the account-directory audit command line program."""
    if not _is_windows():
        print("此工具仅支持 Windows。", file=sys.stderr)
        return 2
    args = build_parser().parse_args(argv)
    try:
        if args.command == "install":
            install(args.target, args.log_dir)
        elif args.command == "uninstall":
            uninstall(args.target, args.log_dir)
        elif args.command == "watch":
            if args.interval <= 0:
                raise ValueError("--interval 必须大于 0")
            watch(args.target, args.log_dir, args.interval, args.once)
        else:
            status(args.target, args.log_dir)
    except (OSError, PermissionError, RuntimeError, ValueError) as error:
        print(f"错误: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
