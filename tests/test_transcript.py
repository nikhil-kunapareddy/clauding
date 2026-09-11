"""Reading model and effort out of a transcript."""

from __future__ import annotations

from pathlib import Path

import pytest
from clauding.transcript import (
    TranscriptReader,
    model_label,
    read_model_effort,
    tail_lines,
)


def assistant_line(
    model: str = "claude-opus-5",
    effort: str = "xhigh",
    per_turn: str | None = None,
    sidechain: bool = False,
    content: str = '{"type":"text","text":"hi"}',
) -> str:
    """A line shaped like a real assistant turn: model first, effort trailing."""
    per = f'"{per_turn}"' if per_turn else "null"
    return (
        '{"parentUuid":"p","isSidechain":%s,"message":{"model":"%s","id":"m",'
        '"type":"message","role":"assistant","content":[%s]},"type":"assistant",'
        '"uuid":"u","timestamp":"2026-09-11T08:04:45.150Z","effort":"%s",'
        '"perTurnEffort":%s,"sessionId":"s","version":"2.1.268"}'
        % ("true" if sidechain else "false", model, content, effort, per)
    )


def write(tmp_path: Path, *lines: str) -> str:
    path = tmp_path / "transcript.jsonl"
    path.write_text("\n".join(lines) + "\n")
    return str(path)


@pytest.mark.parametrize(
    "model_id,expected",
    [
        ("claude-opus-5", "Opus 5"),
        ("claude-sonnet-5", "Sonnet 5"),
        ("claude-haiku-4-5-20251001", "Haiku 4.5"),
        ("claude-fable-5-1", "Fable 5.1"),
        ("claude-opus-5[1m]", "Opus 5"),
        ("claude-opus-4-1-20250805", "Opus 4.1"),
        # The older ids put the version first; matching by token handles both orders.
        ("claude-3-7-sonnet-20250219", "Sonnet 3.7"),
        ("us.anthropic.claude-sonnet-4-20250514-v1:0", "Sonnet 4"),
        ("publishers/anthropic/models/claude-opus-4@20250514", "Opus 4"),
        # Anything unparseable comes back verbatim rather than as a confident guess.
        ("gpt-4o", "gpt-4o"),
        ("claude-something-new", "claude-something-new"),
        ("", ""),
    ],
)
def test_model_label(model_id: str, expected: str) -> None:
    assert model_label(model_id) == expected


def test_reads_model_and_effort(tmp_path: Path) -> None:
    path = write(tmp_path, assistant_line())
    assert read_model_effort(path) == ("claude-opus-5", "xhigh")


def test_per_turn_effort_overrides_the_session_default(tmp_path: Path) -> None:
    path = write(tmp_path, assistant_line(effort="high", per_turn="low"))
    assert read_model_effort(path) == ("claude-opus-5", "low")


def test_a_tool_use_model_argument_is_not_mistaken_for_the_model(tmp_path: Path) -> None:
    """Delegating to a subagent puts a second "model" key on the line."""
    agent_call = (
        '{"type":"tool_use","id":"t","name":"Agent",'
        '"input":{"model":"sonnet","prompt":"go"}}'
    )
    path = write(tmp_path, assistant_line(content=agent_call))
    assert read_model_effort(path)[0] == "claude-opus-5"


def test_an_effort_inside_the_content_does_not_win(tmp_path: Path) -> None:
    """The real effort is a top-level key, so it is always the last one on the line."""
    tool_call = '{"type":"tool_use","id":"t","name":"X","input":{"effort":"low"}}'
    path = write(tmp_path, assistant_line(effort="xhigh", content=tool_call))
    assert read_model_effort(path)[1] == "xhigh"


def test_subagent_turns_are_skipped(tmp_path: Path) -> None:
    """A delegation must not swap the displayed model for the subagent's."""
    path = write(
        tmp_path,
        assistant_line(model="claude-opus-5"),
        assistant_line(model="claude-haiku-4-5", sidechain=True),
    )
    assert read_model_effort(path)[0] == "claude-opus-5"


def test_a_tail_without_an_assistant_line_finds_nothing(tmp_path: Path) -> None:
    path = write(tmp_path, '{"type":"user","message":{"role":"user"}}')
    assert read_model_effort(path) == ("", "")


def test_missing_file_is_not_an_error(tmp_path: Path) -> None:
    assert read_model_effort(str(tmp_path / "nope.jsonl")) == ("", "")
    assert tail_lines(str(tmp_path / "nope.jsonl")) == []


def test_tail_drops_the_line_the_seek_landed_inside(tmp_path: Path) -> None:
    """A partial JSON record is worse than no record."""
    path = tmp_path / "big.jsonl"
    filler = ['{"type":"user","pad":"%s"}' % ("x" * 500) for _ in range(40)]
    path.write_text("\n".join(filler) + "\n" + assistant_line() + "\n")

    lines = tail_lines(str(path))
    assert all(line.startswith("{") and line.endswith("}") for line in lines)
    assert read_model_effort(str(path)) == ("claude-opus-5", "xhigh")


def test_reader_holds_the_last_known_value(tmp_path: Path) -> None:
    """An idle session stops appending, and its tail may hold no assistant line at all."""
    reader = TranscriptReader()
    good = write(tmp_path, assistant_line())
    assert reader.label("s1", good) == "Opus 5 · xhigh"

    # A transcript the reader can learn nothing from must not blank what it knows.
    empty = str(tmp_path / "empty.jsonl")
    Path(empty).write_text('{"type":"user"}\n')
    assert reader.label("s1", empty) == "Opus 5 · xhigh"
    # ...but a session it has never resolved stays empty rather than borrowing.
    assert reader.label("s2", empty) == ""


def test_reader_label_omits_a_missing_effort(tmp_path: Path) -> None:
    reader = TranscriptReader()
    line = assistant_line().replace(',"effort":"xhigh"', "")
    assert reader.label("s", write(tmp_path, line)) == "Opus 5"


def test_interrupt_marker_is_detected(tmp_path: Path) -> None:
    """An Esc fires no hook, so this marker is the only route back to idle."""
    reader = TranscriptReader()
    path = write(
        tmp_path,
        assistant_line(),
        '{"type":"user","message":{"role":"user","content":'
        '"[Request interrupted by user]"}}',
    )
    assert reader.interrupted(path) is True


def test_bookkeeping_lines_do_not_hide_the_interrupt_marker(tmp_path: Path) -> None:
    """Claude Code appends non-turn lines after an interrupt; they must be skipped."""
    reader = TranscriptReader()
    path = write(
        tmp_path,
        '{"type":"user","message":{"role":"user","content":"[Request interrupted by user]"}}',
        '{"type":"system","subtype":"away_summary"}',
        '{"type":"ai-title","title":"something"}',
    )
    assert reader.interrupted(path) is True


def test_a_completed_turn_is_not_interrupted(tmp_path: Path) -> None:
    reader = TranscriptReader()
    assert reader.interrupted(write(tmp_path, assistant_line())) is False
    assert reader.interrupted("") is False
