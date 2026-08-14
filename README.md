<img src="./resources/img/logo.ico" width="300" height="300" alt="logo" align=right />

<div align="center">

# EuoraCraft Launcher

**一个使用 Python 编写的现代化 Minecraft 第三方启动器，支持插件拓展功能**

*Modern Minecraft third-party launcher written in Python, with plugin extensibility.*

</div>

> **免责声明**：本启动器是独立的第三方社区工具，与 Mojang Studios、Microsoft 或任何其子公司没有任何附属关系、背书关系或官方关联。

---

## 介绍

**EuoraCraft Launcher** 是一款现代化、可插拔的 Minecraft 第三方启动器，采用 **Python + Tauri (pytauri)** 构建，前端使用 **Vue 3 + TypeScript**。只需编写少量代码即可通过插件系统扩展启动器功能，满足个性化需求。

---

## 特性

| 特性 | 说明 |
|:----|:-----|
| 轻量高效 | 基于 pytauri 构建，启动迅速，资源占用低 |
| 插件系统 | 完善的后端插件机制，轻松扩展启动器功能 |
| 现代化 UI | Vue 3 + Naive UI + Tailwind CSS，支持亮暗主题 |
| 多账户支持 | 微软账户登录 + Yggdrasil 认证 + 离线模式 |
| 实例管理 | 多版本隔离，独立配置，模组/资源包管理 |
| 国际化 | 内置 vue-i18n，支持多语言 |
| 自动更新 | 基于 GitHub Releases 的自动更新机制 |
| 安全可靠 | 插件沙箱隔离，GPL-3.0 开源协议 |

---

## 快速开始

### 下载

前往 [Releases](https://github.com/ECLTeam/EuoraCraft-Launcher/releases) 页面下载最新版本。

> 首次使用请务必查看文档了解使用教程。

---

## 链接

| 文档 | GitHub | Wiki | Issues |
|:----:|:----:|:----:|:----:|
| 链接 | [GitHub](https://github.com/ECLTeam/EuoraCraft-Launcher) | [Wiki](https://github.com/ECLTeam/EuoraCraft-Launcher/wiki) | [Issues](https://github.com/ECLTeam/EuoraCraft-Launcher/issues) |

---

## 贡献

欢迎提交 Issue 和 Pull Request！

本项目使用 semantic-release 管理版本，请遵循 Conventional Commits 规范。

```bash
# 开发环境
pip install -e ".[dev]"

# 代码检查
ruff check ECL

# 运行测试
pytest
```

---

## 致谢

- [pytauri](https://github.com/pytauri/pytauri) — Python + Tauri 桌面框架
- [Naive UI](https://github.com/tusen-ai/naive-ui) — Vue 3 组件库
- 所有贡献者和社区支持者

---

## 许可证

本项目基于 **GNU General Public License v3.0** 开源。

Copyright © 2026 ECLTeam
