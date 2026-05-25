from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import jieba
import pandas as pd
from snownlp import SnowNLP

from src.common.io import ensure_parent
from src.common.models import clean_content, detect_language


TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z'-]{1,}|[\u4e00-\u9fff]+")

POSITIVE_WORDS = {
    "peace",
    "safe",
    "support",
    "hope",
    "agree",
    "protect",
    "stable",
    "calm",
    "ceasefire",
    "solution",
    "justice",
}
NEGATIVE_WORDS = {
    "war",
    "attack",
    "bomb",
    "killed",
    "death",
    "dead",
    "bad",
    "worse",
    "fear",
    "danger",
    "hate",
    "crisis",
    "terror",
    "risk",
}

CATEGORY_RULES = {
    "军事行动": {"导弹", "空袭", "袭击", "反击", "打击", "军队", "无人机", "missile", "strike", "attack", "drone"},
    "战争影响": {"石油", "经济", "难民", "伤亡", "死亡", "市场", "能源", "oil", "price", "economy", "refugee", "death"},
    "国际关系": {"美国", "中国", "俄罗斯", "联合国", "中东", "外交", "usa", "america", "china", "russia", "un", "nato"},
    "立场评价": {"支持", "反对", "正义", "侵略", "责任", "骗子", "support", "oppose", "justice", "blame", "fault"},
    "和平停火": {"和平", "停火", "谈判", "协议", "peace", "ceasefire", "talk", "deal", "agreement"},
}


def analyze_comments(raw_path: Path, clean_path: Path, summary_path: Path) -> dict[str, Any]:
    if not raw_path.exists():
        raise FileNotFoundError(f"raw comments not found: {raw_path}")
    df = pd.read_csv(raw_path, encoding="utf-8-sig").fillna("")
    if df.empty:
        raise ValueError("raw comments csv is empty")

    df["content"] = df["content"].map(clean_content)
    df = df[df["content"].map(_is_valid_content)].copy()
    df = df.drop_duplicates(subset=["platform", "source_id"])
    df = df.drop_duplicates(subset=["content", "user_name"])
    df["language"] = df.apply(
        lambda row: row["language"] if row.get("language") in {"zh", "en"} else detect_language(row["content"]),
        axis=1,
    )

    stopwords = _load_stopwords(Path(__file__).resolve().parents[2])
    df["tokens_list"] = df.apply(lambda row: _tokenize(row["content"], row["language"], stopwords), axis=1)
    df = df[df["tokens_list"].map(bool)].copy()
    df["tokens"] = df["tokens_list"].map(lambda tokens: " ".join(tokens))
    df["sentiment_score"] = df.apply(lambda row: _sentiment(row["content"], row["language"]), axis=1)
    df["sentiment"] = df["sentiment_score"].map(_sentiment_label)
    df["category"] = df.apply(lambda row: _category(row["content"], row["tokens_list"]), axis=1)
    df["published_date"] = _published_dates(df["published_at"])

    keyword_scores = _tfidf_keywords(df["tokens_list"].tolist())
    summary = _build_summary(df, keyword_scores)

    ensure_parent(clean_path)
    export_df = df.drop(columns=["tokens_list"])
    export_df.to_csv(clean_path, index=False, encoding="utf-8-sig")
    ensure_parent(summary_path)
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"[analyze] saved={clean_path}")
    print(f"[analyze] summary={summary_path}")
    return summary


def _load_stopwords(project_root: Path) -> dict[str, set[str]]:
    resources = project_root / "resources"
    return {
        "zh": _read_stopwords(resources / "stopwords_zh.txt"),
        "en": _read_stopwords(resources / "stopwords_en.txt"),
    }


def _read_stopwords(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {line.strip().lower() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def _is_valid_content(text: str) -> bool:
    if len(text) < 4:
        return False
    useful = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", text)
    return len(useful) >= max(3, len(text) * 0.35)


def _tokenize(text: str, language: str, stopwords: dict[str, set[str]]) -> list[str]:
    if language == "zh":
        raw_tokens = jieba.lcut(text)
        tokens = [token.strip().lower() for token in raw_tokens]
        return [
            token
            for token in tokens
            if token and token not in stopwords["zh"] and re.search(r"[\u4e00-\u9fffA-Za-z0-9]", token)
        ]
    tokens = [token.group(0).lower() for token in TOKEN_RE.finditer(text)]
    return [token for token in tokens if token not in stopwords["en"] and len(token) > 2]


def _sentiment(text: str, language: str) -> float:
    if language == "zh":
        try:
            return float(SnowNLP(text).sentiments)
        except Exception:
            return 0.5
    tokens = [token.group(0).lower() for token in TOKEN_RE.finditer(text)]
    if not tokens:
        return 0.5
    pos = sum(1 for token in tokens if token in POSITIVE_WORDS)
    neg = sum(1 for token in tokens if token in NEGATIVE_WORDS)
    score = 0.5 + (pos - neg) / max(8, len(tokens))
    return max(0.0, min(1.0, score))


def _sentiment_label(score: float) -> str:
    if score >= 0.6:
        return "正面"
    if score <= 0.4:
        return "负面"
    return "中性"


def _category(text: str, tokens: list[str]) -> str:
    lower_text = text.lower()
    token_set = set(tokens)
    for category, words in CATEGORY_RULES.items():
        if token_set & words:
            return category
        if any(word in lower_text for word in words):
            return category
    return "其他讨论"


def _published_dates(values: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(values, errors="coerce", utc=True)
    return parsed.dt.strftime("%Y-%m-%d").fillna("")


def _tfidf_keywords(docs: list[list[str]], top_n: int = 80) -> list[dict[str, Any]]:
    doc_count = len(docs)
    df_counter: Counter[str] = Counter()
    for tokens in docs:
        df_counter.update(set(tokens))

    scores: defaultdict[str, float] = defaultdict(float)
    for tokens in docs:
        tf_counter = Counter(tokens)
        for word, count in tf_counter.items():
            if _skip_keyword(word):
                continue
            idf = math.log((doc_count + 1) / (df_counter[word] + 1)) + 1
            scores[word] += (1 + math.log(count)) * idf

    return [
        {"word": word, "score": round(score, 4)}
        for word, score in sorted(scores.items(), key=lambda item: item[1], reverse=True)[:top_n]
    ]


def _skip_keyword(word: str) -> bool:
    if len(word) <= 1:
        return True
    if re.fullmatch(r"\d+", word):
        return True
    if re.fullmatch(r"[a-z]", word):
        return True
    return False


def _build_summary(df: pd.DataFrame, keyword_scores: list[dict[str, Any]]) -> dict[str, Any]:
    platform_counts = _series_counts(df["platform"])
    sentiment_counts = _series_counts(df["sentiment"])
    category_counts = _series_counts(df["category"])
    date_counts = _series_counts(df[df["published_date"] != ""]["published_date"])
    language_counts = _series_counts(df["language"])

    return {
        "total": int(len(df)),
        "platform_counts": platform_counts,
        "sentiment_counts": sentiment_counts,
        "category_counts": category_counts,
        "language_counts": language_counts,
        "date_counts": date_counts,
        "top_keywords": keyword_scores,
        "avg_sentiment_score": round(float(df["sentiment_score"].mean()), 4) if not df.empty else 0,
    }


def _series_counts(series: pd.Series) -> dict[str, int]:
    counts = series.value_counts().to_dict()
    return {str(key): int(value) for key, value in counts.items()}
