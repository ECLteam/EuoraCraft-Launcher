<img src="./resources/img/logo.ico" width="300" height="300" alt="logo" align=right />

<div align="center">

# EuoraCraft Launcher

<p align="center">
    <a href="https://www.eclteam.top">官网</a> | <a href="https://docs.eclteam.top">文档</a> | <a href="https://github.com/ECLTeam/EuoraCraft-Launcher/issues">反馈</a>
</p>

<p align="center">
  <a href="https://github.com/FloraBotTeam/FloraBot/blob/main/LICENSE">
    <img src="https://img.shields.io/badge/license-GPL3.0-green" alt="license">
  </a>
  <a href="https://www.python.org">
    <img src="https://img.shields.io/badge/Python-3.11-blue?logo=Python" alt="python">
  </a>
  <a href="https://github.com/ECLTeam/EuoraCraft-Launcher/releases">
    <img src="https://img.shields.io/github/v/release/ECLTeam/EuoraCraft-Launcher" alt="release">
  </a>
</p>

**一个使用 Python 编写的现代化 Minecraft 第三方启动器，支持插件拓展功能，构建出自己的启动器吧**

*Modern Minecraft third-party launcher written in Python, with plugin extensibility, build your own launcher.*

</div>

> **免责声明**：本启动器是独立的第三方社区工具，与 Mojang Studios、Microsoft 或任何其子公司没有任何附属关系、背书关系或官方关联。

---

## 介绍

**EuoraCraft Launcher**(ECL) 是一款现代化的 Minecraft 第三方启动器，采用 **Python + Tauri (pytauri)** 构建，前端使用 **Vue 3 + TypeScript**。只需编写少量代码即可通过插件系统扩展启动器功能，满足个性化需求。

---

## 特性

| 特性 | 说明 |
|:----|:-----|
| 插件系统 | 后端插件、主题、联机扩展、认证、崩溃分析等扩展点，使用声明式权限模型控制插件能力 |
| 现代化 UI | Vue 3 + Naive UI + Tailwind CSS，支持亮暗主题、自定义外观和主题设计器 |
| 多账户支持 | 微软账户登录 + Yggdrasil 认证 + 离线模式与皮肤衣柜 |
| 实例管理 | 多版本实例隔离，独立配置，模组/资源包/世界/服务器/截图管理 |
| 联机大厅 | 内置 EasyTier 虚拟网络与联机房间管理，支持插件扩展联机协议 |
| 国际化 | 内置 vue-i18n，支持多语言 |
| 版本发布 | 基于 GitHub Releases 发布安装包，由用户从 Release 页面手动下载更新 |
| 安全可靠 | 插件在宿主进程内执行，通过声明式权限限制访问范围，GPL-3.0 开源协议 |

---

## 合作 / 相关社区项目

- [Qomicex.Tauri（QML）](https://github.com/Qomicex-Public/Qomicex.Tauri/) — QML 维护的 Tauri 第三方 Minecraft 启动器，与 EuoraCraft Launcher 共用联机节点，并兼容 SCF 拓展协议实现互相联机。

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
