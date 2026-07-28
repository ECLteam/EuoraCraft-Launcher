# 前端需要的后端命令（白话版）

这份文档不讲 TypeScript 类型语法，只说明：

1. 前端调用哪个命令；
2. 前端要传什么；
3. 后端成功时要返回什么；
4. 这个命令是做什么的。

当前一共有 **87 个命令**。

> 注意：`ECL/Api/frontend.py` 中的大多数命令目前只是临时接口，还没有真正的业务逻辑。本文写的是这些命令最终应该接收和返回的数据。

## 一、先看懂一次完整调用

前端调用 `accounts_add_offline`：

```ts
const result = await backend.command('accounts_add_offline', {
  username: 'Steve',
})
```

实际传给 Python 后端的 `body`：

```json
{
  "username": "Steve"
}
```

后端成功时返回：

```json
{
  "success": true,
  "data": {
    "id": "offline-steve",
    "alias": "Steve",
    "type": "offline",
    "uuid": "玩家 UUID",
    "isCurrent": true
  }
}
```

后端失败时统一返回：

```json
{
  "success": false,
  "message": "用户名不能为空",
  "errorCode": "INVALID_USERNAME"
}
```

本文中的规则：

- **不传参数**：前端直接调用命令，不需要准备内容。
- **必传**：缺少这个参数，后端应该返回失败。
- **可不传**：前端可以省略，后端使用默认值。
- **只看成功或失败**：成功时不需要返回具体数据，返回 `{"success": true}` 即可。
- 文档里的路径、版本号和账号只是示例，不是真实固定值。

---

## 二、基础命令（2 个）

### `ping`——检查前后端是否连通

前端不传参数。

后端返回：

```json
{
  "success": true,
  "data": {
    "status": "ok",
    "message": "正常"
  }
}
```

### `frontend_ready`——告诉后端“页面加载好了”

前端不传参数。后端收到后显示主窗口。

```json
{
  "success": true
}
```

`WebviewWindow` 是 PyTauri 自动交给后端的，前端不用传。

---

## 三、配置命令（5 个）

### 命令和参数

| 命令 | 前端传什么 | 后端做什么 |
| --- | --- | --- |
| `config_get` | 必传 `section`：配置分区名 | 读取一个配置分区 |
| `config_set` | 必传 `section` 和 `data` | 保存一个配置分区 |
| `config_list` | 不传参数 | 返回所有配置分区名 |
| `config_get_all` | 不传参数 | 返回全部配置 |
| `config_get_many` | 必传 `sections`：分区名数组 | 一次读取多个分区 |

常用分区名：`launcher`、`game`、`download`、`ui`、`locale`、`background`。

### `config_get` 示例

前端传：

```json
{
  "section": "game"
}
```

后端返回：

```json
{
  "success": true,
  "data": {
    "minecraft_paths": [
      {
        "name": "默认游戏目录",
        "path": "D:/Minecraft/.minecraft",
        "protected": false
      }
    ],
    "java_auto": true,
    "java_path": "C:/Java/bin/javaw.exe",
    "memory_auto": false,
    "memory_size": 4096,
    "game_width": 1280,
    "game_height": 720,
    "jvm_args": ["-XX:+UseG1GC"],
    "fullscreen": false,
    "last_install_path": "D:/Minecraft/.minecraft"
  }
}
```

不同分区的 `data` 内容不同：

```json
{
  "launcher": {
    "version": "0.1.1",
    "version_type": "dev",
    "debug": true,
    "is_dev": true
  },
  "download": {
    "mirror_source": "official",
    "download_threads": 16
  },
  "ui": {
    "locale": "zh-CN",
    "theme": {
      "mode": "dark",
      "primary_color": "#18a058",
      "blur_amount": 16,
      "sidebar_collapsed": false,
      "titlebar_hidden": false,
      "background_opacity": 0.8
    },
    "background": {
      "type": "custom",
      "path": "D:/Pictures/background.png",
      "opacity": 0.8,
      "blur": 4,
      "image_base64": "可不返回"
    }
  },
  "locale": {
    "locale": "zh-CN"
  }
}
```

### `config_set` 示例

```json
{
  "section": "download",
  "data": {
    "mirror_source": "official",
    "download_threads": 16
  }
}
```

保存成功只需返回：

```json
{
  "success": true
}
```

### 其他配置命令返回

`config_list`：

```json
{
  "success": true,
  "data": ["launcher", "game", "download", "ui"]
}
```

`config_get_many` 前端传：

```json
{
  "sections": ["launcher", "game", "download", "ui"]
}
```

`config_get_many` 和 `config_get_all` 返回：

```json
{
  "success": true,
  "data": {
    "launcher": {},
    "game": {},
    "download": {},
    "ui": {}
  }
}
```

其中每个 `{}` 应替换成对应分区的真实配置。

---

## 四、Java 命令（2 个）

| 命令 | 前端传什么 | 说明 |
| --- | --- | --- |
| `java_scan` | 不传参数 | 重新扫描电脑中的 Java |
| `java_list` | 不传参数 | 获取已经保存的 Java 列表 |

两个命令都返回 Java 数组：

```json
{
  "success": true,
  "data": [
    {
      "path": "C:/Program Files/Java/jdk-21/bin/javaw.exe",
      "version": "21.0.2",
      "major_version": 21,
      "java_type": "JDK",
      "arch": "x64",
      "sources": ["PATH", "注册表"]
    }
  ]
}
```

没有找到 Java 时，`data` 返回空数组 `[]`。

---

## 五、Minecraft 版本命令（10 个）

### 获取官方版本

#### `minecraft_versions`

前端可以不传 `filter_type`；传入时可以按版本类型筛选。

```json
{
  "filter_type": "release"
}
```

返回：

```json
{
  "success": true,
  "data": [
    {
      "id": "1.21.5",
      "type": "release",
      "releaseTime": "2025-03-25T12:00:00Z",
      "time": "2025-03-25T12:00:00Z",
      "url": "版本 JSON 地址"
    }
  ]
}
```

版本类型可能是：`release`、`snapshot`、`old_beta`、`old_alpha`、`april_fools`。

#### `minecraft_versions_classified`

前端不传参数。后端按类型返回版本数组：

```json
{
  "success": true,
  "data": {
    "all": [],
    "release": [
      {
        "id": "1.21.5",
        "type": "release",
        "releaseTime": "2025-03-25T12:00:00Z"
      }
    ],
    "snapshot": [],
    "april_fools": [],
    "old_beta": [],
    "old_alpha": []
  }
}
```

### 获取加载器版本

以下 5 个命令的参数和返回格式相同：

| 命令 | 加载器 |
| --- | --- |
| `fabric_versions` | Fabric |
| `forge_versions` | Forge |
| `neoforge_versions` | NeoForge |
| `optifine_versions` | OptiFine |
| `quilt_versions` | Quilt |

前端必须传游戏版本：

```json
{
  "game_version": "1.21.5"
}
```

后端返回：

```json
{
  "success": true,
  "data": [
    {
      "all": ["加载器版本 A", "加载器版本 B"],
      "stable": ["稳定版本"],
      "unstable": ["测试版本"]
    }
  ]
}
```

### 扫描本地版本

#### `scan_versions`

`path` 可以传一个路径，也可以传多个路径；也可以不传，让后端扫描默认目录。

```json
{
  "path": ["D:/Minecraft/.minecraft", "E:/Games/.minecraft"]
}
```

返回：

```json
{
  "success": true,
  "data": [
    {
      "id": "1.21.5-Fabric",
      "versionId": "1.21.5",
      "versionType": "release",
      "path": "D:/Minecraft/.minecraft/versions/1.21.5-Fabric",
      "displayName": "1.21.5 Fabric",
      "primaryLoader": "Fabric",
      "vanillaName": "1.21.5",
      "hasForge": false,
      "hasNeoForge": false,
      "hasFabric": true,
      "hasQuilt": false,
      "hasOptiFine": false,
      "isBroken": false,
      "jsonPath": "D:/Minecraft/.minecraft/versions/1.21.5-Fabric/1.21.5-Fabric.json",
      "sourceName": "默认游戏目录"
    }
  ]
}
```

### 安装和卸载版本

#### `install_version`

只有 `version_id` 必传，其他参数都可以不传。

```json
{
  "version_id": "1.21.5",
  "version_name": "我的 1.21.5",
  "loader_type": "Fabric",
  "task_id": "install-001",
  "fabric_version": "0.16.14",
  "forge_version": "可不传",
  "neoforge_version": "可不传",
  "optifine_version": "可不传",
  "optifine_type": "可不传",
  "optifine_patch": "可不传",
  "quilt_version": "可不传",
  "game_path": "D:/Minecraft/.minecraft",
  "download_threads": 16
}
```

安装成功只需返回 `{"success": true}`。安装进度通过事件发送，不放在本次返回值里。

#### `uninstall_version`

```json
{
  "version_id": "1.21.5-Fabric",
  "game_path": "D:/Minecraft/.minecraft"
}
```

`version_id` 必传，`game_path` 可不传。成功只需返回 `{"success": true}`。

---

## 六、账户命令（11 个）

### 账户对象长什么样

```json
{
  "id": "账户唯一标识",
  "alias": "显示名称",
  "type": "microsoft、offline 或 authlib",
  "email": "可不返回",
  "uuid": "可不返回",
  "isCurrent": true,
  "skinUrl": "可不返回",
  "auth_server": "Authlib 账户可返回"
}
```

### 查询账户

| 命令 | 前端传什么 | 后端返回什么 |
| --- | --- | --- |
| `accounts_list` | 不传参数 | `accounts` 账户数组和 `current` 当前账户 |
| `accounts_current` | 不传参数 | 当前账户；没有当前账户时返回 `null` |

`accounts_list` 返回：

```json
{
  "success": true,
  "data": {
    "accounts": [
      {
        "id": "offline-steve",
        "alias": "Steve",
        "type": "offline",
        "uuid": "玩家 UUID",
        "isCurrent": true
      }
    ],
    "current": {
      "id": "offline-steve",
      "alias": "Steve",
      "type": "offline",
      "uuid": "玩家 UUID",
      "isCurrent": true
    }
  }
}
```

### 添加账户

#### `accounts_add_offline`

```json
{
  "username": "Steve"
}
```

返回新建的账户对象。

#### `accounts_add_authlib`

以下三个参数全部必传：

```json
{
  "server_url": "https://example.com/api/yggdrasil",
  "email": "player@example.com",
  "password": "用户输入的密码"
}
```

返回登录成功后的账户对象。

### Microsoft 登录

#### `accounts_start_microsoft_login`

不传参数。可能返回：

```json
{
  "success": true,
  "data": {
    "status": "pending",
    "needs_client_id": false,
    "userCode": "ABCD-EFGH",
    "verificationUri": "https://microsoft.com/link",
    "message": "请在浏览器中输入代码",
    "interval": 5
  }
}
```

#### `accounts_poll_microsoft_login`

不传参数。返回：

```json
{
  "success": true,
  "data": {
    "status": "pending",
    "message": "等待用户授权",
    "retry_after": 5
  }
}
```

`status` 可能是 `pending`、`ready` 或 `error`。

#### `accounts_complete_microsoft_login`

不传参数。返回：

```json
{
  "success": true,
  "data": {
    "success": true,
    "account": {
      "id": "microsoft-account-id",
      "alias": "Player",
      "type": "microsoft",
      "email": "player@example.com",
      "uuid": "Minecraft UUID",
      "isCurrent": true
    },
    "message": "登录完成"
  }
}
```

### 修改账户

| 命令 | 前端传什么 | 成功时返回 |
| --- | --- | --- |
| `accounts_switch` | 必传 `account_id` | 只看成功或失败 |
| `accounts_remove` | 必传 `account_id` | 只看成功或失败 |
| `accounts_refresh_profile` | 必传 `account_id` | 只看成功或失败 |

参数示例：

```json
{
  "account_id": "microsoft-account-id"
}
```

### `authlib_servers`

不传参数，返回：

```json
{
  "success": true,
  "data": [
    {
      "name": "认证服务器名称",
      "url": "https://example.com/api/yggdrasil",
      "description": "服务器说明"
    }
  ]
}
```

---

## 七、用户协议命令（3 个）

| 命令 | 前端传什么 | 后端返回什么 |
| --- | --- | --- |
| `user_agreement_get` | 不传参数 | `accepted` 和 `uuid` |
| `user_agreement_save` | 必传 `accepted` 和 `uuid` | 保存后的 `accepted` 和 `uuid` |
| `user_agreement_clear` | 不传参数 | 只看成功或失败 |

保存时前端传：

```json
{
  "accepted": true,
  "uuid": "本次协议记录的唯一标识"
}
```

读取或保存成功时返回：

```json
{
  "success": true,
  "data": {
    "accepted": true,
    "uuid": "本次协议记录的唯一标识"
  }
}
```

---

## 八、图片和头像命令（4 个）

| 命令 | 前端传什么 | 用途 |
| --- | --- | --- |
| `image_fetch_data_url` | 必传 `url` | 把网络图片转换成前端可显示的数据 |
| `image_save_url` | 必传 `url` | 下载网络图片并返回本地路径 |
| `image_read_file` | 必传 `path` | 读取本地图片 |
| `avatar_data_url` | 必传 `uuid`，其他可不传 | 获取 Minecraft 头像 |

网络图片参数：

```json
{
  "url": "https://example.com/image.png"
}
```

本地图片参数：

```json
{
  "path": "D:/Pictures/image.png"
}
```

头像参数：

```json
{
  "uuid": "Minecraft UUID",
  "type_name": "microsoft",
  "custom_server": "可不传",
  "size": 128,
  "use_default_skin": true,
  "avatar_type": "可不传"
}
```

`image_fetch_data_url`、`image_read_file` 和 `avatar_data_url` 返回：

```json
{
  "success": true,
  "data": {
    "dataUrl": "data:image/png;base64,iVBORw0...",
    "base64": "iVBORw0..."
  }
}
```

`dataUrl` 和 `base64` 都可以不返回，但至少应该返回前端实际要使用的一个。

`image_save_url` 返回：

```json
{
  "success": true,
  "data": {
    "path": "D:/ECL_data/images/image.png"
  }
}
```

---

## 九、选择文件和打开目录（5 个）

| 命令 | 前端传什么 | 成功时 `data` |
| --- | --- | --- |
| `select_directory` | 不传参数 | `{ "path": "选择的目录" }` |
| `select_java` | 不传参数 | `{ "path": "选择的 javaw.exe" }` |
| `select_image` | 不传参数 | `{ "path": "图片路径", "base64": "图片内容" }` |
| `select_file` | 不传参数 | `{ "path": "选择的文件" }` |
| `open_folder` | 必传 `path` | 只看成功或失败 |

`open_folder` 参数：

```json
{
  "path": "D:/Minecraft/.minecraft"
}
```

用户取消选择时，后端可以返回失败并在 `message` 中写明“用户取消选择”。

---

## 十、游戏实例和日志（5 个）

### `instances_list`

不传参数，返回：

```json
{
  "success": true,
  "data": [
    {
      "id": "game-process-001",
      "name": "1.21.5 Fabric",
      "type": "minecraft",
      "isRunning": true,
      "version": "1.21.5"
    }
  ]
}
```

### `launch_instance`

只有 `version_id` 必传：

```json
{
  "version_id": "1.21.5-Fabric",
  "game_path": "D:/Minecraft/.minecraft",
  "java_path": "C:/Java/bin/javaw.exe",
  "memory": 4096,
  "width": 1280,
  "height": 720,
  "jvm_args": ["-XX:+UseG1GC"],
  "download_threads": 16
}
```

除 `version_id` 外都可以不传。成功只需返回 `{"success": true}`，启动进度通过事件发送。

### `cancel_launch`

不传参数。成功只需返回 `{"success": true}`。

### `instance_stop`

```json
{
  "instance_id": "game-process-001"
}
```

`instance_id` 必传。成功只需返回 `{"success": true}`。

### `export_logs`

`output_path` 可以不传：

```json
{
  "output_path": "D:/Desktop"
}
```

返回：

```json
{
  "success": true,
  "data": {
    "path": "D:/Desktop/ECL-logs.zip"
  }
}
```

---

## 十一、插件命令（12 个）

### 插件查询

#### `plugin_list`

不传参数，返回插件数组：

```json
{
  "success": true,
  "data": [
    {
      "name": "example-plugin",
      "title": "示例插件",
      "version": "1.0.0",
      "description": "插件说明",
      "author": "作者",
      "icon": "图标路径",
      "status": "enabled",
      "error": null,
      "dependencies": {
        "dependency-name": "1.0.0"
      },
      "events": {},
      "services": ["example-service"],
      "is_system": false
    }
  ]
}
```

#### `plugin_info`

```json
{
  "plugin_name": "example-plugin"
}
```

返回一个和上面数组元素相同的插件对象。

### 插件操作

| 命令 | 必传参数 | 可不传参数 | 成功时返回 |
| --- | --- | --- | --- |
| `plugin_enable` | `plugin_name` | 无 | 只看成功或失败 |
| `plugin_disable` | `plugin_name` | `force` | 只看成功或失败 |
| `plugin_unload` | `plugin_name` | 无 | 只看成功或失败 |
| `plugin_reload` | `plugin_name` | `cascade` | 只看成功或失败 |
| `plugin_install` | `plugin_path` | 无 | 只看成功或失败 |

启用、卸载插件时传：

```json
{
  "plugin_name": "example-plugin"
}
```

禁用插件时可以额外传 `force`：

```json
{
  "plugin_name": "example-plugin",
  "force": false
}
```

重新加载插件时可以额外传 `cascade`：

```json
{
  "plugin_name": "example-plugin",
  "cascade": false
}
```

安装插件时传：

```json
{
  "plugin_path": "D:/Downloads/example-plugin"
}
```

### 插件页面和插槽

#### `plugin_get_routes`

`plugin_id` 可以不传：

```json
{
  "plugin_id": "example-plugin"
}
```

返回：

```json
{
  "success": true,
  "data": [
    {
      "plugin": "example-plugin",
      "path": "/plugins/example",
      "title": "示例页面",
      "icon": "图标名称"
    }
  ]
}
```

#### `plugin_get_slots`

传空对象 `{}`，返回以插槽名称为键的对象：

```json
{
  "success": true,
  "data": {
    "game-page-header": [
      {
        "plugin": "example-plugin",
        "html": "<div>插件内容</div>",
        "priority": 10
      }
    ]
  }
}
```

### 插件命令和设置

#### `plugin_call_command`

```json
{
  "command": "example-plugin.do_something",
  "params": {
    "任意参数": "任意值"
  }
}
```

`command` 必传，`params` 可以不传。返回内容由插件自己决定：

```json
{
  "success": true,
  "data": "插件命令返回的任意内容"
}
```

#### `plugin_get_settings`

```json
{
  "plugin_name": "example-plugin"
}
```

返回：

```json
{
  "success": true,
  "data": {
    "schema": {
      "插件设置结构": "具体格式由插件系统决定"
    },
    "values": {
      "设置名称": "当前值"
    }
  }
}
```

#### `plugin_update_setting`

以下三个参数全部必传：

```json
{
  "plugin_name": "example-plugin",
  "key": "设置名称",
  "value": "新值，可以是任意 JSON 数据"
}
```

成功只需返回 `{"success": true}`。

---

## 十二、本地 Mod 管理（5 个）

### `get_mods`

`game_path` 可以不传：

```json
{
  "game_path": "D:/Minecraft/.minecraft"
}
```

返回：

```json
{
  "success": true,
  "data": [
    {
      "filename": "example-mod.jar",
      "name": "Example Mod",
      "version": "1.0.0",
      "author": "作者",
      "loader_type": "Fabric",
      "game_version": "1.21.5",
      "enabled": true
    }
  ]
}
```

### `toggle_mod`

```json
{
  "game_path": "D:/Minecraft/.minecraft",
  "filename": "example-mod.jar"
}
```

两个参数都必传。返回切换后的状态：

```json
{
  "success": true,
  "data": {
    "enabled": false
  }
}
```

### `add_mod`

```json
{
  "game_path": "D:/Minecraft/.minecraft",
  "source_path": "D:/Downloads/example-mod.jar"
}
```

两个参数都必传。返回复制后的文件名：

```json
{
  "success": true,
  "data": {
    "filename": "example-mod.jar"
  }
}
```

### `remove_mod`

```json
{
  "game_path": "D:/Minecraft/.minecraft",
  "filename": "example-mod.jar"
}
```

两个参数都必传。成功只需返回 `{"success": true}`。

### `open_mods_folder`

```json
{
  "game_path": "D:/Minecraft/.minecraft"
}
```

返回：

```json
{
  "success": true,
  "data": {
    "path": "D:/Minecraft/.minecraft/mods"
  }
}
```

---

## 十三、整合包、资源包、光影和存档（12 个）

### 整合包

#### `detect_modpack_type`

```json
{
  "file_path": "D:/Downloads/example-modpack.zip"
}
```

返回：

```json
{
  "success": true,
  "data": {
    "type": "curseforge",
    "其他信息": "后端可以按整合包类型增加字段"
  }
}
```

#### `import_modpack`

只有 `file_path` 必传：

```json
{
  "file_path": "D:/Downloads/example-modpack.zip",
  "game_path": "D:/Minecraft/.minecraft",
  "version_name": "我的整合包",
  "download_threads": 16
}
```

成功只需返回 `{"success": true}`。

#### `export_modpack`

所有参数都可以不传：

```json
{
  "game_path": "D:/Minecraft/.minecraft",
  "output_path": "D:/Desktop/example-modpack.zip",
  "format": "curseforge",
  "name": "示例整合包",
  "version": "1.0.0",
  "author": "作者"
}
```

成功只需返回 `{"success": true}`。

### 查询资源

| 命令 | 前端传什么 | 返回什么 |
| --- | --- | --- |
| `list_resourcepacks` | 可不传 `game_path` | 资源包数组 |
| `list_shaderpacks` | 可不传 `game_path` | 光影包数组 |
| `list_saves` | 可不传 `game_path` | 存档数组 |

返回示例：

```json
{
  "resourcepacks": [
    {
      "filename": "resourcepack.zip",
      "name": "资源包名称",
      "description": "资源包说明",
      "format": 34
    }
  ],
  "shaderpacks": [
    {
      "filename": "shaderpack.zip",
      "name": "光影包名称"
    }
  ],
  "saves": [
    {
      "name": "New World",
      "lastPlayed": "最后游玩时间",
      "gameMode": "survival"
    }
  ]
}
```

这里为了节省篇幅放在一个对象中展示。实际调用时，每个命令都使用标准格式，例如：

```json
{
  "success": true,
  "data": [
    {
      "filename": "resourcepack.zip",
      "name": "资源包名称",
      "description": "资源包说明",
      "format": 34
    }
  ]
}
```

### 删除资源

| 命令 | 必传参数 | 成功时返回 |
| --- | --- | --- |
| `remove_resourcepack` | `game_path`、`filename` | 只看成功或失败 |
| `remove_shaderpack` | `game_path`、`filename` | 只看成功或失败 |
| `delete_save` | `game_path`、`save_name` | 只看成功或失败 |

删除资源包或光影包：

```json
{
  "game_path": "D:/Minecraft/.minecraft",
  "filename": "resourcepack.zip"
}
```

删除存档：

```json
{
  "game_path": "D:/Minecraft/.minecraft",
  "save_name": "New World"
}
```

### 打开资源目录

| 命令 | 必传参数 | 成功时返回 |
| --- | --- | --- |
| `open_resourcepacks_folder` | `game_path` | 只看成功或失败 |
| `open_shaderpacks_folder` | `game_path` | 只看成功或失败 |
| `open_saves_folder` | `game_path` | 只看成功或失败 |

参数格式相同：

```json
{
  "game_path": "D:/Minecraft/.minecraft"
}
```

---

## 十四、在线 Mod（4 个）

### `search_mods`

只有 `query` 必传：

```json
{
  "query": "sodium",
  "source": "modrinth",
  "game_version": "1.21.5",
  "loader_type": "fabric",
  "limit": 20,
  "offset": 0
}
```

返回：

```json
{
  "success": true,
  "data": [
    {
      "id": "mod-id",
      "slug": "sodium",
      "title": "Sodium",
      "description": "Mod 简介",
      "author": "作者",
      "icon_url": "图标地址",
      "downloads": 1000000,
      "follows": 50000,
      "date_modified": "更新时间",
      "source": "modrinth"
    }
  ]
}
```

### `get_mod_info`

两个参数都必传：

```json
{
  "mod_id": "mod-id",
  "source": "modrinth"
}
```

返回：

```json
{
  "success": true,
  "data": {
    "id": "mod-id",
    "slug": "sodium",
    "title": "Sodium",
    "description": "完整介绍",
    "author": "作者",
    "icon_url": "图标地址",
    "source": "modrinth",
    "loaders": ["fabric", "quilt"],
    "game_versions": ["1.21.5"],
    "其他字段": "不同平台可以增加其他信息"
  }
}
```

### `get_mod_versions`

`mod_id` 和 `source` 必传，另外两个可以不传：

```json
{
  "mod_id": "mod-id",
  "source": "modrinth",
  "game_version": "1.21.5",
  "loader_type": "fabric"
}
```

返回：

```json
{
  "success": true,
  "data": [
    {
      "id": "mod-version-id",
      "version_number": "1.0.0",
      "game_versions": ["1.21.5"],
      "loaders": ["fabric"],
      "download_url": "文件下载地址",
      "filename": "sodium.jar",
      "date_published": "发布时间"
    }
  ]
}
```

### `download_mod`

前四个参数必传，`filename` 可以不传：

```json
{
  "mod_id": "mod-id",
  "source": "modrinth",
  "version_id": "mod-version-id",
  "game_path": "D:/Minecraft/.minecraft",
  "filename": "sodium.jar"
}
```

成功只需返回 `{"success": true}`。下载进度应通过事件发送。

---

## 十五、启动器信息（3 个）

### `launcher_info`

不传参数，返回：

```json
{
  "success": true,
  "data": {
    "version": "0.1.1",
    "version_type": "dev"
  }
}
```

### `info_card_get`

不传参数，返回：

```json
{
  "success": true,
  "data": {
    "mode": "auto",
    "tips": ["可以在设置中调整游戏内存"],
    "announcements": [
      {
        "title": "公告标题",
        "date": "2026-07-22",
        "content": "公告内容"
      }
    ],
    "welcome": {
      "title": "欢迎使用 ECL",
      "content": "欢迎内容"
    },
    "interval": 10
  }
}
```

`mode` 可以是：

- `auto`：自动决定；
- `rotate`：轮播；
- `announcement_first`：公告优先；
- `tip_only`：只显示提示；
- `announcement_only`：只显示公告。

`welcome` 和 `interval` 可以不返回，`welcome` 也可以是 `null`。

### `list_sections`

不传参数，返回：

```json
{
  "success": true,
  "data": ["launcher", "game", "download", "ui"]
}
```

---

## 十六、文件系统和路径（4 个）

### `fs_read_dir`

```json
{
  "path": "D:/Minecraft/.minecraft/mods"
}
```

返回：

```json
{
  "success": true,
  "data": [
    {
      "name": "example-mod.jar",
      "is_dir": false,
      "size": 1024000,
      "mtime": 1784692800
    }
  ]
}
```

### `fs_read_file`

`path` 必传，`mode` 可以不传。`mode` 只能是 `text` 或 `base64`。

```json
{
  "path": "D:/ECL/config.json",
  "mode": "text"
}
```

返回：

```json
{
  "success": true,
  "data": {
    "content": "文件文本或 Base64 内容",
    "size": 1024
  }
}
```

### `fs_exists`

```json
{
  "path": "D:/Minecraft/.minecraft"
}
```

返回：

```json
{
  "success": true,
  "data": {
    "exists": true,
    "is_dir": true,
    "is_file": false
  }
}
```

### `file_resolve`

```json
{
  "path": "D:/Pictures/avatar.png"
}
```

返回规整后的路径：

```json
{
  "success": true,
  "data": {
    "path": "D:/Pictures/avatar.png"
  }
}
```

---

## 十七、后端实现时最重要的检查清单

实现每条命令时，只需要逐项确认：

1. 方法名称和本文命令名称完全一致；
2. 从 `body` 中读取本文写明的参数；
3. 缺少必传参数时返回 `success: false`；
4. 成功时返回 `success: true`；
5. `data` 的字段名和本文示例一致；
6. 在 `ECL/Adapters/adapter.py` 的 `_api()` 中注册该方法。

后端方法示例：

```python
async def accounts_add_offline(self, body: dict[str, Any]) -> dict[str, Any]:
    """
    添加离线账户
    :param body: 包含 username 的请求参数
    :return: 新建的离线账户
    """
    username = body.get("username")
    if not username:
        return {
            "success": False,
            "message": "用户名不能为空",
            "errorCode": "INVALID_USERNAME",
        }

    account_data = {
        "id": "临时账户 ID",
        "alias": username,
        "type": "offline",
        "uuid": "临时 UUID",
        "isCurrent": True,
    }
    return {"success": True, "data": account_data}
```

注册命令：

```python
self.commands.command("accounts_add_offline")(
    self.fronteanapi_instance.accounts_add_offline
)
```
