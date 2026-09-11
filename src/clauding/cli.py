"""The ``clauding`` command.

    clauding              run the indicator
    clauding install      wire the hooks into ~/.claude/settings.json
    clauding uninstall    take them back out and stop the indicator
    clauding status       print the current state once, and exit
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import sys

from . import __version__
from .paths import BASE_DIR, SETTINGS_BACKUP


def _cmd_install(_args: argparse.Namespace) -> int:
    from .hook import start_indicator
    from .install import HOOK_COUNT, install

    path = install()
    print(f"Installed {HOOK_COUNT} clauding hooks into {path}")
    if SETTINGS_BACKUP.exists():
        print(f"Backup of your original settings: {SETTINGS_BACKUP}")
    start_indicator()
    print("Indicator started. Open a Claude Code session and watch the menu bar.")
    print("Sessions already open appear the next time they do anything.")
    return 0


def _cmd_uninstall(_args: argparse.Namespace) -> int:
    from .hook import PID_FILE
    from .install import uninstall
    from .sessions import pid_alive

    path = uninstall()
    print(f"Removed clauding hooks from {path}")
    try:
        pid = int(PID_FILE.read_text().strip())
        if pid_alive(pid):
            os.kill(pid, signal.SIGTERM)
            print("Stopped the running indicator.")
    except (OSError, ValueError, ProcessLookupError):
        pass
    if BASE_DIR.exists():
        shutil.rmtree(BASE_DIR, ignore_errors=True)
        print(f"Removed {BASE_DIR}")
    return 0


def _cmd_status(_args: argparse.Namespace) -> int:
    """Print what the bar would show. The indicator needs a GUI session; this doesn't."""
    from .bar import bar_text
    from .sessions import SessionStore

    store = SessionStore()
    found = store.refresh()
    if found is None:
        print("no live Claude Code session")
        return 0
    session, state = found
    label = store.reader.label(session.id, session.transcript)
    print(f"{state:9} {bar_text(state, label)}")
    print(f"          {session.project or 'session'}  pid={session.pid}  {session.cwd}")
    return 0


def _cmd_run(_args: argparse.Namespace) -> int:
    from .bar import run

    return run()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="clauding",
        description="A macOS menu bar indicator for Claude Code.",
    )
    parser.add_argument("--version", action="version", version=f"clauding {__version__}")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("install", help="wire the hooks into ~/.claude/settings.json")
    sub.add_parser("uninstall", help="remove the hooks and stop the indicator")
    sub.add_parser("status", help="print the current state once and exit")
    sub.add_parser("run", help="run the indicator (the default)")

    args = parser.parse_args(argv)
    handlers = {
        "install": _cmd_install,
        "uninstall": _cmd_uninstall,
        "status": _cmd_status,
        "run": _cmd_run,
        None: _cmd_run,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
