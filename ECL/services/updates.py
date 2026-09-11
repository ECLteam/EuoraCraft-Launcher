from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from ECL.utils import get_logger, get_with_retries

# GitHub Releases API 地址：仓库与前端 issues 链接保持一致。
RELEASES_API = "https://api.github.com/repos/ECLteam/EuoraCraft-Launcher/releases"
_RELEASES_PER_PAGE = 50
_REQUESTS_TIMEOUT = 10.0

# 预发布标识的通道优先级：序号相同且 release 相同时，alpha < beta < rc < 正式版。
_PRERELEASE_ORDER = {"alpha": 0, "beta": 1, "rc": 2}


def parse_version(version: str) -> tuple[tuple[int, ...], tuple[int, int] | None] | None:
    """
    解析 SemVer 版本为可比较结构，忽略构建元数据。

    :param version: 版本号，如 ``v1.4.2-alpha.3+20260906`` 或 ``1.4.2``
    :return: ``(release 段, 预发布标识)``；预发布标识为 ``(通道优先级, 序号)``，无法解析时返回 None
    """
    text = version.strip().lstrip("vV")
    text = text.split("+", 1)[0]
    prerelease = None
    if "-" in text:
        text, _, marker = text.partition("-")
        marker = marker.strip()
        if marker:
            parts = marker.split(".")
            order = _PRERELEASE_ORDER.get(parts[0], 99)
            try:
                number = int(parts[1]) if len(parts) > 1 else 0
            except ValueError:
                return None
            prerelease = (order, number)
    try:
        release = tuple(int(part) for part in text.split("."))
    except ValueError:
        return None
    if not release:
        return None
    return release, prerelease


def compare_versions(left: str, right: str) -> int:
    """
    按 SemVer 规则比较两个版本号：left 小于 right 返回负数、相等返回 0、大于返回正数。

    无法解析的版本视为相等，避免误报更新。

    :param left: 左侧版本号
    :param right: 右侧版本号
    """
    left_parsed = parse_version(left)
    right_parsed = parse_version(right)
    if left_parsed is None or right_parsed is None:
        return 0
    left_release, left_pre = left_parsed
    right_release, right_pre = right_parsed
    for index in range(max(len(left_release), len(right_release))):
        left_part = left_release[index] if index < len(left_release) else 0
        right_part = right_release[index] if index < len(right_release) else 0
        if left_part != right_part:
            return left_part - right_part
    if left_pre is None and right_pre is None:
        return 0
    if left_pre is None:
        return 1
    if right_pre is None:
        return -1
    return (left_pre[0] - right_pre[0]) or (left_pre[1] - right_pre[1])


@dataclass
class UpdateCheckResult:
    """
    一次版本检测的结果。

    :param status: disabled=通道不检测 / up_to_date=已是最新 / update_available=有新版本 / error=检测失败
    :param current_version: 当前启动器版本
    :param channel: 检测通道，alpha=预发布禁用 / beta=测试版 / release=正式版
    :param latest_version: 通道内最新版本号，无可用版本或失败时为 None
    :param latest_url: 最新版本的 GitHub Release 页面地址
    :param latest_notes: 最新版本的更新说明（Release 正文）
    :param message: 失败原因等补充信息
    """

    status: str
    current_version: str
    channel: str
    latest_version: str | None = None
    latest_url: str | None = None
    latest_notes: str | None = None
    message: str | None = None


class UpdateChecker:
    """
    按当前版本通道检查 GitHub Releases 是否有新版本。

    版本类型为 alpha 时直接禁用检测；beta/rc 查询预发布版本，正式版只查询
    正式 release，避免把测试版本误报给正式版用户。

    :param http_client: 共享的启动器通道 HTTP 客户端
    :param current_version: 当前启动器版本号
    :param version_type: 当前版本类型（alpha / beta / rc / release）
    """

    def __init__(
        self,
        http_client: httpx.Client,
        *,
        current_version: str,
        version_type: str,
        request_timeout: float = _REQUESTS_TIMEOUT,
        request_retries: int = 2,
    ):
        self.logger = get_logger("UpdateChecker")
        self.http = http_client
        self.current_version = current_version
        self.version_type = version_type or "release"
        self._request_timeout = max(1.0, float(request_timeout))
        self._request_retries = max(0, int(request_retries))

    def check(self) -> UpdateCheckResult:
        channel = self._channel()
        base = UpdateCheckResult(
            status="error",
            current_version=self.current_version,
            channel=channel,
        )
        releases = self._fetch_releases(base)
        if releases is None:
            return base
        # alpha 查看全部版本类型的最新版本；beta/rc 只看预发布；正式版只看正式 release
        want_prerelease = None if channel == "alpha" else (channel == "beta")
        best_tag, best_release = self._select_best_release(releases, want_prerelease=want_prerelease)
        if best_release is None:
            base.status = "up_to_date"
            return base
        if compare_versions(best_tag, self.current_version) > 0:
            base.status = "update_available"
            base.latest_version = best_tag.lstrip("vV")
            base.latest_url = str(best_release.get("html_url") or "") or None
            base.latest_notes = str(best_release.get("body") or "").strip() or None
            return base
        base.status = "up_to_date"
        return base

    def latest_release(self) -> dict[str, Any] | None:
        """
        返回当前通道匹配到的最高版本 Release 对象，供自动更新提取安装包。

        :return: 最高版本的 Release 对象；检测失败或无可用版本时返回 None
        """
        channel = self._channel()
        releases = self._fetch_releases(
            UpdateCheckResult(status="error", current_version=self.current_version, channel=channel)
        )
        if releases is None:
            return None
        want_prerelease = None if channel == "alpha" else (channel == "beta")
        best_tag, best_release = self._select_best_release(releases, want_prerelease=want_prerelease)
        if best_release is None or compare_versions(best_tag, self.current_version) <= 0:
            return None
        return best_release

    def _channel(self) -> str:
        # 按版本类型映射检测通道，alpha 归入预发布通道。
        if self.version_type == "alpha":
            return "alpha"
        return "beta" if self.version_type in ("beta", "rc") else "release"

    def _fetch_releases(self, base: UpdateCheckResult) -> list[dict[str, Any]] | None:
        """
        请求 GitHub Releases 并返回解析结果，失败时写入提示信息并返回 None。

        :param base: 用于记录失败提示的检测结果载体
        :return: Release 列表；请求或解析失败时返回 None
        """
        try:
            response = get_with_retries(
                self.http.get,
                RELEASES_API,
                retries=self._request_retries,
                timeout=self._request_timeout,
                params={"per_page": _RELEASES_PER_PAGE},
                headers={"Accept": "application/vnd.github+json"},
            )
        except httpx.RequestError as exc:
            self.logger.warning("版本检测请求失败: %s", exc)
            base.message = "无法连接更新服务器，请检查网络后重试"
            return None
        if response.status_code != 200:
            self.logger.warning("版本检测接口返回异常状态: %s", response.status_code)
            base.message = "更新服务器响应异常，请稍后重试"
            return None
        try:
            releases = response.json()
        except ValueError:
            base.message = "更新服务器数据解析失败，请稍后重试"
            return None
        if not isinstance(releases, list):
            base.message = "更新服务器数据格式异常，请稍后重试"
            return None
        return releases

    @staticmethod
    def _select_best_release(
        releases: list[dict[str, Any]], *, want_prerelease: bool | None
    ) -> tuple[str, dict[str, Any] | None]:
        """
        按通道筛选 Release 列表并返回其中版本号最高的一项。

        :param releases: GitHub Releases 返回的 Release 列表
        :param want_prerelease: 是否只看预发布版本；None 表示不过滤全部版本
        :return: ``(最高版本号, 对应 Release 对象)``；无可匹配项时返回空串与 None
        """
        best_tag = ""
        best_release: dict[str, Any] | None = None
        for release in releases:
            if not isinstance(release, dict):
                continue
            if want_prerelease is not None and bool(release.get("prerelease")) != want_prerelease:
                continue
            tag = str(release.get("tag_name") or "").strip()
            if parse_version(tag) is None:
                continue
            if best_tag and compare_versions(tag, best_tag) <= 0:
                continue
            best_tag = tag
            best_release = release
        return best_tag, best_release


__all__ = ["UpdateCheckResult", "UpdateChecker", "compare_versions", "parse_version"]
