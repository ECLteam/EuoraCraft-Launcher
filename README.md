# EuoraCraft Launcher

EuoraCraft Launcher 是一个强大的 Minecraft Java Edition 启动器，采用前后端分离的混合架构设计，支持多版本管理、Mod 加载器安装、微软账户认证、自动 Java 检测等功能，旨在为玩家提供最佳的 Minecraft 游戏体验。

## 项目架构

项目采用前后端分离架构：

- **后端** - 使用 Python 3.11+ 编写，基于 pywebview 提供原生 UI 容器，负责游戏管理、下载、认证等核心功能
- **前端** - 使用 Vue 3 + TypeScript + Vite 构建，提供现代化的用户界面

## 功能特性

- **多版本管理** - 支持安装和管理多个 Minecraft 版本
- **账户系统** - 支持离线账户和微软账户认证
- **MOD 集成** - 支持 Fabric 等 Mod 加载器安装
- **性能优化** - 智能内存分配和 Java 版本自动检测
- **跨平台支持** - 目前支持 Windows（Linux/macOS 暂不支持）
- **现代化 UI** - 响应式设计，深色/浅色/系统主题
- **国际化** - 支持中文（zh-CN）和英文（en-US）界面
- **安全认证** - 使用 Fernet 加密令牌，多密钥环后端支持

## 技术栈

- **Python**: 3.11+
- **UI 框架**: pywebview >= 4.0
- **日志**: colorama + 自定义彩色日志系统
- **HTTP 请求**: requests
- **认证**: msal（微软认证）+ keyring（凭据存储）+ cryptography（加密）
- **剪贴板**: pyperclip
- **构建**: PyInstaller >= 5.0
- **版本管理**: python-semantic-release

## 项目结构

```
EuoraCraft-Launcher/
├── main.py                    # 应用程序入口点
├── pyproject.toml            # Python 项目配置
├── requirements.txt          # Python 依赖
├── "EuoraCraft Launcher.spec" # PyInstaller 打包配置
├── .env.dev                  # 开发环境配置
├── setting.json              # 用户配置文件（运行时生成）
├── logs/                     # 日志目录（按天轮转）
├── ECL/                      # 主 Python 包
│   ├── __init__.py          # 版本导出
│   ├── launcher.py          # 启动器主类
│   ├── Core/                # 核心工具
│   │   ├── __init__.py      # 版本信息
│   │   ├── config.py        # ConfigManager - JSON 配置管理
│   │   └── logger.py        # LoggerManager - 彩色日志与轮转
│   ├── ui/                  # UI 层
│   │   ├── __init__.py
│   │   └── ui.py            # PyWebView UI 运行器 & API 类
│   └── Game/                # 游戏相关模块
│       ├── __init__.py
│       ├── java.py          # Java 检测与管理
│       ├── MicrosoftAuth.py # 微软/Minecraft 认证流程
│       ├── AccountManager.py # 账户管理封装
│       └── Core/            # 游戏核心功能
│           ├── __init__.py
│           ├── ECLauncherCore.py   # Minecraft 启动逻辑
│           ├── C_Downloader.py     # 文件下载工具
│           ├── C_FilesChecker.py   # 游戏文件验证
│           ├── C_GetGames.py       # 版本扫描
│           └── C_Libs.py           # 工具函数
└── test/                    # 测试脚本
```

## 开发环境设置

### 前置要求

- Python 3.11 或更高版本
- Windows 操作系统（目前仅支持 Windows）

### 安装步骤

1. 克隆仓库
```bash
git clone https://github.com/ECLTeam/EuoraCraft-Launcher.git
cd EuoraCraft-Launcher/EuoraCraft-Launcher
```

2. 创建虚拟环境
```bash
python -m venv .venv
.venv\Scripts\activate
```

3. 安装依赖
```bash
pip install -r requirements.txt
```

4. 运行启动器（开发模式）
```bash
python main.py
```

## 配置系统

启动器采用分层配置系统：

1. **默认配置** (`ECL/Core/config.py:DEFAULT_CONFIG`)
2. **用户配置** (`setting.json`)
3. **环境覆盖** (`.env.dev` 或 `.env`，格式 `ECL_SECTION_KEY=value`)

### 配置文件示例

`setting.json`:
```json
{
  "launcher": {
    "version": "0.0.0",
    "version_type": "dev",
    "debug": false
  },
  "ui": {
    "width": 900,
    "height": 600,
    "title": "EuoraCraft Launcher",
    "locale": "zh-CN",
    "background": {
      "type": "default",
      "path": "",
      "opacity": 0.8,
      "blur": 0
    }
  },
  "game": {
    "minecraft_paths": ["./.minecraft"],
    "java_auto": true,
    "java_path": "",
    "memory_auto": true,
    "memory_size": 4096
  },
  "download": {
    "mirror_source": "official",
    "download_threads": 4
  },
  "theme": {
    "mode": "system",
    "primary_color": "#0078d4",
    "blur_amount": 6
  }
}
```

### 环境变量配置

在 `.env.dev` 文件中设置（格式: `ECL_SECTION_KEY=VALUE`）：

```ini
# 调试模式
ECL_LAUNCHER_DEBUG=true
ECL_LAUNCHER_VERSION_TYPE=dev

# UI 配置
ECL_UI_TITLE=EuoraCraft Launcher (Dev Mode)
ECL_UI_WIDTH=1000
ECL_UI_HEIGHT=700
```

## API 接口

后端通过 `Api` 类暴露方法给前端调用，所有 API 返回统一格式：

```python
{
    "success": bool,
    "data": Any,          # 可选
    "message": str        # 人类可读状态
}
```

### 主要 API 分类

- **配置管理**: `get_launcher_config()`, `update_launcher_config()`
- **游戏管理**: `get_installed_versions()`, `launch_game()`
- **Java 检测**: `get_java_list()`, `get_recommended_java()`
- **账户管理**: `get_accounts()`, `add_account()`, `switch_account()`, `remove_account()`
- **下载管理**: `download_version()`, `get_download_progress()`

### 前端调用示例

```typescript
// 通过 window.pywebview.api 调用
const result = await window.pywebview.api.getLauncherConfig();
if (result.success) {
    console.log(result.data);
}
```

## 核心模块说明

### ConfigManager (`ECL/Core/config.py`)

单例模式管理配置，支持：
- 自动创建默认配置
- 环境变量覆盖 (`ECL_*` 格式)
- 配置文件热重载

### LoggerManager (`ECL/Core/logger.py`)

彩色日志系统，支持：
- 跨平台彩色终端输出
- 日志按天轮转
- 30 天后自动压缩旧日志

### JavaDetector (`ECL/Game/java.py`)

Java 自动检测：
- 扫描注册表、环境变量、常用路径
- 版本、架构、类型信息识别
- 根据 MC 版本推荐 Java 版本

### AccountManager (`ECL/Game/AccountManager.py`)

账户管理：
- 支持离线账户和微软账户
- OAuth 设备码流程认证
- 凭据加密存储（Fernet）
- 多密钥环后端支持

### ECLauncherCore (`ECL/Game/Core/ECLauncherCore.py`)

Minecraft 启动核心：
- 版本 JSON 解析
- 库文件解析和原生库解压
- JVM 参数构建
- 支持 Forge/Fabric 等 Mod 加载器

## 构建与发布

### 前端构建

```bash
cd ../EuoraCraft-UI
pnpm install
pnpm build
# 输出到 EuoraCraft-UI/dist/
```

### Python 可执行文件打包

```bash
pyinstaller "EuoraCraft Launcher.spec"
# 输出: dist/EuoraCraft Launcher.exe
```

### 发布流程

1. 更新 `ECL/Core/__init__.py` 中的版本号
2. 更新 `CHANGELOG.md`
3. 构建前端: `pnpm build`
4. 构建可执行文件: `pyinstaller "EuoraCraft Launcher.spec"`
5. 分发 `dist/EuoraCraft Launcher.exe`

## 调试

### 启用调试日志

在 `setting.json` 中设置：
```json
{
  "launcher": {
    "debug": true
  }
}
```

或在 `.env.dev` 中：
```ini
ECL_LAUNCHER_DEBUG=true
```

### DevTools

前端提供 `/dev` 路由用于诊断，可访问：
- API 诊断工具
- 配置查看器
- 日志查看器

## 安全说明

- 微软 OAuth 通过设备码流程，无需密码
- 使用 Fernet 对称加密令牌（密钥派生自用户密码）
- 凭据存储支持系统密钥环、加密文件、JSON 等多种后端
- 账户数据加密存储在 `~/.ECLAuth/`
- 敏感信息永不记录到日志

## 平台支持

| 平台 | 状态 |
|------|------|
| Windows | ✅ 完全支持 |
| Linux | ❌ 暂不支持 |
| macOS | ❌ 暂不支持 |

## 依赖许可证

本项目使用以下开源组件：

- pywebview - BSD 3-Clause
- colorama - BSD 3-Clause
- requests - Apache 2.0
- msal - MIT
- keyring - MIT
- cryptography - Apache 2.0 或 BSD

## 贡献指南

1. Fork 本仓库
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送分支 (`git push origin feature/AmazingFeature`)
5. 创建 Pull Request

## 许可证

本项目采用 GPL-3.0 许可证 - 详见 [LICENSE](../LICENSE) 文件

## 联系方式

- 项目主页: https://github.com/ECLTeam/EuoraCraft-Launcher
- 问题反馈: https://github.com/ECLTeam/EuoraCraft-Launcher/issues
- 邮箱: EuoraCraft-Studio@outlook.com.

---

**版本**: 0.0.0-dev  
**最后更新**: 2026-04-10
