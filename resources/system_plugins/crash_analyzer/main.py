from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from ECL.plugin.plugin import Plugin


# ── 诊断规则 ──

DIAGNOSTIC_RULES = [
    {
        "type": "java_version_incompatible",
        "severity": "error",
        "pattern": r"UnsupportedClassVersionError",
        "message": "Java 版本不兼容",
        "suggestion": "请使用更高版本的 Java 运行 Minecraft，当前 Java 版本无法支持此 Mod",
    },
    {
        "type": "vram_overflow",
        "severity": "error",
        "pattern": r"Out of memory|Failed to allocate",
        "message": "显存溢出",
        "suggestion": "显卡显存不足，请尝试降低渲染距离、关闭光影或降低纹理包分辨率",
    },
    {
        "type": "optifine_conflict",
        "severity": "warning",
        "pattern": r"OptiFine[\s\S]*?NoSuchMethodError",
        "message": "OptiFine 冲突",
        "suggestion": "OptiFine 与当前 Mod 存在方法冲突，请尝试移除 OptiFine 或更新到最新版本",
    },
    {
        "type": "fabric_api_missing",
        "severity": "error",
        "pattern": r"Could not find required mod: fabric",
        "message": "Fabric API 缺失",
        "suggestion": "缺少 Fabric API，请下载并安装 Fabric API 到 mods 文件夹",
    },
    {
        "type": "forge_version_mismatch",
        "severity": "error",
        "pattern": r"net\.minecraftforge[\s\S]*?version",
        "message": "Forge 版本不匹配",
        "suggestion": "当前 Forge 版本与 Mod 要求不匹配，请检查并安装正确版本的 Forge",
    },
    {
        "type": "gpu_driver_issue",
        "severity": "error",
        "pattern": r"Pixel format not accelerated|LWJGLException",
        "message": "显卡驱动问题",
        "suggestion": "显卡驱动过旧或不兼容，请更新显卡驱动到最新版本",
    },
    {
        "type": "out_of_memory",
        "severity": "error",
        "pattern": r"OutOfMemoryError",
        "message": "内存不足",
        "suggestion": "Minecraft 内存不足，请在启动器中增加分配的内存大小（建议至少 4GB）",
    },
    {
        "type": "file_permission",
        "severity": "error",
        "pattern": r"AccessDeniedException|FileNotFoundException",
        "message": "文件权限问题",
        "suggestion": "文件访问被拒绝或文件不存在，请检查游戏目录权限或重新安装游戏",
    },
]

# Mod 冲突附加规则
MOD_CONFLICT_PATTERN = re.compile(r"(NoClassDefFoundError|NoSuchMethodError|ClassNotFoundException)[\s\S]*?(?:at\s+)?([\w.$]+)")


class CrashAnalyzerPlugin(Plugin):

    def on_enable(self):
        self.register_command("list_crash_reports", self._list_crash_reports, "列出崩溃报告")
        self.register_command("get_crash_report", self._get_crash_report, "获取崩溃报告内容")
        self.register_command("analyze_crash_report", self._analyze_crash_report, "分析崩溃报告")

    def on_frontend_ready(self):
        self.register_route("/crash-reports", "崩溃报告", "bug")

    # ── 列出崩溃报告 ──

    def _list_crash_reports(self, game_path: str) -> list[dict[str, Any]]:
        crash_dir = Path(game_path) / "crash-reports"
        if not crash_dir.is_dir():
            return []

        reports = []
        for entry in sorted(crash_dir.iterdir(), reverse=True):
            if not entry.is_file():
                continue
            filename = entry.name
            try:
                stat = entry.stat()
                size = stat.st_size
                mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            except OSError:
                size = 0
                mtime = "未知"

            # 读取前三行作为摘要
            summary = ""
            try:
                with open(entry, "r", encoding="utf-8", errors="replace") as f:
                    lines = []
                    for i, line in enumerate(f):
                        if i >= 3:
                            break
                        lines.append(line.strip())
                    summary = " | ".join(lines)
            except (OSError, UnicodeDecodeError):
                summary = "无法读取"

            reports.append({
                "filename": filename,
                "date": mtime,
                "size": size,
                "summary": summary,
            })

        return reports

    # ── 获取完整报告 ──

    def _get_crash_report(self, game_path: str, filename: str) -> dict[str, Any]:
        crash_dir = Path(game_path) / "crash-reports"
        file_path = crash_dir / filename

        if not file_path.exists():
            return {"success": False, "message": f"崩溃报告不存在: {filename}"}

        try:
            content = file_path.read_text("utf-8", errors="replace")
            return {"success": True, "filename": filename, "content": content}
        except OSError as e:
            return {"success": False, "message": f"读取崩溃报告失败: {e}"}

    # ── 分析崩溃报告 ──

    def _analyze_crash_report(self, game_path: str, filename: str) -> dict[str, Any]:
        crash_dir = Path(game_path) / "crash-reports"
        file_path = crash_dir / filename

        if not file_path.exists():
            return {"success": False, "message": f"崩溃报告不存在: {filename}"}

        try:
            content = file_path.read_text("utf-8", errors="replace")
        except OSError as e:
            return {"success": False, "message": f"读取崩溃报告失败: {e}"}

        # 提取日期
        date_str = ""
        try:
            stat = file_path.stat()
            date_str = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        except OSError:
            date_str = "未知"

        # 提取游戏版本
        game_version = ""
        version_match = re.search(r"Minecraft Version:\s*(.+)", content)
        if version_match:
            game_version = version_match.group(1).strip()

        # 应用诊断规则
        issues: list[dict[str, Any]] = []
        for rule in DIAGNOSTIC_RULES:
            if re.search(rule["pattern"], content, re.IGNORECASE):
                issues.append({
                    "severity": rule["severity"],
                    "type": rule["type"],
                    "message": rule["message"],
                    "suggestion": rule["suggestion"],
                })

        # 检测 Mod 冲突
        mod_conflicts = MOD_CONFLICT_PATTERN.findall(content)
        seen_classes: set[str] = set()
        for error_type, class_name in mod_conflicts:
            if class_name not in seen_classes:
                seen_classes.add(class_name)
                issues.append({
                    "severity": "warning",
                    "type": "mod_conflict",
                    "message": f"Mod 冲突 ({error_type}): {class_name}",
                    "suggestion": f"类 {class_name} 引发了 {error_type}，请检查相关 Mod 的兼容性",
                })

        # 提取堆栈关键字
        stack_keywords: list[str] = []
        stack_lines = re.findall(r"at\s+([\w.$]+)", content)
        # 提取包名前缀，过滤 Minecraft 自身
        for full_class in stack_lines:
            parts = full_class.split(".")
            if len(parts) >= 2:
                prefix = parts[0] + "." + parts[1]
                if prefix not in ("net.minecraft", "com.mojang", "java.", "sun.", "jdk."):
                    if prefix not in stack_keywords:
                        stack_keywords.append(prefix)
                        if len(stack_keywords) >= 20:
                            break

        # 去重 issue（按 type 去重，保留第一个）
        seen_types: set[str] = set()
        unique_issues: list[dict[str, Any]] = []
        for issue in issues:
            if issue["type"] not in seen_types:
                seen_types.add(issue["type"])
                unique_issues.append(issue)

        result: dict[str, Any] = {
            "success": True,
            "filename": filename,
            "date": date_str,
            "game_version": game_version,
            "issues": unique_issues,
            "stack_trace_keywords": stack_keywords,
        }

        self.emit("crash:detected", {
            "filename": filename,
            "game_version": game_version,
            "issue_count": len(unique_issues),
        })

        self.emit("crash:analyzed", result)

        return result