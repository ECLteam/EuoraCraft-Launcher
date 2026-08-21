# CHECKPOINT_BATCH_1 — 后端移除自定义主题系统

- 日期：2026-08-21
- 状态：✅ 通过（后端 18+19 测试全绿；import 链正常；ruff 通过）
- 提交：d0661f6（Batch 1-A）+ 待提交（Batch 1-B）

## 目标
完全移除后端自定义主题功能：ThemeService 会话/preset/导入导出、theme_* IPC 命令、theme-studio 窗口。保留 theme_id ∈ {classic, folia} 配置承载。

## 改动
| 文件 | 变更 |
|------|------|
| ECL/api/themes.py | 删除（ThemeHandlers 20 方法） |
| ECL/services/themes.py | 重写为极简模块（BUILTIN_THEME_IDS + normalize_theme_id，867→13 行） |
| ECL/api/models.py | 删除 Theme*Request 模型/枚举/REQUEST_MODELS/__all__ 条目 |
| ECL/api/registry.py | COMMAND_NAMES 删除 20 个 theme_* |
| ECL/api/frontend.py | 移除 ThemeHandlers 混入 |
| ECL/api/bridge.py | 删除 ThemeService 实例化 + theme-studio 窗口类型/白名单 |
| ECL/api/windows.py | 删除 theme-studio 描述符 |
| ECL/api/files.py | 删除 THEME_PRESET 文件选择逻辑 |
| ECL/adapters/tauri.py | 删除 theme:* 事件转发 |
| ECL/plugins/permissions.py | 删除 PermissionScope.THEME |
| ECL/utils/config.py | ui.theme 默认值精简（theme_id + appearance 新键，去 scheme/reduce_motion/compact_density/custom_css） |
| tests/test_themes.py | 重写为极简（BUILTIN_THEME_IDS + normalize_theme_id） |
| tests/test_api_models.py | 移除 theme 命令名断言与用例 |
| tests/test_windows.py | 移除 theme-studio 用例与 capability 断言 |

## 验证
- `pytest tests/test_themes.py test_config_defaults.py test_api_models.py test_windows.py`：18 passed
- `pytest tests/test_plugin_permissions.py test_architecture.py`：19 passed
- ruff + compileall 通过；grep 无旧符号残留

## 备注
- 前端通过 `config:init` 的 `ui.theme.theme_id` 应用皮肤，无需后端命令。
- 遗留：frontend 侧移除（Batch 2-4）、folia 完整迁移（Batch 5）。
