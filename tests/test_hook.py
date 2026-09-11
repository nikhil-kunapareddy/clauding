"""The hook: event in, session state out."""

from __future__ import annotations

from pathlib import Path

from conftest import read_state, run_hook, state_files

SESSION = "hook-test"


def fire(home: Path, event: str, **payload):
    payload.setdefault("session_id", SESSION)
    return run_hook(home, event, payload)


def test_prompt_starts_a_clauding_turn(home: Path) -> None:
    fire(home, "prompt", cwd="/tmp/myproject", transcript_path="/tmp/t.jsonl")
    state = read_state(home, SESSION)

    assert state["state"] == "clauding"
    assert state["project"] == "myproject"
    assert state["cwd"] == "/tmp/myproject"
    assert state["transcript"] == "/tmp/t.jsonl"
    # The hook's parent is the session's `claude` process; here, the test runner.
    assert state["pid"] > 0
    assert state["ts"] > 0


def test_tool_events_stay_clauding(home: Path) -> None:
    """Both tool phases mean "still working" — the display shows one word for a turn."""
    for event in ("pre", "post"):
        fire(home, event, cwd="/tmp/p", tool_name="Edit")
        assert read_state(home, SESSION)["state"] == "clauding"


def test_stop_returns_to_idle(home: Path) -> None:
    fire(home, "prompt", cwd="/tmp/p")
    fire(home, "stop")
    assert read_state(home, SESSION)["state"] == "idle"


def test_permission_request_waits(home: Path) -> None:
    fire(home, "permreq", cwd="/tmp/p")
    assert read_state(home, SESSION)["state"] == "waiting"


def test_both_kinds_of_notification_wait(home: Path) -> None:
    """A permission prompt and the idle "waiting for your input" both count.

    The Swift implementation filtered the second one out; this reverses that on purpose.
    """
    for payload in (
        {"notification_type": "permission_prompt"},
        {"notification_type": "idle_prompt"},
        {"message": "Claude needs your permission to use Bash"},
        {"message": "Claude is waiting for your input"},
    ):
        fire(home, "stop")  # back to idle first, so each case is proved on its own
        fire(home, "notify", **payload)
        assert read_state(home, SESSION)["state"] == "waiting", payload


def test_unrecognised_notification_is_ignored(home: Path) -> None:
    """An unrelated notification must not park the indicator on "Waiting for input"."""
    fire(home, "prompt", cwd="/tmp/p")
    fire(home, "notify", message="Background task finished")
    assert read_state(home, SESSION)["state"] == "clauding"


def test_session_end_removes_the_session(home: Path) -> None:
    fire(home, "prompt", cwd="/tmp/p")
    assert len(state_files(home)) == 1
    fire(home, "end")
    assert state_files(home) == []


def test_unknown_event_writes_nothing(home: Path) -> None:
    fire(home, "wat")
    assert state_files(home) == []


def test_details_carry_forward_when_an_event_omits_them(home: Path) -> None:
    """Not every event's payload repeats cwd or the transcript path."""
    fire(home, "prompt", cwd="/tmp/myproject", transcript_path="/tmp/t.jsonl")
    fire(home, "stop")
    state = read_state(home, SESSION)

    assert state["cwd"] == "/tmp/myproject"
    assert state["project"] == "myproject"
    assert state["transcript"] == "/tmp/t.jsonl"


def test_surface_is_recorded_from_the_environment(home: Path) -> None:
    run_hook(
        home,
        "prompt",
        {"session_id": SESSION, "cwd": "/tmp/p"},
        CLAUDE_CODE_ENTRYPOINT="cli",
        TERM_PROGRAM="iTerm.app",
    )
    state = read_state(home, SESSION)

    assert state["entrypoint"] == "cli"
    assert state["term_program"] == "iTerm.app"


def test_session_ids_cannot_escape_the_state_directory(home: Path) -> None:
    """A session id becomes a filename, so it must not be able to traverse."""
    run_hook(home, "prompt", {"session_id": "../../etc/passwd", "cwd": "/tmp/p"})
    names = [p.name for p in state_files(home)]

    assert names == ["....etcpasswd.json"]
