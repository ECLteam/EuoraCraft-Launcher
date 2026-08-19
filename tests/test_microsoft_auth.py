import httpx

from ECL.game.Core.MicrosoftAuth import _friendly_network_error


def test_connect_error_yields_readable_hint_even_with_empty_message() -> None:
    error = httpx.ConnectError("")

    hint = _friendly_network_error(error)

    assert hint is not None
    assert "网络" in hint
    assert "代理" in hint


def test_network_error_nested_in_cause_chain_is_recognized() -> None:
    try:
        try:
            raise httpx.ConnectError("")
        except httpx.ConnectError as inner:
            raise RuntimeError("外层异常") from inner
    except RuntimeError as outer:
        hint = _friendly_network_error(outer)

    assert hint is not None
    assert "代理" in hint


def test_timeout_error_yields_timeout_hint() -> None:
    hint = _friendly_network_error(httpx.ReadTimeout("timed out"))

    assert hint is not None
    assert "超时" in hint


def test_non_network_error_returns_none() -> None:
    assert _friendly_network_error(ValueError("boom")) is None


class _ConnectFailingClient:
    async def post(self, *args, **kwargs):
        raise httpx.ConnectError("")


async def test_device_flow_connect_error_message_is_readable() -> None:
    from ECL.game.Core.MicrosoftAuth import MicrosoftAuth, MicrosoftAuthError

    auth = MicrosoftAuth(client_id="test-client", client=_ConnectFailingClient())

    try:
        await auth._device_flow()
    except MicrosoftAuthError as error:
        assert "无法连接到微软认证服务器" in str(error)
    else:
        raise AssertionError("device flow 应抛出 MicrosoftAuthError")


class _RefreshFailingClient:
    async def post(self, *args, **kwargs):
        raise httpx.ConnectError("")


class _InvalidGrantClient:
    async def post(self, *args, **kwargs):
        return httpx.Response(400, json={"error": "invalid_grant"})


class _OtherErrorClient:
    async def post(self, *args, **kwargs):
        return httpx.Response(400, json={"error": "invalid_scope"})


class _RateLimitedClient:
    async def get(self, *args, **kwargs):
        return httpx.Response(429, json={"error": "Too Many Requests"})


async def test_get_profile_429_raises_friendly_message() -> None:
    from ECL.game.Core.MicrosoftAuth import MinecraftAuthError, MinecraftClient

    client = MinecraftClient(client=_RateLimitedClient())

    try:
        await client.get_profile("test-token")
    except MinecraftAuthError as error:
        assert "请求过快" in str(error)
    else:
        raise AssertionError("429 应抛出 MinecraftAuthError")


async def test_refresh_network_error_preserves_refresh_token() -> None:
    from ECL.game.Core.MicrosoftAuth import MicrosoftAuth

    auth = MicrosoftAuth(client_id="test-client", client=_RefreshFailingClient())
    auth._cache["refresh_token"] = "test-refresh-token"

    result = await auth._refresh_token()

    assert result is None
    assert auth._cache.get("refresh_token") == "test-refresh-token"


async def test_refresh_invalid_grant_clears_cache() -> None:
    from ECL.game.Core.MicrosoftAuth import MicrosoftAuth

    auth = MicrosoftAuth(client_id="test-client", client=_InvalidGrantClient())
    auth._cache["refresh_token"] = "test-refresh-token"

    result = await auth._refresh_token()

    assert result is None
    assert auth._cache.get("refresh_token") is None


async def test_refresh_other_error_preserves_refresh_token() -> None:
    from ECL.game.Core.MicrosoftAuth import MicrosoftAuth

    auth = MicrosoftAuth(client_id="test-client", client=_OtherErrorClient())
    auth._cache["refresh_token"] = "test-refresh-token"

    result = await auth._refresh_token()

    assert result is None
    assert auth._cache.get("refresh_token") == "test-refresh-token"


async def test_get_token_without_device_flow_raises_on_refresh_failure() -> None:
    from ECL.game.Core.MicrosoftAuth import MicrosoftAuth, MicrosoftAuthError

    auth = MicrosoftAuth(client_id="test-client", client=_RefreshFailingClient())
    auth._cache["refresh_token"] = "test-refresh-token"

    async def unexpected_device_flow():
        raise AssertionError("已有账户不应进入设备码流程")

    auth._device_flow = unexpected_device_flow  # type: ignore[method-assign]

    try:
        await auth.get_token(allow_device_flow=False)
    except MicrosoftAuthError as error:
        assert "令牌刷新失败" in str(error)
    else:
        raise AssertionError("刷新失败且禁止设备码流程时应抛出 MicrosoftAuthError")


class _FailingCloseClient:
    async def aclose(self):
        raise RuntimeError("Event loop is closed")


async def test_manager_aclose_ignores_closed_loop_error(tmp_path) -> None:
    from ECL.game.Core.MicrosoftAuth import MicrosoftAuthManager

    manager = MicrosoftAuthManager(client_id="test-client", cache_path=tmp_path)
    manager._shared_client = _FailingCloseClient()

    await manager.aclose()  # 事件循环已关闭时不应抛出异常


async def test_get_token_with_device_flow_enters_flow_on_refresh_failure() -> None:
    from ECL.game.Core.MicrosoftAuth import MicrosoftAuth, MicrosoftAuthError

    auth = MicrosoftAuth(client_id="test-client", client=_RefreshFailingClient())
    auth._cache["refresh_token"] = "test-refresh-token"

    async def fake_device_flow():
        raise MicrosoftAuthError("设备码流程已进入")

    auth._device_flow = fake_device_flow  # type: ignore[method-assign]

    try:
        await auth.get_token(allow_device_flow=True)
    except MicrosoftAuthError as error:
        assert "设备码流程已进入" in str(error)
    else:
        raise AssertionError("允许设备码流程时应进入设备码流程")
