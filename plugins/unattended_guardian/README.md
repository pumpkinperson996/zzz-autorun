# 无人值守安全守护 / Unattended Guardian

[中文安装说明](#中文安装说明) · [English installation guide](#english-installation-guide)

插件版本：`0.4.0`

> [!IMPORTANT]
> 本目录是可安装的插件源码，但它位于 `ZZZ-autorun` 仓库中，不会因为克隆仓库而自动安装到一条龙。必须把整个 `unattended_guardian` 目录复制到一条龙根目录的 `plugins` 下。

---

## 中文安装说明

### 1. 插件负责什么

无人值守安全守护负责检测并阻断以下危险情况：

- 运行中出现“账号在其他地方登录”等顶号弹窗；
- 一条龙已经进入业务流程后，游戏返回登录页并尝试使用缓存 token 自动登录；
- 已武装会话再次初始化登录 SDK；
- 危险画面出现后仍有脚本尝试点击、按键、拖拽、滚动或输入文字。

插件触发后会：

1. 阻断后续游戏输入；
2. 保存证据截图；
3. 发送通知；
4. 关闭游戏并停止当前一条龙；
5. 写入冷却标记，禁止外部恢复脚本提前重新登录。

外部 `OneDragon_FINAL_Restart_90min.ahk` 仍负责启动、故障恢复和冷却结束后的重新运行。AHK 已不再持续执行顶号 OCR；这部分保护完全由本插件负责。

### 2. 安装前提

安装前确认：

- 系统为 Windows；
- 一条龙安装在 `C:\ZZZ-OD`；
- 当前版本支持项目根目录下的第三方插件目录 `plugins/<插件名>/`；
- 游戏、一条龙 GUI 和 `OneDragon_FINAL_Restart_90min.ahk` 均已退出；
- 使用的是一条龙完整环境，OCR、截图与通知依赖已经安装。

如果一条龙不在 `C:\ZZZ-OD`，请把下文命令中的路径替换为实际安装目录。

### 3. 下载插件源码

#### 方法 A：已经克隆整个仓库

插件源目录为：

```text
C:\ZZZ-autorun\plugins\unattended_guardian
```

#### 方法 B：从 GitHub 下载 ZIP

1. 打开 [pumpkinperson996/zzz-autorun](https://github.com/pumpkinperson996/zzz-autorun)。
2. 点击 `Code` → `Download ZIP`。
3. 解压 ZIP。
4. 在解压目录中找到：

   ```text
   plugins\unattended_guardian
   ```

后续步骤中的 `$source` 应改为这个实际解压路径。

### 4. 首次安装

先确认目标目录不存在：

```powershell
Test-Path "C:\ZZZ-OD\plugins\unattended_guardian"
```

返回 `False` 后，执行：

```powershell
$source = "C:\ZZZ-autorun\plugins\unattended_guardian"
$target = "C:\ZZZ-OD\plugins\unattended_guardian"

if (Test-Path $target) {
    throw "目标目录已存在，请按升级步骤操作：$target"
}

Copy-Item -LiteralPath $source -Destination $target -Recurse
```

安装后的目录必须是：

```text
C:\ZZZ-OD\plugins\unattended_guardian\
├── __init__.py
├── unattended_guardian_factory.py
├── unattended_guardian_const.py
├── unattended_guardian_app.py
├── unattended_guardian_app_setting.py
├── unattended_guardian_config.py
├── guardian_setting_flyout.py
├── screenshot_hook.py
├── unattended_guardian.yml.example
└── README.md
```

以下结构是错误的，多套了一层目录，插件不会被正确扫描：

```text
C:\ZZZ-OD\plugins\unattended_guardian\unattended_guardian\unattended_guardian_factory.py
```

### 5. 配置文件

插件在没有 YAML 文件时也能运行，代码内置默认值：

| 配置项 | 默认值 | 说明 |
|---|---:|---|
| `detect_enabled` | `true` | 顶号与未授权重登录保护总开关 |
| `check_interval_seconds` | `1` | 顶号弹窗 OCR 的最短检测间隔 |
| `kicked_cooldown_minutes` | `120` | 触发后禁止重新登录的时间 |
| `kicked_keywords` | 6 个默认关键词 | 任一关键词命中即触发 |

首次启动后可在插件设置界面修改。配置会保存到：

```text
C:\ZZZ-OD\config\unattended_guardian.yml
```

如果希望在首次启动前创建配置，可复制仓库内的示例：

```powershell
$example = "C:\ZZZ-autorun\plugins\unattended_guardian\unattended_guardian.yml.example"
$config = "C:\ZZZ-OD\config\unattended_guardian.yml"

if (-not (Test-Path $config)) {
    Copy-Item -LiteralPath $example -Destination $config
}
```

不要在升级时覆盖已有配置，除非明确希望恢复默认值。

### 6. 首次启动与验证

1. 启动一条龙 GUI。
2. 在默认一条龙应用列表中确认出现“无人值守安全守护”。
3. 运行该应用一次。
4. 正常结果应为“顶号检测与重登录熔断已启用”。
5. 打开一条龙日志，搜索 `[顶号检测]`。

正常启动时应看到以下日志中的一种或多种：

```text
[顶号检测] Operation、控制器输入与 SDK 日志钩子安装成功
[顶号检测] Operation 与 SDK 钩子已安装，等待真实控制器初始化
[顶号检测] 已绑定真实控制器的截图与输入熔断
```

如果看到下面的日志，插件没有正常启用：

```text
加载工厂文件 ... 失败
[顶号检测] 钩子安装异常，插件功能停用
```

此时不要启动无人值守流程，应先按“常见问题”排查。

### 7. 与 AutoHotkey 恢复脚本联动

插件触发后会写入：

```text
C:\ZZZ-OD\.debug\temp\unattended_kicked_until.txt
```

文件内容是本地时间，格式为 `yyyyMMddHHmmss`。AHK 每次准备恢复一条龙前都会读取这个时间：

- 冷却未结束：只等待，不启动游戏；
- 冷却结束：删除标记并恢复运行；
- 标记不存在：按普通故障恢复流程运行。

只安装 AHK、不安装本插件时，AHK 仍能做普通重启，但不会主动检测顶号和未授权重登录，因此不应视为完整的无人值守保护。

### 8. 升级插件

升级前关闭游戏、一条龙和 AHK。旧插件必须移到 `C:\ZZZ-OD\plugins` 之外，因为插件扫描器会递归扫描 `plugins`，留在里面的备份仍可能被加载。

```powershell
$source = "C:\ZZZ-autorun\plugins\unattended_guardian"
$target = "C:\ZZZ-OD\plugins\unattended_guardian"
$backupRoot = "C:\ZZZ-OD\.debug\backups\unattended_guardian"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backup = Join-Path $backupRoot $stamp

New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null

if (Test-Path $target) {
    Move-Item -LiteralPath $target -Destination $backup
}

try {
    Copy-Item -LiteralPath $source -Destination $target -Recurse
}
catch {
    if ((-not (Test-Path $target)) -and (Test-Path $backup)) {
        Move-Item -LiteralPath $backup -Destination $target
    }
    throw
}
```

升级不会修改 `C:\ZZZ-OD\config\unattended_guardian.yml`。

重新启动后，再按“首次启动与验证”检查应用和日志。

### 9. 回滚

如果升级后插件无法加载：

```powershell
$target = "C:\ZZZ-OD\plugins\unattended_guardian"
$backup = "C:\ZZZ-OD\.debug\backups\unattended_guardian\这里替换为备份时间目录"
$failedRoot = "C:\ZZZ-OD\.debug\failed-plugins"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"

if (Test-Path $target) {
    New-Item -ItemType Directory -Path $failedRoot -Force | Out-Null
    Move-Item -LiteralPath $target -Destination (Join-Path $failedRoot "unattended_guardian-$stamp")
}

Move-Item -LiteralPath $backup -Destination $target
```

回滚前同样需要关闭游戏、一条龙和 AHK。确认回滚版本正常后，再处理 `.debug\failed-plugins` 中的失败版本；不要在一条龙运行时直接删除。

### 10. 卸载

关闭游戏、一条龙和 AHK，然后把插件移出 `plugins`：

```powershell
$target = "C:\ZZZ-OD\plugins\unattended_guardian"
$uninstallRoot = "C:\ZZZ-OD\.debug\uninstalled-plugins"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"

New-Item -ItemType Directory -Path $uninstallRoot -Force | Out-Null
Move-Item -LiteralPath $target -Destination (Join-Path $uninstallRoot "unattended_guardian-$stamp")
```

默认保留以下数据，便于重新安装和审计：

- `config\unattended_guardian.yml`；
- `.debug\images\UnattendedGuardian_*.png`；
- `.debug\temp\unattended_kicked_until.txt`；
- 一条龙日志。

卸载插件后，如果仍使用 AHK 无人值守恢复，请明确知晓顶号保护已经不存在。

### 11. 常见问题

#### 一条龙列表里没有插件

依次检查：

1. `unattended_guardian_factory.py` 是否直接位于 `C:\ZZZ-OD\plugins\unattended_guardian`；
2. 是否错误地多复制了一层目录；
3. 插件目录中是否存在多个 `*_factory.py` 或 `*_const.py`；
4. 是否已经完全重启一条龙；
5. 日志中是否出现“加载工厂文件失败”。

#### 插件显示但运行检查失败

查看日志中的 `[顶号检测]` 异常。常见原因包括控制器尚未初始化、当前版本接口变化或依赖不完整。不要只看插件是否出现在列表中；必须以运行检查和日志为准。

#### 修改配置后没有生效

确认编辑的是：

```text
C:\ZZZ-OD\config\unattended_guardian.yml
```

不要编辑插件目录里的 `.example` 文件来代替运行配置。修改后重启一条龙，或在 GUI 中通过插件设置保存。

#### 收不到通知

插件会调用一条龙已有的推送服务。先确认一条龙的通知渠道已经配置并能发送普通通知，再检查日志中的“通知推送失败”。通知失败不会取消输入阻断、关闭游戏和冷却标记。

#### 冷却结束后仍不恢复

打开冷却标记并检查时间格式是否为 14 位数字。还要确认 AHK 正在运行、路径与本文一致，并查看 `ZZZ-autorun\logs\closedloop.log` 中的 `KICKED:` 日志。

#### 是否需要用真实顶号测试

不建议为了测试而在另一台设备强行登录。先用插件运行检查、启动日志、配置写入和 AHK 冷却读取验证安装。真实顶号属于会影响账号会话的破坏性测试，应只在明确安排的测试账号和时段进行。

### 12. 运行数据位置

| 数据 | 路径 |
|---|---|
| 插件配置 | `C:\ZZZ-OD\config\unattended_guardian.yml` |
| 冷却标记 | `C:\ZZZ-OD\.debug\temp\unattended_kicked_until.txt` |
| 证据截图 | `C:\ZZZ-OD\.debug\images\UnattendedGuardian_*.png` |
| 一条龙日志 | `C:\ZZZ-OD\.log\log.txt` |
| AHK 日志 | `C:\ZZZ-autorun\logs\closedloop.log` |

---

## English installation guide

### 1. What the plugin does

Unattended Guardian detects and blocks login-conflict popups, unauthorized returns to the login screen, repeated login-SDK initialization, and further mouse, keyboard, controller, clipboard, or text input after a dangerous screen is detected.

When triggered, it blocks input, saves evidence, sends a notification, stops OneDragon, closes the game, and writes a cooldown marker. `OneDragon_FINAL_Restart_90min.ahk` remains responsible for startup and recovery after the cooldown; AHK no longer performs continuous login-conflict OCR.

### 2. Requirements

- Windows and a working OneDragon installation, assumed below to be `C:\ZZZ-OD`.
- A OneDragon version that scans third-party plugins from `plugins/<plugin-name>/`.
- The full OneDragon environment with its OCR, capture, and notification dependencies.
- The game, OneDragon GUI, and the AutoHotkey recovery script must be stopped while copying or upgrading the plugin.

Replace `C:\ZZZ-OD` in the commands if your installation uses another path.

### 3. Obtain the source

If the repository is cloned at the recommended location, the source is:

```text
C:\ZZZ-autorun\plugins\unattended_guardian
```

Alternatively, download the repository ZIP from [GitHub](https://github.com/pumpkinperson996/zzz-autorun), extract it, and locate `plugins\unattended_guardian` inside the extracted directory.

### 4. First installation

```powershell
$source = "C:\ZZZ-autorun\plugins\unattended_guardian"
$target = "C:\ZZZ-OD\plugins\unattended_guardian"

if (Test-Path $target) {
    throw "The target already exists. Follow the upgrade instructions: $target"
}

Copy-Item -LiteralPath $source -Destination $target -Recurse
```

The factory file must end up directly at:

```text
C:\ZZZ-OD\plugins\unattended_guardian\unattended_guardian_factory.py
```

An extra nested `unattended_guardian\unattended_guardian` directory is incorrect and prevents normal discovery.

### 5. Configuration

The plugin works without a YAML file and uses these built-in defaults:

| Key | Default | Meaning |
|---|---:|---|
| `detect_enabled` | `true` | Master protection switch |
| `check_interval_seconds` | `1` | Minimum popup OCR interval |
| `kicked_cooldown_minutes` | `120` | Time before login recovery is allowed |
| `kicked_keywords` | 6 built-in entries | Any matching phrase triggers protection |

Runtime settings are stored at:

```text
C:\ZZZ-OD\config\unattended_guardian.yml
```

To create it from the example before first launch:

```powershell
$example = "C:\ZZZ-autorun\plugins\unattended_guardian\unattended_guardian.yml.example"
$config = "C:\ZZZ-OD\config\unattended_guardian.yml"

if (-not (Test-Path $config)) {
    Copy-Item -LiteralPath $example -Destination $config
}
```

Do not overwrite an existing configuration during an upgrade unless you intentionally want to reset it.

### 6. Verify the installation

1. Start the OneDragon GUI.
2. Confirm that “无人值守安全守护” appears in the default application list.
3. Run it once; the expected status is “顶号检测与重登录熔断已启用”.
4. Search the OneDragon log for `[顶号检测]`.

Expected startup messages include:

```text
[顶号检测] Operation、控制器输入与 SDK 日志钩子安装成功
[顶号检测] Operation 与 SDK 钩子已安装，等待真实控制器初始化
[顶号检测] 已绑定真实控制器的截图与输入熔断
```

Do not enable unattended operation if the log reports a factory-loading failure or `[顶号检测] 钩子安装异常，插件功能停用`.

### 7. AutoHotkey integration

The plugin writes this cooldown marker:

```text
C:\ZZZ-OD\.debug\temp\unattended_kicked_until.txt
```

AHK waits until the timestamp expires before allowing another login. Without this plugin, AHK can still restart failed processes, but it cannot detect login conflicts or unauthorized relogin and is not a complete unattended-protection setup.

### 8. Upgrade

Stop the game, OneDragon, and AHK first. Move the old plugin outside `C:\ZZZ-OD\plugins`; the scanner is recursive, so a backup left anywhere under `plugins` may still be loaded.

```powershell
$source = "C:\ZZZ-autorun\plugins\unattended_guardian"
$target = "C:\ZZZ-OD\plugins\unattended_guardian"
$backupRoot = "C:\ZZZ-OD\.debug\backups\unattended_guardian"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backup = Join-Path $backupRoot $stamp

New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null

if (Test-Path $target) {
    Move-Item -LiteralPath $target -Destination $backup
}

try {
    Copy-Item -LiteralPath $source -Destination $target -Recurse
}
catch {
    if ((-not (Test-Path $target)) -and (Test-Path $backup)) {
        Move-Item -LiteralPath $backup -Destination $target
    }
    throw
}
```

The runtime YAML configuration is outside the plugin directory and remains unchanged.

### 9. Rollback and uninstall

To roll back, stop all related processes, move the failed plugin out of `plugins`, and move the selected timestamped backup back to `C:\ZZZ-OD\plugins\unattended_guardian`.

To uninstall while keeping a recoverable copy:

```powershell
$target = "C:\ZZZ-OD\plugins\unattended_guardian"
$uninstallRoot = "C:\ZZZ-OD\.debug\uninstalled-plugins"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"

New-Item -ItemType Directory -Path $uninstallRoot -Force | Out-Null
Move-Item -LiteralPath $target -Destination (Join-Path $uninstallRoot "unattended_guardian-$stamp")
```

Configuration, evidence screenshots, cooldown markers, and logs are preserved by default. Remember that AHK no longer provides login-conflict protection after the plugin is removed.

### 10. Troubleshooting checklist

- Verify that `unattended_guardian_factory.py` is directly inside the installed plugin directory.
- Remove accidental extra nesting and ensure there is only one `*_factory.py` and one `*_const.py` in the plugin directory.
- Fully restart OneDragon after copying files.
- Check `.log\log.txt` for factory-loading errors and `[顶号检测]` messages.
- Edit `config\unattended_guardian.yml`, not the `.example` file in the plugin directory.
- Configure and test OneDragon's normal notification channel before relying on guardian notifications.
- Check `ZZZ-autorun\logs\closedloop.log` for `KICKED:` messages when cooldown recovery does not occur.
- Do not force a real account conflict merely to test installation; use the status application and startup logs first.

### 11. Runtime data

| Data | Path |
|---|---|
| Configuration | `C:\ZZZ-OD\config\unattended_guardian.yml` |
| Cooldown marker | `C:\ZZZ-OD\.debug\temp\unattended_kicked_until.txt` |
| Evidence screenshots | `C:\ZZZ-OD\.debug\images\UnattendedGuardian_*.png` |
| OneDragon log | `C:\ZZZ-OD\.log\log.txt` |
| AHK recovery log | `C:\ZZZ-autorun\logs\closedloop.log` |
