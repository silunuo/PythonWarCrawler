from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


_SPACE_RE = re.compile(r"\s+")
_TAG_RE = re.compile(r"<[^>]+>")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def clean_content(text: Any) -> str:
    if text is None:
        return ""
    value = str(text)
    value = _TAG_RE.sub("", value)
    value = value.replace("\u200b", " ").replace("\xa0", " ")
    value = _SPACE_RE.sub(" ", value)
    return value.strip()


def detect_language(text: str) -> str:
    cjk_count = len(_CJK_RE.findall(text))
    latin_count = len(re.findall(r"[A-Za-z]", text))
    return "zh" if cjk_count >= latin_count else "en"


def iso_from_unix(value: Any) -> str:
    try:
        timestamp = int(float(value))
    except (TypeError, ValueError):
        return ""
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


def stable_id(*parts: Any) -> str:
    raw = "|".join(clean_content(part) for part in parts)
    return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()


@dataclass
class Comment:
    platform: str
    source_id: str
    content: str
    published_at: str = ""
    user_name: str = ""
    like_count: int = 0
    url: str = ""
    language: str = ""

    def __post_init__(self) -> None:
        self.content = clean_content(self.content)
        self.user_name = clean_content(self.user_name)
        self.language = self.language or detect_language(self.content)
        if not self.source_id:
            self.source_id = f"{self.platform}:{stable_id(self.content, self.user_name, self.published_at)}"
        try:
            self.like_count = int(self.like_count or 0)
        except (TypeError, ValueError):
            self.like_count = 0

    def is_valid(self) -> bool:
        if len(self.content) < 4:
            return False
        lowered = self.content.lower()
        if lowered in {"[deleted]", "[removed]", "deleted", "removed"}:
            return False
        useful_chars = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", self.content)
        return len(useful_chars) >= max(3, len(self.content) * 0.35)

    def to_row(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "source_id": self.source_id,
            "content": self.content,
            "published_at": self.published_at,
            "user_name": self.user_name,
            "like_count": self.like_count,
            "url": self.url,
            "language": self.language,
        }


def dedupe_comments(comments: list[Comment]) -> list[Comment]:
    seen: set[str] = set()
    result: list[Comment] = []
    for comment in comments:
        if not comment.is_valid():
            continue
        key = comment.source_id or stable_id(comment.platform, comment.content, comment.user_name)
        if key in seen:
            continue
        seen.add(key)
        result.append(comment)
    return result

