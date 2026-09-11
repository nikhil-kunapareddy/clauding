"""Hook installation. Ported from the Swift implementation's install.test.js."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from conftest import all_commands, our_commands, run_cli, settings, state_files


def test_installs_absolute_commands_and_replaces_stale_hooks(home: Path) -> None:
    """A user's own hooks and settings survive; an earlier copy of ours is replaced."""
    settings_path = home / ".claude" / "settings.json"
    unrelated = "echo keep-me"
    stale = "/somewhere/old/clauding-hook pre"
    original = {
        "customSetting": True,
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "*",
                    "hooks": [
                        {"type": "command", "command": stale},
                        {"type": "command", "command": unrelated},
                        {"type": "prompt"},
                    ],
                }
            ],
            "Notification": [{"matcher": "empty-entry"}],
        },
    }
    settings_path.write_text(json.dumps(original, indent=2))

    run_cli(home, "install")
    data = settings(home)

    assert data["customSetting"] is True
    assert len(our_commands(data)) == 8
    # Absolute paths only, so no PATH lookup can be influenced at all.
    assert all(c.startswith("/") for c in our_commands(data))
    assert stale not in all_commands(data)
    # The unrelated command and the non-command hook are left exactly as they were.
    assert all_commands(data).count(unrelated) == 1
    prompts = [
        h
        for entry in data["hooks"]["PreToolUse"]
        for h in entry["hooks"]
        if h.get("type") == "prompt"
    ]
    assert len(prompts) == 1
    # The backup captures the file as it was before we ever touched it.
    backup = home / ".claude" / "settings.json.bak-clauding"
    assert json.loads(backup.read_text()) == original


def test_reinstalling_is_idempotent(home: Path) -> None:
    run_cli(home, "install")
    first = settings(home)
    run_cli(home, "install")
    assert settings(home) == first
    assert len(our_commands(first)) == 8


def test_uninstall_leaves_foreign_hooks_alone(home: Path) -> None:
    unrelated = "echo keep-me"
    (home / ".claude" / "settings.json").write_text(
        json.dumps(
            {
                "customSetting": True,
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "*",
                            "hooks": [{"type": "command", "command": unrelated}],
                        }
                    ]
                },
            }
        )
    )
    run_cli(home, "install")
    run_cli(home, "uninstall")
    data = settings(home)

    assert our_commands(data) == []
    assert data["customSetting"] is True
    assert all_commands(data) == [unrelated]
    # An event whose only hooks were ours is removed rather than left as an empty list.
    assert "Stop" not in data["hooks"]


def test_empty_inherited_path_never_searches_the_working_directory(home: Path) -> None:
    """The hazard: ``sh`` with an empty PATH will happily run ./name from the cwd.

    An absolute hook command removes the lookup entirely, so a hostile file planted in a
    project directory is never a candidate.
    """
    run_cli(home, "install")
    command = next(c for c in our_commands(settings(home)) if c.endswith(" stop"))
    assert command.startswith("/")

    hostile = home / "hostile-project"
    hostile.mkdir()
    canary = home / "cwd-hook-ran"
    impostor = hostile / "clauding-hook"
    impostor.write_text(f"#!/bin/sh\n: > '{canary}'\nexit 0\n")
    impostor.chmod(0o755)

    subprocess.run(
        ["/bin/sh", "-c", command],
        cwd=hostile,
        env={"HOME": str(home), "PATH": "", "CLAUDING_NO_LAUNCH": "1"},
        input=json.dumps({"session_id": "path-test", "cwd": str(hostile)}),
        capture_output=True,
        text=True,
        check=True,
    )

    assert not canary.exists(), "the working directory's clauding-hook was executed"
    # ...and the real one did run, so this can't pass by the command merely failing.
    assert [p.name for p in state_files(home)] == ["path-test.json"]
