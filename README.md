# 全球网友对美以伊战争评论分析与可视化操作说明

这份文档说明怎么运行这个 Python 大作业程序。程序会从 Bilibili、百度贴吧、Reddit 抓取真实评论，然后做清洗、分词、情感分析、关键词提取、主题分类，最后生成 pyecharts 图表和结论。

---

## 1. 文件清单

| 路径 | 用途 |
| --- | --- |
| `main.py` | 程序入口，所有命令都从这里执行 |
| `config.json` | 代理、关键词、抓取页数、输出路径配置 |
| `requirements.txt` | 项目依赖清单 |
| `src/crawlers/` | Bilibili、百度贴吧、Reddit 三个平台爬虫 |
| `src/analysis/` | 数据清洗、分词、情感分析、关键词、分类 |
| `src/visualization/` | pyecharts 图表和结论生成 |
| `resources/` | 中英文停用词 |
| `data/raw/comments.csv` | 原始评论数据 |
| `data/processed/analyzed_comments.csv` | 分析后的评论数据 |
| `output/dashboard.html` | 图表页面 |
| `output/conclusions.md` | 自动生成的结论 |
| `output/summary.json` | 图表用的统计结果 |

---

## 2. 准备环境

依赖只放在当前项目目录里。主要目录是 `.venv` 和 `.pip-cache`。不要把依赖装到系统 Python 里。

在项目目录执行：

```powershell
python -m venv .venv
$env:PIP_CACHE_DIR = (Join-Path (Get-Location) '.pip-cache')
$env:HTTP_PROXY = 'http://127.0.0.1:7890'
$env:HTTPS_PROXY = 'http://127.0.0.1:7890'
.\.venv\Scripts\python -m pip install -r requirements.txt
```

如果 `.venv` 已经存在，可以跳过这一步。

---

## 3. 配置说明

主要改 `config.json`。

| 字段 | 说明 |
| --- | --- |
| `proxy.enabled` | 是否使用代理 |
| `proxy.http` / `proxy.https` | 代理地址，当前是 `127.0.0.1:7890` |
| `crawl.target_total` | 正式抓取目标数量，默认 3000 |
| `crawl.queries_cn` | 中文关键词，用于 Bilibili 和贴吧 |
| `crawl.queries_en` | 英文关键词，用于 Reddit |
| `crawl.tieba_forums` | 贴吧列表 |
| `paths.raw_comments` | 原始 CSV 输出路径 |
| `paths.clean_comments` | 分析后 CSV 输出路径 |
| `paths.dashboard_html` | 图表页面输出路径 |

如果不用代理，把这里改成：

```json
"proxy": {
  "enabled": false,
  "http": "http://127.0.0.1:7890",
  "https": "http://127.0.0.1:7890"
}
```

---

## 4. 运行步骤

### 4.1 先跑少量数据

这一步用来确认三个平台都能访问。

```powershell
.\.venv\Scripts\python main.py crawl --smoke
```

成功后会生成：

```text
data/raw/comments.csv
```

### 4.2 清洗和分析

```powershell
.\.venv\Scripts\python main.py analyze
```

成功后会生成：

```text
data/processed/analyzed_comments.csv
output/summary.json
```

### 4.3 生成图表和结论

```powershell
.\.venv\Scripts\python main.py visualize
```

成功后会生成：

```text
output/dashboard.html
output/conclusions.md
```

### 4.4 一条命令跑完整流程

少量验证：

```powershell
.\.venv\Scripts\python main.py all --smoke
```

正式抓取 3000 条：

```powershell
.\.venv\Scripts\python main.py all --target-total 3000
```

正式模式下，如果真实平台返回的数据不够 3000 条，程序会退出并提示实际数量。程序不会补假数据。

---

## 5. 看结果

1. 打开 `data/raw/comments.csv`，确认有三类平台数据：`Bilibili`、`Tieba`、`Reddit`。
2. 打开 `data/processed/analyzed_comments.csv`，看 `sentiment_score`、`sentiment`、`category`、`tokens` 字段。
3. 用浏览器打开 `output/dashboard.html`，查看平台数量、情感分布、主题占比、时间趋势、关键词词云。
4. 打开 `output/conclusions.md`，查看自动生成的结论。

---

## 6. 验证清单

运行完后按这个清单检查：

- [ ] `.venv` 在项目目录里。
- [ ] `.pip-cache` 在项目目录里。
- [ ] `data/raw/comments.csv` 已生成。
- [ ] `data/processed/analyzed_comments.csv` 已生成。
- [ ] `output/dashboard.html` 已生成。
- [ ] `output/conclusions.md` 已生成。
- [ ] `comments.csv` 里有 Bilibili、Tieba、Reddit 三个平台。
- [ ] 正式抓取时没有人为补数据。

开发时已经验证过这些命令：

```powershell
.\.venv\Scripts\python main.py crawl --smoke
.\.venv\Scripts\python main.py analyze
.\.venv\Scripts\python main.py visualize
.\.venv\Scripts\python main.py all --smoke
.\.venv\Scripts\python -m pip check
.\.venv\Scripts\python -m compileall main.py src
```

---

## 7. 常见问题

### Bilibili 出现 `HTTP 412`

这是平台拦截请求。程序会重试，也会继续跑后面的关键词。可以稍后再跑，或者把 `config.json` 里的 `request.delay_seconds` 调大。

### 贴吧提示某个吧暂不开放

程序会跳过这个吧，继续抓其他贴吧。可以在 `crawl.tieba_forums` 里换别的相关贴吧。

### Reddit 出现 `502`

程序会先用公开评论接口，失败后再用 Reddit JSON 接口。代理不稳定时，可以稍后再跑。

### 正式抓不到 3000 条

先确认代理可用，再增加这些页数：

```json
"bilibili": {
  "search_pages": 8,
  "comment_pages_per_video": 8
},
"tieba": {
  "thread_pages_per_forum": 6,
  "post_pages_per_thread": 6
},
"reddit": {
  "pages_per_query": 8
}
```

页数越大，运行时间越长，被限流的概率也会变高。

