# Contributing

Thanks for your interest. This is a deliberately tiny tool and I'd like to keep it that
way.

It does one thing: show whether Claude Code is working, waiting on you, or idle, and which
model and effort level the session is on. It stays local (no network calls at all), free
(no API key, no spend), and small.

## What's welcome

Bug fixes. Compatibility fixes — macOS versions, Python versions, terminals, the desktop
app. Fixes for cases where the indicator gets stuck because Claude Code fired no hook.
Better handling of model ids as new ones appear.

## Probably not

- **Anything that grows the display.** Timers, per-tool labels, session lists, progress.
  The three states are the whole design, and a menu bar item that changes width every few
  seconds is worse than one that doesn't.
- **Network access of any kind**, including update checks. `PRIVACY.md` is a promise.
- **Anything that costs money or needs an API key.** No usage meters, no cost dashboards,
  no telemetry.
- **Heavy work in the hooks.** They run on every single event: write one small file and
  exit. No network, no imports that aren't needed, nothing that can hang a session.
- **Acting on your machine.** This displays state. It doesn't prevent sleep, hold power
  assertions, run privileged helpers, or do anything in the background beyond drawing.
- **Ports to other agents or platforms.** Great projects — as your own fork. This one is
  Claude Code on macOS.

## Working on it

```bash
git clone https://github.com/nikhil-kunapareddy/clauding && cd clauding
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest
```

To try your build without disturbing an existing install, point `HOME` at a scratch
directory — every path the tool touches hangs off it:

```bash
HOME=/tmp/clauding-scratch .venv/bin/clauding install
HOME=/tmp/clauding-scratch .venv/bin/clauding status
```

`clauding status` is the fastest way to check behaviour: it prints exactly what the bar
would show, with no GUI involved, so it works over SSH and in tests.

A few things in here look arbitrary and aren't — the literal-string transcript parsing,
the `isSidechain` filter, the process-based liveness check, the absolute-path hook
commands. Each has a comment saying why. If one seems needlessly clever, read the comment
before simplifying it; if the comment doesn't justify it, that's a bug in the comment.

## Tests

`pytest`. The install and hook tests run the real console scripts as subprocesses against
a temporary `HOME`, because that's what Claude Code actually executes. New behaviour wants
a test; the suite runs in under two seconds.
