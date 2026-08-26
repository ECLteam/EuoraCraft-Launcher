# EuoraCraft Launcher 第二轮深度审计报告

- **审计日期**：2026-08-26（第二轮，第一轮见 `code-audit-report-2026-08-26.md`）
- **审计范围**：第一轮未深读的全部模块——IPC 全量命令（`ECL/api/*`）、插件系统全链路（发现/加载/生命周期/权限/扩展点）、账户与认证全流程（`services/accounts.py`、`services/authlib.py`）、游戏服务（`services/game/*`）、窗口管理、日志/网络/环境基础设施、前端 XSS 汇点/路由/存储面
- **审计方式**：逐模块深读 + 跨层攻击链推演（webview → IPC → 文件系统/子进程/网络）
- **范围约定**：联机（`services/connector.py`、`services/florolding`）与 `ECL/game` 子模块不在本轮修复范围内，但涉及它们的交互面仍做了分析
- **结论摘要**：发现 **5 个高危问题**（其中 3 个构成 webview 被攻破后的完整提权链：任意文件读、读型 SSRF、任意文件打开；2 个在插件生态侧：安装路径穿越、插件无权限启动子进程）、**若干中危**（凭证存储与内存驻留、AuthProvider 抢注、事件伪造面）与一批隐藏 Bug（损坏文件崩溃启动、命令超时线程泄漏、任意路径覆盖等）

---

## 一、高危发现

### 🔴 D1 webview 可读取用户权限内的任意文件（`fs_*` / `image_read_file` 无目录边界）

**位置**：`ECL/api/files.py` `fs_read_file`、`fs_read_dir`、`fs_exists`、`file_resolve`、`image_read_file`、`image_list_files`

这些命令接受前端传入的任意 `path`，只做空值与 `\0` 检查：

```python
# fs_read_file
path = Path(self._normalize_file_path(raw_path)).expanduser()
if not path.is_file(): ...
if path.stat().st_size > _MAX_FILE_READ_BYTES: ...   # 20 MiB
content = await to_thread.run_sync(path.read_bytes)
```

webview（以及注入其中的任何插件 JS、或任何一处 XSS）可以读取当前用户可读的任意文件并以 text/base64 取回：`~/.ECL/accounts/` 下的令牌、`~/.ssh/`、浏览器配置、其他启动器凭据等。`image_read_file`/`image_list_files`/`fs_read_dir` 同理，无大小之外的任何限制。

**攻击链**：恶意插件注入脚本（合法能力）或任意 XSS → `fs_read_file` → 数据外传（配合 D2 甚至不用出网）。

**修复建议**：为 `fs_*` 增加目录白名单（配置过的游戏目录、`ECL_data`、日志目录），或要求路径必须来自此前的对话框选择结果（后端持有句柄）。

---

### 🔴 D2 读型 SSRF：`image_fetch_data_url` 等可借启动器读取任意 HTTP 端点

**位置**：`ECL/api/files.py` `image_fetch_data_url`/`image_save_url`/`image_save_as`；`ECL/api/bridge.py` `_download_remote_image`（183-204）

`_normalize_image_url` 只校验 http/https scheme。`_download_remote_image` 下载后**不校验 Content-Type**，响应体（上限 50 MiB）经 `image_fetch_data_url` 原样 base64 返回给前端：

```python
async with httpx.AsyncClient(follow_redirects=True, ...) as client, client.stream("GET", url) as response:
    response.raise_for_status()
    ...  # 无任何 content-type / 主机限制
```

后果：
- webview 可把启动器当代理，读取 `http://127.0.0.1:<任意端口>/...`（本机服务、联机组件管理端口、云元数据 `169.254.169.254` 等）并拿到响应内容；
- `follow_redirects=True` 允许外部服务器把请求重定向到内网地址；
- 50 MiB 的下载上限也放大了资源消耗。

**修复建议**：强制响应 Content-Type 为图片类；拒绝环回/链路本地/元数据地址段；或仅在 URL 来自可信来源（账户材质元数据、搜索结果缩略图）时放行。

---

### 🔴 D3 `open_folder` 不校验目标是目录 → 任意本地项目打开/执行

**位置**：`ECL/api/bridge.py:212-223` `_open_folder`；调用方 `files.py open_folder`、`mods.py open_mods_folder`

```python
def _open_folder(path: str) -> None:
    target = Path(path).resolve()
    if not target.exists():
        raise FileNotFoundError(...)
    if sys.platform == "win32":
        os.startfile(str(target))   # 对文件同样生效
```

`os.startfile` 对**文件**会用关联程序打开（`.lnk`、`.html`、`.exe` 等直接触发执行/浏览器）。`open_folder` IPC 接受 webview 任意路径 → 被攻破的前端可打开/执行用户主目录下的任意项目。

**修复建议**：`if not target.is_dir(): raise`；确需“在资源管理器中定位文件”时用 `explorer /select,<file>` 专用分支。

---

### 🔴 D4 插件安装路径穿越：`plugin.json` 的 `name` 未校验

**位置**：`ECL/plugins/manager/lifecycle.py` `install()`（246-276）、`ECL/plugins/manager/storage.py` `_load_plugin_config`/`_save_plugin_config`

```python
target_name = metadata.get("name")          # 来自插件自带的 plugin.json，无任何校验
target_dir = self._plugin_dir / target_name
if target_dir.exists():
    shutil.rmtree(target_dir)               # name="../../x" → 删除插件目录之外的任意目录
shutil.copytree(source, target_dir)         # 并向该处写入任意内容
```

`name` 含 `..`/`/` 时，`rmtree + copytree` 落在插件目录之外。插件配置持久化同样用 `plugin_config/<name>.json` 拼接，存在同根因的写越界。对照：`uninstall()` 有正确的 `resolved_plugin_dir.parent != plugin_root` 边界检查，`install()` 没有。

**修复建议**：在发现阶段用既有模式 `^[a-z][a-z0-9_-]{1,63}$`（`plugins/connector.py`、`instance_compat.py` 已在用）统一校验插件名，非法即拒绝加载。

---

### 🔴 D5 插件无需任何声明权限即可启动任意子进程

**位置**：`ECL/plugins/plugin.py:136`、`ECL/services/processes.py`

```python
self.processes = getattr(framework, "processes", None)   # Plugin.__init__ 直接暴露
```

`PermissionScope` 覆盖 settings/events/commands/filesystem/network/ui/instances/connector/launch/accounts/crash，唯独**没有进程能力的作用域**。任何插件（哪怕 plugin.json 声明零权限）都能 `self.processes.spawn(name, type_, args)` 执行任意命令、写 stdin、列进程。这比受 `ui:write` 门禁的 `inject_script` 更强——后者至少还要声明权限。

**修复建议**：新增 `PROCESS`（或复用 `commands`）作用域，`spawn` 前走 `_check_permission`；或仅对系统插件暴露该能力。

---

## 二、中危发现

### 🟠 D6 AuthProvider ID 抢注：恶意插件可劫持他人登录表单

**位置**：`ECL/plugins/auth_providers.py` `AuthProviderRegistry.register`（87-110）

`register` 对同 `provider_id` **原位静默替换**，不检查 owner 冲突。插件 B 可以注册与插件 A 相同的 `provider_id`：用户在账户页填写的表单值（可能含第三方服务口令）会提交给 B 的 `authenticate` 回调；卸载 A 也不会移除 B 的劫持条目。

**修复建议**：`provider_id` 已存在且 owner 不同时拒绝注册并记录告警。

### 🟠 D7 声明式权限自动授予 + 事件伪造面

**位置**：`ECL/adapters/tauri.py:98-132`（事件转发表）、`ECL/plugins/plugin.py emit`

总线事件 `launcher:popup`、`launcher:error`、`accounts:changed`、`game:*_progress` 等被适配器无条件转发到 UI。插件声明 `events:emit:*` 即可伪造弹窗/错误/进度（钓鱼提示、假安装进度）；声明 `network:read:*` 即可经共享客户端访问环回地址（与 D2 叠加）。当前模型在插件**安装/启用时没有任何权限确认 UI**——声明即授予。

**修复建议**：插件启用前展示其声明权限清单并要求用户确认；对转发到 UI 的敏感事件可加“来源标注”。

### 🟠 D8 令牌明文落盘且权限默认（跨平台）

**位置**：`ECL/services/authlib.py` `_save_token`/`_save_accounts`（`~/.ECL/accounts/yggdrasil_accounts/*.json`）；MS 令牌缓存同理（`ECL/game` 写入）

AccessToken/ClientToken 以明文 JSON 存储，目录/文件按默认 umask 创建（Linux 上 0755/0644）。启动器声明支持 Linux/macOS——多用户机器上其他本地账户可直接读取令牌。

**修复建议**：创建 `~/.ECL` 及账户文件时显式 0700/0600（`os.chmod` 或 `os.open` + mode）。

### 🟠 D9 Authlib 待选角色登录的口令长期驻留内存且无上限累积

**位置**：`ECL/services/authlib.py` `_create_pending_login`（238-256）、`select_profile`

多角色登录时口令被存入 `pending_accounts[account_id]["Password"]`，仅在 `select_profile` 成功时移除。用户放弃选择（关弹窗）后，口令保留至进程退出；每次新的多角色登录都会**新增**一条含口令条目，无过期、无上限、无清理。第一轮将其评估为“短生命周期”不准确——实际是无限期驻留。

**修复建议**：不保存口令，选角色时需要时让用户重新输入；或至少在新登录/超时/进程空闲时清理过期 pending 条目。

### 🟠 D10 `info_card` 保留 `verify=False` 降级路径

**位置**：`ECL/services/info_card.py:45-48`

```python
def _get_without_ssl_verify(url: str, **kwargs):
    return httpx.get(url, verify=False, **kwargs)
```

生产装配确实注入了共享客户端（`application.py:289`），该分支目前是死代码；但“未注入即放弃证书校验”是危险默认值，测试或未来重构随时可能踩中。第一轮修掉了 bridge 的 `verify=False`，此处为遗漏。

**修复建议**：删除降级分支，未注入客户端时改用 `verify=True` 的独立客户端。

---

## 三、隐藏 Bug 与逻辑缺陷

### Bug-D1（中）：`yggdrasil_accounts_list.json` 损坏会导致启动器无法启动

**位置**：`ECL/services/authlib.py` `_load`（113-124）

`json.loads` 无异常处理，异常经 `AuthlibAccountManager.__init__` → `AccountManager.__init__` 一路冒到启动流程。对照：`AccountManager._load_state` 与 `WardrobeStore._load_items` 都做了“损坏→备份→重建”的优雅降级，此处缺失。手工编辑失误或掉电写坏即可让启动器进入启动即崩的死循环。

### Bug-D2（中）：插件命令超时后工作线程泄漏，8 次挂起即全瘫

**位置**：`ECL/plugins/manager/registry.py` `call_command`（300-326）

`future.result(timeout=timeout)` 超时抛错后，处理函数仍在线程中运行（Python 线程不可中断），也没有调用 `future.cancel()`。`_command_executor` 仅 8 个 worker：一个行为异常（死循环/阻塞）的插件命令永久占用一个槽位，累计 8 次后**所有插件命令**排队至死。这是插件侧可触发的启动器功能 DoS。

**建议**：超时后 `future.cancel()`（至少防止未开始的任务占槽）、对屡次超时的插件降级（禁用其命令）、把“超时不终止线程”写进插件 SDK 文档。

### Bug-D3（中）：`export_logs` 接受任意 `output_path` → 任意文件覆盖

**位置**：`ECL/api/system.py` `export_logs`（150-180）

`output_path` 由前端直接给定（非对话框结果），`resolve` 后 `temporary.replace(target)` 可覆盖用户可写的任意文件（内容固定为日志 zip，危害低于任意写但仍可破坏文档）。同类问题：`game_screenshot_save_as`、`game_world_export`、`game_resource_manifest_export` 等的 `output_path` 正常流程来自 `select_save_file`，但后端未强制。

**建议**：后端要么强制输出目录（`data_path/exports`），要么校验路径来自最近一次保存对话框的选择。

### Bug-D4（低）：`image_save_as` 的本地 `path` 分支读文件无大小上限

**位置**：`ECL/api/files.py` `image_save_as`（`file_path.read_bytes()` 无 20 MiB 限制，`fs_read_file` 却有限制）→ 指向超大文件可 OOM。

### Bug-D5（低）：非单例窗口重复 `instance_key` 会静默顶掉旧窗口登记

**位置**：`ECL/api/windows.py` `window_open`——singleton 分支有“已存在则聚焦”逻辑，非 singleton 时同一 `descriptor_id:instance_key` 再次 `window_open` 会覆盖 `_webviews[label]`/`_window_metadata[label]`，旧 webview 失去宿主登记（无法再关闭/聚焦）。

### Bug-D6（低）：`debug_devtools_open` 未做调试模式门禁

**位置**：`ECL/api/system.py`——`debug_reset_launcher_data`/`debug_clear_plugins`/`debug_process_spawn` 都要求 `launcher.debug`，唯独 devtools 无条件开放，与“调试命令”命名不符。

### Bug-D7（低）：认证链各客户端的 SSL/代理策略不一致

- `AuthlibAccountManager` 创建时未接入 `disable_ssl_verify`（微软链接了，`services/accounts.py:235` 传 `verify=not disable_ssl_verify`；authlib 链的 `YggdrasilClient()` 永远默认校验）；
- `AuthlibInjector` 在 `services/game/base.py` 的回退构造 `AuthlibInjector(data_path)` 自建客户端，不走用户代理。
用户在设置里关掉证书校验或配置代理后，外置登录链行为不一致（该失败时不失败、该走代理时直连）。

### Bug-D8（低）：`_build_local_player_icon_provider` 下载皮肤无总量上限

**位置**：`ECL/application.py:112-118`——`b"".join(response.iter_bytes(64*1024))` 无尺寸上限，恶意材质服务器返回超大文件即可吃满内存（联机头像功能路径）。

### Bug-D9（低）：衣柜损坏备份名按秒级时间戳可互相覆盖

**位置**：`ECL/services/wardrobe.py` `_load_items`——`wardrobe.corrupt-%Y%m%d%H%M%S.json` 同秒内两次损坏会相互覆盖，建议补随机后缀。

---

## 四、编码不合理与冗余（第二轮补充）

1. **旧版模组 API 与资源 API 双轨并存**：`api/mods.py` 的 `get_mods`/`toggle_mod`/`add_mod`/`remove_mod`/`search_mods`/`download_mod`/`download_mod_to_path` 与 `game_resource_*` 功能重叠；且 mods.py 全部用裸 `body.get(...)`，是唯一不走 Pydantic 请求模型的正式 IPC 域。
2. **`BUILTIN_WINDOW_DESCRIPTORS` 恒为空 dict**（`api/windows.py:31`）——内置窗口全部走插件描述符路径，该表是死脚手架。
3. **`_query_context` 用 `Path.cwd() / ".minecraft"` 占位**（`services/game/base.py`）——查询类操作伪造游戏目录，语义脆弱。
4. **`Environment.apply_to_config` 允许 `ECL_CONFIG_*` 覆盖任意配置键**——虽然环境变量与用户同权，但与已建立的配置分区白名单思路相悖，建议至少排除 `tauri` 分区。
5. **`plugin_install` 的 `plugin_path` 无模型校验**（`api/plugins.py`）——IPC 域内少数仍裸取 body 的命令之一。

---

## 五、复查确认无问题的面（第二轮）

- **事件总线**：异常隔离、owner 反注册、快照分发均正确；无全局单例状态。
- **账户服务并发模型**：`AccountManager` 单把可重入锁 + 登录任务状态机（starting/pending/progress/ready/cancelled）路径完整；确认 `MicrosoftAuthManager` 的 `on_device_code` 回调**不在其内部锁内触发**，不存在锁序反转死锁。
- **窗口体系**：`WindowOpenRequest` 等模型有严格模式校验；插件窗口描述符要求 `ui:write:window:<id>` 权限 + `contributes.windows` 双重校验，路由前缀强制 `/plugin/<插件名>/`；`authorize_window_command` 对非主窗口逐命令授权；`window:ready` 防劫持（第一轮已修）仍在位。
- **游戏服务路径面**：`_normalize_version_name` 拒绝分隔符；世界/截图/资源均走 `resolve_relative_id`/`safe_extract_zip`；`uninstall` 插件目录有边界校验；`_mod_path` 有 parent+name 双校验。
- **前端**：公告/弹窗/帮助文本全部经 `renderMarkdown`（marked + DOMPurify，FORBID style）；插件路由命名空间化，无法遮蔽内置路由；localStorage 不存任何令牌/凭据；传输层响应有 valibot 校验；`capabilities/default.toml` 权限面最小化（无 shell:open/fs 插件）。
- **日志管道**：前端日志上报有长度上限（20000/100000），轮转压缩正确。

---

## 六、修复优先级建议

### 立即（一行~几十行，收益最大）
1. **D4**：插件名在发现/安装时按 `^[a-z][a-z0-9_-]{1,63}$` 校验（封堵 rmtree/copytree 越界与配置写越界）；
2. **D3**：`_open_folder` 强制 `is_dir()`；
3. **D10**：删除 `info_card` 的 `verify=False` 降级；
4. **Bug-D1**：`AuthlibAccountManager._load` 加损坏降级；
5. **D6**：AuthProvider 注册加 owner 冲突检查。

### 本周
6. **D2**：`_download_remote_image` 强制图片 Content-Type + 环回/元数据地址拒绝（或至少内容类型强制）；
7. **D1**：`fs_*`/`image_read_file` 加目录白名单；
8. **D5**：插件 `processes.spawn` 增加权限作用域门禁；
9. **Bug-D2**：命令超时后 `future.cancel()` + 屡犯插件降级策略。

### 近期
10. **D8**：`~/.ECL` 目录与令牌文件显式 0700/0600；
11. **D9**：pending 登录口令不落内存（重新输入）或加过期清理；
12. **D7**：插件启用时的权限清单确认 UI；
13. **Bug-D3**：导出类命令的输出路径强制（导出目录或对话框句柄）；
14. 旧版模组 API 与 `game_resource_*` 合流，统一走 Pydantic 模型。

---

*第二轮报告基于 2026-08-26 工作区（第一轮修复已合入工作树）。行号以当前工作树为准。*
