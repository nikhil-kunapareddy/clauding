"""Which session the bar reflects, and when a stuck one recovers."""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import pytest
from clauding import sessions as mod
from clauding.sessions import (
    CLAUDING,
    CLAUDING_CAP,
    IDLE,
    WAITING,
    WAITING_CAP,
    Session,
    SessionStore,
    pid_alive,
)


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SessionStore:
    monkeypatch.setattr(mod, "STATE_DIR", tmp_path / "state.d")
    (tmp_path / "state.d").mkdir()
    return SessionStore()


def put(store: SessionStore, session_id: str, **fields) -> Session:
    """Write a session file the way a hook would."""
    fields.setdefault("pid", os.getpid())
    fields.setdefault("ts", time.time())
    session = Session(id=session_id, **fields)
    mod.write_state(session)
    return session


def dead_pid() -> int:
    """A pid that certainly no longer exists."""
    proc = subprocess.Popen(["/usr/bin/true"])
    proc.wait()
    return proc.pid


def test_no_sessions_means_nothing_to_show(store: SessionStore) -> None:
    assert store.refresh() is None


def test_a_single_session_is_the_one_shown(store: SessionStore) -> None:
    put(store, "only", state=CLAUDING, project="myproject")
    session, state = store.refresh()

    assert session.id == "only"
    assert state == CLAUDING


def test_the_most_urgent_session_wins(store: SessionStore) -> None:
    """An unanswered prompt matters more than a turn that is merely running."""
    now = time.time()
    put(store, "busy", state=CLAUDING, ts=now)
    put(store, "blocked", state=WAITING, ts=now - 60)
    put(store, "resting", state=IDLE, ts=now)

    session, state = store.refresh()
    assert (session.id, state) == ("blocked", WAITING)


def test_within_a_tier_the_most_recent_wins(store: SessionStore) -> None:
    now = time.time()
    put(store, "older", state=CLAUDING, ts=now - 30)
    put(store, "newer", state=CLAUDING, ts=now)

    session, _ = store.refresh()
    assert session.id == "newer"


def test_a_turn_that_outlives_its_stop_hook_recovers(store: SessionStore) -> None:
    """A killed terminal means no Stop hook ever arrives; the cap is the way back."""
    put(store, "stuck", state=CLAUDING, ts=time.time() - CLAUDING_CAP - 1)
    _, state = store.refresh()
    assert state == IDLE


def test_a_long_wait_is_still_a_wait(store: SessionStore) -> None:
    """A permission prompt can legitimately sit unanswered for a long while."""
    put(store, "patient", state=WAITING, ts=time.time() - 3600)
    _, state = store.refresh()
    assert state == WAITING

    put(store, "patient", state=WAITING, ts=time.time() - WAITING_CAP - 1)
    _, state = store.refresh()
    assert state == IDLE


def test_an_interrupted_turn_recovers(store: SessionStore, tmp_path: Path) -> None:
    """Esc fires no hook at all, so the transcript marker is the only signal."""
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(
        '{"type":"user","message":{"role":"user","content":'
        '"[Request interrupted by user]"}}\n'
    )
    put(store, "escaped", state=CLAUDING, transcript=str(transcript))
    _, state = store.refresh()
    assert state == IDLE


def test_a_session_leaves_when_its_process_dies(store: SessionStore) -> None:
    """Liveness is the process, not a timeout — an idle-but-open session must stay."""
    put(store, "gone", state=IDLE, pid=dead_pid())
    put(store, "here", state=IDLE, pid=os.getpid())

    session, _ = store.refresh()
    assert session.id == "here"
    assert not (mod.STATE_DIR / "gone.json").exists()


def test_a_removed_file_drops_the_session(store: SessionStore) -> None:
    put(store, "transient", state=CLAUDING)
    assert store.refresh() is not None

    (mod.STATE_DIR / "transient.json").unlink()
    assert store.refresh() is None


def test_a_rewritten_file_is_picked_up(store: SessionStore) -> None:
    put(store, "s", state=CLAUDING)
    _, state = store.refresh()
    assert state == CLAUDING

    time.sleep(0.01)  # the reader keys on mtime
    put(store, "s", state=WAITING)
    _, state = store.refresh()
    assert state == WAITING


def test_a_corrupt_file_is_skipped_not_fatal(store: SessionStore) -> None:
    (mod.STATE_DIR / "broken.json").write_text("{not json")
    put(store, "fine", state=CLAUDING)

    session, _ = store.refresh()
    assert session.id == "fine"


def test_an_unknown_state_reads_as_idle(store: SessionStore) -> None:
    put(store, "weird", state="teleporting")
    _, state = store.refresh()
    assert state == IDLE


def test_state_is_written_atomically(store: SessionStore) -> None:
    """A poller must never catch a half-written file, and no .tmp may be left behind."""
    put(store, "s", state=CLAUDING, cwd="/tmp/x")
    files = sorted(p.name for p in mod.STATE_DIR.iterdir())

    assert files == ["s.json"]
    assert json.loads((mod.STATE_DIR / "s.json").read_text())["state"] == CLAUDING


def test_pid_alive(store: SessionStore) -> None:
    assert pid_alive(os.getpid()) is True
    assert pid_alive(dead_pid()) is False
    assert pid_alive(0) is False
    assert pid_alive(1) is True  # launchd: exists, not ours to signal
