import pytest

from pasr.perception.sensitivity.keyword import KeywordSensitivityClassifier as K


def classify(text, **params):
    return K(K.Params(**params)).classify(text)


@pytest.mark.parametrize(
    "text",
    ["Doctor's appointment", "pick up my prescription", "Therapy session", "call the BANK"],
)
def test_sensitive(text):
    result = classify(text)
    assert result.sensitive
    assert result.score == 1.0
    assert result.reasons


@pytest.mark.parametrize("text", ["Buy groceries", "Water the plants", "Gym"])
def test_not_sensitive(text):
    assert not classify(text).sensitive


def test_sensitive_keyword_wins_over_non_sensitive():
    assert classify("groceries and medication").sensitive


def test_unknown_text_uses_the_default():
    assert not classify("Feed the cat").sensitive
    assert classify("Feed the cat", unknown_is_sensitive=True).sensitive
    assert classify("Feed the cat").score == 0.5


def test_keyword_lists_are_configurable():
    assert classify("Feed the cat", sensitive_keywords=["cat"]).sensitive
    assert not classify("Doctor", sensitive_keywords=[], non_sensitive_keywords=[]).sensitive


def test_matches_whole_words_with_plural_and_possessive_endings():
    assert classify("new bank PIN", sensitive_keywords=["pin"]).sensitive
    assert classify("two doctors", sensitive_keywords=["doctor"]).sensitive
    assert classify("the doctor’s note", sensitive_keywords=["doctor"]).sensitive
    assert not classify("Pinch of salt", sensitive_keywords=["pin"]).sensitive
    assert not classify("spinach", sensitive_keywords=["pin"]).sensitive
