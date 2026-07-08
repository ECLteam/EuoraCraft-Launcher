# EuoraCraft Launcher

现代化 Minecraft Java Edition 启动器，Python 后端 + Vue 3 前端，PyTauri 桥接通信。支持多版本管理、Mod 加载器安装、微软账户认证、自动 Java 检测、插件系统。

## 架构

```
 ┌──────────────────────────────────────────────────────┐
 │                  Vue 3 前端                           │
 │    TypeScript + Vite + Naive UI + Tauri API          │
 │    ┌──────────┬──────────┬──────────┬─────────────┐  │
 │    │ 版本管理  │  设置页   │  侧边栏   │   插件 UI    │  │
 │    │ ManageTab│ Settings │ SideBar  │ PluginSlot  │  │
 │    └──────────┴──────────┴──────────┴─────────────┘  │
 ├──────────────────────────────────────────────────────┤
 │                  PyTauri Bridge                       │
 │    invoke('api_call', {body})  ◄──►  Emitter.emit()  │
 ├──────────────────────────────────────────────────────┤
 │                Python 后端 ECL                         │
 │  ┌──────────────────────────────────────────────────┐ │
 │  │  launcher.py          EuoraCraftLauncher         │ │
 │  │  adapters/adapter.py  TauriAdapter               │ │
 │  ├──────────────────────────────────────────────────┤ │
 │  │  api/handlers.py      60+ 命令处理器              │ │
 │  │  api/events.py        EventEmitter 线程安全推送    │ │
 │  ├────────────┬──────────────┬──────────────────────┤ │
 │  │ game/Core/ │   plugin/    │  auth/ + java/       │ │
 │  │ 启动引擎    │  插件框架     │  认证 + Java 检测     │ │
 │  │ 下载器      │  生命周期     │  OAuth + 离线        │ │
 │  │ 文件校验    │  事件/服务    │  四级密钥环加密       │ │
 │  │ 版本获取    │  HTML 注入    │  多源并行扫描         │ │
 │  └────────────┴──────────────┴──────────────────────┘ │
 │  common/   config.py  state.py  logger.py  env.py    │
 └──────────────────────────────────────────────────────┘
```

- **前端** — Vue 3 + TypeScript + Vite，通过 `invoke('api_call')` 调用后端命令，监听 `Emitter` 事件更新 UI
- **后端** — Python 3.11+，负责游戏管理、下载、认证、插件等核心功能
- **桥接** — PyTauri 提供 `api_call` 命令注册与 `Emitter.emit` 双向事件推送

## 功能

- **多版本管理** — 安装和管理多个 Minecraft 版本（Release / Snapshot / Beta / Alpha），支持版本卸载与跨目录扫描
- **Mod 加载器** — Fabric 安装（Meta v2 API），预置 Forge / NeoForge / Quilt 接口
- **账户系统** — 离线账户和微软正版账户（MSAL 设备码流），多账户切换，皮肤头像自动获取
- **Java 自动检测** — 注册表、JAVA_HOME、PATH 并行扫描，按 MC 版本智能推荐 Java 运行时
- **插件系统** — 完整生命周期管理、事件/服务注册、HTML 插槽注入、前端路由注入、设置持久化
- **安全加密** — PBKDF2HMAC (SHA256, 600k 迭代) + Fernet (AES-128-CBC)，四级密钥环降级策略
- **现代化 UI** — 深色/浅色/系统主题切换，中文/英文国际化，自定义背景与鼠标特效
- **版本管理** — python-semantic-release 自动化版本号迭代，Conventional Commits 规范

## 技术栈

| 类别 | 技术 |
|------|------|
| 运行环境 | Python 3.11+ |
| 前后端桥接 | PyTauri >= 0.8.0 |
| 前端 | Vue 3 + TypeScript + Vite + Naive UI |
| 桌面框架 | Tauri 2.x |
| HTTP | requests |
| 认证 | msal + keyring + keyrings-alt + cryptography |
| 图像 | Pillow |
| 数据校验 | pydantic >= 2.0 |
| 异步 I/O | anyio >= 4.0 |
| 剪贴板 | pyperclip |
| 终端色彩 | colorama |
| 构建 | PyInstaller (onedir) |
| 版本管理 | python-semantic-release |
| 代码检查 | Ruff (py311, 120 列) |

## 快速开始

### 环境要求

- Python 3.11+
- Windows 操作系统
- Node.js 18+ 和 pnpm（前端开发时需要）

### 后端开发

```bash
git clone https://github.com/ECLTeam/EuoraCraft-Launcher.git
cd EuoraCraft-Launcher

python -m venv .venv
.venv\Scripts\activate
pip install -e .

python main.py
```

### 前端开发

```bash
cd EuoraCraftLauncher-UI
pnpm install
pnpm dev
```

在 `.env` 中指向开发服务器：

```ini
FRONTEND_DEV_SERVER=http://localhost:5173
```

加载优先级：`.env.dev` > `.env` > `os.environ`

## 项目结构

```
EuoraCraft-Launcher/
├── main.py                    # 应用入口
├── pyproject.toml              # 项目配置、依赖、构建、版本管理
├── Tauri.toml                  # Tauri 桌面配置（窗口大小、无边框等）
├── setting.json                # 用户运行时配置（自动生成与补全）
├── CHANGELOG.md                # 版本变更日志（semantic-release 生成）
├── requirements.txt            # pip 依赖列表
├── LICENSE                     # GPL-3.0
├── .env / .env.dev             # 环境变量覆盖
├── capabilities/
│   └── default.toml            # Tauri 权限声明
├── resources/                  # 资源文件（皮肤、用户协议等）
├── logs/                       # 日志（按天轮转，每日 gz 压缩）
├── tests/                      # 单元测试
├── docs/                       # 项目文档
│   ├── backend-intro/          # 后端项目介绍（HTML）
│   ├── backend-dev-doc/        # 后端开发文档（HTML）
│   ├── post-dev-plan/          # 开发后计划
│   └── plugin-dev-guide.md     # 插件开发指南（628 行）
├── ECL/                        # 后端主包
│   ├── app.py                  # 应用入口函数 main()
│   ├── launcher.py             # EuoraCraftLauncher 三阶段初始化
│   ├── adapters/
│   │   └── adapter.py          # TauriAdapter PyTauri 桥接器
│   ├── api/
│   │   ├── handlers.py         # Api 60+ 命令处理器
│   │   └── events.py           # EventEmitter 线程安全事件推送
│   ├── game/Core/
│   │   ├── ECLauncherCore.py   # 启动引擎（参数校验→JVM→ClassPath→子进程）
│   │   ├── C_GetGames.py       # 版本获取与下载（Mojang + Fabric v2）
│   │   ├── C_Downloader.py     # 多线程下载器（断点续传/SHA1/重试）
│   │   ├── C_FilesChecker.py   # 文件完整性校验（多镜像源路由）
│   │   ├── C_Libs.py           # 工具函数与 API 地址
│   │   ├── C_Skin.py           # 皮肤渲染与缓存
│   │   └── InstancesManager.py # 游戏进程实例管理
│   ├── plugin/
│   │   ├── framework.py        # PluginFramework 插件管理器
│   │   ├── plugin.py           # Plugin 基类（生命周期/事件/注入）
│   │   ├── registry.py         # ServiceRegistry + EventRegistry
│   │   └── importer.py         # PluginImporter 隔离命名空间导入
│   ├── auth/
│   │   ├── manager.py          # AccountManager 账户管理
│   │   ├── microsoft.py        # MultiAccountMinecraftAuth MSAL OAuth
│   │   ├── crypto.py           # SmartKeyringManager + EncryptionManager
│   │   └── models.py           # MinecraftAccount 数据模型
│   ├── java/
│   │   ├── detector.py         # JavaDetector 多源并行扫描
│   │   └── models.py           # JavaInfo 数据模型
│   └── common/
│       ├── config.py           # ConfigManager 配置管理
│       ├── state.py            # AppState 全局状态中心
│       ├── logger.py           # LoggerManager 日志系统
│       ├── env.py              # EnvLoader 环境变量加载
│       └── version.py          # 版本号（semantic-release 管理）
├── plugins/                    # 插件目录
│   ├── hello_world/            # 示例插件
│   └── mouse_effect/           # 鼠标特效插件
├── plugin_config/              # 插件配置（隔离存储）
├── ECL_Libs/                   # 核心库目录
│   ├── Skins/                  # 默认皮肤（9 种）
│   ├── Cache/Skin/             # 皮肤缓存
│   └── user_agreement.json     # 用户协议状态
└── EuoraCraftLauncher-UI/      # 前端（独立 Git 仓库）
    ├── src/
    │   ├── components/         # layout / modals / versions / settings / animation
    │   ├── composables/        # 组合式函数
    │   ├── views/              # 页面视图
    │   ├── i18n/               # 中英文国际化
    │   ├── styles/             # 样式
    │   └── router/             # 路由
    ├── Tauri.toml
    └── package.json
```

## 配置系统

### 配置层级

```
默认配置 (ConfigManager.DEFAULT_CONFIG)
    ↓ 覆盖
用户配置 (setting.json)
    ↓ 覆盖
环境变量 (ECL_* 前缀)
```

- `setting.json` 不存在时自动生成，缺失项自动补全
- 相对路径（如 `./.minecraft`）自动转换为绝对路径
- 版本号以 `ECL/common/version.py` 为权威来源，每次启动时同步到 `setting.json`

### setting.json

```json
{
  "launcher": {
    "version": "0.1.0",
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
      "opacity": 0.2,
      "blur": 0
    },
    "theme": {
      "mode": "system",
      "primary_color": "#4A7FD9",
      "blur_amount": 6,
      "sidebar_collapsed": true,
      "titlebar_hidden": true
    },
    "mouse_effect": {
      "enabled": false,
      "color": "45,175,255",
      "scale": 1.5,
      "opacity": 1.0,
      "speed": 1.0
    }
  },
  "game": {
    "minecraft_paths": [{ "name": "默认路径", "path": "./.minecraft" }],
    "java_auto": true,
    "java_path": "",
    "memory_auto": true,
    "memory_size": 4096,
    "fullscreen": false
  },
  "download": {
    "mirror_source": "official",
    "download_threads": 4
  }
}
```

### 环境变量覆盖

以 `ECL_` 为前缀，下划线对应嵌套路径：

```ini
ECL_LAUNCHER_DEBUG=true          # → launcher.debug = true
ECL_UI_LOCALE=en-US              # → ui.locale = "en-US"
ECL_DOWNLOAD_DOWNLOAD_THREADS=8  # → download.download_threads = 8
ECL_GAME_MEMORY_SIZE=8192        # → game.memory_size = 8192
```

## 核心模块

### EuoraCraftLauncher `ECL/launcher.py`

启动器主类，三阶段初始化：

1. **Phase 1** — 系统检测、平台兼容、核心目录创建、皮肤资源初始化
2. **Phase 2** — 并行执行 Java 扫描（线程池）和账户系统初始化
3. **Phase 3** — 版本信息、游戏目录、调试模式、后台预加载版本列表

### ConfigManager `ECL/common/config.py`

配置管理中心。功能：JSON 加载/保存、自动补全缺失项、环境变量覆盖（`ECL_*` 前缀自动映射）、相对路径迁移、版本号同步（以 `version.py` 为权威来源）。

### AppState `ECL/common/state.py`

全局单例状态中心，持有所有核心模块实例（ConfigManager、AccountManager、PluginFramework 等），串联 Core 日志/进度回调到前端事件推送。

### LoggerManager `ECL/common/logger.py`

彩色控制台输出 + 按天轮转文件日志（每日 gz 压缩）+ 错误日志独立分离。调试模式下提升至 DEBUG 级别。

### EnvLoader `ECL/common/env.py`

环境变量加载器，`.env.dev` > `.env` > `os.environ` 层级覆盖，`ECL_*` 前缀自动映射到嵌套配置项。

### TauriAdapter `ECL/adapters/adapter.py`

PyTauri 桥接适配器，注册 `api_call` 命令到 Tauri IPC，管理前端就绪事件推送（用户协议检查、版本提醒、插件初始化）。

### Api `ECL/api/handlers.py`

60+ 命令处理器，统一入口 `api_call`，返回 `{success, data, message}` 格式。覆盖配置管理、版本管理、账户管理、游戏启动、插件管理、文件操作、窗口控制。

### EventEmitter `ECL/api/events.py`

线程安全前端事件推送器，通过 `AppHandle.run_on_main_thread` 确保在主线程执行，避免 PyO3 跨线程访问 panic。同时提供 `emit_plugin_event` 桥接插件事件系统。

### ECLauncherCore `ECL/game/Core/ECLauncherCore.py`

Minecraft 启动引擎：参数校验 → 文件完整性校验 → JVM 参数构建 → 依赖解析 → ClassPath 构建 → Native 解压 → 语言设置 → 子进程启动。

### GetGames `ECL/game/Core/C_GetGames.py`

版本获取与下载。Mojang API 版本元数据 + Fabric Meta v2 API 加载器版本。支持原版和 Fabric 版本的完整下载安装（JAR + 库文件 + 资源索引）。

### Downloader `ECL/game/Core/C_Downloader.py`

多线程下载器，支持断点续传、SHA1 校验、自动重试（指数退避算法）、实时进度回调。通过 `cancel_all_downloads()` 支持取消。

### FilesChecker `ECL/game/Core/C_FilesChecker.py`

文件完整性校验，校验游戏本体、依赖库、资源索引文件。支持多镜像源智能路由。

### PluginFramework `ECL/plugin/framework.py`

插件生命周期管理：扫描 → 加载 → 启用 → 禁用 → 卸载 → 重载。依赖解析（拓扑排序）、隔离命名空间导入、设置持久化、路由/命令/插槽注册。

### Plugin `ECL/plugin/plugin.py`

插件基类，提供完整生命周期钩子（同步 + 异步）、`@Plugin.on()` 事件装饰器、`@Plugin.provide_event()` 事件注册、服务注册/获取、设置读写、CSS/HTML/JS/路由/命令前端注入。

### AccountManager `ECL/auth/manager.py`

单例账户管理器，封装微软正版和离线账户的添加、切换、移除、令牌刷新。账户数据加密持久化。

### MultiAccountMinecraftAuth `ECL/auth/microsoft.py`

微软 OAuth 2.0 设备码流程认证，支持多账户缓存与令牌自动刷新。

### SmartKeyringManager `ECL/auth/crypto.py`

四级密钥环降级策略：系统密钥环 → 加密文件 → JSON 文件 → 自定义回退。EncryptionManager 提供 PBKDF2HMAC (SHA256, 600k 迭代) + Fernet (AES-128-CBC) 加密。

### JavaDetector `ECL/java/detector.py`

多源并行 Java 扫描：Windows 注册表 → JAVA_HOME 环境变量 → PATH 搜索 → Unix 工具链。线程池并行执行，按 MC 版本智能推荐合适的 Java 运行时。

## API 参考

所有 API 通过 `invoke('api_call', {body: {method, args, kwargs}})` 调用，统一返回：

```json
{ "success": true, "data": {}, "message": "" }
```

### 通用配置

| 方法 | 参数 | 说明 |
|------|------|------|
| `config_get` | `section: str` | 获取指定配置分区 |
| `config_set` | `section: str, data: dict` | 设置指定配置分区 |
| `config_get_all` | — | 获取全部配置 |
| `config_get_many` | `sections: list[str]` | 批量获取多个配置分区 |
| `config_list` | — | 列出所有配置分区名 |

### 启动器配置

| 方法 | 参数 | 说明 |
|------|------|------|
| `get_launcher_config` | — | 获取启动器配置 |
| `get_background_config` | — | 获取背景配置 |
| `get_background_image` | — | 获取背景图片 |
| `update_background_config` | `background_config: dict` | 更新背景配置 |
| `update_background_image` | `image_type: str, image_path: str` | 更新背景图片 |
| `get_locale_config` | — | 获取语言配置 |
| `update_locale_config` | `locale: str` | 更新语言设置 |

### 主题配置

| 方法 | 参数 | 说明 |
|------|------|------|
| `get_theme_config` | — | 获取主题配置 |
| `update_theme_config` | `theme_config: dict` | 更新主题配置 |

### 鼠标特效

| 方法 | 参数 | 说明 |
|------|------|------|
| `get_mouse_effect_config` | — | 获取鼠标特效配置 |
| `update_mouse_effect_config` | `mouse_effect_config: dict` | 更新鼠标特效配置 |

### 游戏配置

| 方法 | 参数 | 说明 |
|------|------|------|
| `get_game_config` | — | 获取游戏配置 |
| `update_game_config` | `game_config: dict` | 更新游戏配置 |

### 下载配置

| 方法 | 参数 | 说明 |
|------|------|------|
| `get_download_config` | — | 获取下载配置 |
| `update_download_config` | `download_config: dict` | 更新下载配置 |

### Java

| 方法 | 参数 | 说明 |
|------|------|------|
| `get_java_list` | — | 获取已检测的 Java 列表 |

### 版本管理

| 方法 | 参数 | 说明 |
|------|------|------|
| `get_minecraft_versions` | `filter_type: str \| None` | 获取 Minecraft 版本列表，可按类型过滤 |
| `get_fabric_versions` | `game_version: str \| None` | 获取 Fabric 加载器版本列表 |
| `install_version` | `params: dict` | 安装版本（原版或 Fabric） |
| `uninstall_version` | `version_id: str, game_path: str \| None` | 卸载版本 |
| `scan_versions_in_path` | `path: str \| list` | 扫描指定目录中的已安装版本 |

### 账户管理

| 方法 | 参数 | 说明 |
|------|------|------|
| `get_accounts` | — | 获取所有账户列表 |
| `get_current_account` | — | 获取当前选中账户 |
| `add_offline_account` | `username: str` | 添加离线账户 |
| `start_microsoft_login` | — | 开始微软登录（获取设备码） |
| `poll_microsoft_login` | — | 轮询微软登录状态 |
| `complete_microsoft_login` | — | 完成微软登录 |
| `switch_account` | `account_id: str` | 切换当前账户 |
| `remove_account` | `account_id: str` | 移除账户 |
| `refresh_account_profile` | `account_id: str` | 刷新账户信息（皮肤/头像） |

### 游戏启动

| 方法 | 参数 | 说明 |
|------|------|------|
| `get_game_instances` | — | 获取运行中的游戏实例 |
| `launch_instance` | `params: dict` | 启动游戏实例 |
| `get_launch_status` | `task_id: str` | 获取启动任务状态 |
| `stop_instance` | `instance_id: str` | 停止游戏实例 |
| `cancel_launch` | — | 取消当前启动 |

### 密钥环

| 方法 | 参数 | 说明 |
|------|------|------|
| `set_master_password` | `password: str` | 设置主密码 |
| `get_keyring_info` | — | 获取密钥环状态信息 |
| `clear_keyring` | — | 清除密钥环数据 |

### 插件管理

| 方法 | 参数 | 说明 |
|------|------|------|
| `plugin_list` | — | 列出所有插件及状态 |
| `plugin_info` | `plugin_name: str` | 获取插件详细信息 |
| `plugin_enable` | `plugin_name: str` | 启用插件 |
| `plugin_disable` | `plugin_name: str, force: bool` | 禁用插件 |
| `plugin_unload` | `plugin_name: str` | 卸载插件 |
| `plugin_reload` | `plugin_name: str, cascade: bool` | 重载插件 |
| `plugin_install` | `plugin_path: str` | 安装插件 |
| `plugin_get_settings` | `plugin_name: str` | 获取插件设置 |
| `plugin_update_setting` | `plugin_name: str, key: str, value: any` | 更新插件设置 |
| `plugin_get_routes` | — | 获取所有插件注册的路由 |
| `plugin_call_command` | `command: str, params: dict` | 调用插件命令 |
| `plugin_get_slots` | — | 获取所有插件 HTML 插槽 |

### 文件操作

| 方法 | 参数 | 说明 |
|------|------|------|
| `select_directory` | — | 打开目录选择对话框 |
| `select_java_executable` | — | 打开 Java 可执行文件选择对话框 |
| `select_local_image` | — | 打开本地图片选择对话框 |
| `load_image_from_local` | `path: str` | 从本地路径加载图片 |
| `load_image_from_url` | `url: str` | 从 URL 加载图片 |
| `fetch_image_data_url` | `url: str` | 从 URL 获取图片并转为 Data URL |

### 用户协议

| 方法 | 参数 | 说明 |
|------|------|------|
| `get_user_agreement_status` | — | 获取用户协议接受状态 |
| `save_user_agreement` | — | 保存用户协议接受状态 |
| `clear_user_agreement` | — | 清除用户协议状态 |

### 窗口控制

| 方法 | 参数 | 说明 |
|------|------|------|
| `minimize_window` | — | 最小化窗口 |
| `close_window` | — | 关闭窗口 |
| `get_window_position` | — | 获取窗口位置 |
| `set_window_position` | `x: int, y: int` | 设置窗口位置 |

### 其他

| 方法 | 参数 | 说明 |
|------|------|------|
| `ping` | — | 健康检查 |
| `frontend_ready` | — | 前端就绪通知（触发插件初始化） |
| `get_avatar_data_url` | `account_id: str` | 获取账户头像 Data URL |

### 前端调用示例

```typescript
import { invoke } from '@tauri-apps/api/core';

// 获取版本列表
const result = await invoke('api_call', {
  body: { method: 'get_minecraft_versions', args: [], kwargs: {} }
});

// 安装版本
await invoke('api_call', {
  body: {
    method: 'install_version',
    args: [],
    kwargs: {
      params: {
        version_id: '1.21',
        version_type: 'release',
        game_path: './.minecraft',
        loader_type: 'fabric',
        loader_version: '0.16.10',
        version_name: '1.21-fabric-0.16.10'
      }
    }
  }
});
```

## 事件系统

### 后端 → 前端事件

通过 `EventEmitter.emit()` 推送，前端通过 `listen()` 监听：

| 事件 | 触发时机 | 载荷 |
|------|---------|------|
| `launcher:notify` | 通用通知 | `{title, message, level}` |
| `launcher:agreement_required` | 需要用户协议确认 | `{}` |
| `keyring:password_required` | 需要输入主密码 | `{}` |
| `download:progress` | 下载进度更新 | `{version_id, progress, speed, ...}` |
| `launcher:launch_progress` | 启动进度更新 | `{stage, progress, message}` |
| `plugin:css_injected` | 插件注入 CSS | `{plugin, css}` |
| `plugin:script_injected` | 插件注入 JS | `{plugin, script}` |
| `plugin:slots_cleared` | 插件插槽已清除 | `{}` |

### 插件事件系统

插件通过 `EventRegistry` 进行事件订阅/发布：

```python
# 订阅事件
@Plugin.on("game:launched")
def on_game_launched(self, version_id: str):
    print(f"游戏已启动: {version_id}")

# 注册事件提供者
@Plugin.provide_event("my_plugin:data_ready", desc="数据就绪", params=["data_id"])
def prepare_data(self, data_id: str):
    return {"status": "ready"}
```

## 插件开发

### 插件目录结构

```
plugins/
└── my-plugin/
    ├── plugin.json          # 清单文件
    └── main.py              # 入口模块（Plugin 子类）
```

### plugin.json

```json
{
  "name": "my-plugin",
  "version": "1.0.0",
  "title": "我的插件",
  "description": "插件描述",
  "author": "作者",
  "entry_point": "main:MyPlugin",
  "dependencies": {
    "plugins": {},
    "third_party": {}
  },
  "events": {
    "provided": [],
    "required": []
  }
}
```

### 生命周期钩子

| 钩子 | 同步 | 异步 | 调用时机 |
|------|------|------|---------|
| `on_load` | `on_load()` | `async_on_load()` | 加载资源，读取配置 |
| `on_enable` | `on_enable()` | `async_on_enable()` | 初始化状态，注册服务 |
| `on_frontend_ready` | `on_frontend_ready()` | `async_on_frontend_ready()` | 前端就绪，可注入 UI |
| `on_disable` | `on_disable()` | `async_on_disable()` | 清理运行时状态 |
| `on_unload` | `on_unload()` | `async_on_unload()` | 释放资源 |

### Plugin 基类 API

```python
from ECL.plugin import Plugin

class MyPlugin(Plugin):
    def on_enable(self):
        # 注册服务
        self.register_service("my_service", handler)

        # 注册设置
        self.register_settings({
            "my_setting": {"type": "string", "default": "hello"}
        })

        # 注册前端路由
        self.register_route("/my-plugin", "我的插件", "plugin")

        # 注册命令
        self.register_command("my_action", self.handle_action, "执行操作")

    def on_frontend_ready(self):
        # 注入 CSS
        self.inject_css(".my-class { color: red; }")

        # 注入 HTML 到指定插槽
        self.inject_html("sidebar", "<div>Hello</div>")

        # 注入 JS
        self.inject_script("console.log('plugin loaded')")

        # 发送事件
        self.emit("my_plugin:ready", data="hello")

    def on_disable(self):
        # 清理路由
        self.unregister_route("/my-plugin")
```

### 读取/更新设置

```python
# 读取设置（带默认值）
value = self.get_setting("my_setting", "default_value")

# 更新设置（自动持久化到 plugin_config/）
self.update_setting("my_setting", "new_value")
```

### 获取服务

```python
# 获取其他插件注册的服务
other_service = self.get_service("other_plugin.service_name")
```

详细插件开发文档见 [plugin-dev-guide.md](docs/plugin-dev-guide.md) 和 [后端开发文档](docs/backend-dev-doc/backend-dev-doc.html)。

## 构建与发布

### 前端构建

```bash
cd EuoraCraftLauncher-UI
pnpm build
```

构建产物输出到 `EuoraCraftLauncher-UI/dist/`，Tauri 打包时自动引用。

### 打包

```bash
pyinstaller "EuoraCraft-Launcher.spec"
```

配置：onedir 模式，带控制台窗口，图标 `assets/icon.ico`。

### 版本发布

项目使用 python-semantic-release，遵循 Conventional Commits 规范：

| Commit 前缀 | 版本变更 | 示例 |
|------------|---------|------|
| `fix:` | 补丁版本 (0.1.0 → 0.1.1) | `fix: 修复下载器断点续传逻辑` |
| `feat:` | 次版本 (0.1.0 → 0.2.0) | `feat: 添加 Forge 安装支持` |
| `feat!:` / `BREAKING CHANGE:` | 主版本 (0.1.0 → 1.0.0) | `feat!: 重构插件 API` |

```bash
# 自动计算版本号并更新 pyproject.toml、version.py、CHANGELOG.md
semantic-release version
```

版本号自动同步到三个位置：`pyproject.toml:project.version`、`ECL/common/version.py:__version__`、`CHANGELOG.md`。启动器每次启动时以 `version.py` 为权威来源同步到 `setting.json`。

## 调试

在 `setting.json` 中启用：

```json
{ "launcher": { "debug": true } }
```

或通过环境变量：

```ini
ECL_LAUNCHER_DEBUG=true
```

调试模式下日志级别提升至 DEBUG，启动时输出完整配置内容，日志文件位于 `logs/` 目录。

## 安全

- 微软 OAuth 通过设备码流程认证，无需用户密码
- 账户凭据使用 PBKDF2HMAC (SHA256, 600,000 次迭代) + Fernet (AES-128-CBC) 加密
- 密钥环四级降级策略：系统密钥环 → 加密文件 → JSON 文件 → 自定义回退
- 账户数据加密存储在 `~/.ECLAuth/`
- 敏感信息不记录到日志文件

## 相关链接

- 项目主页: https://github.com/ECLTeam/EuoraCraft-Launcher
- 问题反馈: https://github.com/ECLTeam/EuoraCraft-Launcher/issues
- 邮箱: EuoraCraft-Studio@outlook.com
- 许可证: GPL-3.0