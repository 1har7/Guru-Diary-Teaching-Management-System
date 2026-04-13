from __future__ import annotations

import hashlib
from datetime import date


QUOTES = [
    "Teaching is the one profession that creates all other professions.",
    "A good teacher can inspire hope, ignite the imagination, and instill a love of learning.",
    "The art of teaching is the art of assisting discovery.",
    "The best teachers are those who show you where to look but don’t tell you what to see.",
    "Every student can learn—just not on the same day or in the same way.",
    "Small progress each day adds up to big results.",
    "Clarity beats complexity—teach what matters, then practice it.",
    "Your patience today becomes someone’s confidence tomorrow.",
    "A lesson that lands is better than a syllabus that’s rushed.",
    "Make it simple, make it engaging, make it stick.",
]


def quote_for_day(d: date) -> str:
    """
    Deterministic per-date quote selection (stable for the whole day).
    Avoid Python's built-in hash() because it is randomized per process.
    """
    if not QUOTES:
        return ""
    h = hashlib.md5(d.isoformat().encode("utf-8")).hexdigest()
    idx = int(h[:8], 16) % len(QUOTES)
    return QUOTES[idx]

