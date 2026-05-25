from __future__ import annotations

import csv
from pathlib import Path

from src.common.models import Comment


CSV_FIELDS = [
    "platform",
    "source_id",
    "content",
    "published_at",
    "user_name",
    "like_count",
    "url",
    "language",
]


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_comments(path: Path, comments: list[Comment]) -> None:
    ensure_parent(path)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for comment in comments:
            writer.writerow(comment.to_row())

