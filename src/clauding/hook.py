"""The hook Claude Code fires. One console script, one event argument.

    clauding-hook <prompt|pre|post|notify|permreq|stop|start|end>

Every event writes this session's state file; that write is also what keeps the session
counted as alive. The indicator polls those files — nothing here talks to it directly,
apart from starting it if it isn't running.

Nothing in here may fail loudly or block: a hook that raises or hangs is a hook that
interferes with the session it's reporting on.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time

from .paths import BASE_DIR, QUIT_MARKER, STATE_DIR, script_path
from .sessions import (
    CLAUDING,
    IDLE,
    WAITING,
    Session,
    pid_alive,
    safe_id,
    state_path,
    write_state,
)

PID_FILE = BASE_DIR / "indicator.pid"

#: Event -> the state it puts the session in. ``pre``/``post`` both mean "still working":
#: the indicator shows one word for a running turn, so which tool it is doesn't matter.
_EVENT_STATE = {
    "prompt": CLAUDING,
    "pre": CLAUDING,
    "post": CLAUDING,
    "permreq": WAITING,
    "stop": IDLE,
    "start": IDLE,
}


def _read_stdin(timeout: float = 2.0) -> str:
    """The hook payload, giving up rather than blocking the session that fired us."""
    chunks: list[str] = []

    def worker() -> None:
        try:
            chunks.append(sys.stdin.read())
        except Exception:
            pass

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    thread.join(timeout)
    return chunks[0] if chunks else ""


def _payload() -> dict:
    try:
        parsed = json.loads(_read_stdin() or "{}")
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def indicator_running() -> bool:
    try:
        return pid_alive(int(PID_FILE.read_text().strip()))
    except (OSError, ValueError):
        return False


def start_indicator() -> None:
    """Launch the indicator detached, unless it's running or was explicitly quit.

    This is the self-heal: installing mid-session, or a crash, would otherwise leave
    live sessions with nothing displaying them until the next manual start.
    """
    # The escape hatch is for tests, which must exercise the hooks without a GUI
    # process appearing in the menu bar of whoever is running them.
    if os.environ.get("CLAUDING_NO_LAUNCH") == "1":
        return
    if QUIT_MARKER.exists() or indicator_running():
        return
    try:
        subprocess.Popen(
            [script_path("clauding")],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except (OSError, FileNotFoundError):
        pass


def _is_waiting_notification(payload: dict) -> bool:
    """Whether a Notification means Claude needs something from you.

    Both kinds count: a permission prompt, and the idle "waiting for your input". The
    Swift implementation filtered the second one out deliberately — this reverses that,
    because a session sitting on an unanswered prompt is exactly what you tab away from.

    Anything else is ignored rather than guessed at, so an unrelated notification can't
    park the indicator on "Waiting for input".
    """
    kind = str(payload.get("notification_type") or "").lower()
    if kind in ("permission_prompt", "idle_prompt"):
        return True
    message = str(payload.get("message") or "").lower()
    return any(
        phrase in message
        for phrase in ("permission", "approve", "allow", "waiting for your input")
    )


def _clear_stale_state() -> None:
    """Wipe leftover session files when no indicator is running to own them.

    They can only be the remains of a crash: every live session rewrites its file on the
    next hook, so nothing real is lost.
    """
    try:
        for name in os.listdir(STATE_DIR):
            try:
                os.unlink(os.path.join(STATE_DIR, name))
            except OSError:
                pass
    except OSError:
        pass


def handle(event: str, payload: dict) -> None:
    session_id = safe_id(payload.get("session_id"))
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    if event == "end":
        # Removing the file drops the session. This is also what recovers a frozen
        # state on force-quit, where SessionEnd fires but Stop never does.
        try:
            os.unlink(state_path(session_id))
        except OSError:
            pass
        return

    if event == "notify":
        if not _is_waiting_notification(payload):
            return
        state = WAITING
    else:
        state = _EVENT_STATE.get(event)
        if state is None:
            return

    previous: dict = {}
    try:
        with open(state_path(session_id), encoding="utf-8") as fh:
            previous = json.load(fh)
    except (OSError, ValueError):
        previous = {}

    cwd = payload.get("cwd") or previous.get("cwd") or ""
    session = Session(
        id=session_id,
        state=state,
        project=os.path.basename(cwd) if cwd else previous.get("project") or "",
        cwd=cwd,
        transcript=payload.get("transcript_path") or previous.get("transcript") or "",
        # Set for the session's whole life, but not present on every single event, so
        # carry the last known value forward rather than dropping it.
        entrypoint=os.environ.get("CLAUDE_CODE_ENTRYPOINT")
        or previous.get("entrypoint")
        or "",
        term_program=os.environ.get("TERM_PROGRAM") or previous.get("term_program") or "",
        # The parent of a hook IS the session's `claude` process — hooks are spawned by
        # it directly, and the pid is stable for the session's life. That's what makes
        # liveness a process check rather than a timeout.
        pid=os.getppid(),
        ts=time.time(),
    )

    if event == "start":
        # A new session voids an earlier explicit Quit.
        try:
            QUIT_MARKER.unlink()
        except OSError:
            pass
        if not indicator_running():
            _clear_stale_state()

    write_state(session)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    event = argv[0] if argv else ""
    try:
        handle(event, _payload())
        start_indicator()
    except Exception:
        # A hook must never surface an error into the session it reports on.
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
