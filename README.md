# PythonWarCrawler 使用说明

本程序会从 Bilibili、百度贴吧、Reddit 抓取真实评论，然后做清洗、分词、情感分析、关键词提取、主题分类，最后生成 pyecharts 图表和结论。

适合 Python 大作业方向二：全球网友对美以伊战争评论分析与可视化。

---

## 1. 克隆项目

从远程仓库克隆：

```powershell
git clone https://github.com/silunuo/PythonWarCrawler.git
cd PythonWarCrawler
```

如果你用 SSH：

```powershell
git clone git@github.com:silunuo/PythonWarCrawler.git
cd PythonWarCrawler
```

仓库里只提交代码、配置和说明文档。`.venv`、`.pip-cache`、爬取结果、图表结果都需要在本地生成。

---

## 2. 本地环境

建议使用 Python 3.10。依赖安装到项目目录里的 `.venv`，pip 缓存放到 `.pip-cache`。

Windows PowerShell：

```powershell
python -m venv .venv
$env:PIP_CACHE_DIR = (Join-Path (Get-Location) '.pip-cache')
```

如果需要代理，安装依赖前先设置：

```powershell
$env:HTTP_PROXY = 'http://127.0.0.1:7890'
$env:HTTPS_PROXY = 'http://127.0.0.1:7890'
```

安装依赖：

```powershell
.\.venv\Scripts\python -m pip install -r requirements.txt
```

macOS / Linux：

```bash
python3 -m venv .venv
export PIP_CACHE_DIR="$PWD/.pip-cache"
```

如果需要代理：

```bash
export HTTP_PROXY="http://127.0.0.1:7890"
export HTTPS_PROXY="http://127.0.0.1:7890"
```

安装依赖：

```bash
.venv/bin/python -m pip install -r requirements.txt
```

---

## 3. 配置代理和关键词

主要改 `config.json`。

| 字段 | 说明 |
| --- | --- |
| `proxy.enabled` | 是否使用代理 |
| `proxy.http` / `proxy.https` | 代理地址，默认是 `127.0.0.1:7890` |
| `crawl.target_total` | 正式抓取目标数量，默认 3000 |
| `crawl.queries_cn` | 中文关键词，用于 Bilibili 和贴吧 |
| `crawl.queries_en` | 英文关键词，用于 Reddit |
| `crawl.tieba_forums` | 贴吧列表 |
| `paths.raw_comments` | 原始 CSV 输出路径 |
| `paths.clean_comments` | 分析后 CSV 输出路径 |
| `paths.dashboard_html` | 图表页面输出路径 |

不用代理时，把 `proxy.enabled` 改成 `false`：

```json
"proxy": {
  "enabled": false,
  "http": "http://127.0.0.1:7890",
  "https": "http://127.0.0.1:7890"
}
```

---

## 4. 快速验证

先跑少量数据，确认三个平台都能访问：

Windows：

```powershell
.\.venv\Scripts\python main.py all --smoke
```

macOS / Linux：

```bash
.venv/bin/python main.py all --smoke
```

成功后会生成这些文件：

```text
data/raw/comments.csv
data/processed/analyzed_comments.csv
output/summary.json
output/dashboard.html
output/conclusions.md
```

---

## 5. 分步运行

如果想看每一步结果，可以分步执行。

### 5.1 爬取评论

```powershell
.\.venv\Scripts\python main.py crawl --smoke
```

输出：

```text
data/raw/comments.csv
```

### 5.2 清洗和分析

```powershell
.\.venv\Scripts\python main.py analyze
```

输出：

```text
data/processed/analyzed_comments.csv
output/summary.json
```

### 5.3 生成图表和结论

```powershell
.\.venv\Scripts\python main.py visualize
```

输出：

```text
output/dashboard.html
output/conclusions.md
```

---

## 6. 正式抓取 3000 条

Windows：

```powershell
.\.venv\Scripts\python main.py all --target-total 3000
```

macOS / Linux：

```bash
.venv/bin/python main.py all --target-total 3000
```

正式模式会检查有效评论数量。如果真实平台返回的数据少于 3000 条，程序会退出并提示实际数量。程序不会补假数据。

---

## 7. 查看结果

| 文件 | 怎么看 |
| --- | --- |
| `data/raw/comments.csv` | 看原始评论，字段有平台、内容、时间、用户名、点赞数、链接、语言 |
| `data/processed/analyzed_comments.csv` | 看 `tokens`、`sentiment_score`、`sentiment`、`category` |
| `output/dashboard.html` | 用浏览器打开，看 pyecharts 图表 |
| `output/conclusions.md` | 看自动生成的结论 |
| `output/summary.json` | 看统计结果，主要给图表使用 |

---

## 8. 验证清单

运行完后检查：

- [ ] `.venv` 在项目目录里。
- [ ] `.pip-cache` 在项目目录里。
- [ ] `data/raw/comments.csv` 已生成。
- [ ] `data/processed/analyzed_comments.csv` 已生成。
- [ ] `output/dashboard.html` 已生成。
- [ ] `output/conclusions.md` 已生成。
- [ ] `comments.csv` 里有 `Bilibili`、`Tieba`、`Reddit` 三个平台。
- [ ] 正式抓取时没有人为补数据。

可用下面命令检查依赖和语法：

```powershell
.\.venv\Scripts\python -m pip check
.\.venv\Scripts\python -m compileall main.py src
```

---

## 9. 常见问题

### Bilibili 出现 `HTTP 412`

这是平台拦截请求。程序会重试，也会继续跑后面的关键词。可以稍后再跑，或者把 `config.json` 里的 `request.delay_seconds` 调大。

### 贴吧提示某个吧暂不开放

程序会跳过这个吧，继续抓其他贴吧。可以在 `crawl.tieba_forums` 里换别的相关贴吧。

### Reddit 出现 `502`

程序会先用公开评论接口，失败后再用 Reddit JSON 接口。代理不稳定时，可以稍后再跑。

### 正式抓不到 3000 条

先确认代理可用，再修改这些页数：

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

---

## 10. 项目结构

```text
.
├── main.py
├── config.json
├── requirements.txt
├── resources/
├── src/
│   ├── analysis/
│   ├── common/
│   ├── crawlers/
│   └── visualization/
├── data/
└── output/
```
