# EuoraCraft Launcher 插件开发指南

## 目录

1. [快速开始](#快速开始)
2. [插件结构](#插件结构)
3. [Manifest 格式](#manifest-格式)
4. [Plugin 基类](#plugin-基类)
5. [生命周期](#生命周期)
6. [事件系统](#事件系统)
7. [服务注册](#服务注册)
8. [插件设置](#插件设置)
9. [前端自由注入](#前端自由注入)
10. [依赖管理](#依赖管理)
11. [前端交互](#前端交互)
12. [完整示例](#完整示例)

---

## 快速开始

一个最小插件只需要两个文件：

```
plugins/my_plugin/
├── plugin.json
└── main.py
```

**main.py**

```python
from ECL.plugin.plugin import Plugin

class MyPlugin(Plugin):

    def on_enable(self):
        pass

    def on_frontend_ready(self):
        from ECL.api.events import emit
        emit("launcher:notify", {"message": "插件已加载", "type": "info"})
```

**plugin.json**

```json
{
  "name": "my_plugin",
  "version": "1.0.0",
  "title": "我的插件",
  "description": "这是一个示例插件",
  "author": "你的名字",
  "entry_point": "main:MyPlugin"
}
```

重启启动器，插件会自动加载。

---

## 插件结构

插件存放在启动器根目录的 `plugins/` 下，每个插件是一个独立目录：

```
plugins/
├── hello_world/
│   ├── plugin.json
│   └── main.py
├── my_plugin/
│   ├── plugin.json
│   ├── main.py
│   └── resources/
│       └── icon.png
```

---

## Manifest 格式

`plugin.json` 是插件的元数据文件，必需字段如下：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | 是 | 插件唯一标识，只能包含字母、数字、下划线 |
| `version` | string | 是 | 版本号，建议用语义化版本 |
| `title` | string | 否 | 显示名称，缺省使用 `name` |
| `description` | string | 否 | 插件描述 |
| `author` | string | 否 | 作者 |
| `icon` | string | 否 | 图标路径（相对插件目录） |
| `entry_point` | string | 是 | 入口点，格式 `module:ClassName` |
| `dependencies` | object | 否 | 依赖声明 |

### dependencies 格式

```json
{
  "dependencies": {
    "third_party": {
      "requests": ">=2.28.0"
    },
    "plugins": {
      "hello_world": ">=1.0.0"
    }
  }
}
```

- `third_party`：第三方 Python 包，需预先放入 `dep_cache/` 目录
- `plugins`：其他插件依赖，框架会自动按拓扑顺序加载

---

## Plugin 基类

所有插件必须继承 `ECL.plugin.plugin.Plugin`。

```python
from ECL.plugin.plugin import Plugin

class MyPlugin(Plugin):
    ...
```

### 内置属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `self.name` | str | 插件名称（来自 manifest） |
| `self.version` | str | 插件版本 |
| `self.status` | PluginStatus | 当前状态 |
| `self.meta` | dict | 完整的 manifest 数据 |
| `self.framework` | PluginFramework | 框架控制器 |

### 内置方法

| 方法 | 说明 |
|------|------|
| `self.register_service(name, handler)` | 注册服务 |
| `self.unregister_service(name)` | 注销服务 |
| `self.get_service(name)` | 获取其他插件的服务 |
| `self.emit(event, *args, **kwargs)` | 发送同步事件 |
| `self.emit_async(event, *args, **kwargs)` | 发送异步事件（后台执行） |
| `self.require(package_name)` | 加载第三方包 |

---

## 生命周期

插件有完整的生命周期状态机：

```
UNLOADED → LOADING → LOADED → ENABLING → ENABLED
                              ↓
                        DISABLING → DISABLED → UNLOADING → UNLOADED
```

### 回调方法

| 回调 | 触发时机 | 用途 |
|------|----------|------|
| `on_load()` | 插件被加载时 | 读取配置、准备资源 |
| `async_on_load()` | `on_load()` 后异步执行 | 异步初始化 |
| `on_enable()` | 插件被启用时 | 注册服务、订阅事件 |
| `async_on_enable()` | `on_enable()` 后异步执行 | 异步启用逻辑 |
| `on_frontend_ready()` | 前端 Vue 挂载完成后 | **向前端发送事件、UI 交互** |
| `on_disable()` | 插件被禁用时 | 清理运行时状态 |
| `async_on_disable()` | `on_disable()` 后异步执行 | 异步清理 |
| `on_unload()` | 插件被卸载时 | 释放资源 |
| `async_on_unload()` | `on_unload()` 后异步执行 | 异步释放 |

### 重要约定

- `on_enable` 只做**内部初始化**，不要向前端发事件（此时前端可能未就绪）
- `on_frontend_ready` 是向前端发送通知的正确时机
- `on_disable` / `on_unload` 中不要调用 `emit`（框架已标记为 shutting_down）

---

## 事件系统

### 订阅事件

使用类装饰器 `@Plugin.on(event_name)` 在类定义阶段声明事件处理器：

```python
class MyPlugin(Plugin):

    @Plugin.on("game:launch_start")
    def on_game_launch(self, payload):
        print(f"游戏启动: {payload}")

    @Plugin.on("some_event", async_handler=True)
    async def on_some_event_async(self, payload):
        await asyncio.sleep(1)
        print("异步处理完成")
```

- `@Plugin.on("event")` 在类定义时注册，插件 enable 时自动绑定到实例方法
- `async_handler=True` 标记为异步处理器

### 声明提供的事件

使用 `@Plugin.provide_event(name, desc, params)` 声明本插件提供的事件：

```python
class MyPlugin(Plugin):

    @Plugin.provide_event("my_plugin:custom_event", "自定义事件", ["data"])
    def on_custom_event(self, payload):
        pass
```

### 发送事件

```python
# 同步发送（在当前线程立即执行所有同步处理器）
self.emit("my_plugin:custom_event", {"key": "value"})

# 异步发送（在有事件循环时后台执行）
self.emit_async("my_plugin:custom_event", {"key": "value"})
```

### 系统内置事件

#### 游戏生命周期

| 事件 | 说明 | payload | 可取消 |
|------|------|---------|--------|
| `game:pre_launch` | 游戏启动前 | `{"version_id", "player_name", "user_type", "options"}` | 是（返回 False） |
| `game:launch_start` | 游戏进程已启动 | `{"version_id", "player_name"}` | 否 |
| `game:exit` | 游戏进程退出/停止 | `{"instance_id"?, "version_id"?, "exit_code", "reason"}` | 否 |

#### 账户

| 事件 | 说明 | payload |
|------|------|---------|
| `account:login` | 用户登录成功 | `{"account_type", "player_name", "uuid"?}` |
| `account:logout` | 用户登出/移除账户 | `{"account_type", "account_id"}` |
| `account:switch` | 切换账户 | `{"from_type", "to_type", "player_name"}` |

#### 下载

| 事件 | 说明 | payload |
|------|------|---------|
| `download:start` | 下载任务开始 | `{"task_id", "total_size"}` |
| `download:complete` | 下载完成 | `{"task_id"}` |
| `download:error` | 下载失败 | `{"task_id", "error"}` |

#### 版本/实例

| 事件 | 说明 | payload |
|------|------|---------|
| `version:installed` | 版本安装完成 | `{"version_id", "loader_type"}` |
| `version:uninstalled` | 版本卸载 | `{"version_id"}` |
| `instance:created` | 实例创建 | `{"instance_id", "name", "version"}` |
| `instance:deleted` | 实例删除 | `{"instance_id", "name"}` |

#### 配置

| 事件 | 说明 | payload |
|------|------|---------|
| `config:changed` | 配置项变更 | `{"section", "old_value", "new_value"}` |

#### 启动器生命周期

| 事件 | 说明 | payload |
|------|------|---------|
| `launcher:init_complete` | 启动器初始化完成 | `{}` |
| `launcher:shutdown` | 启动器即将关闭 | `{}` |
| `launcher:notify` | 向前端发送通知 | `{"message": "...", "type": "info/warning/error"}` |

#### Java / 版本

| 事件 | 说明 | payload |
|------|------|---------|
| `java:selected` | 用户选择 Java | `{"path": "..."}` |
| `version:scanned` | 版本扫描完成 | `{"count": N, "versions": [...]}` |

#### 用户

| 事件 | 说明 | payload |
|------|------|---------|
| `user:agreed` | 用户同意协议 | `{"uuid": "..."}` |

#### 插件

| 事件 | 说明 | payload | 可取消 |
|------|------|---------|--------|
| `plugin:pre_disable` | 某插件即将被禁用 | `{"plugin": "plugin_name"}` | 是 |
| `plugin:disabled` | 某插件已被禁用 | `{"plugin": "plugin_name"}` | 否 |
| `plugin:pre_reload` | 某插件即将重载 | `{"plugin": "plugin_name"}` | 是 |
| `plugin:reloaded` | 某插件已重载 | `{"plugin": "plugin_name"}` | 否 |
| `plugin:installed` | 新插件已安装 | `{"name": "plugin_name"}` | 否 |
| `plugin:enabled` | 插件启用完成 | `{"name": "...", "version": "..."}` | 否 |
| `plugin:pre_unload` | 插件即将卸载 | `{"name": "..."}` | 否 |
| `plugin:error` | 插件进入错误状态 | `{"name": "...", "error": "..."}` | 否 |

#### 账户补充

| 事件 | 说明 | payload |
|------|------|---------|
| `account:profile_refreshed` | 账户档案刷新 | `{"account_type", "player_name"}` |

### 拒绝机制

`game:pre_launch`、`plugin:pre_disable` 和 `plugin:pre_reload` 支持拒绝机制。处理器返回 `False` 可阻止操作：

```python
@Plugin.on("game:pre_launch")
def on_pre_launch(self, payload):
    # 检查版本是否允许启动
    if payload.get("version_id") == "forbidden_version":
        return False  # 阻止启动
    return None  # 允许

@Plugin.on("plugin:pre_disable")
def on_pre_disable(self, payload):
    plugin_name = payload.get("plugin", "")
    if plugin_name == "critical_plugin":
        return False  # 拒绝禁用
    return None  # 同意
```

---

## 服务注册

插件可以通过服务注册表暴露功能供其他插件调用：

```python
class MyPlugin(Plugin):

    def on_enable(self):
        self.register_service("my_plugin.calculate", self.calculate)

    def calculate(self, a, b):
        return a + b
```

其他插件调用：

```python
class OtherPlugin(Plugin):

    def on_enable(self):
        calc = self.get_service("my_plugin.calculate")
        if calc:
            result = calc(1, 2)
```

---

## 插件设置

插件可以注册自己的配置面板，供用户在前端设置页中调整：

```python
class MyPlugin(Plugin):

    def on_enable(self):
        self.register_settings({
            "greeting": {
                "type": "text",
                "label": "问候语",
                "description": "启动时显示的问候文字",
                "default": "你好世界"
            },
            "enabled": {
                "type": "boolean",
                "label": "启用功能",
                "description": "是否启用该功能",
                "default": True
            },
            "interval": {
                "type": "number",
                "label": "间隔(秒)",
                "description": "刷新间隔",
                "default": 30,
                "min": 5,
                "max": 300
            },
            "theme": {
                "type": "select",
                "label": "主题",
                "description": "选择显示主题",
                "default": "auto",
                "options": [
                    {"label": "自动", "value": "auto"},
                    {"label": "浅色", "value": "light"},
                    {"label": "深色", "value": "dark"}
                ]
            }
        })
```

支持的字段类型：`text`、`number`、`boolean`、`select`。

在代码中读取和修改设置：

```python
def on_frontend_ready(self):
    greeting = self.get_setting("greeting", "默认问候")
    if self.get_setting("enabled", False):
        from ECL.api.events import emit
        emit("launcher:notify", {"message": greeting, "type": "info"})
```

---

## 前端自由注入

插件可以对前端进行非常自由的修改，包括注入 CSS、HTML、JavaScript，注册自定义路由和命令。

### CSS 注入

修改任意页面样式：

```python
def on_frontend_ready(self):
    self.inject_css("""
        .plugins-page {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }
    """)
```

每个插件拥有独立的 `<style>` 标签，重复调用会覆盖之前的内容。插件卸载时样式自动移除。

### HTML 插槽注入

在预定义的 UI 位置注入 HTML 内容：

**可用插槽位置：**

| 插槽名 | 位置 |
|--------|------|
| `sidebar-extra` | 侧栏扩展区域 |
| `page-bottom` | 所有页面底部 |
| `plugin-{plugin_name}` | 插件自定义页面（需配合 `register_route`） |

```python
def on_frontend_ready(self):
    self.inject_html("page-bottom", """
        <div style="padding: 16px; text-align: center; color: var(--text-tertiary)">
            Powered by MyPlugin v1.0
        </div>
    """)
```

### 自定义路由

在侧栏导航中注册独立的页面入口：

```python
def on_enable(self):
    self.register_route("/dashboard", "数据面板", "chart")

def on_frontend_ready(self):
    self.inject_html("plugin-my_plugin", "<h1>数据面板</h1><div id='chart-container'></div>")
    self.inject_script("""
        document.getElementById('chart-container').innerHTML = '<p>实时数据...</p>';
    """)

def on_disable(self):
    self.unregister_route("/dashboard")
```

注册后侧栏会自动出现对应的导航按钮，URL 为 `/plugin/{plugin_name}/dashboard`。

### 自定义命令

注册命令供前端或其他插件调用：

```python
def on_enable(self):
    self.register_command("my_plugin.get_status", self.get_status, "获取插件状态")

def get_status(self):
    return {"running": True, "uptime": 3600}
```

前端调用：

```typescript
import { callPluginCommand } from '@/composables/usePluginBridge'

const result = await callPluginCommand('my_plugin:get_status')
console.log(result.data) // { running: true, uptime: 3600 }
```

### JavaScript 注入

在前端执行任意脚本：

```python
def on_frontend_ready(self):
    self.inject_script("""
        // 每 5 秒刷新一次数据
        setInterval(async () => {
            const res = await window.__TAURI__.invoke('exec_action', {
                action: 'plugin_call_command',
                params: { command: 'my_plugin:get_status' }
            });
            console.log('插件状态:', res.data);
        }, 5000);
    """)
```

> **注意**：JavaScript 注入拥有完全的 DOM 访问权限，请谨慎使用。插件卸载时注入的脚本会自动移除。

---

## 依赖管理

### 第三方 Python 包

1. 将包放入 `dep_cache/{package_name}/` 目录
2. 在 `plugin.json` 的 `dependencies.third_party` 中声明
3. 在代码中使用 `self.require("package_name")` 导入

```python
def on_enable(self):
    requests = self.require("requests")
    response = requests.get("https://api.example.com")
```

**注意**：不同插件依赖同名包时，框架会自动隔离，通过 `_plugin_{plugin_name}_{package_name}` 命名空间避免冲突。

### 插件间依赖

在 `plugin.json` 中声明：

```json
{
  "dependencies": {
    "plugins": {
      "hello_world": ">=1.0.0"
    }
  }
}
```

框架会自动按拓扑顺序加载，确保依赖插件先 enable。

---

## 前端交互

### 向后端发送事件

```python
from ECL.api.events import emit

emit("launcher:notify", {
    "message": "任务完成",
    "type": "info"
})
```

### 前端监听后端事件

前端在 `App.vue` 中通过 `backend.on()` 监听：

```typescript
backend.on('my_plugin:custom_event', (payload) => {
  console.log('收到事件:', payload)
})
```

### 后端 API

插件可以通过 `self.framework` 访问框架，但推荐通过事件系统与前端通信，保持松耦合。

---

## 完整示例

```python
from ECL.plugin.plugin import Plugin

class ExamplePlugin(Plugin):

    def on_load(self):
        # 读取配置文件
        self.config = {"interval": 30}

    def on_enable(self):
        # 注册服务
        self.register_service("example.get_config", self.get_config)

    def on_frontend_ready(self):
        # 通知前端插件已就绪
        from ECL.api.events import emit
        emit("launcher:notify", {
            "message": f"ExamplePlugin v{self.version} 已加载",
            "type": "info"
        })

    def on_disable(self):
        # 清理服务
        self.unregister_service("example.get_config")

    def on_unload(self):
        pass

    @Plugin.on("plugin:pre_disable")
    def on_pre_disable(self, payload):
        # 允许任何插件被禁用
        return None

    @Plugin.provide_event("example:heartbeat", "心跳事件", ["timestamp"])
    def on_heartbeat(self, payload):
        pass

    def get_config(self):
        return self.config
```

---

## 调试技巧

1. **查看日志**：插件日志输出到 `logs/EuoraCraft-Launcher.log`
2. **热重载**：在前端插件页点击"重载"按钮可热重载单个插件
3. **手动加载**：将插件目录放入 `plugins/` 后重启启动器
4. **错误状态**：如果插件状态显示为 `error`，查看日志获取详细错误信息
