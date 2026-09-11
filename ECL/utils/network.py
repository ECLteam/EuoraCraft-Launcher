# ============================================================
# EuoraCraft Launcher
# ECLTeam © 2026 GPL-3.0 License
# https://github.com/ECLTeam/EuoraCraft-Launcher
#
# 文件作用：网络工具：带重试的 GET 与下载代理解析。
#
# 公开接口：
#   - DOWNLOAD_PROXY_ENV_KEY（str）
#   - download_proxy_url() -> str | None — 读取游戏下载通道的代理地址。
#   - get_with_retries(request, url, retries, retry_delay, **kwargs) -> httpx.Response — 对幂等 GET 请求执行有限次数的指数退避重试。
# ============================================================

from __future__ import annotations

import os
from collections.abc import Callable
from time import sleep
from typing import Any

import httpx

_RETRYABLE_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})

DOWNLOAD_PROXY_ENV_KEY = "ECL_DOWNLOAD_PROXY"


def download_proxy_url() -> str | None:
    """
    读取游戏下载通道的代理地址。

    启动器把"游戏下载"代理配置同步到进程环境变量 ECL_DOWNLOAD_PROXY，
    与启动器网络代理（账户登录等，api_proxy_*）相互独立；
    下载类请求应显式传入该地址，避免 trust_env 误用启动器环境代理。

    :return: 代理地址；未配置时返回 None 表示直连
    """
    return os.environ.get(DOWNLOAD_PROXY_ENV_KEY) or None


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
