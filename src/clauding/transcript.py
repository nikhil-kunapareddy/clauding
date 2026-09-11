"""Model and effort, read out of a session's transcript.

No Claude Code hook payload carries the model, so the only source is the transcript
JSONL the session appends to. Two things make that cheap enough to poll:

* the read is a fixed ~8KB tail, never the whole file, and
* it is gated on the file's mtime, so a session that isn't streaming costs one stat().
"""

from __future__ import annotations

import os
from typing import Iterable

TAIL_BYTES = 8192

# The families a model id can name. Version digits are matched separately because the
# two id generations put them on opposite sides of the family ("3-7-sonnet", "opus-5").
_FAMILIES = {"opus": "Opus", "sonnet": "Sonnet", "haiku": "Haiku", "fable": "Fable"}


def tail_lines(path: str, chunk: int = TAIL_BYTES) -> list[str]:
    """The whole lines in the last ``chunk`` bytes of a file.

    A seek into the middle of a file lands mid-line, so the first fragment is dropped
    unless the read started at 0 — a partial JSON record is worse than no record.
    """
    try:
        with open(path, "rb") as fh:
            size = fh.seek(0, os.SEEK_END)
            fh.seek(max(0, size - chunk))
            data = fh.read()
    except OSError:
        return []
    text = data.decode("utf-8", errors="replace")
    lines = [line for line in text.split("\n") if line]
    if size > chunk and lines:
        lines.pop(0)
    return lines


def _value_after(line: str, opener: str, last: bool = False) -> str:
    """The string value following a literal ``"key":"`` opener.

    Scanning for a literal beats parsing the record: an assistant line carries the whole
    message and can run to tens of KB. ``last`` searches from the end, for the top-level
    keys that trail the content — a coincidental match inside the content then loses.
    """
    i = line.rfind(opener) if last else line.find(opener)
    if i < 0:
        return ""
    start = i + len(opener)
    end = line.find('"', start)
    return line[start:end] if end > start else ""


def _last_main_assistant_line(lines: Iterable[str]) -> str:
    """The newest assistant turn that isn't a subagent's.

    A subagent (``isSidechain``) can run a different model, and letting one through would
    swap the displayed model out for the duration of a delegation.
    """
    for line in reversed(list(lines)):
        if '"type":"assistant"' in line and '"isSidechain":true' not in line:
            return line
    return ""


def read_model_effort(path: str) -> tuple[str, str]:
    """``(model_id, effort)`` from a transcript, or empty strings if the tail has neither."""
    line = _last_main_assistant_line(tail_lines(path))
    if not line:
        return "", ""
    # `model` is the first key inside `message`, so this opener pins it exactly — a
    # tool_use input carrying its own "model" argument can't be mistaken for it.
    model = _value_after(line, '"message":{"model":"')
    # effort/perTurnEffort are top-level keys that trail the content, hence the reverse
    # scan. perTurnEffort overrides the session default for one turn and is usually null.
    effort = _value_after(line, '"perTurnEffort":"', last=True) or _value_after(
        line, '"effort":"', last=True
    )
    return model, effort


def model_label(model_id: str) -> str:
    """A model id as a short display name: ``claude-opus-5`` -> ``Opus 5``.

    Family and version are matched by token rather than position, because the id
    generations disagree on the order ("claude-3-7-sonnet" vs "claude-opus-5"). An id
    that doesn't parse is returned verbatim — a wrong guess is worse than a raw id.
    """
    if not model_id:
        return ""
    core = model_id.rsplit("/", 1)[-1]  # publishers/anthropic/models/<id>
    marker = core.find("claude-")
    if marker < 0:
        return model_id
    core = core[marker + len("claude-") :]
    core = core.split("@", 1)[0]  # Vertex "<id>@20250514"
    core = core.split("[", 1)[0]  # "opus-5[1m]"

    family = ""
    version: list[str] = []
    for part in core.split("-"):
        if part.lower() in _FAMILIES:
            family = _FAMILIES[part.lower()]
        elif part.isdigit() and len(part) <= 2:
            version.append(part)
        # anything longer (a date stamp, "latest", "v1:0") is noise
    if not family:
        return model_id
    return f"{family} {'.'.join(version)}" if version else family


class TranscriptReader:
    """Mtime-gated, sticky reader over a session's transcript.

    One tail read serves both consumers — the model/effort label and the interrupt
    marker — because doing them separately would double the file I/O this cache exists
    to avoid.

    Sticky matters for the label: the 8KB tail doesn't always reach back to an assistant
    line (one in eight real transcripts didn't), and an idle session stops appending
    altogether. A miss therefore holds the last known value rather than blanking it.
    """

    def __init__(self) -> None:
        self._tail: dict[str, tuple[float | None, str, str, bool]] = {}
        self._by_session: dict[str, tuple[str, str]] = {}

    def _read(self, transcript: str) -> tuple[str, str, bool]:
        """``(model_id, effort, interrupted)``, re-reading only when the file moved."""
        try:
            mtime: float | None = os.stat(transcript).st_mtime
        except OSError:
            mtime = None
        cached = self._tail.get(transcript)
        if cached is not None and cached[0] == mtime:
            return cached[1], cached[2], cached[3]

        lines = tail_lines(transcript)
        model, effort = "", ""
        line = _last_main_assistant_line(lines)
        if line:
            # `model` is the first key inside `message`, so this opener pins it exactly —
            # a tool_use input carrying its own "model" argument can't be mistaken for it.
            model = _value_after(line, '"message":{"model":"')
            # effort/perTurnEffort are top-level keys that trail the content, hence the
            # reverse scan. perTurnEffort overrides the default for one turn; usually null.
            effort = _value_after(line, '"perTurnEffort":"', last=True) or _value_after(
                line, '"effort":"', last=True
            )
        # Only a real turn line can carry the marker. The bookkeeping lines Claude Code
        # appends after an interrupt (away_summary, last-prompt, ai-title, mode) would
        # otherwise hide it and leave the indicator stuck on "Clauding…".
        interrupted = False
        for candidate in reversed(lines):
            if '"type":"user"' in candidate or '"type":"assistant"' in candidate:
                interrupted = "interrupted by user" in candidate
                break

        self._tail[transcript] = (mtime, model, effort, interrupted)
        return model, effort, interrupted

    def get(self, session_id: str, transcript: str) -> tuple[str, str]:
        """``(model_id, effort)`` for a session, held from the last successful read."""
        if transcript:
            model, effort, _ = self._read(transcript)
            if model:
                self._by_session[session_id] = (model, effort)
        return self._by_session.get(session_id, ("", ""))

    def interrupted(self, transcript: str) -> bool:
        """Whether the session's last turn ended in an Esc / denied permission.

        Those fire no hook, so the state file freezes mid-turn; the marker is the only
        way back to idle.
        """
        if not transcript:
            return False
        return self._read(transcript)[2]

    def forget(self, session_id: str) -> None:
        self._by_session.pop(session_id, None)

    def label(self, session_id: str, transcript: str) -> str:
        """``"Opus 5 · xhigh"``, or ``""`` when nothing is known yet."""
        model, effort = self.get(session_id, transcript)
        name = model_label(model)
        if not name:
            return ""
        return f"{name} · {effort}" if effort else name
