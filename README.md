# clauding

A tiny macOS menu bar indicator for Claude Code. It tells you three things at a glance:
whether Claude is working, whether it's waiting on you, and which model and effort level
the session is running.

```
✦ Opus 5 · xhigh              idle — nothing running
✦ Clauding… Opus 5 · xhigh    a turn is in progress
● Waiting for input           Claude needs you: a permission prompt, or your next message
```

That's the whole feature set. No animations, no timers, no dashboards, no window, no Dock
icon. Built so you can tab away mid-turn and still know, sideways, whether it's your move.

## Install

Requires macOS and Python 3.10+.

```bash
uv tool install git+https://github.com/nikhil-kunapareddy/clauding
clauding install
```

`pipx install git+https://github.com/nikhil-kunapareddy/clauding` works the same way, as
does a plain `pip install` inside a virtualenv.

`clauding install` is the only setup step. It wires the Claude Code hooks into
`~/.claude/settings.json` and starts the indicator. Your existing settings and hooks are
merged, never replaced, and the original file is backed up to
`~/.claude/settings.json.bak-clauding` the first time.

Sessions that were already open pick it up the next time they do anything — a prompt or a
tool call. A new `claude` session works immediately.

## Uninstall

```bash
clauding uninstall     # removes the hooks, stops the indicator, deletes its state
uv tool uninstall clauding
```

Hooks you wrote yourself, and hooks from other tools, are left untouched.

## Commands

| | |
|---|---|
| `clauding` | run the indicator (this is what `clauding install` starts for you) |
| `clauding install` | wire up the hooks and start the indicator |
| `clauding uninstall` | remove the hooks and stop the indicator |
| `clauding status` | print the current state once and exit — handy when the menu bar is hidden |

## How it works

Claude Code fires a hook on every prompt, tool call, notification and stop. Each one runs
`clauding-hook`, which writes a single small JSON file describing that session to
`~/.claude/clauding/state.d/`. The indicator polls that directory twice a second and
renders whatever it finds. Nothing talks over a socket; the filesystem is the whole
protocol.

The model and effort aren't in any hook payload, so they come from the session's
transcript: an 8KB tail of the JSONL, gated on the file's mtime, so a session that isn't
streaming costs one `stat()` per poll.

A session's file names its `claude` process, which is what makes liveness a process check
rather than a timeout — an idle-but-open session stays, and a killed terminal leaves
immediately. Two cases fire no hook at all (pressing Esc mid-turn, and a denied
permission); those recover from the transcript's interrupt marker and a hard age cap.

With more than one session live, the bar shows the most urgent: waiting beats working
beats idle, ties going to whichever moved most recently.

## No network, no data

clauding makes no network requests of any kind and has no servers. It reads state files
and transcripts that Claude Code has already written on your machine, and draws a line of
text in your menu bar. See [PRIVACY.md](PRIVACY.md).

## Lineage

clauding is a Python rewrite of [**Claude Status
Bar**](https://github.com/m1ckc3s/claude-status-bar) by Mick Cesanek — a Swift/AppKit menu
bar app distributed as a signed DMG and a Homebrew cask. This version keeps the idea, the
hook protocol and the per-session state-file design, drops the animations and the app
bundle, and installs from source instead.

The original's contributors worked out most of what's subtle in here: multi-session state,
the process-based liveness check, the interrupt recovery, and the hook PATH hardening that
an absolute-path command now makes unnecessary. They're credited in
[ACKNOWLEDGEMENTS.md](ACKNOWLEDGEMENTS.md). MIT, both then and now.

## Also

- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) — when the icon doesn't show up
- [CONTRIBUTING.md](CONTRIBUTING.md) — what's welcome
- [CHANGELOG.md](CHANGELOG.md)
