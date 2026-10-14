# Apple OS Release RSS Feed

通过 GitHub Actions 定时拉取 [Apple Developer Releases RSS](https://developer.apple.com/news/releases/rss/releases.rss) 和 [Apple 安全更新页面](https://support.apple.com/en-us/100100)，过滤出 iOS / macOS / iPadOS / watchOS 的正式版和测试版更新，通过 Bark 推送，并将 RSS 托管在 GitHub Pages 上。无需服务器。

## Bark 推送与运行

- 在仓库 Settings → Secrets and variables → Actions 中配置 `BARK_KEY`。`SLACK_WEBHOOK` 可选。
- GitHub Pages 的发布源设为 GitHub Actions。
- 每 15 分钟自动检查一次，也可在 Actions → Update Apple OS Feed 中选择 Run workflow 手动运行；勾选 `test` 会强制发送测试通知。
- 首次运行会推送配置时间窗口内的更新：Developer RSS 最近 5 天、安全更新最近 30 天，系统主版本不低于 26。
- `.last_guids` 自动提交到仓库，记录 Bark 已确认成功的更新。Bark 发送失败时任务失败，不记录为已发送，下一次运行重试。可选 Slack 失败会显示任务失败，但不会重复已成功的 Bark 通知。

## 订阅地址

```
https://eliu-lotso.github.io/os-rss/feed.xml
```

### 在 Slack 中订阅

在任意频道输入：

```
/feed subscribe https://eliu-lotso.github.io/os-rss/feed.xml
```

### 在其他 RSS 阅读器中订阅

将上面的 URL 添加到任意 RSS 阅读器（Feedly、Inoreader、NetNewsWire 等）即可。

## 工作原理

- GitHub Actions 每 15 分钟拉取一次两个 Apple 官方更新源
- 过滤出标题以 iOS / macOS / iPadOS / watchOS 开头的条目
- 生成过滤后的 RSS XML 文件到 `docs/feed.xml`
- 通过 GitHub Pages artifact 发布为公开 URL，无需提交生成的 XML

## 自定义过滤

编辑 `feeds.yml` 中的 `keywords` 列表，添加或移除你关心的系统名称。

## 文件说明

| 文件 | 用途 |
|------|------|
| `rss_filter.py` | 主脚本：拉取 RSS、过滤、生成 XML |
| `feeds.yml` | RSS 源地址与过滤关键词配置 |
| `docs/feed.xml` | 生成的过滤后 RSS（自动维护） |
| `.last_guids` | Bark 已确认成功的更新标识（自动维护） |
| `.github/workflows/rss-to-slack.yml` | GitHub Actions 工作流 |
