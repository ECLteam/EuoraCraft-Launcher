# 插件框架完整开发文档

## 📋 目录
1. [框架概述](#框架概述)
2. [快速开始](#快速开始)
3. [插件开发规范](#插件开发规范)
4. [生命周期管理](#生命周期管理)
5. [依赖管理](#依赖管理)
6. [事件系统](#事件系统)
7. [服务注册与调用](#服务注册与调用)
8. [热重载与动态管理](#热重载与动态管理)
9. [命令行工具](#命令行工具)
10. [高级功能](#高级功能)
11. [最佳实践](#最佳实践)
12. [常见问题](#常见问题)

---

## 框架概述

### 什么是插件框架？

这是一个**轻量级、模块化**的Python插件系统，支持：
- ✅ **版本隔离**：每个插件独立管理依赖版本
- ✅ **热重载**：无需重启即可更新插件
- ✅ **事件驱动**：插件间通过事件松耦合通信
- ✅ **服务注册**：插件功能共享与调用
- ✅ **动态安装**：打包后仍可添加新插件
- ✅ **线程安全**：支持多线程环境
- ✅ **同步/异步**：完整支持异步操作

### 核心设计理念

```
┌─────────────────────────────────────────┐
│           应用主程序                      │
│  ┌─────────────────────────────────┐   │
│  │       PluginFramework           │   │
│  │  ┌─────────┐  ┌──────────┐    │   │
│  │  │ Service │  │  Event   │    │   │
│  │  │ Registry│  │ Registry │    │   │
│  │  └─────────┘  └──────────┘    │   │
│  │  ┌──────────────────────────┐  │   │
│  │  │     Plugin Manager       │  │   │
│  │  │  • 加载/卸载/启用/禁用   │  │   │
│  │  │  • 依赖解析              │  │   │
│  │  │  • 热重载                │  │   │
│  │  └──────────────────────────┘  │   │
│  │  ┌──────────────────────────┐  │   │
│  │  │   Package Downloader     │  │   │
│  │  │  • PyPI下载              │  │   │
│  │  │  • 版本管理              │  │   │
│  │  └──────────────────────────┘  │   │
│  └─────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

---

## 快速开始

### 1. 环境准备

```bash
# 安装依赖
pip install packaging requests filelock

# 克隆框架（假设已提供）
git clone <repository-url>
cd plugin-framework
```

### 2. 最小化插件示例

创建一个最简单的插件：

**目录结构：**
```
plugins/
  hello_plugin/
    plugin.json
    main.py
```

**plugin.json：**
```json
{
  "name": "hello_plugin",
  "version": "1.0.0",
  "title": "Hello插件",
  "description": "最简单的插件",
  "author": "张三",
  "entry_point": "main:HelloPlugin"
}
```

**main.py：**
```python
from plugin_framework import Plugin

class HelloPlugin(Plugin):
    @classmethod
    def get_metadata(cls):
        return {
            'name': 'hello_plugin',
            'version': '1.0.0',
            'title': 'Hello插件',
            'description': '最简单的插件'
        }
    
    def on_load(self):
        print("Hello Plugin 已加载!")
    
    def on_enable(self):
        print("Hello Plugin 已启用!")
```

### 3. 使用框架

```python
from plugin_framework import PluginFramework

# 初始化框架
framework = PluginFramework(
    plugins_dir="./plugins",
    deps_meta_path="./deps_meta.json",
    cache_root="./dep_cache"
)

# 加载插件
framework.load_plugin('hello_plugin')

# 获取插件实例
plugin = framework.get_plugin('hello_plugin')
print(f"插件状态: {plugin.status}")

# 列出所有插件
for info in framework.list_plugins():
    print(f"{info['title']} v{info['version']} - {info['status']}")
```

---

## 插件开发规范

### 目录结构

```
plugins/
  your_plugin_name/
    ├── plugin.json          # 必需：元数据配置
    ├── main.py              # 必需：插件入口
    ├── icon.png             # 可选：插件图标
    ├── README.md            # 可选：文档
    └── other_files/         # 可选：其他资源
```

### plugin.json 完整配置

```json
{
  "name": "plugin_name",           // 必需：唯一标识符
  "version": "1.0.0",              // 必需：语义化版本
  "title": "插件标题",              // 必需：显示名称
  "description": "插件描述",        // 可选
  "author": "作者名",              // 可选
  "icon": "icon.png",              // 可选：图标文件名
  "entry_point": "main:PluginClass", // 必需：入口类
  
  "dependencies": {
    "third_party": {               // 第三方库依赖
      "requests": ">=2.25.0,<3.0.0",
      "flask": "*",                // * 表示最新版本
      "numpy": ">=1.19.0"
    },
    "plugins": {                   // 其他插件依赖
      "base_plugin": ">=1.0.0",
      "database": "==2.0.0"
    }
  },
  
  "events": {                      // 事件声明
    "provided": [                  // 插件提供的事件
      {
        "name": "plugin.data_processed",
        "description": "数据处理完成时触发",
        "params": ["data", "status"]
      }
    ],
    "required": [                  // 插件依赖的事件
      "framework.ready",
      "database.connected"
    ]
  }
}
```

### 版本约束语法

| 约束 | 说明 | 示例 |
|------|------|------|
| `*` | 任何版本（最新） | `"*"` |
| `==1.2.3` | 精确版本 | `"==2.28.2"` |
| `>=1.0.0` | 大于等于 | `">=1.0.0"` |
| `<=2.0.0` | 小于等于 | `"<=2.0.0"` |
| `>1.0.0` | 大于 | `">1.0.0"` |
| `<2.0.0` | 小于 | `"<2.0.0"` |
| `>=1.0.0,<2.0.0` | 区间 | `">=1.0.0,<2.0.0"` |
| `~=1.2.0` | 兼容版本 | `"~=1.2.0"` |

### 插件类定义

```python
from plugin_framework import Plugin
from typing import Dict, Any

class YourPlugin(Plugin):
    """你的插件类"""
    
    @classmethod
    def get_metadata(cls) -> Dict[str, Any]:
        """必需：返回插件元数据"""
        return {
            'name': 'your_plugin',
            'version': '1.0.0',
            'title': '你的插件',
            'description': '插件描述',
            'author': '作者',
            'dependencies': {
                'third_party': {},
                'plugins': {}
            },
            'events': {
                'provided': [],
                'required': []
            }
        }
    
    def __init__(self, framework):
        """初始化插件"""
        super().__init__(framework)
        # 注册服务
        self.register_service('your.service', self.your_method)
        
        # 注册事件处理器
        @self.on('framework.ready')
        def on_ready():
            print("框架已就绪")
    
    # ========== 生命周期方法 ==========
    
    def on_load(self) -> None:
        """插件加载时调用（同步）"""
        pass
    
    async def async_on_load(self) -> None:
        """插件加载时调用（异步）"""
        pass
    
    def on_enable(self) -> None:
        """插件启用时调用（同步）"""
        pass
    
    async def async_on_enable(self) -> None:
        """插件启用时调用（异步）"""
        pass
    
    def on_disable(self) -> None:
        """插件禁用时调用（同步）"""
        pass
    
    async def async_on_disable(self) -> None:
        """插件禁用时调用（异步）"""
        pass
    
    def on_unload(self) -> None:
        """插件卸载时调用（同步）"""
        pass
    
    async def async_on_unload(self) -> None:
        """插件卸载时调用（异步）"""
        pass
    
    # ========== 自定义方法 ==========
    
    def your_method(self, param):
        """你的业务方法"""
        return f"处理: {param}"
```

---

## 生命周期管理

### 状态流转图

```
┌──────────┐
│ UNLOADED │
└─────┬────┘
      │ load_plugin()
      ▼
┌──────────┐
│ LOADING  │
└─────┬────┘
      │ 加载完成
      ▼
┌──────────┐     disable_plugin()     ┌───────────┐
│ LOADED   │ ────────────────────────▶│ DISABLING │
└─────┬────┘                          └─────┬─────┘
      │ enable_plugin()                     │ 禁用完成
      ▼                                      ▼
┌──────────┐                          ┌───────────┐
│ ENABLING │                          │ DISABLED  │
└─────┬────┘                          └───────────┘
      │ 启用完成
      ▼
┌──────────┐     load_plugin()   ┌──────────┐
│ ENABLED  │ ◀──────────────────│  ERROR   │
└──────────┘                     └──────────┘
      │ unload_plugin()
      ▼
┌──────────┐
│ UNLOADING│
└─────┬────┘
      │ 卸载完成
      ▼
┌──────────┐
│ UNLOADED │
└──────────┘
```

### 生命周期方法调用顺序

```python
class MyPlugin(Plugin):
    # 加载阶段
    def on_load(self):
        """1. 同步加载"""
        print("加载中...")
    
    async def async_on_load(self):
        """2. 异步加载（在 on_load 之后）"""
        await asyncio.sleep(1)
        print("异步加载完成")
    
    # 启用阶段
    def on_enable(self):
        """3. 同步启用"""
        print("启用中...")
    
    async def async_on_enable(self):
        """4. 异步启用（在 on_enable 之后）"""
        await asyncio.sleep(1)
        print("异步启用完成")
    
    # 禁用阶段
    def on_disable(self):
        """5. 同步禁用（在 async_on_disable 之前）"""
        print("禁用中...")
    
    async def async_on_disable(self):
        """6. 异步禁用"""
        await asyncio.sleep(1)
        print("异步禁用完成")
    
    # 卸载阶段
    def on_unload(self):
        """7. 同步卸载（在 async_on_unload 之前）"""
        print("卸载中...")
    
    async def async_on_unload(self):
        """8. 异步卸载"""
        await asyncio.sleep(1)
        print("异步卸载完成")
```

### 生命周期管理API

```python
# 加载插件（自动启用）
framework.load_plugin('plugin_name')

# 启用插件
framework.enable_plugin('plugin_name')

# 禁用插件
framework.disable_plugin('plugin_name', force=False)  # force=True 强制禁用

# 卸载插件
framework.unload_plugin('plugin_name')

# 热重载
framework.reload_plugin('plugin_name', cascade=False)  # cascade=True 级联重载

# 查询状态
plugin = framework.get_plugin('plugin_name')
print(plugin.status)  # PluginStatus.ENABLED
```

---

## 依赖管理

### 第三方库依赖

```python
# plugin.json
{
  "dependencies": {
    "third_party": {
      "requests": ">=2.25.0,<3.0.0",
      "pandas": ">=1.3.0",
      "flask": "*"  # 最新版本
    }
  }
}

# main.py
class MyPlugin(Plugin):
    def on_load(self):
        # 使用 require 获取依赖库
        requests = self.require('requests')
        response = requests.get('https://api.example.com')
        
        pandas = self.require('pandas')
        df = pandas.DataFrame({'col': [1, 2, 3]})
        
        flask = self.require('flask')
        # 使用 flask...
```

### 插件依赖

```python
# plugin.json
{
  "dependencies": {
    "plugins": {
      "base_plugin": ">=1.0.0",    # 依赖版本
      "database": "==2.0.0"        # 精确版本
    }
  }
}

# 框架自动处理：
# 1. 先加载 base_plugin 和 database
# 2. 检查版本是否满足约束
# 3. 按依赖顺序加载（被依赖者先加载）
```

### 版本选择策略

```python
# 版本选择优先级：
# 1. 已缓存版本（满足约束的最高版本）
# 2. PyPI 最新满足版本（自动下载）

# 示例
"requests": ">=2.25.0,<3.0.0"
# → 选择 2.28.2（如果有缓存）或从 PyPI 下载最新满足版本

"flask": "*"
# → 选择最新版本

"numpy": "==1.21.0"
# → 精确版本，不存在则下载
```

---

## 事件系统

### 事件类型

| 类型 | 说明 | 示例 |
|------|------|------|
| 同步事件 | 立即执行，阻塞调用方 | `plugin.emit('event')` |
| 异步事件 | 异步执行，不阻塞调用方 | `await plugin.emit_async('event')` |

### 定义事件

#### 方式1：在 plugin.json 中声明
```json
{
  "events": {
    "provided": [
      {
        "name": "data_processor.start",
        "description": "数据处理开始",
        "params": ["data_id", "data_size"]
      },
      {
        "name": "data_processor.complete",
        "description": "数据处理完成",
        "params": ["result", "duration"]
      }
    ]
  }
}
```

#### 方式2：使用装饰器
```python
class DataProcessor(Plugin):
    def __init__(self, framework):
        super().__init__(framework)
        
        # 使用装饰器提供事件
        @self.provide_event('data_processor.custom', '自定义事件', ['param1', 'param2'])
        def _trigger_custom_event(param1, param2):
            self.emit('data_processor.custom', param1, param2)
```

#### 方式3：手动注册
```python
# 在插件代码中
self._event_registry.register_event(
    event_name='my.custom.event',
    plugin_name=self.name,
    description='我的自定义事件',
    params=['param1', 'param2']
)
```

### 订阅事件

```python
class EventSubscriber(Plugin):
    
    # 订阅同步事件
    @Plugin.on('data_processor.start')
    def on_process_start(self, data_id, data_size):
        print(f"处理开始: {data_id}, 大小: {data_size}")
    
    # 订阅异步事件
    @Plugin.on('data_processor.complete', async_handler=True)
    async def on_process_complete(self, result, duration):
        await asyncio.sleep(0.1)
        print(f"处理完成: {result}, 耗时: {duration}s")
    
    # 订阅框架事件
    @Plugin.on('framework.ready')
    def on_framework_ready(self):
        print("框架就绪，插件已准备好")
```

### 触发事件

```python
class EventPublisher(Plugin):
    def process_data(self, data):
        # 触发同步事件
        self.emit('data_processor.start', data['id'], len(data))
        
        # 处理数据...
        result = self._do_process(data)
        
        # 触发异步事件
        await self.emit_async('data_processor.complete', result, time.time())
        
        return result
    
    def trigger_custom(self):
        # 触发自定义事件
        self.emit('my.custom.event', 'value1', 'value2')
```

### 事件查询

```python
# 获取所有可用事件
events = plugin.get_available_events()
for evt in events:
    print(f"{evt.name} (由 {evt.plugin_name} 提供): {evt.description}")

# 获取插件提供的事件
provided = plugin.get_provided_events()
print(f"提供的事件: {provided}")

# 获取插件订阅的事件
subscribed = plugin.get_subscribed_events()
print(f"订阅的事件: {subscribed}")

# 通过框架查询
events = framework._event_registry.list_events()
```

---

## 服务注册与调用

### 什么是服务？

**服务**是插件对外提供的功能接口，其他插件可以通过服务名调用这些功能。

### 注册服务

```python
class CalculatorPlugin(Plugin):
    def __init__(self, framework):
        super().__init__(framework)
        
        # 注册服务
        self.register_service('calculator.add', self.add)
        self.register_service('calculator.subtract', self.subtract)
        self.register_service('calculator.multiply', self.multiply)
        self.register_service('calculator.divide', self.divide)
    
    def add(self, a, b):
        return a + b
    
    def subtract(self, a, b):
        return a - b
    
    def multiply(self, a, b):
        return a * b
    
    def divide(self, a, b):
        if b == 0:
            raise ValueError("除数不能为零")
        return a / b
```

### 调用服务

```python
class ReportPlugin(Plugin):
    def generate_report(self, data):
        # 方式1：通过插件实例
        calc = self.get_service('calculator.add')
        if calc:
            total = calc(data['a'], data['b'])
        
        # 方式2：通过框架
        multiply = self.framework.get_service('calculator.multiply')
        if multiply:
            result = multiply(data['x'], data['y'])
        
        # 方式3：直接获取（推荐，更简洁）
        add = self.get_service('calculator.add')
        subtract = self.get_service('calculator.subtract')
        
        return {
            'total': add(data['a'], data['b']),
            'difference': subtract(data['a'], data['b']),
            'product': multiply(data['x'], data['y'])
        }
```

### 服务命名规范

```
<plugin_name>.<service_category>.<action>
```

**示例：**
- `calculator.add` - 计算器插件的加法
- `data.process` - 数据处理插件的处理功能
- `logger.write` - 日志插件的写入功能
- `database.query` - 数据库插件的查询功能
- `monitor.status` - 监控插件的状态查询

### 服务代理（自动热重载）

```python
class ServiceProxy:
    """服务代理 - 确保始终获取最新插件实例"""
    
    def __init__(self, framework, plugin_name):
        self._framework = framework
        self._plugin_name = plugin_name
    
    def __getattr__(self, name):
        # 每次调用都获取最新实例
        instance = self._framework.get_plugin_instance(self._plugin_name)
        if instance is None:
            raise RuntimeError(f"插件 {self._plugin_name} 未加载")
        return getattr(instance, name)

# 使用代理
proxy = ServiceProxy(framework, 'calculator_plugin')
result = proxy.add(3, 5)  # 始终调用最新版本的插件
```

---

## 热重载与动态管理

### 热重载

```python
# 单插件重载
framework.reload_plugin('plugin_name')

# 级联重载（同时重载依赖此插件的所有插件）
framework.reload_plugin('plugin_name', cascade=True)

# 重载顺序：被依赖者先重载，依赖者后重载
# 示例：plugin_a 依赖 plugin_base
# 重载顺序：plugin_base → plugin_a
```

### 动态管理

```python
# 启用/禁用
framework.enable_plugin('plugin_name')   # 启用
framework.disable_plugin('plugin_name')  # 禁用

# 强制禁用（忽略依赖检查）
framework.disable_plugin('plugin_name', force=True)

# 卸载
framework.unload_plugin('plugin_name')

# 加载
framework.load_plugin('plugin_name')
```

### 热重载实现原理

```python
class PluginFramework:
    def reload_plugin(self, plugin_name, cascade=False):
        """
        热重载流程：
        1. 获取依赖此插件的所有插件
        2. 如果 cascade=True，按依赖顺序重载所有插件
        3. 否则只重载指定插件
        4. 重载时：
           a. 禁用旧插件
           b. 卸载服务
           c. 重新加载代码
           d. 创建新实例
           e. 注册服务
           f. 启用新插件
        """
        with self._lock:
            dependents = self._get_dependents(plugin_name)
            
            if cascade:
                # 级联重载
                order = self._resolve_plugin_order([plugin_name] + dependents)
                for name in order:
                    self._reload_single(name)
            else:
                if dependents:
                    raise RuntimeError(
                        f"插件 {plugin_name} 被以下插件依赖: {dependents}，"
                        f"请使用 cascade=True 进行级联重载"
                    )
                self._reload_single(plugin_name)
```

---

## 命令行工具

### plugin-pip 命令

```bash
# 安装插件依赖
python plugin_pip.py install ./plugins/my_plugin

# 安装指定包（最新版本）
python plugin_pip.py install requests

# 安装指定版本
python plugin_pip.py install requests==2.28.2

# 安装版本约束（自动选最新满足版本）
python plugin_pip.py install requests ">=2.25.0,<3.0.0"

# 列出已安装的包
python plugin_pip.py list
```

### 环境变量配置

```bash
# 自定义缓存目录
export PLUGIN_CACHE_ROOT=/path/to/cache

# 自定义元数据文件
export PLUGIN_DEPS_META=/path/to/deps_meta.json

# 使用
python plugin_pip.py install requests
```

### 程序化调用

```python
from plugin_framework.package_downloader import PackageDownloader

# 下载包
downloader = PackageDownloader(cache_root='./dep_cache')
downloader.download_package('requests', '2.28.2', './dep_cache/requests/2.28.2')

# 安装插件依赖
from plugin_framework.plugin_pip import install_plugin_deps
install_plugin_deps('./plugins/my_plugin')
```

---

## 高级功能

### 自定义导入器

```python
class PluginImporter:
    """自定义导入器，实现版本隔离"""
    
    def __init__(self, plugin_name, libs):
        self.plugin_name = plugin_name
        self.libs = libs
    
    def find_spec(self, fullname, path, target=None):
        pkg_name = fullname.split('.')[0]
        if pkg_name in self.libs:
            # 从插件专属路径加载
            return self._create_spec(fullname, self.libs[pkg_name])
        return None
    
    def _create_spec(self, fullname, module):
        # 创建自定义spec
        spec = importlib.util.spec_from_loader(fullname, self)
        return spec
```

### 插件沙箱

```python
class PluginSandbox:
    """插件沙箱 - 限制资源访问"""
    
    def __init__(self, plugin_name):
        self.plugin_name = plugin_name
        self.allowed_modules = ['os', 'json', 're']
        self.max_memory = 256 * 1024 * 1024  # 256MB
        self.timeout = 30  # 30秒
    
    def create_sandbox(self):
        """创建沙箱环境"""
        globals = {
            '__builtins__': self._safe_builtins(),
            '__import__': self._safe_import,
        }
        return globals
    
    def _safe_import(self, name, *args, **kwargs):
        if name not in self.allowed_modules:
            raise ImportError(f"模块 {name} 被禁止")
        return __import__(name, *args, **kwargs)
```

### 插件性能监控

```python
class PluginMonitor:
    """插件性能监控"""
    
    def __init__(self):
        self.metrics = {}
    
    def track(self, plugin_name, operation):
        """跟踪插件操作"""
        start_time = time.time()
        try:
            result = operation()
        finally:
            duration = time.time() - start_time
            self._record_metric(plugin_name, duration)
        return result
    
    def _record_metric(self, plugin_name, duration):
        if plugin_name not in self.metrics:
            self.metrics[plugin_name] = {
                'calls': 0,
                'total_time': 0,
                'avg_time': 0,
                'max_time': 0
            }
        metric = self.metrics[plugin_name]
        metric['calls'] += 1
        metric['total_time'] += duration
        metric['avg_time'] = metric['total_time'] / metric['calls']
        metric['max_time'] = max(metric['max_time'], duration)
```

---

## 最佳实践

### 1. 插件设计原则

```python
# ✅ 好的设计：使用服务
class GoodPlugin(Plugin):
    def __init__(self, framework):
        super().__init__(framework)
        self.register_service('good.process', self.process)
    
    def process(self, data):
        return self._do_work(data)

# ❌ 差的设计：直接暴露方法
class BadPlugin(Plugin):
    def process(self, data):
        return self._do_work(data)
```

### 2. 事件使用建议

```python
# ✅ 使用事件进行状态通知
class DataPlugin(Plugin):
    def process(self, data):
        self.emit('data.start', len(data))
        result = self._process(data)
        self.emit('data.complete', result)
        return result

# ❌ 不要用事件传递大量数据
class BadPlugin(Plugin):
    def process(self, data):
        # 传递大量数据到事件
        self.emit('data.process', data)  # 可能阻塞
```

### 3. 错误处理

```python
class RobustPlugin(Plugin):
    def on_load(self):
        try:
            # 初始化资源
            self._init_resources()
        except Exception as e:
            # 记录错误并优雅降级
            self.error = str(e)
            self.status = PluginStatus.ERROR
            print(f"加载失败: {e}")
    
    def process(self, data):
        if self.status == PluginStatus.ERROR:
            # 返回错误状态
            return {'error': self.error}
        try:
            return {'success': True, 'result': self._process(data)}
        except Exception as e:
            return {'success': False, 'error': str(e)}
```

### 4. 异步操作

```python
class AsyncPlugin(Plugin):
    async def async_on_load(self):
        # 异步加载资源
        await self._load_resources()
    
    def on_enable(self):
        # 启动异步任务
        asyncio.create_task(self._background_task())
    
    async def _background_task(self):
        while self.status == PluginStatus.ENABLED:
            await asyncio.sleep(60)
            await self._periodic_work()
```

### 5. 资源管理

```python
class ResourcePlugin(Plugin):
    def __init__(self, framework):
        super().__init__(framework)
        self._connections = []
        self._temp_files = []
    
    def on_load(self):
        # 分配资源
        self._connections.append(self._create_connection())
        self._temp_files.append(self._create_temp_file())
    
    def on_disable(self):
        # 释放资源
        for conn in self._connections:
            conn.close()
        for file in self._temp_files:
            file.close()
    
    def on_unload(self):
        # 完全清理
        self.on_disable()
        self._connections.clear()
        self._temp_files.clear()
```

---

## 常见问题

### Q1: 插件加载失败怎么办？

```python
try:
    framework.load_plugin('plugin_name')
except Exception as e:
    print(f"加载失败: {e}")
    # 检查错误状态
    plugin = framework.get_plugin('plugin_name')
    if plugin:
        print(f"错误状态: {plugin.error}")
```

### Q2: 如何调试插件？

```python
# 启用调试模式
import logging
logging.basicConfig(level=logging.DEBUG)

# 查看插件状态
plugin = framework.get_plugin('plugin_name')
print(f"状态: {plugin.status}")
print(f"依赖: {plugin.meta.dependencies}")
print(f"服务: {plugin.services}")
print(f"事件: {plugin.get_provided_events()}")
```

### Q3: 如何更新插件？

```python
# 方法1：热重载
framework.reload_plugin('plugin_name', cascade=True)

# 方法2：手动更新
framework.disable_plugin('plugin_name', force=True)
# 更新插件文件
framework.unload_plugin('plugin_name')
framework.load_plugin('plugin_name')
```

### Q4: 如何处理循环依赖？

```python
# 框架会自动检测循环依赖并报错
# plugin_a 依赖 plugin_b
# plugin_b 依赖 plugin_a
# → RuntimeError: Circular dependency detected

# 解决方案：解耦
# 1. 使用事件代替依赖
# 2. 提取共同依赖为独立插件
# 3. 重新设计插件架构
```

### Q5: 如何打包应用程序？

```python
# 1. 设置可写缓存目录
# 在用户目录创建缓存
import os
user_dir = os.path.expanduser('~/.myapp')
os.makedirs(user_dir, exist_ok=True)

framework = PluginFramework(
    plugins_dir=os.path.join(user_dir, 'plugins'),
    deps_meta_path=os.path.join(user_dir, 'deps_meta.json'),
    cache_root=os.path.join(user_dir, 'dep_cache')
)

# 2. 打包时排除缓存目录
# PyInstaller: --add-data "plugins;plugins" --exclude dep_cache
```

### Q6: 如何提高性能？

```python
# 1. 使用异步操作
await self.emit_async('event', data)  # 不阻塞

# 2. 懒加载
if not self._initialized:
    self._initialize()
    self._initialized = True

# 3. 缓存服务
self._cached_services = {}
def get_cached_service(self, name):
    if name not in self._cached_services:
        self._cached_services[name] = self.get_service(name)
    return self._cached_services[name]
```

### Q7: 如何处理插件间通信？

```python
# 方案1：服务调用（同步，有返回值）
result = self.get_service('plugin.service')(param)

# 方案2：事件（异步，无返回值）
self.emit('plugin.event', data)

# 方案3：共享对象（谨慎使用）
# 通过框架注册共享数据
framework.register_shared_data('key', value)
```

---

## 总结

### 核心优势

| 特性 | 说明 |
|------|------|
| **模块化** | 每个插件独立开发、测试、部署 |
| **版本隔离** | 不同插件可同时使用不同版本依赖 |
| **松耦合** | 通过服务/事件通信，插件互不依赖 |
| **热重载** | 无需重启即可更新插件 |
| **扩展性** | 打包后仍可动态添加新插件 |
| **标准化** | 统一的开发规范和管理接口 |

### 快速参考

```python
# 开发插件必做
1. 创建 plugins/plugin_name/ 目录
2. 编写 plugin.json 元数据
3. 继承 Plugin 类实现业务逻辑
4. 使用装饰器注册事件和服务
5. 实现生命周期方法

# 使用框架必做
1. 初始化 PluginFramework
2. 加载所需插件
3. 获取服务或触发事件
4. 管理插件生命周期

# 部署插件必做
1. 复制插件目录到 plugins/
2. 运行 plugin-pip install 安装依赖
3. 重启或热重载插件
```

---

**文档版本**: 1.0.0  
**最后更新**: 2024年  
**维护者**: 插件框架开发团队