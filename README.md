# 渠道余额监测工具

这是一个适合新手使用的渠道余额监测工具：

- 每 30 分钟检查一次 `https://uptime.maolaoapi.com/dashboard` 的渠道余额
- 默认只监测后台里已星标的渠道
- 余额只使用上游站点实时读取结果，不再使用后台同步余额兜底
- 当前支持实时读取 `Sub2API` 和 `NewApi` 类型渠道
- 当渠道余额低于 `30 元` 时，发送 Telegram 提醒
- GitHub Pages 展示最近一次检查结果

## 需要准备的信息

请在 GitHub 仓库的 `Settings -> Secrets and variables -> Actions -> New repository secret` 里添加这些信息：

| 名称 | 说明 |
| --- | --- |
| `UPTIME_USERNAME` | 监测后台登录账号，默认通常是 `admin` |
| `UPTIME_PASSWORD` | 监测后台登录密码 |
| `TELEGRAM_BOT_TOKEN` | Telegram 机器人 token |
| `TELEGRAM_CHAT_ID` | 接收提醒的 Telegram chat id |

如果你已经有后台 token，也可以只填 `UPTIME_TOKEN`，不用填 `UPTIME_USERNAME` 和 `UPTIME_PASSWORD`。

## Telegram 配置方法

1. 在 Telegram 里找到 `@BotFather`
2. 发送 `/newbot` 创建机器人
3. 复制它给你的 token，填到 `TELEGRAM_BOT_TOKEN`
4. 给你的机器人发送一条消息
5. 打开 `https://api.telegram.org/bot你的机器人token/getUpdates`
6. 在返回内容里找到 `chat` 下面的 `id`，填到 `TELEGRAM_CHAT_ID`

## GitHub Pages 开启方法

1. 打开仓库 `Settings -> Pages`
2. `Build and deployment` 选择 `Deploy from a branch`
3. Branch 选择 `main`，文件夹选择 `/docs`
4. 保存后等待 1 到 3 分钟

## 网页手动检测

页面右上角的 `立即检测` 可以直接触发一次 GitHub Actions 检测。首次使用时需要输入一个有 `actions:write` 权限的 GitHub Token，这个 token 会保存在当前浏览器里，之后重新打开网页也不用反复输入。

## 手动测试

1. 打开仓库的 `Actions`
2. 选择 `Check Channel Balance`
3. 点击 `Run workflow`
4. 等待运行完成
5. 打开 GitHub Pages 页面查看结果

## 调整阈值

默认阈值是 `30`。如果要修改，编辑 `.github/workflows/check-balance.yml` 里的：

```yaml
BALANCE_THRESHOLD: "30"
```

## 是否只监测星标渠道

默认只监测后台里已星标的渠道：

```yaml
MONITOR_STARRED_ONLY: "true"
```

如果以后想恢复监测全部渠道，把它改成：

```yaml
MONITOR_STARRED_ONLY: "false"
```

## 是否只使用上游实时余额

默认只使用上游实时读取到的余额：

```yaml
UPSTREAM_BALANCE_ONLY: "true"
```

如果某个上游实时读取失败，页面会显示 `读取失败`，不会再用后台旧余额代替。

目前实时读取已接入：

- `Sub2API`
- `NewApi`

## 避免重复提醒

默认同一个低余额渠道每 `12` 小时最多提醒一次。可以修改：

```yaml
NOTIFY_COOLDOWN_HOURS: "12"
```
