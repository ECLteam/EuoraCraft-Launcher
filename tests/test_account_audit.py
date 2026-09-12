from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_audit_module():
    path = Path(__file__).parents[1] / "tools" / "ecl_account_audit.py"
    spec = importlib.util.spec_from_file_location("ecl_account_audit", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


audit = _load_audit_module()


def test_is_under_target_matches_only_the_selected_directory() -> None:
    target = r"C:\Users\Wuchang325\.ECL"

    assert audit.is_under_target(r"C:\Users\Wuchang325\.ECL\accounts\ms_accounts_list.json", target)
    assert not audit.is_under_target(r"C:\Users\Wuchang325\.ECL-backup\accounts.json", target)


def test_access_actions_reports_write_and_delete_bits() -> None:
    assert audit.access_actions("0x10002") == ["write_data", "delete"]


def test_parse_security_events_keeps_process_attribution_for_target_files() -> None:
    raw_xml = """<Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event">
  <System><EventID>4663</EventID><EventRecordID>42</EventRecordID><TimeCreated SystemTime="2026-09-13T00:00:00.000Z" /></System>
  <EventData>
    <Data Name="SubjectUserName">Wuchang325</Data><Data Name="SubjectDomainName">DESKTOP</Data>
    <Data Name="SubjectUserSid">S-1-5-21-test</Data>
    <Data Name="ObjectName">C:\\Users\\Wuchang325\\.ECL\\accounts\\ms_accounts_list.json</Data>
    <Data Name="ProcessId">0x123</Data><Data Name="ProcessName">C:\\Python\\python.exe</Data>
    <Data Name="AccessMask">0x10000</Data>
  </EventData>
</Event>
<Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event">
  <System><EventID>4663</EventID><EventRecordID>43</EventRecordID></System>
  <EventData><Data Name="ObjectName">C:\\Windows\\temp.txt</Data></EventData>
</Event>"""

    events = audit.parse_security_events(raw_xml, r"C:\Users\Wuchang325\.ECL")

    assert events == [
        {
            "record_id": "42",
            "timestamp": "2026-09-13T00:00:00.000Z",
            "event_id": "4663",
            "path": r"C:\Users\Wuchang325\.ECL\accounts\ms_accounts_list.json",
            "actions": ["delete"],
            "access_mask": "0x10000",
            "user": "DESKTOP\\Wuchang325",
            "sid": "S-1-5-21-test",
            "process_id": 291,
            "process_path": r"C:\Python\python.exe",
        }
    ]


def test_parse_policy_report_handles_enabled_and_disabled_states() -> None:
    assert audit._parse_policy_report('"System audit policy","File System","Success and Failure"') == audit.AuditPolicy(
        success=True, failure=True
    )
    assert audit._parse_policy_report('"System audit policy","File System","No Auditing"') == audit.AuditPolicy(
        success=False, failure=False
    )
