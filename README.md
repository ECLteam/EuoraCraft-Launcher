# EuoraCraft Launcher

现代化 Minecraft Java Edition 启动器。

- 项目主页：https://github.com/ECLTeam/EuoraCraft-Launcher
- 问题反馈：https://github.com/ECLTeam/EuoraCraft-Launcher/issues
- 邮箱：EuoraCraft-Studio@outlook.com
- 许可证：GPL-3.0

---

## 本地开发教程

本仓库为后端主仓库。前端代码位于独立的 `EuoraCraftLauncher-UI` 仓库，本地开发时需要将前后端同时准备好。

### 前置要求

| 工具 | 最低版本 | 说明 |
|------|----------|------|
| Python | 3.11 | 后端运行时 |
| Rust | 1.82+ | PyTauri / Tauri 底层依赖 |
| Node.js | 18+ | 前端运行时 |
| pnpm | 11.10+ | 前端包管理器 |
| Git | 2.x | 版本控制 |

Windows 开发为主力平台，Linux 与 macOS 亦可运行后端与打包流程。

### 克隆仓库

后端与前端分属两个仓库。建议按如下目录结构存放：

```text
EuoraCraft-Launcher/
├── ECL/
├── main.py
├── Tauri.toml
├── ...
└── EuoraCraftLauncher-UI/   # 前端仓库克隆到这里
    ├── package.json
    ├── vite.config.ts
    └── ...
```

```bash
# 克隆后端
mkdir EuoraCraft-Launcher
cd EuoraCraft-Launcher
git clone https://github.com/ECLTeam/EuoraCraft-Launcher.git .

# 克隆前端到子目录
git clone https://github.com/ECLTeam/EuoraCraftLauncher-UI.git EuoraCraftLauncher-UI
```

如果你已有自己的前端 fork，将上面的 URL 替换为对应地址即可。

### 后端环境配置

#### 1. 创建虚拟环境

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate
```

#### 2. 安装依赖

```bash
pip install -e ".[dev]"
```

这会安装 `pyproject.toml` 中声明的全部依赖，包括 `pytauri-wheel`、`pytauri` 以及开发工具。

#### 3. 配置环境变量

在项目根目录创建 `.env.dev`（开发环境优先读取）或 `.env`：

```env
# 必填：微软 OAuth 客户端 ID
# 为空时启动器会弹窗提示配置
MICROSOFT_CLIENT_ID=

# 可选：前端 dev server 地址，默认 http://localhost:5173
FRONTEND_DEV_SERVER=http://localhost:5173
```

环境变量统一通过 `ECL/common/env.py` 中的 `EnvLoader` 读取，代码中不要直接使用 `os.environ.get()`。

### 前端环境配置

```bash
cd EuoraCraftLauncher-UI
pnpm install
```

### 启动开发模式

需要同时运行两个进程。

#### 终端 1：启动前端 dev server

```bash
cd EuoraCraftLauncher-UI
pnpm dev
```

默认监听 `http://localhost:5173`。

#### 终端 2：启动后端

```bash
# 确保已激活虚拟环境
python main.py
```

后端启动时会自动读取 `FRONTEND_DEV_SERVER` 并连接前端 dev server。如果一切正常，会弹出 EuoraCraft Launcher 窗口。

### 使用本地构建的前端

如果你想在不启动 dev server 的情况下测试前端构建产物：

```bash
cd EuoraCraftLauncher-UI
pnpm build
```

构建输出位于 `EuoraCraftLauncher-UI/dist`。确保 `Tauri.toml` 中的 `frontendDist` 指向正确路径：

```toml
[build]
frontendDist = "EuoraCraftLauncher-UI/dist"
devUrl = "http://localhost:5173"
```

然后直接运行：

```bash
python main.py
```

此时后端会使用本地静态文件，而不是 dev server。

### 项目结构速览

```text
EuoraCraft-Launcher/
├── ECL/                        # 后端源码
│   ├── app.py                  # 应用入口
│   ├── launcher.py             # 启动器核心初始化
│   ├── adapters/adapter.py     # PyTauri 适配器
│   ├── api/                    # API 处理器与事件
│   ├── auth/                   # 微软 / Authlib 账户鉴权
│   ├── common/                 # 配置、环境、日志、状态
│   ├── game/Core/              # 游戏核心（避免修改）
│   ├── java/                   # Java 探测
│   ├── mods/                   # Mod 管理
│   ├── plugin/                 # 插件框架
│   └── resources/              # 资源管理
├── EuoraCraftLauncher-UI/      # 前端仓库
├── plugins/                    # 本地插件
├── resources/                  # 运行时资源
├── Tauri.toml                  # Tauri / PyTauri 配置
├── pyproject.toml              # Python 项目配置
└── main.py                     # 启动入口
```

### 常用命令

| 命令 | 说明 |
|------|------|
| `python main.py` | 以开发模式启动启动器 |
| `cd EuoraCraftLauncher-UI && pnpm dev` | 启动前端 dev server |
| `cd EuoraCraftLauncher-UI && pnpm build` | 构建前端到 `dist/` |
| `cd EuoraCraftLauncher-UI && pnpm lint` | 前端 ESLint 检查 |
| `cd EuoraCraftLauncher-UI && pnpm format` | 前端 Prettier 格式化 |
| `pyinstaller EuoraCraft-Launcher.spec` | 打包可执行文件 |
| `python-semantic-release version` | 自动更新版本号 |

### 打包发布

#### 1. 准备前端构建产物

```bash
cd EuoraCraftLauncher-UI
pnpm build
cd ..
```

#### 2. 写入生产环境变量

在项目根目录创建 `.env`：

```env
MICROSOFT_CLIENT_ID=你的微软客户端ID
```

#### 3. 执行打包

```bash
pyinstaller EuoraCraft-Launcher.spec
```

打包结果位于 `dist/EuoraCraft Launcher/`。

### 常见问题

#### 启动时提示缺少 `MICROSOFT_CLIENT_ID`

在 `.env` 或 `.env.dev` 中填写微软 OAuth 客户端 ID。该 ID 不会硬编码在源码中，必须通过环境变量提供。

#### 后端启动后窗口空白或报错 `not implemented`

这是 `pytauri-wheel` 的 `DirAssets::csp_hashes` 未实现导致的。当前解决方案是暂时不在 `Tauri.toml` 中配置 `csp` 字段。详细说明见历史 issue。

#### `pnpm install --frozen-lockfile` 在 CI 中提示找不到 package.json

表示 `FRONTEND_REPO` 仓库变量未设置，导致 CI 把后端仓库误检出到 `EuoraCraftLauncher-UI/`。请在 GitHub 仓库设置中添加 `FRONTEND_REPO` 变量，值为前端仓库名，例如 `ECLTeam/EuoraCraftLauncher-UI`。

#### 前端修改后没有热更新

确认 `FRONTEND_DEV_SERVER` 指向的地址与 `pnpm dev` 实际输出的地址一致，默认都是 `http://localhost:5173`。

### 开发规范

- 不要修改 `ECL/game/Core/` 目录下的文件。
- 后端非核心模块使用类封装。
- 异常处理使用具体异常类型，避免裸 `except Exception`。
- 前后端参数名保持一致，例如 `version_id` 不要写成 `version`。
- 插件命令统一通过 `backend.command('plugin_name:command')` 调用。

### 更多文档

- [后端开发文档](./docs/backend-dev-guide.md)
- [前端开发文档](./docs/frontend-dev-guide.md)
- [插件开发文档](./docs/plugin-dev-guide.md)
