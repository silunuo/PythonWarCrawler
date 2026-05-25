from __future__ import annotations

import time
from typing import Any

import requests

from src.common.config import AppConfig
from src.common.models import Comment, clean_content, iso_from_unix


class BilibiliCrawler:
    platform = "Bilibili"

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": config.get("request", "user_agent", default="Mozilla/5.0"),
                "Accept": "application/json,text/plain,*/*",
                "Referer": "https://search.bilibili.com/",
            }
        )
        self.proxies = config.proxies
        self.timeout = int(config.get("request", "timeout", default=15))
        self.delay = float(config.get("request", "delay_seconds", default=1.0))
        self.max_retries = int(config.get("request", "max_retries", default=3))

    def crawl(self, target: int, smoke: bool = False) -> list[Comment]:
        comments: list[Comment] = []
        seen: set[str] = set()
        queries = self.config.get("crawl", "queries_cn", default=[])
        search_pages = 1 if smoke else int(self.config.get("crawl", "bilibili", "search_pages", default=5))
        comment_pages = 1 if smoke else int(
            self.config.get("crawl", "bilibili", "comment_pages_per_video", default=5)
        )
        page_size = int(self.config.get("crawl", "bilibili", "page_size", default=20))

        for query in queries:
            for page in range(1, search_pages + 1):
                videos = self._search_videos(query, page)
                for video in videos:
                    aid = video.get("aid")
                    bvid = video.get("bvid") or ""
                    if not aid:
                        continue
                    video_url = f"https://www.bilibili.com/video/{bvid}/" if bvid else ""
                    video_comments = self._fetch_video_comments(
                        aid=aid,
                        video_url=video_url,
                        page_size=page_size,
                        page_limit=comment_pages,
                    )
                    for comment in video_comments:
                        if comment.source_id in seen:
                            continue
                        seen.add(comment.source_id)
                        comments.append(comment)
                        if len(comments) >= target:
                            return comments
                self._sleep(smoke)
        return comments

    def _search_videos(self, query: str, page: int) -> list[dict[str, Any]]:
        url = "https://api.bilibili.com/x/web-interface/search/type"
        params = {
            "search_type": "video",
            "keyword": query,
            "page": page,
        }
        data = self._get_json(url, params)
        if not data or data.get("code") != 0:
            return []
        return data.get("data", {}).get("result", []) or []

    def _fetch_video_comments(
        self,
        aid: int,
        video_url: str,
        page_size: int,
        page_limit: int,
    ) -> list[Comment]:
        result: list[Comment] = []
        for page in range(1, page_limit + 1):
            url = "https://api.bilibili.com/x/v2/reply"
            params = {
                "oid": aid,
                "type": 1,
                "sort": 2,
                "pn": page,
                "ps": page_size,
            }
            data = self._get_json(url, params, referer=video_url or "https://www.bilibili.com/")
            if not data or data.get("code") != 0:
                break
            replies = data.get("data", {}).get("replies") or []
            if not replies:
                break
            for reply in replies:
                parsed = self._parse_reply(reply, aid, video_url)
                if parsed:
                    result.append(parsed)
                for child in reply.get("replies") or []:
                    child_parsed = self._parse_reply(child, aid, video_url)
                    if child_parsed:
                        result.append(child_parsed)
            self._sleep(False)
        return result

    def _parse_reply(self, reply: dict[str, Any], aid: int, video_url: str) -> Comment | None:
        content = clean_content(reply.get("content", {}).get("message", ""))
        if not content:
            return None
        rpid = reply.get("rpid") or reply.get("rpid_str") or ""
        member = reply.get("member") or {}
        return Comment(
            platform=self.platform,
            source_id=f"bilibili:{rpid or aid}:{content[:30]}",
            content=content,
            published_at=iso_from_unix(reply.get("ctime")),
            user_name=member.get("uname", ""),
            like_count=reply.get("like", 0),
            url=video_url,
            language="zh",
        )

    def _get_json(self, url: str, params: dict[str, Any], referer: str | None = None) -> dict[str, Any] | None:
        headers = {}
        if referer:
            headers["Referer"] = referer
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.get(
                    url,
                    params=params,
                    headers=headers,
                    proxies=self.proxies,
                    timeout=self.timeout,
                )
                if response.status_code == 200:
                    return response.json()
                print(f"[Bilibili] HTTP {response.status_code}: {url}")
            except requests.RequestException as exc:
                print(f"[Bilibili] request failed {attempt}/{self.max_retries}: {exc}")
            self._sleep(False)
        return None

    def _sleep(self, smoke: bool) -> None:
        time.sleep(min(self.delay, 0.2) if smoke else self.delay)

