# EuoraCraft Launcher 后端开发文档

## 项目概览

EuoraCraft Launcher 后端基于 **Python 3.11+**，使用 **PyTauri** 框架与前端通信，通过 **asyncio** 实现异步架构。后端负责 Minecraft 游戏核心逻辑、账户鉴权、版本管理、插件系统、Mod 管理、资源包管理等全部业务逻辑。

仓库地址：`https://github.com/ECLTeam/EuoraCraft-Launcher`

---

## 环境搭建

### 前置要求

| 工具 | 最低版本 | 说明 |
|------|----------|------|
| Python | 3.11 | 运行时 |
| Rust | 1.70+ | Tauri 编译依赖 |
| Git | 2.x | 版本控制 |

### 安装步骤

```bash
git clone https://github.com/ECLTeam/EuoraCraft-Launcher.git
cd EuoraCraft-Launcher

# 创建虚拟环境（推荐）
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/macOS

# 安装依赖
pip install -e ".[dev]"
```

### 环境变量

在项目根目录创建 `.env` 或 `.env.dev`（开发环境优先读取 `.env.dev`）：

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `MICROSOFT_CLIENT_ID` | 微软 OAuth 客户端 ID | 空 |
| `FRONTEND_DEV_SERVER` | 前端 dev server URL | `http://localhost:5173` |
| `FRONTEND_PATH` | 生产模式前端静态文件路径 | 空 |
| `ECL_UI_*` | 运行时覆盖 UI 配置项 | — |
| `ECL_GAME_*` | 运行时覆盖游戏配置项 | — |

> 所有环境变量通过 `EnvLoader` 类统一读取，禁止直接使用 `os.environ.get()`。

### 启动开发模式

```bash
# 终端1：启动前端 dev server
cd EuoraCraftLauncher-UI && pnpm dev

# 终端2：启动后端
python main.py
```

---

## 项目结构

```
ECL/
├── __init__.py
├── app.py              # 应用入口，创建 Launcher 并运行
├── launcher.py         # EuoraCraftLauncher 核心类，初始化全流程
├── adapters/
│   └── adapter.py      # Tauri 适配器，run_app() 绑定 API 处理器
├── api/
│   ├── handlers.py     # Api 类，所有后端命令的处理器
│   └── events.py       # EventEmitter，向前端推送事件
├── auth/
│   ├── manager.py      # AccountManager，账户生命周期管理
│   ├── microsoft.py    # MultiAccountMinecraftAuth，微软 OAuth 登录
│   ├── authlib.py      # AuthlibInjectorAccount + AuthlibInjectorManager
│   ├── crypto.py       # 加密工具（keyring 集成）
│   └── models.py       # MinecraftAccount 数据模型
├── common/
│   ├── config.py       # ConfigManager，setting.json 持久化
│   ├── env.py          # EnvLoader，环境变量统一加载
│   ├── logger.py       # LoggerManager，日志系统
│   ├── state.py        # AppState，全局状态单例
│   └── version.py      # 版本号（由 semantic-release 管理）
├── game/
│   └── Core/           # 游戏核心（严格禁止修改此目录）
│       ├── ECLauncherCore.py    # 启动核心
│       ├── C_Downloader.py      # 下载器
│       ├── C_FilesChecker.py    # 文件校验
│       ├── C_GetGames.py        # 版本获取
│       ├── C_Libs.py            # 工具函数
│       ├── C_Skin.py            # 皮肤管理
│       └── InstancesManager.py  # 实例管理
├── java/
│   ├── detector.py     # JavaDetector，扫描系统 Java 安装
│   └── models.py       # JavaInfo 数据模型
├── mods/
│   ├── manager.py      # ModManager，本地 Mod 管理
│   ├── pack.py         # ModpackManager，整合包导入导出
│   └── search.py       # OnlineModSearch，在线 Mod 搜索
├── plugin/
│   ├── framework.py    # PluginFramework，插件系统核心
│   ├── plugin.py       # Plugin 基类，生命周期钩子
│   ├── importer.py     # PluginImporter，依赖导入隔离
│   └── registry.py     # EventRegistry + ServiceRegistry
└── resources/
    └── manager.py      # ResourceManager，资源包/光影/存档管理
```

---

## 启动流程

应用启动遵循严格的初始化顺序，由 `EuoraCraftLauncher` 类驱动：

```
main.py
  └─ app.main()
       ├─ EuoraCraftLauncher()          # 创建核心实例
       └─ launcher.init_launcher()      # 异步初始化
            ├─ __init_system_test()     # 检测操作系统
            ├─ __check_launcher_coredir() # 验证核心目录
            ├─ AppState.initialize_async()
            │    ├─ ConfigManager.load()     # 加载 setting.json
            │    ├─ ConfigManager.validate() # 校验配置
            │    ├─ JavaDetector.detect_all_parallel() # 扫描 Java
            │    └─ AccountManager.initialize() # 初始化账户
            ├─ __handle_version_info()   # 处理版本信息
            ├─ __check_game_paths()      # 校验游戏路径
            ├─ __setup_debug_mode()      # 调试模式
            └─ __preload_version_list()  # 后台预加载版本列表
       └─ run_app(launcher)             # 启动 Tauri 窗口
```

---

## 核心模块详解

### AppState — 全局状态

`AppState` 使用 `@singleton` 装饰器，全局唯一实例，持有所有核心组件的引用：

```python
from ECL.common.state import AppState

state = AppState()
state.config_manager     # ConfigManager 实例
state.account_manager    # AccountManager 实例
state.java_list          # list[JavaInfo]
state.launcher_core      # ECLauncherCore 实例
state.get_games          # GetGames 实例
state.plugin_framework   # PluginFramework 实例（延迟初始化）
```

进度事件通过**线程安全队列**传递：

- 子线程调用 `_safe_emit()` 将事件入队
- asyncio 主线程每 50ms 轮询消费队列
- 消费时调用 `emit_direct()` 推送到前端

> 单例锁使用 `threading.RLock`（可重入锁），避免初始化代码中递归获取同一单例时死锁。

### ConfigManager — 配置管理

负责 `setting.json` 的读写，位于运行时目录（`get_runtime_dir()`）：

```python
from ECL.common.config import ConfigManager

cm = ConfigManager()
cm.load()                    # 加载配置
cm.get("game")               # {"minecraft_paths": [...], "java_auto": true, ...}
cm.get("game", "memory_size") # 4096
cm.set("ui", "locale", "en-US")  # 设置单个值
cm.set("game", {"memory_size": 8192})  # 深度合并
cm.save()                    # 持久化
```

配置结构：

```json
{
  "launcher": {
    "version": "0.1.0",
    "version_type": "dev",
    "debug": false,
    "launcher_uuid": "..."
  },
  "ui": {
    "width": 900, "height": 600,
    "title": "EuoraCraft Launcher",
    "locale": "zh-CN",
    "theme": { "mode": "system", "primary_color": "#4A7FD9" }
  },
  "game": {
    "minecraft_paths": [{"name": "默认路径", "path": "...", "protected": true}],
    "java_auto": true,
    "memory_size": 4096
  },
  "download": {
    "mirror_source": "official",
    "download_threads": 4
  }
}
```

配置支持自动补全：缺少的字段会自动从 `DEFAULT_CONFIG` 合并，保证新版本向后兼容。版本号始终以 `ECL/common/version.py` 为权威来源，每次启动同步到配置文件。

所有路径解析必须使用 `ConfigManager.config_path.parent`，确保与 `setting.json` 位置一致。

### EnvLoader — 环境变量

统一环境变量读取入口：

```python
from ECL.common.env import EnvLoader

env = EnvLoader()
env.get("MICROSOFT_CLIENT_ID")      # 从 .env / .env.dev / 系统环境变量读取
env.get("MICROSOFT_CLIENT_ID", "")  # 默认值
```

加载优先级：`.env.dev` > `.env` > 系统环境变量。开发模式下从 CWD 查找，打包模式下额外检查 exe 所在目录。

> 禁止在代码中直接使用 `os.environ.get()`，必须通过 `EnvLoader` 统一读取。

### AccountManager — 账户管理

单例模式，统一管理微软账户、离线账户和 Authlib 外置登录账户：

```python
from ECL.auth.manager import AccountManager

am = AccountManager()
await am.initialize()                        # 初始化账户系统

# 离线账户
am.add_offline_account("PlayerName")         # 添加离线账户

# 微软登录（设备码流程）
am.start_microsoft_login()                   # 启动登录，返回 user_code + verification_uri
am.poll_microsoft_login()                    # 轮询登录状态
am.open_browser_for_auth(url)               # 打开浏览器
am.complete_microsoft_login()               # 完成登录

# Authlib 外置登录
am.add_authlib_account(server_url, email, password)

# 账户操作
am.get_all_accounts()                        # 获取所有账户
am.get_current_account()                     # 获取当前选中账户
am.get_current_account_token()              # 获取当前 token（含自动刷新）
am.switch_account(account_id)               # 切换账户
am.remove_account(account_id)               # 移除账户
am.refresh_account_profile(account_id)      # 刷新账户档案
am.shutdown()                                # 清理资源
```

微软登录使用 MSAL 设备码流 OAuth 认证，完整认证链：Microsoft -> Xbox Live -> XSTS -> Minecraft。Token 缓存有自动刷新机制（过期前 5 分钟）。

Authlib 账户与微软账户互斥：切换 Authlib 时清除微软 `current_account`，反之亦然。数据持久化到 `~/.ECLAuth/`。

### MultiAccountMinecraftAuth — 微软认证

`ECL/auth/microsoft.py` 中的 `MultiAccountMinecraftAuth` 类封装完整的微软 OAuth 流程：

- 使用 MSAL 设备码流（`acquire_token_by_device_flow`）
- 异步轮询模式：`ThreadPoolExecutor` 在后台执行认证
- 完整认证链：Microsoft token -> Xbox Live token -> XSTS token -> Minecraft token
- 账户数据通过 `EncryptionManager` 加密存储
- 离线账户 UUID 通过 `MD5("OfflinePlayer:{username}")` 生成

### JavaDetector — Java 扫描

自动扫描系统已安装的 Java 运行时：

```python
from ECL.java.detector import JavaDetector

jd = JavaDetector()
java_list = jd.detect_all()              # 同步扫描
java_list = await jd.detect_all_parallel()  # 异步并行扫描
```

扫描来源：
- **Windows**：注册表（HKLM + WOW6432Node）、JAVA_HOME、PATH
- **Linux/macOS**：`which java`、`update-alternatives`、JAVA_HOME
- 按 `major_version` 降序排列
- 共享线程池（`max_workers=4`）
- 去重依据：`java_home 路径 + major_version`

### ModManager — 本地 Mod 管理

```python
from ECL.mods.manager import ModManager

ModManager.get_mods(game_path)              # 扫描 mods 目录，解析元数据
ModManager.toggle_mod(game_path, filename)  # 启用/禁用（.jar <-> .jar.disabled）
ModManager.add_mod(game_path, source_path)  # 复制 mod 到 mods 目录
ModManager.remove_mod(game_path, filename)  # 删除 mod
ModManager.open_mods_folder(game_path)      # 打开 mods 文件夹
```

元数据解析支持 6 种格式：`mcmod.info`、`fabric.mod.json`、`quilt.mod.json`、`META-INF/mods.toml`（Forge）、`META-INF/neoforge.mods.toml`（NeoForge）、`litemod.json`（LiteLoader）。解析优先级：后面格式覆盖前面。

### OnlineModSearch — 在线 Mod 搜索

```python
from ECL.mods.search import OnlineModSearch

OnlineModSearch.search_mods("optifine", loader="forge", version="1.20.4", limit=20)
OnlineModSearch.get_mod_info("project_id", source="modrinth")
OnlineModSearch.get_mod_versions("project_id", source="modrinth", loader="forge")
OnlineModSearch.download_mod("project_id", "version_id", "modrinth", game_path)
```

支持双源搜索：Modrinth API v2（无需认证）和 CurseForge API v1（需要 API Key）。按 slug 去重，Modrinth 结果优先。

### ResourceManager — 资源管理

```python
from ECL.resources.manager import ResourceManager

ResourceManager.list_resourcepacks(game_path)    # 资源包列表
ResourceManager.list_shaderpacks(game_path)      # 光影包列表
ResourceManager.list_saves(game_path)            # 存档列表（含 NBT 解析）
ResourceManager.remove_resourcepack(game_path, filename)
ResourceManager.delete_save(game_path, save_name)
ResourceManager.open_resourcepacks_folder(game_path)
```

存档列表通过解析 `level.dat`（GZip 压缩的 NBT 格式）提取 `LevelName`、`GameType`、`LastPlayed`。NBT 解析为纯手工实现，支持全部 12 种标签类型。

### EventEmitter — 事件系统

```python
from ECL.api.events import EventEmitter

emitter = EventEmitter(app_handle)
emitter.emit("game:launch_progress", {"phase": "preparing", "percent": 50})
emitter.emit_direct("config:init", config_data)  # 主线程直接发射
emitter._safe_emit("game:install_progress", data)  # 子线程安全入队
```

关键事件列表：

| 事件名 | 方向 | 说明 |
|--------|------|------|
| `config:init` | 后端→前端 | 首次推送完整配置 |
| `launcher:notify` | 后端→前端 | 通知消息（warning/info） |
| `launcher:agreement_required` | 后端→前端 | 需要同意用户协议 |
| `keyring:password_required` | 后端→前端 | 需要设置主密码 |
| `game:launch_progress` | 后端→前端 | 游戏启动进度 |
| `game:install_progress` | 后端→前端 | 版本安装进度 |
| `plugin:css_injected` | 后端→前端 | 插件注入 CSS |
| `plugin:script_injected` | 后端→前端 | 插件注入脚本 |
| `config:changed` | 后端→插件 | 配置变更通知插件 |

> `AppHandle` 必须在主线程创建时存储，跨线程事件通过 `run_on_main_thread` 发射。主线程使用 `emit_direct()`，子线程使用 `_safe_emit()` 入队。

---

## API 处理器

所有后端 API 集中在 `ECL/api/handlers.py` 的 `Api` 类中。每个方法返回 `{"success": bool, "message": str, "data": Any}` 格式。

### 添加新 API

```python
# 在 Api 类中添加方法
async def my_new_command(self, param1: str, param2: int = 0) -> dict:
    try:
        # 业务逻辑
        result = do_something(param1, param2)
        return {"success": True, "message": "", "data": result}
    except SomeSpecificError as e:
        return {"success": False, "message": str(e), "data": None}
```

方法名自动成为前端可调用的命令名（`backend.command('my_new_command', {param1: '...', param2: 1})`）。前后端参数名必须精确匹配，使用蛇形命名（`version_id`，非 `versionId`）。

### 配置存取

配置通过 `Api` 类的 `config_get` 和 `config_set` 方法暴露：

```python
async def config_get(self, section: str) -> dict:
    """获取配置分区"""
    value = self._config_manager.get(section)
    return {"success": True, "message": "", "data": value}

async def config_set(self, section: str, data: dict) -> dict:
    """更新配置分区"""
    self._config_manager.set(section, data)
    self._config_manager.save()
    return {"success": True, "message": "", "data": None}
```

---

## 插件系统

### 插件框架

`PluginFramework` 是插件系统的核心，管理插件的完整生命周期：

```python
from ECL.plugin.framework import PluginFramework

pf = PluginFramework(
    plugins_dir="plugins/",           # 用户插件目录
    cache_root="plugins/dep_cache/",  # 依赖缓存
    config_root="plugins/config/",    # 插件配置
    system_plugins_dir="system_plugins/"  # 系统插件目录
)
```

主要方法：

| 方法 | 说明 |
|------|------|
| `load_plugin(path)` | 加载插件（依赖解析 + 隔离导入） |
| `enable_plugin(name)` | 启用插件 |
| `disable_plugin(name)` | 禁用插件 |
| `unload_plugin(name)` | 卸载插件（清理资源） |
| `reload_plugin(name)` | 重载插件 |
| `get_plugin(name)` | 获取插件实例 |
| `list_plugins()` | 列出所有插件状态 |
| `call_command(plugin_name, command, params)` | 调用插件命令 |
| `get_plugin_settings(name)` | 获取插件设置 |
| `update_plugin_setting(name, key, value)` | 更新插件设置 |
| `register_route(plugin_name, path, title, icon)` | 注册前端路由 |
| `inject_css(plugin_name, css)` | 注入 CSS |
| `inject_html(plugin_name, slot_id, html)` | 注入 HTML |
| `shutdown()` | 关闭所有插件 |

### Plugin 基类

插件必须继承 `Plugin` 基类：

```python
from ECL.plugin.plugin import Plugin

class MyPlugin(Plugin):
    # 元数据（由 plugin.json 加载，也可在此声明）
    # meta = {"name": "my_plugin", "version": "1.0.0", ...}

    def on_load(self):
        """加载资源文件"""
        pass

    def on_enable(self):
        """初始化状态，注册服务"""
        self.register_service("my_service", self.handle_service)
        self.register_settings({"api_key": {"type": "string", "default": ""}})
        self.register_route("/my-page", "我的页面", "icon-name")
        self.register_command("do_something", self.do_something, "执行操作")

    def on_frontend_ready(self):
        """前端就绪后，发送事件、注入 UI"""
        self.inject_css(".my-plugin { color: red; }")
        self.inject_html("page-bottom", "<div>Hello</div>")

    def on_disable(self):
        """清理运行时状态"""
        pass

    def on_unload(self):
        """释放所有资源"""
        pass

    # 声明提供的事件
    @Plugin.provide_event("my_event", "事件描述", ["param1", "param2"])
    def handle_my_event(self, param1, param2):
        pass

    # 监听事件
    @Plugin.on("config:changed")
    def on_config_changed(self, section, old_value, new_value):
        pass
```

### 插件元数据

每个插件目录下必须有 `plugin.json`：

```json
{
  "name": "my_plugin",
  "title": "我的插件",
  "version": "1.0.0",
  "description": "插件描述",
  "author": "作者",
  "icon": "icon-name",
  "entry_point": "main:MyPlugin",
  "dependencies": {
    "plugins": {
      "other_plugin": ">=1.0.0"
    },
    "python": {
      "requests": ">=2.28.0"
    }
  }
}
```

### 插件目录结构

```
plugins/
└── my_plugin/
    ├── plugin.json
    └── main.py         # 包含 Plugin 子类
```

### 注册机制

插件通过 `PluginFramework` 提供的注册方法扩展启动器：

- `register_service(name, handler)` — 注册服务（供其他插件调用）
- `register_settings(schema)` — 注册设置面板
- `register_route(path, title, icon)` — 注册前端路由
- `register_command(name, handler, description)` — 注册后端命令
- `inject_css(css)` — 注入前端样式
- `inject_html(slot_id, html)` — 注入 HTML 到指定插槽

---

## 游戏核心（ECL.game.Core）

游戏核心位于 `ECL/game/Core/`，包含以下模块：

| 模块 | 类/函数 | 说明 |
|------|---------|------|
| `ECLauncherCore` | 类 | 游戏启动核心，管理 JVM 参数、类路径、启动流程 |
| `C_Downloader` | 类 | 多线程下载器，支持断点续传、镜像切换 |
| `C_FilesChecker` | 类 | 文件完整性校验（SHA1） |
| `C_GetGames` | 类 | 版本列表获取（Mojang API + BMCLAPI 镜像） |
| `C_Libs` | 工具函数 | `find_version`、`name_to_path`、`unzip` 等 |
| `C_Skin` | 皮肤函数 | `get_skin_address`、`download_skin`、`get_avatar_data_url` |
| `InstancesManager` | 类 | 版本实例管理 |

> 严格禁止修改 `ECL.game.Core` 目录下的任何文件。新增功能应通过外部模块或插件系统实现。

---

## 开发规范

### 代码风格

1. **模块封装**：非核心模块使用类封装（如 `ConfigManager`、`AccountManager`）
2. **异常处理**：使用具体异常类型（`FileNotFoundError`、`OSError`），避免 `except Exception`
3. **环境变量**：统一通过 `EnvLoader` 类读取
4. **配置路径**：使用 `ConfigManager.config_path.parent` 解析路径
5. **游戏核心**：严格避免修改 `ECL.game.Core` 目录
6. **新代码风格**：匹配 `ECL.game.Core` 风格（无 docstrings、最小化类型注解、行内注释）

### 线程安全

1. `AppHandle` 必须在主线程创建时存储，跨线程事件通过 `run_on_main_thread` 发射
2. 主线程使用 `emit_direct()`，子线程使用 `_safe_emit()` 入队
3. 单例锁使用 `threading.RLock`（可重入锁），避免死锁
4. 下载器必须显式调用 `cancel_all_downloads()` 通知后台线程取消

### 路径处理

1. `game_path` 必须用 `Path.resolve()` 转为绝对路径
2. 资源目录：开发模式读 `{work_dir}/resources/`，打包模式读 `sys._MEIPASS/resources/`
3. 版本文件夹使用用户自定义名称（如 `1.20.4-fabric-0.15.11`）

### Forge/NeoForge 安装

1. 使用合并 JSON 模式：下载原版到版本文件夹，合并 `arguments`/`libraries`，移除 `inheritsFrom`
2. API 端点和文件下载 URL 分离：`ForgeMeta`（API 调用）和 `ForgeMaven`（文件下载）

---

## 构建与部署

### 版本管理

版本号由 `python-semantic-release` 自动管理：

- `pyproject.toml:project.version` — 包版本
- `ECL/common/version.py:__version__` — 运行时版本（禁止手动修改）
- `__version_type__`：`dev`（开发版）、`beta`（测试版）、`release`（正式版）

### 构建命令

```bash
# 代码检查
ruff check ECL/

# 打包
pyinstaller EuoraCraft-Launcher.spec
```

### 多平台 CI

GitHub Actions 自动构建 Windows/Linux/macOS x64 和 macOS arm64 四个平台。前端仓库独立检出，`MICROSOFT_CLIENT_ID` 从 GitHub Secrets 注入。

---

## 常用操作

### 添加新命令（后端 API）

1. 在 `ECL/api/handlers.py` 的 `Api` 类中添加 async 方法
2. 返回标准格式 `{"success": bool, "message": str, "data": Any}`
3. 前端通过 `backend.command('method_name', params)` 调用

### 向前端推送事件

```python
# 在 Api 类中
self._events.emit("my_event", {"key": "value"})

# 在外部模块中
from ECL.api.events import EventEmitter
emitter = EventEmitter(app_handle)
emitter.emit("my_event", {"key": "value"})
```

### 添加新配置项

1. 在 `ConfigManager.DEFAULT_CONFIG` 中添加默认值
2. 配置自动补全会处理已有配置文件的缺失字段

### 添加新账户类型

1. 在 `ECL/auth/models.py` 中扩展 `MinecraftAccount` 或创建新模型
2. 在 `ECL/auth/manager.py` 中添加对应方法
3. 在 `ECL/api/handlers.py` 中添加 API 端点