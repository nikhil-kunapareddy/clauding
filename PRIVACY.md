# Privacy

clauding collects no data, has no servers, and makes no network requests at all — not even
an update check. It runs entirely on your Mac.

It reads two kinds of file, both already written by Claude Code on your machine:

- its own session state files in `~/.claude/clauding/state.d/`, which hold a state word,
  your project's directory, the session's process id and a timestamp; and
- the last 8KB of a session's transcript, to find the model name, the effort level, and
  whether the turn was interrupted.

Nothing is transmitted, logged to a server, or shared with anyone. Nothing is written
outside `~/.claude/`.

---
Back to the [README](README.md).
