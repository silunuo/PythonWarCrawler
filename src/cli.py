from __future__ import annotations

import argparse
import sys
from collections import Counter

from src.common.config import AppConfig
from src.common.io import write_comments
from src.crawlers.runner import crawl_all


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="全球网友评论分析与可视化")
    parser.add_argument("--config", default="config.json", help="配置文件路径")
    subparsers = parser.add_subparsers(dest="command", required=True)

    crawl = subparsers.add_parser("crawl", help="爬取真实评论")
    crawl.add_argument("--smoke", action="store_true", help="少量爬取，用来验证接口")
    crawl.add_argument("--target-total", type=int, default=None, help="正式爬取目标数量")

    analyze = subparsers.add_parser("analyze", help="清洗并分析评论")
    analyze.add_argument("--input", default=None, help="原始 CSV")
    analyze.add_argument("--output", default=None, help="分析后 CSV")

    visualize = subparsers.add_parser("visualize", help="生成 pyecharts 页面")
    visualize.add_argument("--input", default=None, help="分析后 CSV")

    all_cmd = subparsers.add_parser("all", help="爬取、分析、可视化")
    all_cmd.add_argument("--smoke", action="store_true", help="少量跑完整流程")
    all_cmd.add_argument("--target-total", type=int, default=None, help="正式爬取目标数量")
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = AppConfig.load(args.config)

    if args.command == "crawl":
        code = cmd_crawl(config, args.smoke, args.target_total)
    elif args.command == "analyze":
        code = cmd_analyze(config, args.input, args.output)
    elif args.command == "visualize":
        code = cmd_visualize(config, args.input)
    elif args.command == "all":
        code = cmd_all(config, args.smoke, args.target_total)
    else:
        parser.error("unknown command")
        code = 2
    raise SystemExit(code)


def cmd_crawl(config: AppConfig, smoke: bool, target_total: int | None) -> int:
    target = target_total or int(config.get("crawl", "target_total", default=3000))
    comments = crawl_all(config, target_total=target, smoke=smoke)
    output = config.path("raw_comments")
    write_comments(output, comments)
    counts = Counter(comment.platform for comment in comments)
    print(f"[crawl] saved={output}")
    print(f"[crawl] total={len(comments)} platforms={dict(counts)}")
    if not smoke and len(comments) < target:
        print(f"[crawl] need {target}, got {len(comments)}. No fake data was added.")
        return 2
    return 0


def cmd_analyze(config: AppConfig, input_path: str | None, output_path: str | None) -> int:
    from src.analysis.pipeline import analyze_comments

    raw_path = config.path("raw_comments") if input_path is None else config.root / input_path
    clean_path = config.path("clean_comments") if output_path is None else config.root / output_path
    analyze_comments(raw_path, clean_path, config.path("summary_json"))
    return 0


def cmd_visualize(config: AppConfig, input_path: str | None) -> int:
    from src.visualization.dashboard import build_dashboard

    clean_path = config.path("clean_comments") if input_path is None else config.root / input_path
    build_dashboard(
        clean_path,
        config.path("summary_json"),
        config.path("dashboard_html"),
        config.path("conclusions_md"),
    )
    return 0


def cmd_all(config: AppConfig, smoke: bool, target_total: int | None) -> int:
    crawl_code = cmd_crawl(config, smoke=smoke, target_total=target_total)
    if crawl_code:
        return crawl_code
    analyze_code = cmd_analyze(config, None, None)
    if analyze_code:
        return analyze_code
    return cmd_visualize(config, None)


if __name__ == "__main__":
    main(sys.argv[1:])

