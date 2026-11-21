"""Baseline date/time parser.

``dateparser`` silently fills a missing date with today, so the time of day is found with our own
regex and ``dateparser`` is used only to find a date in what remains. That keeps "no date given"
detectable, which the robot needs for its counter-question. A time from now ("in 5 minutes")
gives both the date and the time.
"""

from __future__ import annotations

import re
from datetime import datetime, time, timedelta
from typing import Literal

from dateparser.search import search_dates
from pydantic import BaseModel

from pasr.perception.protocols import ParsedDateTime
from pasr.settings.tiers import setting

_TIME = re.compile(
    r"\b(?:at\s+)?(?:"
    r"(?P<h12>\d{1,2})(?::(?P<m12>\d{2}))?\s*(?P<ampm>a\.?m\.?|p\.?m\.?)"
    r"|(?P<h24>\d{1,2})[:.](?P<m24>\d{2})"
    r"|(?P<word>noon|midday|midnight)"
    r")(?![\w:])",
    re.IGNORECASE,
)
_LEADING = re.compile(
    r"^\s*(?:(?:please\s+)?(?:set|add|create|make)\s+(?:a\s+|me\s+a\s+)?reminder\s+"
    r"(?:for|to|about|that)?\s*|remind\s+me\s+(?:to|about|of|that)?\s*|reminder\s*:?\s*)",
    re.IGNORECASE,
)
_TRAILING = re.compile(r"(?:\s+(?:at|on|for|in|by|next|this|the))+\s*$", re.IGNORECASE)
_MONTH_WORDS = {"may", "march", "june", "august", "sun", "sat", "wed"}
"""Month/day names that are also everyday words; ignored when they appear on their own."""
_COUNTS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "fifteen": 15, "twenty": 20, "thirty": 30,
}  # fmt: skip
"""Number words speech-to-text may write instead of digits."""
_FROM_NOW = re.compile(
    rf"\bin\s+(?:(?P<count>\d+|{'|'.join(_COUNTS)})\s+(?P<unit>min(?:ute)?s?|h(?:ou)?rs?)"
    r"|(?P<half>half\s+an\s+hour))\b",
    re.IGNORECASE,
)


def _extract_from_now(text: str) -> tuple[timedelta | None, str]:
    """A time from now, such as "in 5 minutes" or "in an hour"."""
    match = _FROM_NOW.search(text)
    if match is None:
        return None, text
    if match.group("half"):
        offset = timedelta(minutes=30)
    else:
        count = match.group("count").lower()
        amount = int(count) if count.isdigit() else _COUNTS[count]
        hours = match.group("unit").lower().startswith("h")
        offset = timedelta(hours=amount) if hours else timedelta(minutes=amount)
    return offset, (text[: match.start()] + " " + text[match.end() :])


def _title(remainder: str, text: str) -> str:
    title = _TRAILING.sub("", _LEADING.sub("", " ".join(remainder.split())))
    title = title.strip(" ,.;:!?") or text.strip()
    return title[:1].upper() + title[1:]


def _extract_time(text: str) -> tuple[time | None, str]:
    match = _TIME.search(text)
    if match is None:
        return None, text
    if word := match.group("word"):
        parsed = time(0, 0) if word.lower() == "midnight" else time(12, 0)
    elif match.group("h12"):
        hour, minute = int(match.group("h12")), int(match.group("m12") or 0)
        if not (1 <= hour <= 12 and minute < 60):
            return None, text
        is_pm = match.group("ampm").lower().startswith("p")
        parsed = time(hour % 12 + (12 if is_pm else 0), minute)
    else:
        hour, minute = int(match.group("h24")), int(match.group("m24"))
        if not (hour < 24 and minute < 60):
            return None, text
        parsed = time(hour, minute)
    return parsed, (text[: match.start()] + " " + text[match.end() :])


class DateparserDateTimeParser:
    class Params(BaseModel):
        date_order: Literal["DMY", "MDY", "YMD"] = setting(
            "DMY",
            tier="advanced",
            description="How numeric dates like 12/11 are read (DMY = 12 November).",
        )
        languages: list[str] = setting(
            tier="advanced",
            default_factory=lambda: ["en"],
            min_length=1,
            description="Languages dateparser may use.",
        )

    def __init__(self, params: Params) -> None:
        self.params = params

    def parse(self, text: str, now: datetime) -> ParsedDateTime:
        offset, remainder = _extract_from_now(text)
        if offset is not None:
            at = (now + offset).replace(microsecond=0)
            return ParsedDateTime(title=_title(remainder, text), date=at.date(), time=at.time())
        parsed_time, remainder = _extract_time(text)
        found = search_dates(
            remainder,
            languages=self.params.languages,
            settings={
                "PREFER_DATES_FROM": "future",
                "RELATIVE_BASE": now.replace(tzinfo=None),
                "DATE_ORDER": self.params.date_order,
                "RETURN_AS_TIMEZONE_AWARE": False,
            },
        )
        dates = [
            (substring, value)
            for substring, value in found or []
            if substring.strip().lower() not in _MONTH_WORDS
        ]
        for substring, _ in dates:
            remainder = remainder.replace(substring, " ", 1)
        return ParsedDateTime(
            title=_title(remainder, text),
            date=dates[0][1].date() if dates else None,
            time=parsed_time,
        )
