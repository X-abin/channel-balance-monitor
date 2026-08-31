# 渠道余额监测工具

这是一个适合新手使用的渠道余额监测工具：

- 每 10 分钟检查一次 `https://uptime.maolaoapi.com/dashboard` 的渠道余额
- 默认只监测后台里已星标的渠道
- 余额只使用上游站点实时读取结果，不再使用后台同步余额兜底
- 当前支持实时读取 `Sub2API`、`NewApi` 和 `ThirdParty` 类型渠道
- 当渠道余额低于 `30 元` 时，发送 Telegram 提醒
- GitHub Pages 展示最近一次检查结果和所有已监测渠道的最新余额

## 需要准备的信息

请在 GitHub 仓库的 `Settings -> Secrets and variables -> Actions -> New repository secret` 里添加这些信息：

| 名称 | 说明 |
| --- | --- |
| `UPTIME_USERNAME` | 监测后台登录账号，默认通常是 `admin` |
| `UPTIME_PASSWORD` | 监测后台登录密码 |
| `TELEGRAM_BOT_TOKEN` | Telegram 机器人 token |
| `TELEGRAM_CHAT_ID` | 接收提醒的 Telegram chat id |
| `CHANNELS_CONFIG_JSON` | 可选。后台掉线时使用的备用渠道配置 |

如果你已经有后台 token，也可以只填 `UPTIME_TOKEN`，不用填 `UPTIME_USERNAME` 和 `UPTIME_PASSWORD`。

## 后台掉线备用配置

平时工具会先从 `https://uptime.maolaoapi.com` 读取星标渠道、上游地址和登录信息，然后再去每个上游站点实时读取余额。

如果这个后台掉线，工具就拿不到渠道名单和登录信息。要让后台掉线时也能继续检测，请在 GitHub Secrets 里新增 `CHANNELS_CONFIG_JSON`，内容格式如下：

```json
{
  "channels": [
    {
      "id": "渠道ID",
      "name": "渠道名称",
      "platform": "Sub2API",
      "baseUrl": "https://上游地址",
      "isStarred": true,
      "username": "上游登录账号",
      "password": "上游登录密码"
    }
  ]
}
```

如果某个渠道使用 token 或 refresh token，也可以写：

```json
{
  "channels": [
    {
      "id": "渠道ID",
      "name": "渠道名称",
      "platform": "Sub2API",
      "baseUrl": "https://上游地址",
      "isStarred": true,
      "token": "上游 access token",
      "refreshToken": "上游 refresh token"
    }
  ]
}
```

这份配置只放在 GitHub Secrets，不会显示在网页里。

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
- `ThirdParty`

## 暂不监测渠道

当前已临时排除 `阿伟`，不会检测余额，也不会发送 Telegram 提醒。
