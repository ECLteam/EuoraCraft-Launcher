# EuoraCraft Launcher 插件开发文档

## 概述

EuoraCraft Launcher 提供完整的插件系统，允许第三方开发者扩展启动器功能。插件可以注册后端命令、添加前端页面、注入 UI 组件、监听系统事件、调用启动器 API。

插件分为**后端插件**（Python）和**前端插件**（TypeScript/JavaScript）两部分。后端插件负责业务逻辑，前端插件负责 UI 扩展。后端插件通过 `plugin-sdk` 与前端通信。

---

## 插件架构

```
插件目录/
├── plugin.json          # 插件元数据
├── main.py              # 后端入口（Plugin 子类）
└── frontend/            # 前端资源（可选）
    ├── index.js         # 前端入口脚本
    └── style.css        # 前端样式
```

插件通过 `PluginFramework` 加载，使用隔离命名空间避免插件间模块冲突。前端资源通过 `inject_css()` 和 `inject_html()` 注入到启动器界面。

---

## 快速开始

### 创建插件目录

```
plugins/my-first-plugin/
├── plugin.json
└── main.py
```

### plugin.json

```json
{
  "name": "my-first-plugin",
  "title": "我的第一个插件",
  "version": "1.0.0",
  "description": "一个示例插件",
  "author": "Your Name",
  "icon": "hugeicons:plugin",
  "entry_point": "main:MyPlugin",
  "dependencies": {
    "plugins": {},
    "python": {}
  }
}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `name` | 是 | 插件唯一标识符，只能包含小写字母、数字、连字符和下划线 |
| `title` | 是 | 插件显示名称 |
| `version` | 是 | 语义化版本号 |
| `description` | 否 | 插件描述 |
| `author` | 否 | 作者 |
| `icon` | 否 | Iconify 图标名称 |
| `entry_point` | 是 | 入口声明，格式 `module:ClassName` |
| `dependencies.plugins` | 否 | 依赖的其他插件及版本约束 |
| `dependencies.python` | 否 | 依赖的 Python 包及版本约束 |

### main.py

```python
from ECL.plugin.plugin import Plugin

class MyPlugin(Plugin):
    def on_enable(self):
        self.logger.info("插件已启用")

    def on_disable(self):
        self.logger.info("插件已禁用")
```

### 安装插件

将插件目录放入 `plugins/` 目录，启动器会自动加载。

---

## 生命周期

插件遵循严格的生命周期状态机：

```
UNLOADED -> LOADING -> LOADED -> ENABLING -> ENABLED -> DISABLING -> DISABLED -> UNLOADING -> UNLOADED
```

### 生命周期回调

| 回调 | 调用时机 | 用途 |
|------|----------|------|
| `on_load()` | 插件加载时 | 加载资源文件、初始化数据结构 |
| `async_on_load()` | 插件加载时（异步） | 异步加载资源 |
| `on_enable()` | 插件启用时 | 注册服务、注册命令、注册路由 |
| `async_on_enable()` | 插件启用时（异步） | 异步初始化 |
| `on_frontend_ready()` | 前端就绪后 | 注入 CSS/HTML、发送前端事件 |
| `on_disable()` | 插件禁用时 | 清理运行时状态 |
| `async_on_disable()` | 插件禁用时（异步） | 异步清理 |
| `on_unload()` | 插件卸载时 | 释放所有资源 |
| `async_on_unload()` | 插件卸载时（异步） | 异步释放资源 |

每个回调都有同步和异步两个版本，框架会根据需要调用对应版本。`on_frontend_ready` 仅在插件已启用且前端已初始化后调用。

### 完整示例

```python
from ECL.plugin.plugin import Plugin

class MyPlugin(Plugin):
    def on_load(self):
        self._data = {}

    def on_enable(self):
        self.register_service("my_service", self.handle_service)
        self.register_command("do_something", self.do_something, "执行操作")
        self.register_settings({
            "api_key": {"type": "string", "default": "", "label": "API Key"},
            "max_items": {"type": "number", "default": 100, "label": "最大数量"},
            "auto_refresh": {"type": "boolean", "default": True, "label": "自动刷新"}
        })
        self.register_route("/my-plugin", "我的插件", "hugeicons:plugin")

    def on_frontend_ready(self):
        self.inject_css("""
            .my-plugin-page {
                padding: 20px;
            }
        """)
        self.inject_html("page-bottom", """
            <div class="my-plugin-footer">
                <span>Powered by MyPlugin v1.0.0</span>
            </div>
        """)

    def on_disable(self):
        self._data.clear()

    def on_unload(self):
        self._data = None

    def handle_service(self, *args, **kwargs):
        return {"status": "ok"}

    def do_something(self, param1: str, param2: int = 0):
        self.logger.info(f"执行操作: {param1}, {param2}")
        return {"success": True, "data": f"处理了 {param1}"}
```

---

## 后端 API

### 注册服务

插件可以向服务注册表注册服务，供其他插件调用：

```python
def on_enable(self):
    self.register_service("my_service", self.handle_service)

def handle_service(self, *args, **kwargs):
    # 处理服务请求
    return {"result": "success"}
```

其他插件通过 `ServiceRegistry.get("my_service")` 获取服务处理器。

### 注册命令

插件可以注册后端命令，供前端或其他插件调用：

```python
def on_enable(self):
    self.register_command("my_command", self.handle_command, "命令描述")

def handle_command(self, param1: str, param2: int = 0):
    return {"success": True, "data": f"处理了 {param1}"}
```

前端通过 `callCommand('my_plugin:my_command', { param1: 'hello', param2: 42 })` 调用。

### 注册设置

插件可以注册设置面板，用户可以在启动器设置中配置：

```python
def on_enable(self):
    self.register_settings({
        "api_key": {
            "type": "string",
            "default": "",
            "label": "API Key",
            "description": "用于 API 认证的密钥"
        },
        "max_items": {
            "type": "number",
            "default": 100,
            "label": "最大数量",
            "description": "单次请求的最大条目数"
        },
        "auto_refresh": {
            "type": "boolean",
            "default": True,
            "label": "自动刷新"
        },
        "display_mode": {
            "type": "select",
            "default": "grid",
            "label": "显示模式",
            "options": [
                {"value": "grid", "label": "网格"},
                {"value": "list", "label": "列表"}
            ]
        }
    })
```

在插件中读取设置：

```python
def on_enable(self):
    settings = self.get_settings()
    api_key = settings.get("api_key", "")
    max_items = settings.get("max_items", 100)
```

当用户修改设置时，插件会收到 `settings_changed` 事件。

### 注册前端路由

插件可以注册前端页面路由：

```python
def on_enable(self):
    self.register_route("/my-plugin", "我的插件", "hugeicons:plugin")
```

注册后，侧边栏会显示插件入口，点击后路由到 `/plugin/my_plugin/my-plugin`。前端在 `pluginRoutes` 中获取路由信息并动态渲染。

### 注入前端资源

插件可以注入 CSS 样式和 HTML 内容到启动器界面：

```python
def on_frontend_ready(self):
    # 注入 CSS
    self.inject_css("""
        .my-plugin-container {
            padding: 16px;
            background: var(--bg2);
            border-radius: 8px;
        }
    """)

    # 注入 HTML 到指定插槽
    self.inject_html("page-bottom", """
        <div class="my-plugin-footer">Powered by MyPlugin</div>
    """)

    # 注入脚本
    self.inject_script("""
        console.log('MyPlugin 前端脚本已加载');
        document.querySelector('.my-plugin-footer').addEventListener('click', () => {
            alert('Hello from MyPlugin!');
        });
    """)
```

可用的 HTML 插槽：`page-bottom`、`page-top`、`sidebar-top`、`sidebar-bottom`。

### 事件系统

#### 声明事件

```python
class MyPlugin(Plugin):
    @Plugin.provide_event("my_event", "事件描述", ["param1", "param2"])
    def handle_my_event(self, param1, param2):
        pass
```

#### 监听事件

```python
class MyPlugin(Plugin):
    @Plugin.on("config:changed")
    def on_config_changed(self, section, old_value, new_value):
        self.logger.info(f"配置变更: {section}")
```

系统事件列表：

| 事件名 | 参数 | 说明 |
|--------|------|------|
| `config:changed` | `section, old_value, new_value` | 配置变更 |
| `launcher:notify` | `message, type` | 启动器通知 |
| `plugin:enabled` | `plugin_name` | 插件被启用 |
| `plugin:disabled` | `plugin_name` | 插件被禁用 |
| `plugin:unloaded` | `plugin_name` | 插件被卸载 |
| `frontend:ready` | 无 | 前端初始化完成 |

#### 触发事件

```python
def on_enable(self):
    self.emit_event("my_event", param1="hello", param2=42)
```

---

## 前端 SDK

插件前端资源通过 `plugin-sdk` 与启动器交互。SDK 通过 `window.__plugin_sdk__` 全局注入。

### API 调用

```javascript
const { callCommand, getSettings, updateSetting, getConfig, setConfig } = window.__plugin_sdk__

// 调用后端命令
const result = await callCommand('my_plugin:my_command', { param1: 'hello' })
if (result.success) {
    console.log(result.data)
}

// 获取插件设置
const settings = await getSettings('my_plugin')
console.log(settings.data.api_key)

// 更新设置
await updateSetting('my_plugin', 'api_key', 'new_value')

// 读取启动器配置
const gameConfig = await getConfig('game')
const javaAuto = gameConfig.data.java_auto

// 修改启动器配置
await setConfig('ui', { locale: 'en-US' })
```

### 事件监听

```javascript
const { listen, Events } = window.__plugin_sdk__

// 监听启动器事件
const unlisten = listen(Events.SETTINGS_CHANGED, (payload) => {
    console.log(`设置 ${payload.key} 从 ${payload.old_value} 变为 ${payload.new_value}`)
})

// 取消监听
unlisten()
```

### UI 工具

```javascript
const { $, showToast, showConfirm, showLoading, getSlot, clearSlot } = window.__plugin_sdk__

// 创建元素
const container = $.div({
    class: 'my-container',
    children: [
        $.h2({ text: '我的插件' }),
        $.p({ text: '欢迎使用' }),
        $.button({
            class: 'btn-primary',
            text: '点击',
            events: { click: () => showToast('点击成功') }
        })
    ]
})

// 添加到插槽
const slot = getSlot('page-bottom')
slot.appendChild(container)

// Toast 通知
showToast('操作成功', 'success', 3000)

// 确认对话框
const confirmed = await showConfirm('确认删除', '此操作不可撤销')
if (confirmed) {
    // 执行删除
}

// 加载指示器
const removeLoading = showLoading(container, '加载中...')
// 加载完成后
removeLoading()
```

### 类型定义

```javascript
const { ApiResponse, PluginInfo, GameVersion, JavaInfo, AccountInfo } = window.__plugin_sdk__

// ApiResponse<T> = { success: boolean, data?: T, message?: string, timestamp?: number }
// PluginInfo = { name, version, title, description, author, icon, status, error, is_system }
// GameVersion = { id, type, release_time, url }
// JavaInfo = { path, version, arch, vendor }
// AccountInfo = { id, username, type: 'offline' | 'microsoft', uuid?, avatar_url? }
```

---

## 完整示例

### 示例：天气显示插件

#### plugin.json

```json
{
  "name": "weather_widget",
  "title": "天气组件",
  "version": "1.0.0",
  "description": "在启动器底部显示当前天气",
  "author": "Your Name",
  "icon": "hugeicons:cloud",
  "entry_point": "main:WeatherPlugin",
  "dependencies": {
    "plugins": {},
    "python": {
      "requests": ">=2.28.0"
    }
  }
}
```

#### main.py

```python
import requests
from ECL.plugin.plugin import Plugin

class WeatherPlugin(Plugin):
    def on_enable(self):
        self.register_command("get_weather", self.get_weather, "获取天气信息")
        self.register_settings({
            "city": {"type": "string", "default": "Beijing", "label": "城市"},
            "unit": {
                "type": "select",
                "default": "celsius",
                "label": "温度单位",
                "options": [
                    {"value": "celsius", "label": "摄氏度"},
                    {"value": "fahrenheit", "label": "华氏度"}
                ]
            }
        })

    def on_frontend_ready(self):
        settings = self.get_settings()
        city = settings.get("city", "Beijing")
        weather = self._fetch_weather(city)
        self.inject_css("""
            .weather-widget {
                padding: 8px 16px;
                font-size: 13px;
                color: var(--muted);
                display: flex;
                align-items: center;
                gap: 8px;
            }
        """)
        self.inject_html("sidebar-bottom", f"""
            <div class="weather-widget" id="weather-widget">
                {weather['icon']} {weather['city']}: {weather['temperature']}°{weather['unit']}
            </div>
        """)

    def get_weather(self, city: str = None):
        settings = self.get_settings()
        city = city or settings.get("city", "Beijing")
        result = self._fetch_weather(city)
        return {"success": True, "data": result}

    def _fetch_weather(self, city: str):
        try:
            # 使用免费的天气 API
            resp = requests.get(f"https://wttr.in/{city}?format=j1", timeout=5)
            data = resp.json()
            current = data["current_condition"][0]
            return {
                "city": city,
                "temperature": current["temp_C"],
                "humidity": current["humidity"],
                "description": current["weatherDesc"][0]["value"],
                "icon": current["weatherCode"],
                "unit": "C"
            }
        except Exception as e:
            self.logger.error(f"获取天气失败: {e}")
            return {"city": city, "temperature": "--", "unit": "C", "error": str(e)}

    @Plugin.on("config:changed")
    def on_config_changed(self, section, old_value, new_value):
        if section == "plugin_settings":
            plugin_name = self.meta.get("name")
            if plugin_name in new_value or plugin_name in old_value:
                self.logger.info("天气插件设置已更新，刷新天气数据")
                # 通过 inject_html 更新前端显示
                settings = self.get_settings()
                weather = self._fetch_weather(settings.get("city", "Beijing"))
                self.inject_html("sidebar-bottom", f"""
                    <div class="weather-widget" id="weather-widget">
                        {weather['icon']} {weather['city']}: {weather['temperature']}°{weather['unit']}
                    </div>
                """)
```

#### frontend/index.js（前端扩展）

```javascript
(function() {
    const { listen, Events, callCommand, showToast } = window.__plugin_sdk__

    // 监听设置变更，自动刷新天气
    listen(Events.SETTINGS_CHANGED, async (payload) => {
        if (payload.key === 'city') {
            const result = await callCommand('weather_widget:get_weather', {
                city: payload.new_value
            })
            if (result.success) {
                const widget = document.getElementById('weather-widget')
                if (widget && result.data) {
                    widget.innerHTML = `${result.data.icon} ${result.data.city}: ${result.data.temperature}°${result.data.unit}`
                }
            }
        }
    })

    // 点击天气组件刷新
    const widget = document.getElementById('weather-widget')
    if (widget) {
        widget.style.cursor = 'pointer'
        widget.addEventListener('click', async () => {
            const result = await callCommand('weather_widget:get_weather')
            if (result.success) {
                showToast('天气已刷新', 'success')
            }
        })
    }
})()
```

---

## 调试与测试

### 查看插件日志

插件通过 `self.logger` 输出日志，日志级别跟随启动器配置。开发模式下日志会输出到控制台。

### 重载插件

修改插件代码后，可以在启动器插件管理页面点击"重载"按钮，或通过 API 调用：

```python
framework.reload_plugin("my_plugin")
```

### 开发者工具

启动器在开发模式下提供 `/dev` 路由的开发者工具页面，可以查看插件状态、事件注册、服务注册等信息。

---

## 发布插件

### 打包

插件目录直接打包为 zip 即可分发：

```
my-plugin.zip
├── plugin.json
├── main.py
└── frontend/
    ├── index.js
    └── style.css
```

### 版本管理

遵循语义化版本（SemVer）：`主版本.次版本.修订号`。在 `plugin.json` 中声明版本号，在依赖声明中约束其他插件版本。

### 依赖声明

```json
{
  "dependencies": {
    "plugins": {
      "required_plugin": ">=1.0.0"
    },
    "python": {
      "requests": ">=2.28.0",
      "pillow": ">=10.0.0"
    }
  }
}
```

系统会在加载插件时自动安装 Python 依赖到隔离缓存目录。

---

## 注意事项

1. **命名空间隔离**：插件使用独立的模块命名空间，避免与其他插件冲突
2. **线程安全**：后端插件方法可能在不同线程中调用，注意线程安全
3. **资源清理**：在 `on_disable` 和 `on_unload` 中彻底清理资源，避免内存泄漏
4. **XSS 防护**：注入的 HTML 会经过安全过滤，`<script>` 标签、`javascript:` 协议、内联事件处理器会被移除。如需执行脚本，使用 `inject_script()` 方法
5. **事件处理器**：使用 `@Plugin.on` 装饰器注册的事件处理器会在插件卸载时自动清理
6. **前端资源**：`inject_css` 和 `inject_html` 在 `on_frontend_ready` 中调用，每次调用会覆盖同名插槽的旧内容
7. **错误处理**：命令处理函数中的异常会被框架捕获并返回给调用方，不会导致启动器崩溃