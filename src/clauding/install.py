"""Wiring the hooks into ``~/.claude/settings.json``, and taking them back out.

Merging is the whole difficulty here. The file belongs to the user and may hold hooks
they wrote or another tool installed, so this strips only its own entries, leaves
everything else byte-for-byte, and is safe to re-run.
"""

from __future__ import annotations

import json
import shlex
from typing import Iterable

from .paths import SETTINGS_BACKUP, SETTINGS_PATH, script_path

#: Every command this installer writes contains this, and nothing else plausibly does.
#: It's how a re-install or uninstall recognises its own entries.
MARKER = "clauding-hook"

#: Event -> hook argument. ``matcher`` is required for the tool and permission events
#: and must be absent for the rest, which is why the two groups are listed separately.
MATCHED_EVENTS = {
    "PreToolUse": "pre",
    "PostToolUse": "post",
    "PermissionRequest": "permreq",
}
UNMATCHED_EVENTS = {
    "UserPromptSubmit": "prompt",
    "Notification": "notify",
    "Stop": "stop",
    "SessionStart": "start",
    "SessionEnd": "end",
}
HOOK_COUNT = len(MATCHED_EVENTS) + len(UNMATCHED_EVENTS)


def hook_command(event: str, executable: str | None = None) -> str:
    """The shell command for one event.

    An absolute, quoted path: no PATH lookup happens, so there is no ordering to get
    wrong and no way for a file in the working directory to be picked up instead.
    """
    return f"{shlex.quote(executable or script_path(MARKER))} {event}"


def _is_ours(command: object) -> bool:
    return MARKER in str(command or "")


def _strip_ours(entries: Iterable[dict] | None) -> list[dict]:
    """Drop our hooks from an event's entry list, keeping everything else intact.

    An entry whose hooks were all ours is dropped; an entry that also held someone
    else's keeps its remaining hooks, and its matcher.
    """
    kept = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        hooks = [h for h in entry.get("hooks") or [] if not _is_ours(h.get("command"))]
        if hooks:
            kept.append({**entry, "hooks": hooks})
    return kept


def _load_settings() -> dict:
    if not SETTINGS_PATH.exists():
        return {}
    try:
        loaded = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except ValueError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _save_settings(settings: dict) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")


def install(executable: str | None = None) -> str:
    """Add the hooks, replacing any earlier copy of them. Returns the settings path."""
    settings = _load_settings()
    # One backup, taken before the first modification ever made, so it represents the
    # file as it was before this tool touched it rather than before the latest re-run.
    if SETTINGS_PATH.exists() and not SETTINGS_BACKUP.exists():
        SETTINGS_BACKUP.write_bytes(SETTINGS_PATH.read_bytes())

    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        hooks = {}
        settings["hooks"] = hooks

    for event, arg in UNMATCHED_EVENTS.items():
        hooks[event] = _strip_ours(hooks.get(event))
        hooks[event].append(
            {"hooks": [{"type": "command", "command": hook_command(arg, executable)}]}
        )
    for event, arg in MATCHED_EVENTS.items():
        hooks[event] = _strip_ours(hooks.get(event))
        hooks[event].append(
            {
                "matcher": "*",
                "hooks": [{"type": "command", "command": hook_command(arg, executable)}],
            }
        )

    _save_settings(settings)
    return str(SETTINGS_PATH)


def uninstall() -> str:
    """Remove the hooks, leaving an event key behind only if something else still uses it."""
    settings = _load_settings()
    hooks = settings.get("hooks")
    if isinstance(hooks, dict):
        for event in list(hooks):
            remaining = _strip_ours(hooks.get(event))
            if remaining:
                hooks[event] = remaining
            else:
                del hooks[event]
        _save_settings(settings)
    return str(SETTINGS_PATH)


def installed_commands() -> list[str]:
    """Our hook commands currently present in settings.json."""
    hooks = _load_settings().get("hooks")
    if not isinstance(hooks, dict):
        return []
    found = []
    for entries in hooks.values():
        for entry in entries or []:
            if not isinstance(entry, dict):
                continue
            for hook in entry.get("hooks") or []:
                if _is_ours(hook.get("command")):
                    found.append(hook["command"])
    return found
