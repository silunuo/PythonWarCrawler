from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
from pyecharts import options as opts
from pyecharts.charts import Bar, Line, Page, Pie, WordCloud
from pyecharts.globals import ThemeType

from src.common.io import ensure_parent


def build_dashboard(clean_path: Path, summary_path: Path, dashboard_path: Path, conclusions_path: Path) -> None:
    if not clean_path.exists():
        raise FileNotFoundError(f"clean comments not found: {clean_path}")
    if not summary_path.exists():
        raise FileNotFoundError(f"summary json not found: {summary_path}")

    df = pd.read_csv(clean_path, encoding="utf-8-sig").fillna("")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if df.empty:
        raise ValueError("clean comments csv is empty")

    page = Page(page_title="全球网友对美以伊战争评论分析", layout=Page.SimplePageLayout)
    page.add(
        _bar("各平台评论数量", summary["platform_counts"], "评论数"),
        _pie("情感倾向占比", summary["sentiment_counts"]),
        _pie("主题类别占比", summary["category_counts"]),
        _line("评论发布时间趋势", summary["date_counts"]),
        _wordcloud("高频关键词", summary["top_keywords"]),
    )
    ensure_parent(dashboard_path)
    page.render(str(dashboard_path))
    ensure_parent(conclusions_path)
    conclusions_path.write_text(_build_conclusions(summary), encoding="utf-8")
    print(f"[visualize] dashboard={dashboard_path}")
    print(f"[visualize] conclusions={conclusions_path}")


def _bar(title: str, data: dict[str, int], y_name: str) -> Bar:
    items = _sorted_items(data)
    chart = Bar(init_opts=opts.InitOpts(width="1100px", height="420px", theme=ThemeType.LIGHT))
    chart.add_xaxis([key for key, _ in items])
    chart.add_yaxis(y_name, [value for _, value in items], category_gap="45%")
    chart.set_global_opts(
        title_opts=opts.TitleOpts(title=title),
        toolbox_opts=opts.ToolboxOpts(is_show=True),
        xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=0)),
        yaxis_opts=opts.AxisOpts(name=y_name),
    )
    return chart


def _pie(title: str, data: dict[str, int]) -> Pie:
    chart = Pie(init_opts=opts.InitOpts(width="1100px", height="420px", theme=ThemeType.LIGHT))
    chart.add("", _sorted_items(data), radius=["35%", "65%"])
    chart.set_global_opts(
        title_opts=opts.TitleOpts(title=title),
        legend_opts=opts.LegendOpts(orient="vertical", pos_left="2%", pos_top="15%"),
        toolbox_opts=opts.ToolboxOpts(is_show=True),
    )
    chart.set_series_opts(label_opts=opts.LabelOpts(formatter="{b}: {d}%"))
    return chart


def _line(title: str, data: dict[str, int]) -> Line:
    items = sorted(data.items(), key=lambda item: item[0])
    chart = Line(init_opts=opts.InitOpts(width="1100px", height="420px", theme=ThemeType.LIGHT))
    chart.add_xaxis([key for key, _ in items])
    chart.add_yaxis("评论数", [value for _, value in items], is_smooth=True, symbol_size=6)
    chart.set_global_opts(
        title_opts=opts.TitleOpts(title=title),
        toolbox_opts=opts.ToolboxOpts(is_show=True),
        datazoom_opts=[opts.DataZoomOpts()],
        xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=35)),
        yaxis_opts=opts.AxisOpts(name="评论数"),
    )
    return chart


def _wordcloud(title: str, keywords: list[dict[str, Any]]) -> WordCloud:
    data = [(item["word"], int(max(1, round(float(item["score"]))))) for item in keywords[:80]]
    chart = WordCloud(init_opts=opts.InitOpts(width="1100px", height="520px", theme=ThemeType.LIGHT))
    chart.add("", data, word_size_range=[16, 70], shape="circle")
    chart.set_global_opts(title_opts=opts.TitleOpts(title=title), toolbox_opts=opts.ToolboxOpts(is_show=True))
    return chart


def _sorted_items(data: dict[str, int]) -> list[tuple[str, int]]:
    return sorted(((str(key), int(value)) for key, value in data.items()), key=lambda item: item[1], reverse=True)


def _build_conclusions(summary: dict[str, Any]) -> str:
    total = int(summary.get("total", 0))
    platform = _top_item(summary.get("platform_counts", {}))
    sentiment = _top_item(summary.get("sentiment_counts", {}))
    category = _top_item(summary.get("category_counts", {}))
    keywords = "、".join(item["word"] for item in summary.get("top_keywords", [])[:10])
    peak_day = _top_item(summary.get("date_counts", {}))
    avg_score = summary.get("avg_sentiment_score", 0)

    lines = [
        "# 全球网友对美以伊战争评论分析结论",
        "",
        f"- 清洗后共有 {total} 条有效评论。",
        f"- 评论数量最多的平台是 {platform[0]}，数量为 {platform[1]} 条。",
        f"- 情感倾向以{sentiment[0]}为主，数量为 {sentiment[1]} 条，平均情感分为 {avg_score}。",
        f"- 讨论主题最多的是{category[0]}，数量为 {category[1]} 条。",
        f"- 高频关键词包括：{keywords}。",
    ]
    if peak_day[0]:
        lines.append(f"- 评论量最高的日期是 {peak_day[0]}，当天有 {peak_day[1]} 条评论。")
    lines.append("- 从评论内容看，网友主要关注军事行动、国际关系、战争影响和停火谈判。")
    return "\n".join(lines) + "\n"


def _top_item(data: dict[str, int]) -> tuple[str, int]:
    if not data:
        return ("", 0)
    return max(((str(key), int(value)) for key, value in data.items()), key=lambda item: item[1])

