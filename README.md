# Apple OS Release RSS Feed

通过 GitHub Actions 定时拉取 [Apple Developer Releases RSS](https://developer.apple.com/news/releases/rss/releases.rss)，过滤出 iOS / macOS / iPadOS / watchOS 的正式版和测试版更新，生成一个干净的 RSS Feed，托管在 GitHub Pages 上。

## 订阅地址

```
https://eliu-lotso.github.io/os-system/feed.xml
```

### 在 Slack 中订阅

在任意频道输入：

```
/feed subscribe https://eliu-lotso.github.io/os-system/feed.xml
```

### 在其他 RSS 阅读器中订阅

将上面的 URL 添加到任意 RSS 阅读器（Feedly、Inoreader、NetNewsWire 等）即可。

## 工作原理

- GitHub Actions 每 15 分钟拉取一次 Apple Developer Releases RSS
- 过滤出标题以 iOS / macOS / iPadOS / watchOS 开头的条目
- 生成过滤后的 RSS XML 文件到 `docs/feed.xml`
- 通过 GitHub Pages 托管为公开 URL

## 自定义过滤

编辑 `feeds.yml` 中的 `keywords` 列表，添加或移除你关心的系统名称。

## 文件说明

| 文件 | 用途 |
|------|------|
| `rss_filter.py` | 主脚本：拉取 RSS、过滤、生成 XML |
| `feeds.yml` | RSS 源地址与过滤关键词配置 |
| `docs/feed.xml` | 生成的过滤后 RSS（自动维护） |
| `.github/workflows/rss-to-slack.yml` | GitHub Actions 工作流 |
