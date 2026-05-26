from __future__ import annotations

import asyncio
from typing import Any

import aiotieba

from src.common.config import AppConfig
from src.common.date_range import DateRange, datetime_from_unix, parse_iso_datetime
from src.common.models import Comment, clean_content, iso_from_unix


class TiebaCrawler:
    platform = "Tieba"

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.config.apply_proxy_env()
        self.delay = float(config.get("request", "delay_seconds", default=1.0))
        self.keywords = ["伊朗", "以色列", "美国", "美以伊", "冲突", "战争", "反击"]

    def crawl(self, target: int, smoke: bool = False, date_range: DateRange | None = None) -> list[Comment]:
        return asyncio.run(self._crawl_async(target, smoke, date_range))

    async def _crawl_async(self, target: int, smoke: bool, date_range: DateRange | None) -> list[Comment]:
        result: list[Comment] = []
        seen: set[str] = set()
        forums = self.config.get("crawl", "tieba_forums", default=[])
        queries = self.config.get("crawl", "queries_cn", default=[])
        thread_pages = 1 if smoke else int(self.config.get("crawl", "tieba", "thread_pages_per_forum", default=4))
        post_pages = 1 if smoke else int(self.config.get("crawl", "tieba", "post_pages_per_thread", default=4))
        page_size = int(self.config.get("crawl", "tieba", "page_size", default=30))

        async with aiotieba.Client() as client:
            thread_titles = await self._find_threads(client, forums, queries, thread_pages, page_size, smoke, date_range)
            for tid, title in thread_titles.items():
                for page in range(1, post_pages + 1):
                    try:
                        posts = await client.get_posts(
                            int(tid),
                            pn=page,
                            rn=page_size,
                            sort=0,
                            with_comments=True,
                            comment_rn=20,
                        )
                    except Exception as exc:
                        print(f"[Tieba] get_posts failed tid={tid}: {exc}")
                        break
                    if not posts:
                        break
                    for post in posts:
                        for comment in self._parse_post_with_comments(post, title):
                            comment_dt = parse_iso_datetime(comment.published_at)
                            if date_range and not date_range.contains_datetime(comment_dt):
                                continue
                            if comment.source_id in seen:
                                continue
                            if not self._is_related(comment.content, title):
                                continue
                            seen.add(comment.source_id)
                            result.append(comment)
                            if len(result) >= target:
                                return result
                    await self._sleep(smoke)
        return result

    async def _find_threads(
        self,
        client: aiotieba.Client,
        forums: list[str],
        queries: list[str],
        thread_pages: int,
        page_size: int,
        smoke: bool,
        date_range: DateRange | None,
    ) -> dict[int, str]:
        threads: dict[int, str] = {}
        for forum in forums:
            for query in queries:
                for page in range(1, thread_pages + 1):
                    try:
                        rows = await client.search_post(
                            forum,
                            query,
                            pn=page,
                            rn=page_size,
                            query_type=1,
                            only_thread=True,
                        )
                    except Exception as exc:
                        print(f"[Tieba] search failed forum={forum} query={query}: {exc}")
                        break
                    for row in rows or []:
                        row_dt = datetime_from_unix(getattr(row, "create_time", ""))
                        if date_range and not date_range.contains_datetime(row_dt):
                            continue
                        tid = getattr(row, "tid", 0)
                        title = clean_content(getattr(row, "title", "") or getattr(row, "text", ""))
                        if tid and self._is_related(title, query):
                            threads[int(tid)] = title
                    await self._sleep(smoke)
            for page in range(1, min(thread_pages, 2 if smoke else thread_pages) + 1):
                try:
                    rows = await client.get_threads(forum, pn=page, rn=page_size, sort=1)
                except Exception as exc:
                    print(f"[Tieba] forum failed forum={forum}: {exc}")
                    break
                for row in rows or []:
                    row_dt = datetime_from_unix(getattr(row, "create_time", ""))
                    if date_range and not date_range.contains_datetime(row_dt):
                        continue
                    tid = getattr(row, "tid", 0)
                    title = clean_content(getattr(row, "title", "") or getattr(row, "text", ""))
                    if tid and self._is_related(title, ""):
                        threads[int(tid)] = title
                await self._sleep(smoke)
        return threads

    def _parse_post_with_comments(self, post: Any, title: str) -> list[Comment]:
        parsed: list[Comment] = []
        content = clean_content(getattr(post, "text", ""))
        tid = getattr(post, "tid", "")
        pid = getattr(post, "pid", "")
        if content:
            parsed.append(
                Comment(
                    platform=self.platform,
                    source_id=f"tieba:{pid}",
                    content=content,
                    published_at=iso_from_unix(getattr(post, "create_time", "")),
                    user_name=self._user_name(getattr(post, "user", None)),
                    like_count=getattr(post, "agree", 0),
                    url=f"https://tieba.baidu.com/p/{tid}?pid={pid}#pid{pid}",
                    language="zh",
                )
            )
        for comment in getattr(post, "comments", []) or []:
            child_content = clean_content(getattr(comment, "text", ""))
            child_pid = getattr(comment, "pid", "")
            if not child_content:
                continue
            parsed.append(
                Comment(
                    platform=self.platform,
                    source_id=f"tieba:{tid}:{child_pid}",
                    content=child_content,
                    published_at=iso_from_unix(getattr(comment, "create_time", "")),
                    user_name=self._user_name(getattr(comment, "user", None)),
                    like_count=getattr(comment, "agree", 0),
                    url=f"https://tieba.baidu.com/p/{tid}?pid={pid}#pid{pid}",
                    language="zh",
                )
            )
        return parsed

    def _user_name(self, user: Any) -> str:
        if not user:
            return ""
        for name in ("show_name", "user_name", "nick_name", "nick_name_new"):
            value = getattr(user, name, "")
            if value:
                return clean_content(value)
        return ""

    def _is_related(self, content: str, extra: str) -> bool:
        text = f"{content} {extra}"
        return any(keyword in text for keyword in self.keywords)

    async def _sleep(self, smoke: bool) -> None:
        await asyncio.sleep(min(self.delay, 0.2) if smoke else self.delay)
