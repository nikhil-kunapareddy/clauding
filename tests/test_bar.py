"""The one line of text the menu bar shows."""

from __future__ import annotations

from clauding.bar import bar_text
from clauding.sessions import CLAUDING, IDLE, WAITING


def test_idle_shows_just_the_model() -> None:
    """The icon already says "idle", so the text answers "running what?"."""
    assert bar_text(IDLE, "Opus 5 · xhigh") == "Opus 5 · xhigh"


def test_clauding_names_the_state_and_the_model() -> None:
    assert bar_text(CLAUDING, "Opus 5 · xhigh") == "Clauding… Opus 5 · xhigh"


def test_waiting_says_only_what_it_needs_to() -> None:
    """What matters is that you're being asked for something, not which model asks."""
    assert bar_text(WAITING, "Opus 5 · xhigh") == "Waiting for input"


def test_an_unknown_model_leaves_the_text_clean() -> None:
    """Before the first transcript read there is no model, and no stray separator."""
    assert bar_text(IDLE, "") == ""
    assert bar_text(CLAUDING, "") == "Clauding…"
