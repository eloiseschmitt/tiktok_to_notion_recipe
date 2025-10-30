import re
from typing import Pattern, List

TIME_PATTERNS: List[Pattern[str]] = [
    re.compile(r"(?:(\d+)\s*h)?\s*(\d+)?\s*(?:min|mn|minutes?)", re.I),
    re.compile(r"(\d+)\s*h(?:eurs?)?", re.I)
]

TITLE_STOPWORDS_WORDS = {
    "recette", "recipe", "tiktok", "facile", "easy", "rapide", "quick",
    "pour", "sans", "astuce", "tips", "comment", "best"
}

TITLE_STOPWORDS_PHRASES = {"how to", "easy recipe"}

LIST_PREFIX_RE = re.compile(r"^\s*(?:[-\*\u2022]|\d+[\).])\s*")
