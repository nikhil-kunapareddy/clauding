"""Where everything lives on disk.

The base directory is deliberately NOT the ``~/.claude/statusbar`` used by the Swift app
this replaces: if a leftover copy of that app is still installed, sharing a directory
would let it write state files this indicator would then read as its own.
"""

import os
from pathlib import Path

CLAUDE_DIR = Path.home() / ".claude"
SETTINGS_PATH = CLAUDE_DIR / "settings.json"
SETTINGS_BACKUP = CLAUDE_DIR / "settings.json.bak-clauding"

BASE_DIR = CLAUDE_DIR / "clauding"
STATE_DIR = BASE_DIR / "state.d"

# Written by the menu's Quit item; suppresses the hook's self-relaunch so Quit sticks
# until the next SessionStart.
QUIT_MARKER = BASE_DIR / "quit-intent"


def script_path(name: str) -> str:
    """Absolute path to one of this package's console scripts.

    Every hook command written into settings.json is an absolute path, which is what
    makes the PATH-hardening the Swift implementation needed unnecessary: ``sh`` never
    performs a lookup, so a hostile ``./clauding-hook`` sitting in a project directory
    can never be found instead of the installed one.

    Resolution walks outward from what we know for certain: our own script's directory
    (both console scripts are installed side by side), then the interpreter's directory
    (where a venv or ``uv tool`` install puts them), then PATH as a last resort. Each of
    those is tried both as-is and symlink-resolved, because a venv's ``bin/python`` is
    itself a symlink to the base interpreter, whose directory holds no scripts of ours.
    """
    import shutil
    import sys
    from pathlib import Path

    roots: list[Path] = []
    # Only a sys.argv[0] that actually looks like a path — under `python -c` it is "-c",
    # and treating that as a directory would have us probing the working directory, which
    # is precisely what an absolute hook command exists to avoid.
    argv0 = sys.argv[0] if sys.argv else ""
    if argv0 and os.sep in argv0 and os.path.exists(argv0):
        roots += [Path(argv0).parent, Path(argv0).resolve().parent]
    roots += [Path(sys.executable).parent, Path(sys.executable).resolve().parent]

    for root in roots:
        candidate = root / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate.absolute())
    found = shutil.which(name)
    if found:
        return str(Path(found).absolute())
    raise FileNotFoundError(
        f"could not locate the {name!r} console script; reinstall clauding"
    )
