# ECL.Game.Core API 使用文档

> EuoraCraft Launcher 游戏核心模块，提供 Minecraft 启动、下载、认证、文件校验等全部底层能力。

---

## 目录

1. [模块概览](#模块概览)
2. [快速开始](#快速开始)
3. [启动核心 (ECLauncherCore)](#启动核心-eclaunchercore)
4. [下载器 (Downloader)](#下载器-downloader)
5. [文件校验 (FilesChecker)](#文件校验-fileschecker)
6. [游戏获取 (GetGames)](#游戏获取-getgames)
7. [实例管理 (InstancesManager)](#实例管理-instancesmanager)
8. [工具库 (Libs)](#工具库-libs)
9. [微软认证 (MicrosoftAuth)](#微软认证-microsoftauth)
10. [网络模块 (Net)](#网络模块-net)
11. [完整示例](#完整示例)

---

## 模块概览

```
ECL/Game/Core/
├── __init__.py              # 空文件
├── ECLauncherCore.py         # 启动核心：构建 Minecraft 启动命令
├── Downloader.py             # 下载器：支持并发/限速/断点/暂停恢复
├── FilesChecker.py           # 文件校验：SHA1 完整性检查与补全
├── GetGames.py               # 游戏获取：版本清单、分类、下载
├── InstancesManager.py       # 实例管理：子进程生命周期管理
├── Libs.py                   # 工具库：SHA1、UUID、解压等辅助函数
├── MicrosoftAuth.py          # 微软认证：OAuth 设备码流程、Minecraft API
└── Net/
    ├── __init__.py           # 空文件
    ├── MetaClient.py         # 元数据客户端：Mojang/Fabric API
    └── NetLibs.py            # 网络库：API URL 配置、仓库解析器
```

---

## 快速开始

### 导入

```python
from ECL.Game.Core.ECLauncherCore import build_minecraft_cmd, LaunchConfig
from ECL.Game.Core.Downloader import Downloader
from ECL.Game.Core.FilesChecker import FilesChecker
from ECL.Game.Core.GetGames import GetGames, VersionClassifier
from ECL.Game.Core.InstancesManager import InstancesManager
from ECL.Game.Core.Libs import name_to_uuid, get_file_sha1, unzip
from ECL.Game.Core.MicrosoftAuth import MicrosoftAuthManager
from ECL.Game.Core.Net.NetLibs import ApiUrlConfig, RepositoryResolver
from ECL.Game.Core.Net.MetaClient import MojangClient, FabricClient
```

### 依赖关系

各类之间存在依赖关系，正确初始化顺序如下：

```python
# 1. 创建 API 配置
api_config = ApiUrlConfig()

# 2. 创建 API 客户端
mojang_client = MojangClient(api_config)
fabric_client = FabricClient(api_config)

# 3. 创建仓库解析器
resolver = RepositoryResolver(api_config)

# 4. 创建文件检查器
files_checker = FilesChecker(mojang_client, resolver)

# 5. 创建游戏获取器
game_getter = GetGames(mojang_client, fabric_client, files_checker, ".minecraft")

# 6. 创建账户管理器
auth_manager = MicrosoftAuthManager()
```

---

## 启动核心 (ECLauncherCore)

该模块负责构建完整的 Minecraft 进程启动命令，包含 JVM 参数构建、ClassPath 构建、占位符替换等。

### LaunchConfig

启动配置数据类，包含启动游戏所需的所有参数。

```python
from ECL.Game.Core.ECLauncherCore import LaunchConfig

config = LaunchConfig(
    java_path="C:/java/bin/javaw.exe",   # Java 可执行文件路径
    game_path=".minecraft",               # .minecraft 目录路径
    version_name="1.21.4",                # 游戏版本名称
    use_ram=4096,                         # 分配内存 (MB)
    player_name="Steve",                  # 玩家昵称
    auth_uuid="...",                      # 登录 UUID (UUID3)
    user_type="msa",                      # "legacy" 离线 / "msa" 微软登录
    access_token="...",                   # 微软登录 Token (离线可为 "None")
    use_gc="G1GC",                        # GC 类型: "G1GC" 或 "ZGC"
    launcher_name="ECL",                  # 启动器名称
    launcher_version="0.11.45",           # 启动器版本
    custom_jvm_params=["-Dmy.arg=val"],   # 额外的 JVM 参数
    version_isolation=False,              # 是否版本隔离
    window_width=854,                     # 窗口宽度
    window_height=480,                    # 窗口高度
)
```

**字段说明：**

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `java_path` | `str\|Path` | - | Java 可执行文件路径 |
| `game_path` | `str\|Path` | - | `.minecraft` 路径 |
| `version_name` | `str` | - | 游戏版本名称 |
| `use_ram` | `int` | - | 分配给 Minecraft 的内存 (MB) |
| `player_name` | `str` | - | 玩家昵称 |
| `auth_uuid` | `str` | - | 登录的 UUID (UUID3) |
| `user_type` | `str` | `"legacy"` | 用户类型: `"legacy"` 离线, `"msa"` 微软 |
| `access_token` | `str` | `"None"` | 微软登录 Token |
| `use_gc` | `str` | `"G1GC"` | JVM GC 类型 |
| `launcher_name` | `str` | `"ECL"` | 启动器名称 |
| `launcher_version` | `str` | `"0.11.45"` | 启动器版本号 |
| `custom_jvm_params` | `list[str]\|None` | `None` | 额外 JVM 参数 |
| `version_isolation` | `bool` | `False` | 是否隔离版本 |
| `window_width` | `int\|str` | `"${resolution_width}"` | 窗口宽度 |
| `window_height` | `int\|str` | `"${resolution_height}"` | 窗口高度 |

**方法：**

| 方法 | 说明 |
|------|------|
| `get(key_name)` | 通过字段名获取值 |
| `to_dict()` | 转为字典 |
| `from_dict(d)` | 从字典创建实例 (类方法) |
| `update_from_dict(d)` | 从字典更新字段值 |

### JvmArgumentBuilder

构建 JVM 启动参数。

```python
from ECL.Game.Core.ECLauncherCore import JvmArgumentBuilder

builder = JvmArgumentBuilder(
    java_path="C:/java/bin/javaw.exe",
    version_name="1.21.4",
    use_ram=4096,
    use_gc="G1GC"          # 可选，默认 "G1GC"
)
```

**方法链式调用：**

```python
# 从版本 JSON 添加参数
builder.add_from_version_json(version_json)

# 添加自定义参数（注意添加时机，位置不对可能导致崩溃）
builder.add_custom(["-Dmy.arg=value"])

# 获取参数列表
args = builder.get_args()       # -> list[str]

# 构建为单条指令字符串
cmd = builder.build()           # -> str
```

**自动添加的基础参数：**
- `-Xms{ram}M` / `-Xmx{ram}M` — 内存分配
- `-Dstderr.encoding=UTF-8` / `-Dstdout.encoding=UTF-8` / `-Dfile.encoding=UTF-8` — 编码
- `-XX:+Use{GC}` — 垃圾回收器
- `-XX:-UseAdaptiveSizePolicy` / `-XX:-OmitStackTraceInFastThrow` — 性能优化
- `-Dlog4j2.formatMsgNoLookups=true` — Log4j 安全修复
- `-Dfml.ignoreInvalidMinecraftCertificates=True` / `-Dfml.ignorePatchDiscrepancies=True` — Forge 兼容
- Windows 平台额外添加 `-XX:HeapDumpPath=...`
- macOS 平台额外添加 `-XstartOnFirstThread`

### ClasspathBuilder

构建 ClassPath，自动处理 ASM 版本冲突。

```python
from ECL.Game.Core.ECLauncherCore import ClasspathBuilder

cp_builder = ClasspathBuilder(game_path=".minecraft")

# 从版本 JSON 添加 Libraries
cp_builder.add_libraries(version_json)

# 添加游戏本体 Jar（必须最后执行）
cp_builder.add_version_jar(version_jar_path)

# 获取结果
classpath_str = cp_builder.build(";")      # Windows 用 ";", 其他用 ":"
natives = cp_builder.get_natives()          # -> list[str] 原生库列表
classpath = cp_builder.get_classpath()      # -> list[str] classpath 列表
```

**ASM 版本过滤：** 当多个库包含不同版本的 ASM 时，`ClasspathBuilder` 会自动选择最高版本，避免重复加载冲突。

### PlaceholderReplacer

占位符替换器，将启动命令中的 `${placeholder}` 替换为实际值。

```python
from ECL.Game.Core.ECLauncherCore import PlaceholderReplacer

replacer = PlaceholderReplacer(
    config=launch_config,
    classpath=classpath_str,
    main_class="net.minecraft.client.main.Main",
    index_id="17",
    natives_dir=".minecraft/versions/1.21.4/natives",
    version_jar_path=".minecraft/versions/1.21.4/1.21.4.jar",
    cp_delimiter=";",
    version_isolation=False,
)

final_cmd = replacer.replace(raw_command)
```

**支持的占位符：**

| 占位符 | 替换内容 |
|--------|----------|
| `${classpath}` | ClassPath 字符串 + mainClass |
| `${version_name}` | 版本名称 |
| `${library_directory}` | libraries 目录 |
| `${assets_root}` | assets 目录 |
| `${assets_index_name}` | 资源索引 ID |
| `${natives_directory}` | natives 目录 |
| `${game_directory}` | 游戏目录 |
| `${launcher_name}` | 启动器名称 |
| `${launcher_version}` | 启动器版本 |
| `${version_type}` | 版本类型 |
| `${auth_player_name}` | 玩家昵称 |
| `${user_type}` | 用户类型 |
| `${auth_uuid}` | 玩家 UUID |
| `${auth_access_token}` | 访问令牌 |
| `${user_properties}` | 用户属性 JSON |
| `${classpath_separator}` | ClassPath 分隔符 |
| `${primary_jar_name}` | 主 Jar 文件名 |
| `${resolution_width}` | 窗口宽度 |
| `${resolution_height}` | 窗口高度 |

### build_minecraft_cmd()

一站式构建 Minecraft 启动命令的便捷函数，封装了上述所有构建器的协作流程。

```python
from ECL.Game.Core.ECLauncherCore import build_minecraft_cmd, LaunchConfig

config = LaunchConfig(...)
cmd = build_minecraft_cmd(config)   # -> str 完整启动命令
```

**内部流程：**
1. 创建 `JvmArgumentBuilder` 并添加基础参数
2. 读取版本 JSON 文件
3. 从版本 JSON 添加 JVM 参数和 Game 参数
4. 创建 `ClasspathBuilder` 并添加 Libraries
5. 查找 inheritsFrom 继承版本，追加其参数和 Libraries
6. 添加自定义 JVM 参数
7. 添加版本 Jar 到 ClassPath
8. 解压 Native 库到 natives 目录
9. 通过 `PlaceholderReplacer` 替换所有占位符
10. 返回最终命令字符串

---

## 下载器 (Downloader)

异步下载器，支持并发控制、速度限制、暂停/恢复、多轮重试。

### DynamicSemaphore

可动态调整上限的异步信号量，Downloader 内部使用。

```python
from ECL.Game.Core.Downloader import DynamicSemaphore

sem = DynamicSemaphore(80)  # 初始并发数 80
await sem.acquire()          # 获取许可
sem.release()                # 释放许可
sem.change(200)              # 动态调整并发数
```

### RateLimiter

基于固定时间窗口的令牌桶限速器，Downloader 内部使用。

```python
from ECL.Game.Core.Downloader import RateLimiter

limiter = RateLimiter(speed_limit_mb=10.0, window=0.1)
await limiter.acquire(bytes_to_send)  # 请求允许发送指定字节数
```

### Downloader

核心下载器类。

```python
from ECL.Game.Core.Downloader import Downloader

download_list = [
    ("https://example.com/file1.jar", "libraries/file1.jar"),
    ("https://example.com/file2.jar", "libraries/file2.jar"),
]

downloader = Downloader(
    download_list=download_list,
    speed_limit_mb=0.0,          # 0 = 不限速, 否则为 MB/s
    progress_callback=on_progress,  # (downloaded: int, total: int) -> None
    speed_callback=on_speed,        # (speed_mb: float) -> None
    max_rounds=3,                   # 最大重试轮数, 0 = 不重试
    skip_preflight=False,           # 是否跳过预检
)

# 在异步事件循环中运行
await downloader.run()
```

**构造函数参数：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `download_list` | `list[tuple[str, Path\|str]]` | - | 下载任务列表 `[(url, path)]` |
| `speed_limit_mb` | `float` | `0.0` | 速度限制 (MB/s), 0 为不限速 |
| `progress_callback` | `Callable[[int,int],None]` | `None` | 进度回调 |
| `speed_callback` | `Callable[[float],None]` | `None` | 速度回调 |
| `max_rounds` | `int` | `3` | 最大重试轮数 |
| `skip_preflight` | `bool` | `False` | 跳过预检，直接使用文件计数模式 |

**控制方法：**

| 方法 | 说明 |
|------|------|
| `pause()` | 暂停所有下载任务 |
| `resume()` | 恢复暂停的下载任务 |
| `stop()` | 完全停止下载器并清理资源 |

**状态属性：**

| 属性 | 类型 | 说明 |
|------|------|------|
| `completed_entries` | `set[tuple[str,str]]` | 已完成的 (url, path) |
| `failed_entries` | `set[tuple[str,str]]` | 失败的 (url, path) |
| `total_bytes` | `int` | 总字节数或总文件数 |
| `downloaded_bytes` | `int` | 已下载字节数或已完成文件数 |

**进度模式：**

- **字节模式**（默认）：预检成功获取所有文件大小后使用，`progress_callback(downloaded_bytes, total_bytes)` 传递实际字节数
- **文件计数模式**：预检失败或 `skip_preflight=True` 时使用，`progress_callback(completed_count, total_count)` 传递文件数量

**并发策略：**
- 不限速模式：初始 80 并发，使用 AIMD 算法动态调节（10~500）
- 限速模式：固定 200 并发

**错误处理：**
- 每轮下载失败的文件进入下一轮重试，轮间使用指数退避等待
- 达到最大轮数后仍未完成的文件标记为永久失败，存入 `failed_entries`

---

## 文件校验 (FilesChecker)

通过 SHA1 校验检查 Minecraft 文件的完整性，返回需要下载的文件列表。

### FilesChecker

```python
from ECL.Game.Core.FilesChecker import FilesChecker
from ECL.Game.Core.Net.NetLibs import ApiUrlConfig, RepositoryResolver
from ECL.Game.Core.Net.MetaClient import MojangClient

api_config = ApiUrlConfig()
mojang_client = MojangClient(api_config)
resolver = RepositoryResolver(api_config)

checker = FilesChecker(mojang_client, resolver)

# 检查指定版本的完整性
download_list = checker.check_files(
    game_path=".minecraft",
    version_name="1.21.4"
)
# -> [("https://...", "path/to/file"), ...]
```

**check_files() 返回值：** `list[tuple[str, str]]` — 需要下载的文件列表，每项为 `(URL, 本地路径)`。

**检查范围：**
1. 游戏本体 Jar 文件 (`client.jar`) — 通过 SHA1 比对
2. Libraries 依赖库 — 包括主库和 Native 库
3. Assets 资源文件 — 包括资源索引和所有资源对象
4. 继承版本 (inheritsFrom) — 递归检查继承版本的全部文件

**说明：** 如果某个文件已存在且 SHA1 匹配，则不会加入下载列表。返回值可直接传给 `Downloader` 使用。

---

## 游戏获取 (GetGames)

获取 Minecraft 版本清单、版本分类、下载游戏。

### VersionClassifier

版本分类器，将原始版本列表按类型分类。

```python
from ECL.Game.Core.GetGames import VersionClassifier

classified = VersionClassifier.classify(versions)
# -> {
#     "All": [...],        # 所有版本
#     "Release": [...],    # 正式版
#     "Snapshot": [...],   # 快照版
#     "FoolDays": [...],   # 愚人节版
#     "Beta": [...],       # Beta 版
#     "Alpha": [...],      # Alpha 版
#     "Mapping": {...}     # ID -> 版本信息映射
# }
```

### VersionMetadataManager

管理 `VersionsInfo.json` 缓存文件，记录已安装版本的类型信息。

```python
from ECL.Game.Core.GetGames import VersionMetadataManager

metadata_mgr = VersionMetadataManager(game_path=".minecraft")
metadata_mgr.add_entry("1.21.4", {
    "Type": "Vanilla",
    "Version": "1.21.4",
    "VanillaType": "release"
})
```

### GetGames

游戏获取核心类，整合版本清单获取、下载、分类。

```python
from ECL.Game.Core.GetGames import GetGames

getter = GetGames(
    mojang_client=mojang_client,
    fabric_client=fabric_client,
    files_checker=files_checker,
    game_path=".minecraft",
)

# 自定义日志输出
getter.output_log = my_log_function  # 默认 print
```

**方法：**

| 方法 | 返回值 | 说明 |
|------|--------|------|
| `get_minecraft_versions()` | `dict` | 获取版本清单列表，包含分类和映射 |
| `download_minecraft(version_id, save_name)` | `bool` | 下载指定版本，返回是否成功 |

**get_minecraft_versions() 返回值结构：**

```python
{
    "Latest": {"release": "1.21.4", "snapshot": "25w..."},
    "All": [...],
    "Release": [...],
    "Snapshot": [...],
    "FoolDays": [...],
    "Beta": [...],
    "Alpha": [...],
    "Mapping": {"1.21.4": {...}, ...}
}
```

**download_minecraft() 流程：**
1. 获取版本清单，查找目标版本
2. 通过 Mojang API 获取版本 JSON
3. 保存 JSON 到 `versions/{save_name}/{save_name}.json`
4. 更新元数据缓存
5. 调用 `FilesChecker.check_files()` 生成下载列表

---

## 实例管理 (InstancesManager)

管理子进程（游戏进程）的生命周期，线程安全。

### InstancesManager

```python
from ECL.Game.Core.InstancesManager import InstancesManager

manager = InstancesManager()

# 设置回调
manager.set_log_callback(lambda log, instance_id: print(f"[{instance_id}] {log}"))
manager.set_exit_callback(lambda code, instance_id: print(f"退出码: {code}"))
```

**方法：**

| 方法 | 返回值 | 说明 |
|------|--------|------|
| `create_instance(name, type, args, **opts)` | `str` | 创建子进程实例，返回实例 ID |
| `send_stdin(instance_id, data)` | `None` | 向子进程发送标准输入 |
| `stop_instance(instance_id, force, wait_timeout)` | `bool` | 停止指定实例 |
| `get_instances_info()` | `list[dict]` | 获取所有实例信息 |
| `shutdown_all(force, wait_timeout)` | `None` | 终止所有实例 |
| `set_log_callback(callback)` | `None` | 设置日志回调 |
| `set_exit_callback(callback)` | `None` | 设置退出回调 |

**create_instance() 参数：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `instance_name` | `str` | - | 实例名称 |
| `instance_type` | `str` | - | 实例类型标识 |
| `args` | `str\|list[str]` | - | 启动命令 |
| `cwd` | `str\|Path\|None` | `None` | 工作目录 |
| `new_session` | `bool` | `True` | 是否新会话（关闭父进程时子进程不退出） |
| `only_stdout` | `bool` | `False` | 是否合并 stderr 到 stdout |
| `std_in` | `bool` | `False` | 是否开启 STDIN 管道 |
| `log_callback` | `Callable\|None` | `None` | 实例级日志回调，覆盖全局 |
| `exit_callback` | `Callable\|None` | `None` | 实例级退出回调，覆盖全局 |

**stop_instance() 参数：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `instance_id` | `str` | - | 实例 ID |
| `force` | `bool` | `False` | True 使用 kill(), False 使用 terminate() |
| `wait_timeout` | `float\|None` | `None` | 等待超时 (秒)，超时后强制 kill |

**回调签名：**

```python
# 日志回调: 每行输出触发一次
log_callback(log: str, instance_id: str) -> None

# 退出回调: 进程退出时触发一次
exit_callback(exit_code: int, instance_id: str) -> None
```

**线程安全：** 内部使用 `threading.Lock` 保护共享状态，使用 `_exited` 标志防止 stdout/stderr 两个线程重复触发退出回调。

---

## 工具库 (Libs)

提供一系列实用工具函数。

### 函数列表

| 函数 | 签名 | 说明 |
|------|------|------|
| `replace_last` | `(text, old, new) -> str` | 替换字符串中最后一次出现的匹配项 |
| `name_to_path` | `(name) -> str` | 将 Maven 坐标转换为文件路径 |
| `name_to_uuid` | `(name) -> UUID` | 计算离线玩家 UUID (UUID3) |
| `is_uuid3` | `(uuid_string) -> bool` | 检测字符串是否为 UUID3 |
| `unzip` | `(zip_path, unzip_path) -> bool` | 解压 ZIP 文件 |
| `get_file_sha1` | `(file_path) -> str` | 计算文件 SHA1 |
| `find_version` | `(version_json, game_path) -> tuple[dict, Path]\|None` | 查找 inheritsFrom 继承版本 |
| `set_minecraft_lang` | `(game_path, version_name, lang) -> None` | 设置 Minecraft 语言 |
| `parse_datetime` | `(time_str) -> dict` | 解析 ISO 时间字符串并转换为 UTC+8 |

### 使用示例

```python
from ECL.Game.Core.Libs import (
    name_to_path, name_to_uuid, is_uuid3, unzip,
    get_file_sha1, find_version, set_minecraft_lang, parse_datetime
)

# Maven 坐标转路径
path = name_to_path("net.minecraft:client:1.21.4")
# -> "net/minecraft/client/1.21.4/client-1.21.4.jar"

# 带 @suffix 的坐标
path = name_to_path("com.example:lib:1.0@zip")
# -> "com/example/lib/1.0/lib-1.0.zip"

# 离线玩家 UUID 计算
uuid = name_to_uuid("Steve")
# -> UUID("...")

# UUID3 检测
is_uuid3("xxxxxxxx-xxxx-3xxx-xxxx-xxxxxxxxxxxx")  # -> True

# 文件 SHA1
sha1 = get_file_sha1("path/to/file.jar")

# 查找继承版本
result = find_version(version_json, ".minecraft")
if result:
    game_json, version_dir = result

# 设置游戏语言
set_minecraft_lang(".minecraft", "1.21.4", "zh_CN")

# 解析 Minecraft 时间字符串
dt = parse_datetime("2025-12-16T12:42:29+00:00")
# -> {"Original": {...}, "Converted": {...}}  (UTC+8)
```

---

## 微软认证 (MicrosoftAuth)

提供完整的 Microsoft OAuth 认证流程和 Minecraft API 交互。

### 异常体系

```
Exception
 └── BException
      ├── AuthException
      │    ├── MicrosoftAuthError    # Microsoft OAuth 认证失败
      │    ├── XboxAuthError         # Xbox Live 令牌获取失败
      │    ├── XSTSAuthError         # XSTS 令牌获取失败
      │    └── MinecraftAuthError    # Minecraft 令牌/档案操作失败
      └── NetException
           ├── GetSkinError          # 获取皮肤失败
           └── UpdateSkinError       # 更新皮肤失败
```

### MicrosoftAuth

负责 Microsoft OAuth 设备码流程。

```python
from ECL.Game.Core.MicrosoftAuth import MicrosoftAuth

auth = MicrosoftAuth(
    client_id="your-azure-client-id",
    cache_file="token_cache.json",    # 可选，持久化令牌缓存
    on_device_code=lambda flow: print(flow["user_code"])  # 设备码回调
)

# 获取 Microsoft 访问令牌
access_token, email = auth.get_token()
# -> ("eY...", "user@example.com")
```

**get_token() 流程：**
1. 尝试从缓存静默获取令牌
2. 若失败，启动设备码流程
3. 调用 `on_device_code` 回调通知用户
4. 等待用户完成浏览器授权
5. 返回 `(access_token, email)`

### MinecraftClient

Minecraft API 客户端，处理令牌链认证和皮肤管理。

```python
from ECL.Game.Core.MicrosoftAuth import MinecraftClient

client = MinecraftClient()

# 完整认证链: Microsoft -> Xbox -> XSTS -> Minecraft
mc_token, timestamp, expires_in = client.get_minecraft_token(ms_token)

# 获取玩家档案
profile = client.get_profile(mc_token)
# -> {"id": "...", "name": "PlayerName", ...} 或 None (未购买)

# 获取皮肤
skin = client.get_skin(mc_uuid)

# 上传皮肤
client.upload_skin(mc_token, variant="slim", png_image=image_bytes)

# 重置皮肤为默认
client.reset_skin(mc_token)

# 设置披风
client.set_cape(mc_token, cape_id="...")

# 重置披风
client.reset_cape(mc_token)

# 关闭客户端
client.close()
```

### MicrosoftAuthManager

多账户管理器，线程安全，提供账户增删查改和自动令牌刷新。

```python
from ECL.Game.Core.MicrosoftAuth import MicrosoftAuthManager

# 创建管理器
mgr = MicrosoftAuthManager(
    client_id="f1709935-df0b-400c-843a-530a77fb8d3c",  # 默认值
    cache_path="~/.ECL",                                 # 默认值
    on_device_code=lambda flow: print(flow["user_code"])
)

# 添加微软账户（触发设备码流程）
account_id = mgr.add_microsoft_account()

# 获取所有账户
accounts = mgr.get_microsoft_accounts()
# -> {"account_id": {"AccountId": ..., "Email": ..., "Profile": ..., "Skin": ...}}

# 获取 Minecraft 令牌（自动刷新）
mc_token = mgr.get_minecraft_token(account_id)

# 刷新档案
profile = mgr.refresh_profile(account_id)
# -> {"Profile": {...}, "Skin": {...}}

# 获取指定 UUID 的皮肤
skin = mgr.get_skin(mc_uuid)

# 上传皮肤
mgr.upload_skin(account_id, variant="slim", png_image=bytes)

# 重置皮肤
mgr.reset_skin(account_id)

# 设置/重置披风
mgr.set_cape(account_id, cape_id="...")
mgr.reset_cape(account_id)

# 删除账户
mgr.del_microsoft_account(account_id)

# 关闭资源
mgr.close()
```

**令牌管理：** `get_minecraft_token()` 自动检查令牌过期时间（剩余 > 300 秒时直接返回），过期时自动通过 Microsoft 令牌刷新。

**数据持久化：** 账户列表保存在 `{cache_path}/ms_accounts_list.json`，每个账户的 OAuth 令牌缓存保存在 `{cache_path}/ms_accounts/{account_id}.json`。

---

## 网络模块 (Net)

### ApiUrlConfig

API URL 配置数据类，支持动态修改镜像源。

```python
from ECL.Game.Core.Net.NetLibs import ApiUrlConfig

config = ApiUrlConfig()  # 使用默认值

# 从字典创建（自定义镜像）
config = ApiUrlConfig.from_dict({
    "Meta": "https://bmclapi2.bangbang93.com",
    "Assets": "https://bmclapi2.bangbang93.com/assets",
})

# 修改单个值
config.Meta = "https://bmclapi2.bangbang93.com"

# 查询
config.get("Meta")     # -> "https://..."
config.to_dict()       # -> {"Meta": "...", ...}
config.update_from_dict({"Meta": "..."})
```

**默认 URL：**

| 字段 | 默认值 | 用途 |
|------|--------|------|
| `Meta` | `https://launchermeta.mojang.com` | 版本元数据 |
| `Data` | `https://launcher.mojang.com` | 游戏数据 |
| `Libraries` | `https://libraries.minecraft.net` | 依赖库 |
| `Assets` | `https://resources.download.minecraft.net` | 资源文件 |
| `Forge` | `https://files.minecraftforge.net/maven` | Forge |
| `Fabric` | `https://maven.fabricmc.net` | Fabric |
| `FabricMeta` | `https://meta.fabricmc.net` | Fabric 元数据 |
| `NeoForged` | `https://maven.neoforged.net/releases` | NeoForged |
| `Quilt` | `https://maven.quiltmc.org` | Quilt |
| `QuiltMeta` | `https://meta.quiltmc.org` | Quilt 元数据 |

### BaseApiClient

所有 API 客户端的基类，提供统一的 HTTP 客户端和重试机制。

```python
from ECL.Game.Core.Net.NetLibs import BaseApiClient

# 一般不直接使用，通过子类 MojangClient / FabricClient 使用
```

**特性：**
- HTTP/2 支持
- 自动重试（指数退避）
- 连接池复用（max_keepalive_connections=20, max_connections=40）
- 30 秒超时（15 连接超时）

### RepositoryResolver

仓库解析器，根据依赖的来源自动选择正确的下载仓库。

```python
from ECL.Game.Core.Net.NetLibs import RepositoryResolver

resolver = RepositoryResolver(api_config)

# 根据 URL 和路径判断使用哪个仓库
base_url = resolver.resolve(
    url="https://maven.fabricmc.net/...",
    path="net/fabricmc/fabric-loader/..."
)
# -> "https://maven.fabricmc.net"  (自动识别 Fabric)
```

**解析规则：**
- 包含 "fabric" → `config.Fabric`
- 包含 "neoforged" / "neoforge" → `config.NeoForged`
- 包含 "forge" → `config.Forge`
- 包含 "quilt" → `config.Quilt`
- 默认 → `config.Libraries`

### MojangClient

Mojang 官方 API 交互。

```python
from ECL.Game.Core.Net.MetaClient import MojangClient

mojang = MojangClient(config=api_config, max_retries=3)

# 获取完整版本清单
manifest = mojang.get_version_manifest()

# 获取某个版本的 Meta JSON
version_json = mojang.get_version_json(version_id="1.21.4", sha1="abc123")

# 获取资源索引文件
asset_index = mojang.get_asset_index(asset_id="17", sha1="def456")

# 获取客户端 Jar 下载 URL
jar_url = mojang.get_client_jar_url(sha1="abc123")
```

### FabricClient

Fabric 官方 API 交互。

```python
from ECL.Game.Core.Net.MetaClient import FabricClient

fabric = FabricClient(config=api_config)

# 获取指定 Minecraft 版本可用的 Fabric 版本列表
loaders = fabric.get_loaders(version_id="1.21.4")
# -> [{"loader": {...}}, ...]

# 获取 Fabric 版本的 Meta JSON
profile = fabric.get_loader_profile(
    game_version_id="1.21.4",
    loader_version="0.16.10"
)
```

---

## 完整示例

### 示例 1：从零下载并启动 Minecraft

```python
import asyncio
from pathlib import Path
from ECL.Game.Core.Net.NetLibs import ApiUrlConfig, RepositoryResolver
from ECL.Game.Core.Net.MetaClient import MojangClient, FabricClient
from ECL.Game.Core.FilesChecker import FilesChecker
from ECL.Game.Core.GetGames import GetGames
from ECL.Game.Core.Downloader import Downloader
from ECL.Game.Core.ECLauncherCore import build_minecraft_cmd, LaunchConfig
from ECL.Game.Core.InstancesManager import InstancesManager
from ECL.Game.Core.Libs import name_to_uuid

async def download_and_launch(game_path, version_id, java_path, player_name, ram_mb):
    # 1. 初始化基础设施
    api_config = ApiUrlConfig()
    mojang = MojangClient(api_config)
    fabric = FabricClient(api_config)
    resolver = RepositoryResolver(api_config)
    checker = FilesChecker(mojang, resolver)
    getter = GetGames(mojang, fabric, checker, game_path)

    # 2. 下载游戏
    getter.download_minecraft(version_id)

    # 3. 检查文件完整性并下载缺失文件
    download_list = checker.check_files(game_path, version_id)
    if download_list:
        downloader = Downloader(
            download_list=download_list,
            speed_limit_mb=0.0,
            progress_callback=lambda d, t: print(f"下载进度: {d}/{t}"),
            max_rounds=3
        )
        await downloader.run()

    # 4. 构建启动配置
    config = LaunchConfig(
        java_path=java_path,
        game_path=game_path,
        version_name=version_id,
        use_ram=ram_mb,
        player_name=player_name,
        auth_uuid=str(name_to_uuid(player_name)),
        user_type="legacy",
        window_width=854,
        window_height=480,
    )

    # 5. 构建启动命令
    cmd = build_minecraft_cmd(config)

    # 6. 启动游戏
    manager = InstancesManager()
    manager.set_log_callback(lambda log, iid: print(log))
    manager.set_exit_callback(lambda code, iid: print(f"游戏退出，代码: {code}"))

    instance_id = manager.create_instance(
        instance_name=f"Minecraft {version_id}",
        instance_type="minecraft",
        args=cmd,
        cwd=game_path,
    )

    return instance_id

# 使用
# asyncio.run(download_and_launch(".minecraft", "1.21.4", "C:/java/bin/javaw.exe", "Steve", 4096))
```

### 示例 2：微软账户登录

```python
from ECL.Game.Core.MicrosoftAuth import MicrosoftAuthManager

def handle_device_code(flow):
    """展示设备码给用户"""
    print(f"请在浏览器中打开: {flow['verification_uri']}")
    print(f"输入代码: {flow['user_code']}")

mgr = MicrosoftAuthManager(on_device_code=handle_device_code)

try:
    account_id = mgr.add_microsoft_account()
    accounts = mgr.get_microsoft_accounts()
    print(f"登录成功: {accounts[account_id]['Profile']['name']}")

    # 获取 Minecraft 令牌用于启动
    mc_token = mgr.get_minecraft_token(account_id)

except Exception as e:
    print(f"登录失败: {e}")
```

### 示例 3：使用自定义镜像源

```python
from ECL.Game.Core.Net.NetLibs import ApiUrlConfig

# 使用 BMCLAPI 镜像
config = ApiUrlConfig.from_dict({
    "Meta": "https://bmclapi2.bangbang93.com",
    "Libraries": "https://bmclapi2.bangbang93.com/libraries",
    "Assets": "https://bmclapi2.bangbang93.com/assets",
})

# 后续所有 API 客户端都使用此配置
mojang = MojangClient(config)
# ...
```

### 示例 4：下载器暂停/恢复

```python
import asyncio
from ECL.Game.Core.Downloader import Downloader

async def download_with_pause():
    download_list = [("url1", "path1"), ("url2", "path2")]
    downloader = Downloader(download_list)

    # 在后台启动下载
    task = asyncio.create_task(downloader.run())

    # 5 秒后暂停
    await asyncio.sleep(5)
    downloader.pause()
    print("下载已暂停")

    # 3 秒后恢复
    await asyncio.sleep(3)
    downloader.resume()
    print("下载已恢复")

    await task
    print(f"完成: {len(downloader.completed_entries)}, 失败: {len(downloader.failed_entries)}")
```

---

> **文档版本：** v1.0  
> **最后更新：** 2026-07-21  
> **适用版本：** ECL.Game.Core (当前源码)