"""Simple deterministic log classification."""

from __future__ import annotations

from typing import Dict, Iterable, List


def classify_text(text: str, patterns: Dict[str, List[str]]) -> str:
    lowered = text.lower()
    for category, terms in patterns.items():
        for term in terms:
            if term.lower() in lowered:
                return category
    if text.strip():
        return "assertion"
    return "unknown"


def classify_many(parts: Iterable[str], patterns: Dict[str, List[str]]) -> str:
    joined = "\n".join(part for part in parts if part)
    return classify_text(joined, patterns)

