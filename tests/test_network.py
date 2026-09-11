# ============================================================
# EuoraCraft Launcher
# ECLTeam © 2026 GPL-3.0 License
# https://github.com/ECLTeam/EuoraCraft-Launcher
#
# 文件作用：针对 network 模块的自动化测试。
#
# 公开接口：
#   - test_get_with_retries_retries_transient_response() -> None
#   - test_get_with_retries_stops_after_configured_network_failures() -> None
# ============================================================

from __future__ import annotations

import httpx

from ECL.utils.network import get_with_retries


def test_get_with_retries_retries_transient_response() -> None:
    responses = [httpx.Response(503), httpx.Response(200, json={"ok": True})]
    calls = 0

    def request(_url: str, **_kwargs: object) -> httpx.Response:
        nonlocal calls
        response = responses[calls]
        calls += 1
        return response

    response = get_with_retries(request, "https://example.invalid", retries=2, retry_delay=0)

    assert calls == 2
    assert response.status_code == 200


def test_get_with_retries_stops_after_configured_network_failures() -> None:
    calls = 0

    def request(_url: str, **_kwargs: object) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectTimeout("timeout")

    try:
        get_with_retries(request, "https://example.invalid", retries=2, retry_delay=0)
    except httpx.ConnectTimeout:
        pass
    else:
        raise AssertionError("expected final network error")

    assert calls == 3
