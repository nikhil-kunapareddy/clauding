# Changelog

All notable changes to clauding are documented here. This project follows
[Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-09-11

First release. A Python rewrite of [Claude Status
Bar](https://github.com/m1ckc3s/claude-status-bar), replacing the Swift/AppKit app
entirely.

### What it does

- A menu bar indicator with three states: **idle** and **clauding** both name the session's
  model and effort level (`✦ Opus 5 · xhigh`, `✦ Clauding… Opus 5 · xhigh`), and **waiting
  for input** shows an amber dot.
- `waiting for input` covers both a permission prompt and Claude Code's idle "waiting for
  your input" notification. The Swift version filtered the second out deliberately; this
  reverses that, because a session sitting on an unanswered prompt is exactly the thing you
  tab away from.
- Installs from source and runs as a plain process — `uv tool install`, then
  `clauding install`. No `.app` bundle, no codesigning, no notarization, no DMG, no
  Homebrew cask.
- `clauding status` prints the current state without a GUI, for when the menu bar is full
  or you're on SSH.

### What was dropped

Animations (all three styles), the elapsed timer, the completion sound, the update checker,
the rotating "thinking words", the per-session dropdown, and the per-tool activity labels.
The indicator shows one stable line, so its width barely moves.

### Notes

- Hook commands are written as absolute paths, which removes the PATH-ordering hazard the
  Swift implementation had to harden against explicitly: no lookup happens, so a
  `clauding-hook` planted in a project directory can never be found instead.
- Model and effort come from the session transcript, since no hook payload carries them.
  The read is an 8KB tail gated on mtime and shared with the interrupt check, and the last
  known value is held when a tail contains no assistant turn.
- State lives in `~/.claude/clauding/`, not the `~/.claude/statusbar/` the Swift app used,
  so a leftover install of the old app can't feed state files to this one.

Releases before 1.0.0 belong to the upstream Swift project and are documented in
[its changelog](https://github.com/m1ckc3s/claude-status-bar/blob/main/CHANGELOG.md).
