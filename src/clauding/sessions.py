"""The session state files, and which session the indicator reflects.

Claude Code fires a hook on every prompt, tool call, notification and stop; each writes
one JSON file per session into ``STATE_DIR``. That file is both the state and the
liveness marker — it names the session's ``claude`` process, so a session leaves when
that process dies rather than after an arbitrary idle timeout.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass

from .paths import STATE_DIR
from .transcript import TranscriptReader

#: The three states this indicator knows. ``clauding`` covers thinking and tool use
#: alike — the distinction isn't shown, so the hook doesn't bother to record it.
IDLE = "idle"
CLAUDING = "clauding"
WAITING = "waiting"

_PRIORITY = {WAITING: 2, CLAUDING: 1, IDLE: 0}

# Recovery caps. A turn that claims to still be running after this long lost its Stop
# hook (killed terminal, crash), and a permission prompt left this long was abandoned.
CLAUDING_CAP = 900.0
WAITING_CAP = 7200.0


@dataclass
class Session:
    id: str
    state: str = IDLE
    project: str = ""
    cwd: str = ""
    transcript: str = ""
    entrypoint: str = ""
    term_program: str = ""
    pid: int = 0
    ts: float = 0.0

    @classmethod
    def from_json(cls, obj: dict, session_id: str) -> "Session":
        return cls(
            id=session_id,
            state=obj.get("state") or IDLE,
            project=obj.get("project") or "",
            cwd=obj.get("cwd") or "",
            transcript=obj.get("transcript") or "",
            entrypoint=obj.get("entrypoint") or "",
            term_program=obj.get("term_program") or "",
            pid=int(obj.get("pid") or 0),
            ts=float(obj.get("ts") or 0),
        )

    def to_json(self) -> dict:
        return {
            "state": self.state,
            "project": self.project,
            "cwd": self.cwd,
            "session_id": self.id,
            "transcript": self.transcript,
            "entrypoint": self.entrypoint,
            "term_program": self.term_program,
            "pid": self.pid,
            "ts": self.ts,
        }


def safe_id(raw: object) -> str:
    """A session id reduced to characters that are safe as a filename."""
    text = "".join(c for c in str(raw or "") if c.isalnum() or c in "_.-")
    return text[:64] or "unknown"


def state_path(session_id: str) -> str:
    return str(STATE_DIR / f"{safe_id(session_id)}.json")


def write_state(session: Session) -> None:
    """Write a session's file atomically.

    Write-then-rename means a reader polling the directory can never catch a torn file,
    and the rename bumps mtime, which is what the reader's change detection keys on.
    """
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = state_path(session.id)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(session.to_json(), fh)
    os.replace(tmp, path)


def pid_alive(pid: int) -> bool:
    """Whether a process exists. Signal 0 checks without delivering anything."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, owned by someone else
    return True


class SessionStore:
    """Polls ``STATE_DIR`` and answers "what should the bar say?"."""

    def __init__(self) -> None:
        self.reader = TranscriptReader()
        self._mtimes: dict[str, float] = {}
        self._sessions: dict[str, Session] = {}

    def _reload(self) -> None:
        """Re-parse only the files whose mtime moved; forget the ones that vanished."""
        try:
            names = [n for n in os.listdir(STATE_DIR) if n.endswith(".json")]
        except OSError:
            names = []
        present = set(names)
        for gone in [n for n in self._mtimes if n not in present]:
            del self._mtimes[gone]
            session_id = gone[: -len(".json")]
            self._sessions.pop(session_id, None)
            self.reader.forget(session_id)

        for name in names:
            full = os.path.join(STATE_DIR, name)
            try:
                mtime = os.stat(full).st_mtime
            except OSError:
                continue
            if self._mtimes.get(name) == mtime:
                continue
            self._mtimes[name] = mtime
            try:
                with open(full, encoding="utf-8") as fh:
                    obj = json.load(fh)
            except (OSError, ValueError):
                continue
            session_id = name[: -len(".json")]
            self._sessions[session_id] = Session.from_json(obj, session_id)

    def _reap(self) -> None:
        """Drop sessions whose ``claude`` process is gone, deleting their files."""
        for session_id, session in list(self._sessions.items()):
            if session.pid and not pid_alive(session.pid):
                try:
                    os.unlink(state_path(session_id))
                except OSError:
                    pass
                self._sessions.pop(session_id, None)
                self._mtimes.pop(f"{session_id}.json", None)
                self.reader.forget(session_id)

    def effective_state(self, session: Session, now: float) -> str:
        """The session's state after the recovery nets.

        An Esc or a denied permission fires no hook at all, so the file freezes
        mid-turn; the transcript's interrupt marker and the age caps are the only ways
        back to idle.
        """
        if session.state in (CLAUDING, WAITING):
            cap = WAITING_CAP if session.state == WAITING else CLAUDING_CAP
            if now - session.ts > cap:
                return IDLE
            if self.reader.interrupted(session.transcript):
                return IDLE
            return session.state
        return session.state if session.state in _PRIORITY else IDLE

    def refresh(self, now: float | None = None) -> tuple[Session, str] | None:
        """Reload, reap, and return the session the bar should show, with its state.

        With one session live this is just that session. With several, the most urgent
        wins — a permission prompt you haven't answered matters more than a turn that is
        merely running — and ties go to whichever moved most recently.
        """
        now = time.time() if now is None else now
        self._reload()
        self._reap()
        best: tuple[Session, str] | None = None
        best_key = (-1, -1.0)
        for session in self._sessions.values():
            state = self.effective_state(session, now)
            key = (_PRIORITY.get(state, 0), session.ts)
            if key > best_key:
                best_key = key
                best = (session, state)
        return best
