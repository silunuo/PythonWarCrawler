from __future__ import annotations

import time
from typing import Any

import requests

from src.common.config import AppConfig
from src.common.models import Comment, clean_content, iso_from_unix


class RedditCrawler:
    platform = "Reddit"

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "python-course-project/1.0",
                "Accept": "application/json,text/plain,*/*",
            }
        )
        self.proxies = config.proxies
        self.timeout = int(config.get("request", "timeout", default=15))
        self.delay = float(config.get("request", "delay_seconds", default=1.0))
        self.max_retries = int(config.get("request", "max_retries", default=3))

    def crawl(self, target: int, smoke: bool = False) -> list[Comment]:
        comments = self._crawl_pullpush(target, smoke)
        if len(comments) >= target or comments:
            return comments[:target]
        return self._crawl_reddit_json(target, smoke)

    def _crawl_pullpush(self, target: int, smoke: bool) -> list[Comment]:
        result: list[Comment] = []
        seen: set[str] = set()
        queries = self.config.get("crawl", "queries_en", default=[])
        page_size = min(25, int(self.config.get("crawl", "reddit", "page_size", default=100))) if smoke else int(
            self.config.get("crawl", "reddit", "page_size", default=100)
        )
        pages_per_query = 1 if smoke else int(self.config.get("crawl", "reddit", "pages_per_query", default=6))
        url = "https://api.pullpush.io/reddit/search/comment/"

        for query in queries:
            before: int | None = None
            for _ in range(pages_per_query):
                params: dict[str, Any] = {
                    "q": query,
                    "size": page_size,
                    "sort": "desc",
                    "sort_type": "created_utc",
                }
                if before:
                    params["before"] = before
                data = self._get_json(url, params)
                rows = data.get("data", []) if data else []
                if not rows:
                    break
                min_time: int | None = None
                for row in rows:
                    comment = self._parse_pullpush(row)
                    if not comment or comment.source_id in seen:
                        continue
                    seen.add(comment.source_id)
                    result.append(comment)
                    created = row.get("created_utc")
                    if isinstance(created, (int, float)):
                        min_time = int(created) if min_time is None else min(min_time, int(created))
                    if len(result) >= target:
                        return result
                if min_time:
                    before = min_time - 1
                self._sleep(smoke)
        return result

    def _crawl_reddit_json(self, target: int, smoke: bool) -> list[Comment]:
        result: list[Comment] = []
        seen: set[str] = set()
        for query in self.config.get("crawl", "queries_en", default=[]):
            posts = self._search_posts(query, limit=5 if smoke else 20)
            for post in posts:
                post_id = post.get("id")
                if not post_id:
                    continue
                for row in self._fetch_post_comments(post_id):
                    comment = self._parse_reddit_comment(row)
                    if not comment or comment.source_id in seen:
                        continue
                    seen.add(comment.source_id)
                    result.append(comment)
                    if len(result) >= target:
                        return result
                self._sleep(smoke)
        return result

    def _parse_pullpush(self, row: dict[str, Any]) -> Comment | None:
        content = clean_content(row.get("body", ""))
        if not content:
            return None
        permalink = row.get("permalink") or ""
        url = f"https://www.reddit.com{permalink}" if permalink.startswith("/") else permalink
        return Comment(
            platform=self.platform,
            source_id=f"reddit:{row.get('id', '')}",
            content=content,
            published_at=iso_from_unix(row.get("created_utc")),
            user_name=row.get("author", ""),
            like_count=row.get("score", 0),
            url=url,
            language="en",
        )

    def _parse_reddit_comment(self, row: dict[str, Any]) -> Comment | None:
        if row.get("kind") != "t1":
            return None
        data = row.get("data", {})
        content = clean_content(data.get("body", ""))
        if not content:
            return None
        permalink = data.get("permalink") or ""
        url = f"https://www.reddit.com{permalink}" if permalink.startswith("/") else permalink
        return Comment(
            platform=self.platform,
            source_id=f"reddit:{data.get('id', '')}",
            content=content,
            published_at=iso_from_unix(data.get("created_utc")),
            user_name=data.get("author", ""),
            like_count=data.get("score", 0),
            url=url,
            language="en",
        )

    def _search_posts(self, query: str, limit: int) -> list[dict[str, Any]]:
        data = self._get_json("https://www.reddit.com/search.json", {"q": query, "limit": limit, "sort": "new"})
        children = data.get("data", {}).get("children", []) if data else []
        return [child.get("data", {}) for child in children]

    def _fetch_post_comments(self, post_id: str) -> list[dict[str, Any]]:
        data = self._get_json(f"https://www.reddit.com/comments/{post_id}.json", {"limit": 100})
        if not isinstance(data, list) or len(data) < 2:
            return []
        comments = data[1].get("data", {}).get("children", [])
        flat: list[dict[str, Any]] = []
        for item in comments:
            self._flatten_reddit_tree(item, flat)
        return flat

    def _flatten_reddit_tree(self, item: dict[str, Any], flat: list[dict[str, Any]]) -> None:
        if item.get("kind") != "t1":
            return
        flat.append(item)
        replies = item.get("data", {}).get("replies")
        if isinstance(replies, dict):
            for child in replies.get("data", {}).get("children", []):
                self._flatten_reddit_tree(child, flat)

    def _get_json(self, url: str, params: dict[str, Any]) -> Any:
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.get(url, params=params, proxies=self.proxies, timeout=self.timeout)
                if response.status_code == 200:
                    return response.json()
                print(f"[Reddit] HTTP {response.status_code}: {url}")
            except requests.RequestException as exc:
                print(f"[Reddit] request failed {attempt}/{self.max_retries}: {exc}")
            self._sleep(False)
        return None

    def _sleep(self, smoke: bool) -> None:
        time.sleep(min(self.delay, 0.2) if smoke else self.delay)

