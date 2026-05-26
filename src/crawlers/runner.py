from __future__ import annotations

from math import ceil

from src.common.config import AppConfig
from src.common.date_range import DateRange
from src.common.models import Comment, dedupe_comments
from src.crawlers.bilibili import BilibiliCrawler
from src.crawlers.reddit import RedditCrawler
from src.crawlers.tieba import TiebaCrawler
from src.crawlers.youtube import YouTubeCrawler


def crawl_all(
    config: AppConfig,
    target_total: int,
    smoke: bool = False,
    date_range: DateRange | None = None,
) -> list[Comment]:
    smoke_target = int(config.get("crawl", "smoke_target_per_platform", default=10))
    per_platform = smoke_target if smoke else ceil(target_total / 4)
    comments: list[Comment] = []

    crawlers = [
        BilibiliCrawler(config),
        TiebaCrawler(config),
        RedditCrawler(config),
        YouTubeCrawler(config),
    ]

    for crawler in crawlers:
        target = per_platform
        if not smoke and crawler.platform == "YouTube":
            target = max(per_platform, target_total - len(dedupe_comments(comments)))
        print(f"[crawl] {crawler.platform} target={target}")
        rows = crawler.crawl(target=target, smoke=smoke, date_range=date_range)
        comments.extend(rows)
        comments = dedupe_comments(comments)
        print(f"[crawl] {crawler.platform} got={len(rows)} total={len(comments)}")
        if smoke:
            continue
        if len(comments) >= target_total and len({row.platform for row in comments}) >= 4:
            break

    return dedupe_comments(comments)
