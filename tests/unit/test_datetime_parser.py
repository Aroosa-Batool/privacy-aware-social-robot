from datetime import date, datetime, time

import pytest

from pasr.perception.datetime_parse.dateparser_plugin import DateparserDateTimeParser as D

NOW = datetime(2026, 10, 31, 9, 0).astimezone()  # a Saturday


def parse(text, **params):
    return D(D.Params(**params)).parse(text, NOW)


@pytest.mark.parametrize(
    ("text", "title", "day", "at"),
    [
        (
            "set a reminder for doctor's appointment at 2pm today",
            "Doctor's appointment",
            date(2026, 10, 31),
            time(14, 0),
        ),
        ("buy groceries tomorrow", "Buy groceries", date(2026, 11, 1), None),
        ("dentist on 12 November at 9:30", "Dentist", date(2026, 11, 12), time(9, 30)),
        ("call mum on friday", "Call mum", date(2026, 11, 6), None),
        ("meeting at 14:30 tomorrow", "Meeting", date(2026, 11, 1), time(14, 30)),
        ("lunch with Sam at noon tomorrow", "Lunch with Sam", date(2026, 11, 1), time(12, 0)),
        ("remind me to take my pills at 8 pm", "Take my pills", None, time(20, 0)),
        ("doctor's appointment at 2pm", "Doctor's appointment", None, time(14, 0)),
        ("doctor appointment", "Doctor appointment", None, None),
    ],
)
def test_parses_title_date_and_time(text, title, day, at):
    parsed = parse(text)
    assert (parsed.title, parsed.date, parsed.time) == (title, day, at)


@pytest.mark.parametrize(
    ("text", "title", "at"),
    [
        ("remind me to take my medicine in 5 minutes", "Take my medicine", time(9, 5)),
        ("doctor call in five minutes", "Doctor call", time(9, 5)),
        ("in 3 min therapy session", "Therapy session", time(9, 3)),
        ("blood test results in an hour", "Blood test results", time(10, 0)),
        ("call the clinic in 2 hrs", "Call the clinic", time(11, 0)),
        ("call back in half an hour", "Call back", time(9, 30)),
    ],
)
def test_a_time_from_now_sets_the_date_and_the_time(text, title, at):
    parsed = parse(text)
    assert (parsed.title, parsed.date, parsed.time) == (title, date(2026, 10, 31), at)


def test_a_time_from_now_can_be_tomorrow():
    parsed = D(D.Params()).parse("pills in 5 minutes", datetime(2026, 10, 31, 23, 58).astimezone())
    assert (parsed.date, parsed.time) == (date(2026, 11, 1), time(0, 3))


def test_days_from_now_leave_the_time_to_the_default():
    parsed = parse("dentist in 2 days")
    assert (parsed.title, parsed.date, parsed.time) == ("Dentist", date(2026, 11, 2), None)


def test_answer_to_the_date_question():
    assert parse("tomorrow").date == date(2026, 11, 1)
    assert parse("on Monday").date == date(2026, 11, 2)


def test_numeric_dates_follow_the_configured_order():
    assert parse("dentist 12/11").date == date(2026, 11, 12)
    assert parse("dentist 12/11", date_order="MDY").date == date(2026, 12, 11)


def test_ignores_month_names_that_are_ordinary_words():
    parsed = parse("may I have my pills")
    assert parsed.date is None


def test_invalid_clock_times_are_not_times():
    assert parse("room 13pm").time is None
