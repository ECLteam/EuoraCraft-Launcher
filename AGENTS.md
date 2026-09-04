# EuoraCraft Launcher 项目规范

本文件约束在本仓库中工作的所有 AI 编码助手与协作者，为强制要求。后续新增规范将持续追加到本文件。

## 1. 功能变更必须提交 Git

- 凡是功能性更改、新增功能或缺陷修复，完成后必须立即向 git 仓库提交一次 commit，不得把已完成的改动长期留在工作区。
- 提交信息遵循 Conventional Commits 规范（feat / fix / perf / docs / style / refactor / test / chore），本项目使用 semantic-release 管理版本与 CHANGELOG。
- 一次 commit 只包含同一功能的相关改动，不得夹带无关文件；注意检查 `git status`，避免把子模块指针、构建产物等带进提交。

## 2. 功能测试必须执行

- 功能更改、新增或修复在提交前必须通过功能测试，测试通过才算"完成"。
- 后端改动：`ruff check ECL` 无新增告警，相关 `pytest` 用例通过；为新增或修复的行为补充 / 更新 `tests/` 下的测试用例。
- 前端 / UI 相关改动：先构建前端（`cd frontend && pnpm build`），再实际启动启动器验证功能可用，不得仅做静态检查。
- 测试未通过不得提交；CI（build.yml）会在各平台复检构建与测试。

## 附则

- 规范之间如有冲突，以较严格者为准。
