"""Shared fixtures.

The install and hook tests drive the real console scripts as subprocesses with ``HOME``
pointed at a temporary directory. That's deliberate: the entry points resolve their
paths at import time, and running them for real is the only way to test what Claude Code
will actually execute.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

BIN = Path(sys.executable).parent
CLAUDING = str(BIN / "clauding")
CLAUDING_HOOK = str(BIN / "clauding-hook")


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """An isolated HOME. The name carries shell metacharacters on purpose."""
    path = tmp_path / "home $`\"' dir"
    (path / ".claude").mkdir(parents=True)
    return path


def run_cli(home: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [CLAUDING, *args],
        env={**os.environ, "HOME": str(home), "CLAUDING_NO_LAUNCH": "1"},
        capture_output=True,
        text=True,
        check=True,
    )


def run_hook(home: Path, event: str, payload: dict | None = None, **env_extra):
    return subprocess.run(
        [CLAUDING_HOOK, event],
        env={
            **os.environ,
            "HOME": str(home),
            "CLAUDING_NO_LAUNCH": "1",
            **env_extra,
        },
        input=json.dumps(payload or {}),
        capture_output=True,
        text=True,
        check=True,
    )


def settings(home: Path) -> dict:
    return json.loads((home / ".claude" / "settings.json").read_text())


def all_commands(data: dict) -> list[str]:
    found = []
    for entries in (data.get("hooks") or {}).values():
        for entry in entries or []:
            for hook in entry.get("hooks") or []:
                found.append(hook.get("command", ""))
    return found


def our_commands(data: dict) -> list[str]:
    return [c for c in all_commands(data) if "clauding-hook" in c]


def state_dir(home: Path) -> Path:
    return home / ".claude" / "clauding" / "state.d"


def state_files(home: Path) -> list[Path]:
    directory = state_dir(home)
    return sorted(directory.glob("*.json")) if directory.exists() else []


def read_state(home: Path, session_id: str) -> dict:
    return json.loads((state_dir(home) / f"{session_id}.json").read_text())
