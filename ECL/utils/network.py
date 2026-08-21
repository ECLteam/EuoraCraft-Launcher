from __future__ import annotations

from collections.abc import Callable
from time import sleep
from typing import Any

import httpx

_RETRYABLE_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})


def get_with_retries(
    request: Callable[..., httpx.Response],
    url: str,
    *,
    retries: int,
    retry_delay: float = 0.25,
    **kwargs: Any,
) -> httpx.Response:
    """
    对幂等 GET 请求执行有限次数的指数退避重试。

    :param request: 发起 GET 请求的函数
    :param url: 请求地址
    :param retries: 首次请求失败后的额外尝试次数
    :param retry_delay: 首次重试前的等待秒数
    :param kwargs: 传给请求函数的附加参数
    :return: 最后一次成功响应或不可重试响应
    :raises httpx.RequestError: 所有尝试均发生网络错误时抛出最后一次错误
    """
    retry_count = max(0, int(retries))
    for attempt in range(retry_count + 1):
        try:
            response = request(url, **kwargs)
        except httpx.RequestError:
            if attempt == retry_count:
                raise
        else:
            if response.status_code not in _RETRYABLE_STATUS_CODES or attempt == retry_count:
                return response
            response.close()
        sleep(max(0.0, retry_delay) * (2**attempt))

    raise RuntimeError("请求重试流程意外结束")
