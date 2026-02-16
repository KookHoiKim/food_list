from __future__ import annotations

import re
from datetime import date, timedelta

CATEGORY_DEFAULT_DAYS: dict[str, int] = {
    "dairy": 7,
    "meat": 3,
    "veg": 5,
    "frozen": 30,
    "other": 7,
}

CATEGORY_STORAGE: dict[str, str] = {
    "dairy": "냉장",
    "meat": "냉장",
    "veg": "냉장",
    "frozen": "냉동",
    "other": "실온",
}

_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "frozen": (
        "냉동",
        "아이스",
        "만두",
        "냉동식품",
        "냉동피자",
    ),
    "dairy": (
        "우유",
        "치즈",
        "요거트",
        "요구르트",
        "버터",
        "생크림",
    ),
    "meat": (
        "소고기",
        "돼지고기",
        "닭",
        "오리",
        "삼겹",
        "목살",
        "베이컨",
        "햄",
    ),
    "veg": (
        "양파",
        "감자",
        "당근",
        "대파",
        "상추",
        "토마토",
        "오이",
        "브로콜리",
        "버섯",
        "배추",
        "파프리카",
        "채소",
    ),
}


def normalize_name(name_raw: str, *, remove_parentheses: bool = True) -> str:
    """Normalize raw item name into a core noun-ish text using simple rules."""
    text = name_raw.strip()
    if remove_parentheses:
        text = re.sub(r"\([^)]*\)", " ", text)
        text = re.sub(r"\[[^\]]*\]", " ", text)

    # Remove obvious quantity/capacity hints from normalized name.
    text = re.sub(r"\b\d+(?:\.\d+)?\s?(?:kg|g|mg|l|ml|L|ML)\b", " ", text)
    text = re.sub(r"\b(?:x|X|×)\s?\d+\b", " ", text)
    text = re.sub(r"\b\d+\s?(?:개|팩|봉|병|캔|입)\b", " ", text)
    text = re.sub(r"\b\d+(?:\.\d+)?\b", " ", text)

    text = re.sub(r"[_\-/,]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text or name_raw.strip()


def categorize_item(name_raw: str, name_norm: str | None = None) -> tuple[str, str, int]:
    """Return (category, storage, default_days) using keyword-based rules."""
    target = f"{name_raw} {name_norm or ''}".lower()

    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(keyword.lower() in target for keyword in keywords):
            return category, CATEGORY_STORAGE[category], CATEGORY_DEFAULT_DAYS[category]

    category = "other"
    return category, CATEGORY_STORAGE[category], CATEGORY_DEFAULT_DAYS[category]


def estimate_expiry(purchase_date: date, default_days: int) -> date:
    return purchase_date + timedelta(days=default_days)
