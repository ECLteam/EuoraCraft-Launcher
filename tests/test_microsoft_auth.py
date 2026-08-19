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
