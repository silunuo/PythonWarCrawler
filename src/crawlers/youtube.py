from __future__ import annotations

import json
import re
import time
from typing import Any

import requests

from src.common.config import AppConfig
from src.common.date_range import DateRange
from src.common.models import Comment, clean_content, stable_id


class YouTubeCrawler:
    platform = "YouTube"

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": config.get("request", "user_agent", default="Mozilla/5.0"),
                "Accept": "text/html,application/json,text/plain,*/*",
                "Accept-Language": "en-US,en;q=0.9",
                "Origin": "https://www.youtube.com",
            }
        )
        self.proxies = config.proxies
        self.timeout = int(config.get("request", "timeout", default=15))
        self.delay = float(config.get("request", "delay_seconds", default=1.0))
        self.max_retries = int(config.get("request", "max_retries", default=3))

    def crawl(self, target: int, smoke: bool = False, date_range: DateRange | None = None) -> list[Comment]:
        comments: list[Comment] = []
        seen: set[str] = set()
        queries = self.config.get("crawl", "queries_en", default=[])
        search_pages = 1 if smoke else int(self.config.get("crawl", "youtube", "search_pages", default=2))
        videos_per_query = int(self.config.get("crawl", "youtube", "videos_per_query", default=8))
        comment_pages = 1 if smoke else int(
            self.config.get("crawl", "youtube", "comment_pages_per_video", default=4)
        )

        for query in queries:
            videos = self._search_videos(query, search_pages, videos_per_query)
            for video_id in videos:
                for comment in self._fetch_video_comments(video_id, comment_pages):
                    if comment.source_id in seen:
                        continue
                    seen.add(comment.source_id)
                    comments.append(comment)
                    if len(comments) >= target:
                        return comments
                self._sleep(smoke)
        return comments

    def _search_videos(self, query: str, search_pages: int, limit: int) -> list[str]:
        video_ids: list[str] = []
        seen: set[str] = set()
        continuation: str | None = None
        context: dict[str, Any] | None = None
        innertube_key: str | None = None

        for page in range(search_pages):
            if page == 0:
                html = self._get_text("https://www.youtube.com/results", {"search_query": query})
                if not html:
                    break
                for video_id in re.findall(r'"videoId":"([^"]+)"', html):
                    if video_id not in seen:
                        seen.add(video_id)
                        video_ids.append(video_id)
                    if len(video_ids) >= limit:
                        return video_ids
                context, innertube_key = self._extract_context_and_key(html)
                continuation = self._first_continuation(html)
            elif continuation and context and innertube_key:
                data = self._post_youtubei("browse", innertube_key, context, {"continuation": continuation})
                if not data:
                    break
                for video_id in self._find_values(data, "videoId"):
                    if isinstance(video_id, str) and video_id not in seen:
                        seen.add(video_id)
                        video_ids.append(video_id)
                    if len(video_ids) >= limit:
                        return video_ids
                continuation = self._first_continuation_from_json(data)
            else:
                break
            self._sleep(False)
        return video_ids

    def _fetch_video_comments(self, video_id: str, page_limit: int) -> list[Comment]:
        watch_url = f"https://www.youtube.com/watch?v={video_id}"
        html = self._get_text("https://www.youtube.com/watch", {"v": video_id})
        if not html:
            return []

        context, innertube_key = self._extract_context_and_key(html)
        if not context or not innertube_key:
            return self._parse_comments_from_json_text(html, video_id, watch_url)

        comments = self._parse_comments_from_json_text(html, video_id, watch_url)
        seen = {comment.source_id for comment in comments}
        continuations = self._comment_continuations(html)

        for continuation in continuations[:page_limit]:
            data = self._post_youtubei("next", innertube_key, context, {"continuation": continuation})
            if not data:
                continue
            for comment in self._parse_comment_renderers(data, video_id, watch_url):
                if comment.source_id in seen:
                    continue
                seen.add(comment.source_id)
                comments.append(comment)
            next_cursor = self._first_continuation_from_json(data)
            for _ in range(max(0, page_limit - 1)):
                if not next_cursor:
                    break
                next_data = self._post_youtubei("next", innertube_key, context, {"continuation": next_cursor})
                if not next_data:
                    break
                for comment in self._parse_comment_renderers(next_data, video_id, watch_url):
                    if comment.source_id in seen:
                        continue
                    seen.add(comment.source_id)
                    comments.append(comment)
                next_cursor = self._first_continuation_from_json(next_data)
                self._sleep(False)
            if comments:
                break
            self._sleep(False)
        return comments

    def _parse_comments_from_json_text(self, text: str, video_id: str, watch_url: str) -> list[Comment]:
        result: list[Comment] = []
        for match in re.finditer(r"ytInitialData\s*=\s*(\{.*?\});", text):
            try:
                data = json.loads(match.group(1))
            except json.JSONDecodeError:
                continue
            result.extend(self._parse_comment_renderers(data, video_id, watch_url))
        return result

    def _parse_comment_renderers(self, data: Any, video_id: str, watch_url: str) -> list[Comment]:
        comments: list[Comment] = []
        for renderer in self._find_renderers(data, {"commentRenderer", "commentThreadRenderer"}):
            if "commentThreadRenderer" in renderer:
                renderer = renderer["commentThreadRenderer"].get("comment", {}).get("commentRenderer", {})
            elif "commentRenderer" in renderer:
                renderer = renderer["commentRenderer"]
            if not renderer:
                continue
            content = clean_content(self._runs_text(renderer.get("contentText")))
            if not content:
                continue
            comment_id = renderer.get("commentId") or stable_id(video_id, content, self._runs_text(renderer.get("authorText")))
            comments.append(
                Comment(
                    platform=self.platform,
                    source_id=f"youtube:{comment_id}",
                    content=content,
                    published_at=self._runs_text(renderer.get("publishedTimeText")),
                    user_name=self._runs_text(renderer.get("authorText")),
                    like_count=self._parse_like_count(self._runs_text(renderer.get("voteCount"))),
                    url=f"{watch_url}&lc={comment_id}",
                    language="en",
                )
            )
        return comments

    def _extract_context_and_key(self, html: str) -> tuple[dict[str, Any] | None, str | None]:
        key_match = re.search(r'"INNERTUBE_API_KEY":"([^"]+)"', html)
        cfg_match = re.search(r"ytcfg\.set\((\{.*?\})\);", html)
        innertube_key = key_match.group(1) if key_match else None
        context = None
        if cfg_match:
            try:
                cfg = json.loads(cfg_match.group(1))
                context = cfg.get("INNERTUBE_CONTEXT")
            except json.JSONDecodeError:
                context = None
        return context, innertube_key

    def _comment_continuations(self, html: str) -> list[str]:
        cursors = re.findall(r'"continuation":"([^"]+)"', html)
        preferred = [cursor for cursor in cursors if "comments" in cursor.lower() or "comment" in cursor.lower()]
        rest = [cursor for cursor in cursors if cursor not in preferred]
        return list(dict.fromkeys(preferred + rest))

    def _first_continuation(self, text: str) -> str | None:
        cursors = re.findall(r'"continuation":"([^"]+)"', text)
        return cursors[0] if cursors else None

    def _first_continuation_from_json(self, data: Any) -> str | None:
        for value in self._find_values(data, "continuation"):
            if isinstance(value, str):
                return value
        return None

    def _post_youtubei(
        self,
        endpoint: str,
        innertube_key: str,
        context: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        url = f"https://www.youtube.com/youtubei/v1/{endpoint}"
        body = {"context": context}
        body.update(payload)
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.post(
                    url,
                    params={"key": innertube_key},
                    json=body,
                    proxies=self.proxies,
                    timeout=self.timeout,
                )
                if response.status_code == 200:
                    return response.json()
                print(f"[YouTube] HTTP {response.status_code}: {url}")
            except requests.RequestException as exc:
                print(f"[YouTube] request failed {attempt}/{self.max_retries}: {exc}")
            self._sleep(False)
        return None

    def _get_text(self, url: str, params: dict[str, Any]) -> str:
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.get(url, params=params, proxies=self.proxies, timeout=self.timeout)
                if response.status_code == 200:
                    return response.text
                print(f"[YouTube] HTTP {response.status_code}: {url}")
            except requests.RequestException as exc:
                print(f"[YouTube] request failed {attempt}/{self.max_retries}: {exc}")
            self._sleep(False)
        return ""

    def _runs_text(self, value: Any) -> str:
        if isinstance(value, str):
            return clean_content(value)
        if not isinstance(value, dict):
            return ""
        if "simpleText" in value:
            return clean_content(value["simpleText"])
        runs = value.get("runs") or []
        return clean_content("".join(str(run.get("text", "")) for run in runs if isinstance(run, dict)))

    def _parse_like_count(self, text: str) -> int:
        value = text.lower().replace(",", "").strip()
        if not value:
            return 0
        multiplier = 1
        if value.endswith("k"):
            multiplier = 1000
            value = value[:-1]
        elif value.endswith("m"):
            multiplier = 1000000
            value = value[:-1]
        try:
            return int(float(value) * multiplier)
        except ValueError:
            return 0

    def _find_renderers(self, data: Any, names: set[str]) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        if isinstance(data, dict):
            for key, value in data.items():
                if key in names:
                    found.append({key: value})
                found.extend(self._find_renderers(value, names))
        elif isinstance(data, list):
            for item in data:
                found.extend(self._find_renderers(item, names))
        return found

    def _find_values(self, data: Any, name: str) -> list[Any]:
        found: list[Any] = []
        if isinstance(data, dict):
            for key, value in data.items():
                if key == name:
                    found.append(value)
                found.extend(self._find_values(value, name))
        elif isinstance(data, list):
            for item in data:
                found.extend(self._find_values(item, name))
        return found

    def _sleep(self, smoke: bool) -> None:
        time.sleep(min(self.delay, 0.2) if smoke else self.delay)
