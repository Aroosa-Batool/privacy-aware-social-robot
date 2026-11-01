from __future__ import annotations

import re

from pydantic import BaseModel

from pasr.perception.protocols import SensitivityResult
from pasr.settings.tiers import setting

DEFAULT_SENSITIVE = [
    "doctor", "dentist", "gp", "hospital", "clinic", "surgery", "therapy", "therapist",
    "psychiatrist", "psychologist", "counselling", "counseling", "medication", "medicine",
    "pills", "prescription", "diagnosis", "blood test", "test results", "vaccination",
    "pregnancy", "gynaecologist", "gynecologist", "std", "hiv", "rehab", "bank", "debt",
    "loan", "salary", "tax", "rent arrears", "password", "pin", "lawyer", "court", "divorce",
    "job interview", "visa",
]  # fmt: skip

DEFAULT_NON_SENSITIVE = [
    "groceries", "shopping", "laundry", "dishes", "plants", "water the", "call mum",
    "call mom", "birthday", "gym", "walk", "meeting", "lecture", "class",
]  # fmt: skip


def _pattern(keywords: list[str]) -> re.Pattern[str] | None:
    words = [re.escape(k.strip().lower()) for k in keywords if k.strip()]
    if not words:
        return None
    # Whole words plus plural/possessive endings: "doctor" matches "doctors" and "doctor's",
    # but "pin" does not match "pinch".
    alternatives = "|".join(sorted(words, key=len, reverse=True))
    return re.compile(r"\b(" + alternatives + r")(?:'s|’s|es|s)?\b")


class KeywordSensitivityClassifier:
    """A reminder is sensitive if it mentions a sensitive keyword; otherwise it is not, unless
    ``unknown_is_sensitive`` is set and no non-sensitive keyword matches either."""

    class Params(BaseModel):
        sensitive_keywords: list[str] = setting(
            tier="advanced",
            default_factory=lambda: list(DEFAULT_SENSITIVE),
            description="Words or phrases that make a reminder sensitive.",
        )
        non_sensitive_keywords: list[str] = setting(
            tier="advanced",
            default_factory=lambda: list(DEFAULT_NON_SENSITIVE),
            description="Words or phrases that mark a reminder as not sensitive.",
        )
        unknown_is_sensitive: bool = setting(
            False,
            tier="advanced",
            description="Treat reminders that match neither list as sensitive (safer, "
            "but asks for consent more often).",
        )

    def __init__(self, params: Params) -> None:
        self.params = params
        self._sensitive = _pattern(params.sensitive_keywords)
        self._non_sensitive = _pattern(params.non_sensitive_keywords)

    def classify(self, text: str) -> SensitivityResult:
        lowered = text.lower()
        if self._sensitive and (hits := self._sensitive.findall(lowered)):
            return SensitivityResult(True, 1.0, tuple(dict.fromkeys(hits)))
        if self._non_sensitive and (hits := self._non_sensitive.findall(lowered)):
            return SensitivityResult(False, 0.0, tuple(dict.fromkeys(hits)))
        return SensitivityResult(self.params.unknown_is_sensitive, 0.5)
