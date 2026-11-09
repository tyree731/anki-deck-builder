"""Tests for adb_deck/study_plan.py (config.toml [plan]: 2 review days, 10 to 50 new cards a day)."""

from datetime import date

from adb_deck import study_plan

TODAY = date(2026, 11, 2)


def test_plan_spreads_cards_over_the_days_before_reviews():
    """test_plan_spreads_cards_over_the_days_before_reviews: 200 cards and a test in 12 days leave 10 learning days,
    so 20 new cards a day, with core cards seen first and the last 2 days for reviews."""
    plan = study_plan.plan(date(2026, 11, 14), TODAY, cards=200, core_cards=120)
    assert (plan["days_left"], plan["new_per_day"], plan["fits"]) == (12, 20, True)
    assert (plan["core_seen_by"], plan["all_seen_by"], plan["reviews_from"]) == (
        "2026-11-07",
        "2026-11-11",
        "2026-11-12",
    )


def test_plan_keeps_a_minimum_pace_with_plenty_of_time():
    """test_plan_keeps_a_minimum_pace_with_plenty_of_time: with far more days than needed, the deck still moves at
    the minimum pace and is seen well before the test."""
    plan = study_plan.plan(date(2026, 12, 12), TODAY, cards=30, core_cards=30)
    assert (plan["new_per_day"], plan["all_seen_by"], plan["fits"]) == (10, "2026-11-04", True)


def test_plan_caps_the_pace_and_says_when_cards_do_not_fit():
    """test_plan_caps_the_pace_and_says_when_cards_do_not_fit: 600 cards in 5 learning days would need 120 a day;
    the pace is capped, the plan says it doesn't fit, and core cards are still seen in time."""
    plan = study_plan.plan(date(2026, 11, 9), TODAY, cards=600, core_cards=100)
    assert (plan["new_per_day"], plan["fits"], plan["core_seen_by"]) == (50, False, "2026-11-03")


def test_plan_for_a_test_tomorrow_today_or_past():
    """test_plan_for_a_test_tomorrow_today_or_past: a test tomorrow leaves one day for everything (still capped); a
    test today or in the past gets no pace."""
    assert study_plan.plan(date(2026, 11, 3), TODAY, cards=40, core_cards=40)["new_per_day"] == 40
    for test_date in (TODAY, date(2026, 10, 30)):
        plan = study_plan.plan(test_date, TODAY, cards=40, core_cards=40)
        assert (plan["new_per_day"], plan["fits"]) == (None, False)


def test_deck_counts_cards_and_core_cards():
    """test_deck_counts_cards_and_core_cards: a cloze note becomes one card per cloze number, and a note without a
    priority counts as core."""
    notes = [
        {"type": "cloze", "text": "{{c1::a}} {{c2::b}} {{c2::c}}"},
        {"type": "basic", "priority": "supporting"},
        {"type": "diagram"},
    ]
    assert study_plan.deck_counts(notes) == (4, 3)
