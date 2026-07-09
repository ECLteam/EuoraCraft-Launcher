# EuoraCraft Launcher 前端开发文档

## 项目概览

EuoraCraft Launcher 前端基于 **Vue 3.5 + TypeScript 5.7**，使用 **Vite 7.2** 构建，通过 **PyTauri IPC** 与后端通信。前端采用 **Composition API + 组合式函数** 架构，使用 **Tailwind CSS 4.2** 和 **Naive UI 2.41** 构建 UI，通过 **vue-i18n 10** 实现中英文国际化。

仓库地址：`https://github.com/Wuchang325/EuoraCraftLauncher-UI`

---

## 环境搭建

### 前置要求

| 工具 | 最低版本 | 说明 |
|------|----------|------|
| Node.js | 18+ | 运行时 |
| pnpm | 11.10 | 包管理器 |

### 安装步骤

```bash
git clone https://github.com/ECLTeam/EuoraCraftLauncher-UI.git
cd EuoraCraftLauncher-UI
pnpm install
```

> 前端为独立仓库，需克隆到后端主仓库目录内（`ECLTeam/EuoraCraftLauncher-UI/`），开发时在此目录操作。

### 启动开发模式

```bash
pnpm dev          # 启动 Vite dev server（默认 http://localhost:5173）
pnpm build        # TypeScript 检查 + Vite 构建
pnpm lint         # ESLint 代码检查
pnpm format       # Prettier 格式化
```

开发时需同时启动后端（`python main.py`），后端会自动连接前端 dev server。

---

## 技术栈

| 技术 | 版本 | 用途 |
|------|------|------|
| Vue | 3.5.26 | 前端框架（Composition API） |
| TypeScript | 5.7.3 | 类型系统 |
| Vite | 7.2.4 | 构建工具 |
| Tailwind CSS | 4.2.0 | Atomic CSS 框架 |
| Naive UI | 2.41.0 | 组件库（对话框、通知、表单等） |
| vue-router | 4.6.4 | 路由管理 |
| vue-i18n | 10.0.7 | 国际化 |
| GSAP | 3.12.7 | 高性能动画引擎 |
| Sass | 1.97.1 | CSS 预处理器 |

---

## 项目结构

```
src/
├── api/
│   └── client.ts          # 统一 API 客户端（config / command / event / fs）
├── components/
│   ├── layout/
│   │   ├── SideBar.vue     # 侧边栏导航
│   │   └── TitleBar.vue    # 顶部标题栏（窗口拖拽区）
│   ├── modals/
│   │   └── ContentModal.vue # 通用全屏模态框组件
│   ├── settings/
│   │   ├── AboutTab.vue     # 关于页面
│   │   ├── DownloadTab.vue  # 下载设置
│   │   ├── GameTab.vue      # 游戏设置
│   │   ├── GeneralTab.vue   # 通用设置（含 Keyring 管理）
│   │   └── PluginSettingsTab.vue
│   ├── ui/
│   │   ├── Button.vue       # 按钮组件
│   │   ├── Card.vue         # 卡片组件
│   │   ├── Icon.vue         # 图标组件（Iconify）
│   │   ├── Input.vue        # 输入框组件
│   │   ├── Select.vue       # 下拉选择组件
│   │   └── GlassMessage.vue # 毛玻璃消息提示
│   ├── versions/
│   │   ├── ManageTab.vue    # 版本管理（已安装列表）
│   │   ├── VersionsTab.vue  # 版本安装（在线列表）
│   │   ├── VersionDetailModal.vue
│   │   └── ModsTab.vue      # Mod 管理
│   ├── SkinRenderer.vue     # 3D 皮肤渲染器
│   └── TaskQueuePanel.vue   # 任务队列面板
├── composables/             # 组合式函数（核心业务逻辑）
│   ├── useAccountManager.ts # 账户管理
│   ├── useVersionManager.ts # 版本管理
│   ├── useTaskQueue.ts      # 任务队列
│   ├── useTheme.ts          # 主题管理
│   ├── usePluginBridge.ts   # 插件桥接
│   ├── useLaunchProgress.ts # 启动进度
│   ├── useUserAgreement.ts  # 用户协议
│   ├── useFullscreenModal.ts # 全屏弹窗栈
│   ├── useGlassMessage.ts   # 毛玻璃消息
│   ├── useAnimation.ts      # 动画管理
│   └── useAvatarRenderer.ts # 头像渲染
├── i18n/
│   ├── index.ts             # vue-i18n 初始化
│   └── locales/
│       ├── zh-CN.json       # 中文翻译
│       └── en-US.json       # 英文翻译
├── plugin-sdk/              # 插件 SDK（第三方插件开发用）
│   ├── api.ts               # 命令调用、配置存取、文件操作
│   ├── events.ts            # 事件监听系统
│   ├── ui.ts                # 纯 DOM UI 工具
│   ├── types.ts             # 类型定义
│   └── transpile.ts         # TypeScript 转译
├── router/
│   └── index.ts             # Vue Router 配置（Hash 模式）
├── styles/
│   ├── main.css             # 主样式（Tailwind @source/@theme）
│   ├── animations.css       # 动画关键帧
│   ├── common.css           # 公共样式变量
│   ├── ContentModal.css     # 模态框样式
│   └── Versions.css         # 版本页面样式
├── types/
│   ├── api.ts               # API 响应类型定义
│   └── global.d.ts          # 全局类型声明
├── utils/
│   ├── loader.ts            # 统一加载器常量
│   └── constants.ts         # 通用常量
├── views/                   # 页面级组件
│   ├── Game.vue             # 主页（游戏启动）
│   ├── Settings.vue         # 设置页面
│   ├── Versions.vue         # 版本页面
│   ├── Plugins.vue          # 插件管理
│   ├── OnlineMods.vue       # 在线 Mod 搜索
│   ├── DevTools.vue         # 开发者工具（仅 dev 模式）
│   └── Instances.vue        # 实例管理
├── App.vue                  # 根组件
└── main.ts                  # 入口文件
```

---

## 架构设计

### 状态管理

项目不使用 Pinia 或 Vuex，所有状态管理基于 **模块级响应式状态共享**（全局单例模式）：

```typescript
// composables/useTaskQueue.ts
const tasks = ref<TaskItem[]>([])      // 模块顶层定义
const panelVisible = ref(false)        // 模块顶层定义

export function useTaskQueue() {
  return {
    tasks: readonly(tasks),            // 只读暴露
    panelVisible,
    addTask(task) { ... },
    removeTask(id) { ... },
    // ...
  }
}

// 多个组件共享同一状态
export const globalTaskQueue = useTaskQueue()
```

这种模式的优势：
- 无需引入额外状态管理库
- 模块级 ref 天然支持 Vue 响应式
- 多个组件实例间自动同步

### 返回 reactive() 包装

关键 composable 返回 `reactive()` 对象而非解构，确保 Vue 3 模板中嵌套 ref 自动解包：

```typescript
// useAccountManager.ts
export function useAccountManager(t: TFunction) {
  const accounts = ref<Account[]>([])
  const currentAccount = ref<Account | null>(null)
  // ...

  return reactive({
    accounts,
    currentAccount,
    // 模板中可直接用 account.accounts、account.currentAccount
    // 无需 .value
  })
}
```

### 后端驱动通信

前端采用 **后端驱动** 模式：前端调用 `frontend_ready` 后，后端主动推送所有初始状态：

```typescript
// App.vue onMounted
onMounted(async () => {
  await backend.command('frontend_ready')
  // 后端响应式推送 config:init、launcher:notify 等事件
  // 前端被动接收并更新 UI
})
```

---

## 核心模块详解

### API 客户端 (client.ts)

前端与后端通信的唯一入口，提供类型安全的 API 封装：

```typescript
import { backend } from '@/api/client'

// 配置存取
backend.config.get('game')                    // Promise<ApiResponse<GameConfig>>
backend.config.set('ui', { locale: 'en-US' }) // Promise<ApiResponse<null>>

// 命令调用
backend.command('ping')                       // Promise<ApiResponse<string>>
backend.command('install_version', { version_id: '...', ... })

// 事件监听（返回同步清理函数）
const unlisten = backend.on('game:launch_progress', (payload) => {
  console.log(payload.phase, payload.percent)
})
// 组件卸载时调用
onUnmounted(() => unlisten())

// 取消事件监听
backend.off('game:launch_progress', handler)  // 取消特定处理器
backend.off('game:launch_progress')           // 取消全部
```

关键设计：
- **IPC 超时**：`invokeWithTimeout` 默认 30 秒超时
- **事件桥接**：`on()` 内部通过闭包将异步 `Promise<() => void>` 转为同步 `() => void` 返回
- **类型安全**：`CommandMap` 接口定义所有命令的参数和返回值类型

### 组合式函数

#### useAccountManager

账户管理，包含微软 OAuth 登录、离线账户、Authlib 外置登录：

```typescript
import { useAccountManager } from '@/composables/useAccountManager'

const { t } = useI18n()
const account = useAccountManager(t)

// 响应式状态
account.accounts           // Ref<Account[]>
account.currentAccount     // Ref<Account | null>
account.accountsLoading    // Ref<boolean>

// 方法
account.loadAccounts()     // 从后端拉取账户列表
account.addOfflineAccount() // 添加离线账户
account.startMicrosoftLogin() // 启动微软登录（设备码流程）
account.completeMicrosoftLogin() // 完成微软登录
account.switchAccount(id)  // 切换账户
account.removeAccount(id, alias) // 删除账户
account.addAuthlibAccount() // 添加外置登录
```

微软登录流程：`startMicrosoftLogin()` -> 轮询 `pollLoginStatus()` -> `completeMicrosoftLogin()`。轮询使用 `isPolling` 布尔锁防重入，`onScopeDispose` 自动清理。

#### useVersionManager

版本管理，负责版本列表加载和游戏启动：

```typescript
import { useVersionManager } from '@/composables/useVersionManager'

const version = useVersionManager(t)

version.versions           // 版本列表（全局共享）
version.selectedVersion    // 当前选中版本（全局共享）
version.launching          // 启动中
version.statusMsg          // 状态消息（5 秒自动消失）

version.loadVersions(gamePath?)  // 加载版本列表
version.selectVersion(id)  // 选中版本
version.launchGame(currentAccount) // 启动游戏
```

启动流程：校验 -> 路由跳转 -> 显示进度 -> 监听 `game:launch_progress` 事件 -> 调用 `launch_instance` -> 根据 phase 映射进度百分比（3~95%）。

#### useTaskQueue

全局任务队列，管理安装/下载任务：

```typescript
import { useTaskQueue } from '@/composables/useTaskQueue'

const queue = useTaskQueue()

queue.tasks          // DeepReadonly<Ref<TaskItem[]>>
queue.activeCount    // 活跃任务数
queue.panelVisible   // 面板显隐
queue.hasActiveTasks // 是否有活跃任务

queue.addTask({ type: 'install', name: '安装 1.20.4', ... })  // 返回 taskId
queue.updateTask(taskId, { progress: 50, message: '下载中...' })
queue.addSubtask(taskId, { name: '下载原版', status: 'running' })
queue.removeTask(taskId)
queue.clearCompleted()
```

TaskItem 类型：`{ id, type, name, status, progress, message, subtasks, expanded, timestamp }`。Subtask 类型：`{ id, name, status, message }`。

#### useTheme

主题管理，控制亮色/暗色模式、主题色、背景图等：

```typescript
import { useTheme } from '@/composables/useTheme'

const theme = useTheme()

theme.themeMode        // 'light' | 'dark' | 'system'
theme.primaryColor     // 主题色 hex
theme.isDark           // 当前是否为暗色
theme.naiveTheme       // NaiveUI 主题对象
theme.sidebarCollapsed // 侧边栏折叠

theme.toggleTheme()    // 切换亮暗
theme.setThemeMode('system')
theme.setPrimaryColor('#4A7FD9')
```

主题系统特性：
- 双主题色系（亮色/暗色分别定义背景、文字、边框颜色）
- CSS 变量注入：`updateTheme()` 将颜色写入 `document.documentElement.style`
- 系统主题监听：`window.matchMedia('(prefers-color-scheme: dark)')`
- 防抖保存：`saveThemeConfig()` 100ms 防抖，通过 `backend.config.set('ui', ...)` 持久化
- 初始化防重：`initTheme()` 缓存 Promise

#### usePluginBridge

插件桥接，管理插件路由、HTML 插槽、脚本注入：

```typescript
import { initPluginBridge, destroyPluginBridge, callPluginCommand } from '@/composables/usePluginBridge'

// 初始化（在 App.vue 中调用）
initPluginBridge(app, router)

// 调用插件命令
await callPluginCommand('my_plugin:do_something', { param: 'value' })

// 清理
destroyPluginBridge()
```

导出响应式状态：`pluginRoutes`（插件路由）、`pluginSlots`（HTML 插槽）、`pluginCommands`（插件命令）。

安全措施：`sanitizeHtml()` 移除 `<script>`、内联事件处理器、`javascript:` 协议、`<iframe>`/`<object>`/`<embed>` 标签。

#### useLaunchProgress

启动进度管理，提供平滑动画进度条：

```typescript
import { useLaunchProgress } from '@/composables/useLaunchProgress'

const progress = useLaunchProgress()

progress.progress.percent    // 0-100
progress.progress.stage      // 当前阶段文本
progress.smoothPercent       // 平滑动画后的百分比

progress.show({ cancelable: true })
progress.setProgress(50, 'downloading', '下载中...')
progress.setStage('preparing')
progress.cancel()
progress.hide()
```

动画使用 `requestAnimationFrame` + ease-out 插值（每帧 15% 剩余距离，最低步长 0.3），100% 时直接跳转。取消后忽略后续更新。

#### useFullscreenModal

全屏弹窗栈管理：

```typescript
import { useFullscreenModal } from '@/composables/useFullscreenModal'

const modal = useFullscreenModal()

modal.isVisible   // 是否有弹窗显示
modal.title       // 当前弹窗标题

modal.open('设置', onCloseCallback)  // 推入栈顶
modal.close()     // 弹出栈顶
modal.reset()     // 清空所有弹窗
```

栈式管理支持嵌套全屏弹窗，`onClose` 回调仅在 `close()` 时触发一次。

#### useUserAgreement

用户协议管理：

```typescript
import { useUserAgreement } from '@/composables/useUserAgreement'

const agreement = useUserAgreement()

agreement.isAccepted   // 是否已接受协议
agreement.isLoading    // 保存中
agreement.agreementUrl // 协议 URL

agreement.acceptUserAgreement()  // 接受协议
agreement.rejectUserAgreement()  // 拒绝协议
```

### 路由设计

使用 Hash 模式（`createWebHashHistory`），适配桌面端文件协议：

| 路径 | 组件 | 说明 |
|------|------|------|
| `/` | Game.vue | 主页（游戏启动） |
| `/versions/manage` | ManageTab.vue | 版本管理 |
| `/versions/versions` | VersionsTab.vue | 版本安装 |
| `/plugins` | Plugins.vue | 插件管理 |
| `/online-mods` | OnlineMods.vue | 在线 Mod 搜索 |
| `/settings/general` | GeneralTab.vue | 通用设置 |
| `/settings/download` | DownloadTab.vue | 下载设置 |
| `/settings/game` | GameTab.vue | 游戏设置 |
| `/settings/plugins` | PluginSettingsTab.vue | 插件设置 |
| `/settings/about` | AboutTab.vue | 关于 |
| `/dev` | DevTools.vue | 开发者工具（仅 dev 模式） |
| `/:pathMatch(.*)*` | 404 | 未匹配路由 |

导航守卫：`canNavigate()` 检查用户协议是否已接受，未接受则弹出警告。

### 国际化 (i18n)

使用 `vue-i18n`，支持 `zh-CN` 和 `en-US`：

```typescript
// 组件中使用
const { t } = useI18n()
t('game.launch')  // "启动游戏" 或 "Launch"

// 程序化切换
import { setLocale } from '@/i18n'
await setLocale('en-US')
```

语言检测优先级：
1. 后端 `config:init` 事件推送的 `ui.locale`
2. 浏览器 `navigator.language` 自动检测
3. 默认 `zh-CN`

翻译文件位于 `src/i18n/locales/zh-CN.json` 和 `en-US.json`。添加新翻译时两个文件需同步更新。

### 组件设计

#### 布局组件

- **SideBar.vue**：侧边栏导航，支持折叠/展开、子菜单、活动指示器动画、插件路由动态渲染
- **TitleBar.vue**：顶部标题栏，窗口拖拽区域

#### 通用组件

- **ContentModal.vue**：全屏模态框，使用 `align-items: stretch; width: 100%; height: 100%` 铺满内容区
- **Button.vue**：按钮组件，支持 variant/disabled/loading 状态
- **Card.vue**：卡片组件，支持 interactive 模式
- **Icon.vue**：Iconify 图标封装
- **Input.vue**：输入框组件
- **Select.vue**：下拉选择组件
- **GlassMessage.vue**：毛玻璃消息提示

#### 业务组件

- **TaskQueuePanel.vue**：任务队列面板，支持展开/折叠、进度条、子任务列表
- **SkinRenderer.vue**：3D 皮肤渲染器
- **ManageTab.vue**：版本管理（已安装列表）
- **VersionsTab.vue**：版本安装（在线列表，支持滚动加载、RAF 节流）

---

## 样式系统

### Tailwind CSS v4

使用 Tailwind CSS v4 的新指令系统：

```css
/* src/styles/main.css */
@import "tailwindcss";

@source "../../index.html";
@source "../**/*.{vue,js,ts,jsx,tsx}";

@custom-variant dark (&:where([data-theme="dark"], [data-theme="dark"] *));

@theme {
  --color-primary: #4A7FD9;
  --color-primary-rgb: 74 127 217;
  /* ... */
}
```

关键变更（v3 -> v4）：
- 不再需要 `tailwind.config.js`（已删除）
- 使用 `@source` 指令声明扫描路径
- 使用 `@theme` 声明自定义设计令牌
- 使用 `@custom-variant` 声明自定义变体

### CSS 变量

主题色通过 CSS 变量注入，实现动态主题切换：

```css
:root {
  --primary: #4A7FD9;
  --primary-rgb: 74, 127, 217;
  --primary-hover: #3A6FC9;
  --primary-pressed: #2A5FB9;
  /* 暗色变量 */
  --bg: #0d1117;
  --bg2: #161b22;
  --ink: #e6edf3;
  --rule: #30363d;
}
```

### Naive UI 主题复写

`useTheme` 中的 `createThemeOverrides()` 生成完整的 NaiveUI 主题复写，覆盖 Common、Button、Card、Input、Select、Switch、Slider、Tooltip、Dropdown、Menu 组件。

---

## 插件 SDK

`plugin-sdk/` 目录为插件开发者提供类型安全的 API 封装：

### api.ts

```typescript
import { callCommand, getSettings, updateSetting, getConfig, setConfig } from '@/plugin-sdk/api'

// 调用插件命令
await callCommand('my_command', { param: 'value' })

// 插件设置
await getSettings('my_plugin')
await updateSetting('my_plugin', 'api_key', 'new_value')

// 启动器配置
await getConfig('game')
await setConfig('ui', { locale: 'en-US' })

// Minecraft 版本
await getMinecraftVersions('release')
await scanVersions('/path/to/.minecraft')
await installVersion({ version_id: '1.20.4', ... })

// Java 管理
await scanJava()
await getJavaList()

// 账户
await getAccounts()
await getCurrentAccount()

// 文件操作
await readDir('/path/to/dir')
await readFile('/path/to/file', 'text')
await exists('/path/to/file')
await selectDirectory()
await selectImage()
```

### events.ts

```typescript
import { listen, unlisten, cleanup, Events } from '@/plugin-sdk/events'

// 监听事件
const unlisten = listen(Events.PLUGIN_ENABLED, (payload) => {
  console.log('插件已启用', payload.plugin)
})

// 取消监听
unlisten()  // 取消特定监听
unlisten(Events.PLUGIN_ENABLED, 'my-key')  // 按 key 取消
cleanup()   // 移除所有监听
```

事件常量：`PLUGIN_ENABLED`、`PLUGIN_DISABLED`、`SETTINGS_CHANGED`、`ROUTE_REGISTERED`、`HTML_INJECTED`、`SCRIPT_INJECTED`、`TYPESCRIPT_INJECTED`、`SLOTS_CLEARED`、`PRE_UNLOAD`、`CLEANUP`、`LAUNCHER_NOTIFY` 等。

### ui.ts

纯 DOM 操作 UI 工具，不依赖 Vue 组件：

```typescript
import { $, showToast, showConfirm, showLoading, showEmpty, getSlot, clearSlot } from '@/plugin-sdk/ui'

// 创建元素
const div = $.div({ class: 'my-class', text: 'Hello' })
const btn = $.button({ class: 'btn', text: 'Click', events: { click: () => {} } })

// Toast 通知
showToast('操作成功', 'success', 3000)

// 确认对话框
const confirmed = await showConfirm('确认删除', '此操作不可撤销')

// 加载指示器
const removeLoading = showLoading(container, '加载中...')

// 插槽操作
const slot = getSlot('page-bottom')
clearSlot('page-bottom')
```

### types.ts

类型定义：`ApiResponse<T>`、`PluginInfo`、`PluginSettingsSchema`、`PluginRoute`、`GameVersion`、`JavaInfo`、`AccountInfo`、`ModInfo`、`OnlineModResult`、`DownloadProgress` 等。

---

## 开发规范

### 代码风格

1. **后端驱动**：前端调用 `frontend_ready` 后，后端推送所有初始状态
2. **事件清理**：所有 `backend.on()` 在 `onUnmounted` 中通过 try-finally 清理
3. **统一 API**：使用 `backend.command()`，不直接调用插件接口
4. **参数命名**：前后端参数名必须精确匹配（`version_id`，非 `versionId`）
5. **reactive() 包装**：关键 composable 返回 `reactive()` 确保模板中 ref 自动解包

### UI 约定

1. **全屏弹窗**：使用 `align-items: stretch; width: 100%; height: 100%` 铺满内容区，内容最大宽度 860px 居中
2. **紧凑布局**：账户列表 48px 行高，任务列表 42px 行高，8px 卡片圆角
3. **水平布局**：相关内容区域使用水平排列（如关于页面的 logo + 标题）
4. **进度动画**：使用 `requestAnimationFrame` 实现平滑进度条，避免突兀跳变

### 安全

1. **XSS 防护**：插件注入的 HTML 经过 `sanitizeHtml()` 过滤
2. **postMessage 安全**：iframe 通信使用指定 origin，不使用 `'*'`

### Tailwind v4

1. 使用 `@source` 指令声明扫描路径
2. 使用 `@theme` 声明自定义设计令牌
3. 使用 `@custom-variant dark` 声明暗色变体
4. 不再使用 `tailwind.config.js`

---

## 构建与部署

### 构建命令

```bash
pnpm build     # TypeScript 检查 + Vite 构建 -> dist/
pnpm lint      # ESLint 代码检查
pnpm format    # Prettier 格式化
```

### Vite 配置

```typescript
// vite.config.ts
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      'vue': 'vue/dist/vue.esm-bundler.js',
    },
  },
  build: {
    sourcemap: false,
  },
})
```

### 多平台 CI

前端构建在 GitHub Actions 中独立运行（`build-frontend` job），构建产物上传为 artifact，后续各平台后端构建 job 下载并打包。

---

## 常用操作

### 添加新页面

1. 在 `src/views/` 创建 `.vue` 文件
2. 在 `src/router/index.ts` 添加路由配置
3. 在 `src/components/layout/SideBar.vue` 的 `MENU_ITEMS` 中添加导航项（如需要）
4. 在 `src/i18n/locales/zh-CN.json` 和 `en-US.json` 中添加翻译

### 添加新 composable

1. 在 `src/composables/` 创建 `.ts` 文件
2. 使用模块级 ref 实现全局状态共享
3. 返回 `reactive()` 对象（如包含嵌套 ref）
4. 在 `onScopeDispose` 中清理事件监听器

### 添加新翻译

1. 在 `src/i18n/locales/zh-CN.json` 中添加中文翻译
2. 在 `src/i18n/locales/en-US.json` 中添加对应英文翻译
3. 组件中使用 `t('key.path')` 引用

### 调用后端 API

```typescript
import { backend } from '@/api/client'

// 命令调用
const result = await backend.command('my_command', { param: 'value' })
if (result.success) {
  // 处理 result.data
}

// 事件监听
const unlisten = backend.on('my_event', (payload) => {
  // 处理 payload
})
onUnmounted(() => unlisten())
```

### 打开全屏弹窗

```typescript
const modal = useFullscreenModal()
modal.open('弹窗标题', () => {
  // 弹窗关闭时的回调
})
// 弹窗内容通过插槽或路由渲染
modal.close()
```