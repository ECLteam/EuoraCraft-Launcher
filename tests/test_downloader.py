from __future__ import annotations

from pathlib import Path

import httpx

from ECL.game.Core.Downloader import Downloader


def _redirect_handler(request: httpx.Request) -> httpx.Response:
    """模拟 CDN 307 重定向：/file.jar 跳转到 /real.jar。"""
    if request.url.path == "/file.jar":
        return httpx.Response(307, headers={"Location": "http://example.com/real.jar"})
    if request.url.path == "/real.jar":
        return httpx.Response(200, content=b"REAL-CONTENT", headers={"Content-Length": "12"})
    return httpx.Response(404)


async def test_downloader_follows_redirect(monkeypatch, tmp_path: Path) -> None:
    original = httpx.AsyncClient

    def _client_factory(**kwargs):
        return original(transport=httpx.MockTransport(_redirect_handler), **kwargs)

    monkeypatch.setattr("ECL.game.Core.Downloader.httpx.AsyncClient", _client_factory)

    target = tmp_path / "file.jar"
    downloader = Downloader([("http://example.com/file.jar", target)], max_rounds=1)
    await downloader.run()

    assert downloader.failed_entries == set()
    assert target.read_bytes() == b"REAL-CONTENT"
