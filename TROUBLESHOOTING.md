# Troubleshooting

**The icon doesn't appear.** Work through these in order:

1. Is a Claude Code session actually running? Not just a terminal window — an active
   `claude` session. The indicator shows nothing when there's nothing to show.
2. Was the session already open when you installed? Hooks are picked up on the session's
   next prompt or tool call. Do anything in that session, or start a new one.
3. Is the indicator process up? `pgrep -f clauding` — a number means yes. If it isn't,
   start it with `clauding`.
4. Are the hooks actually installed? `clauding status` prints what the bar would show
   without needing the menu bar at all. If it says "no live Claude Code session" while a
   session is clearly running, re-run `clauding install`.
5. Is your menu bar full? macOS silently hides menu bar items when it runs out of room,
   and a notch makes that much likelier. Quit something else and check again.

**`clauding install` says it can't locate the console script.** The install moved or was
removed after the hooks were written — the commands in `~/.claude/settings.json` point at
absolute paths. Reinstall and re-run `clauding install`.

**Stuck on `Clauding…` after interrupting.** Pressing Esc early in a turn, before anything
has streamed, fires no hook at all, so nothing tells the indicator the turn ended. It
recovers on its own from the transcript's interrupt marker, and failing that after 15
minutes. Sending a new prompt clears it immediately. This is an upstream Claude Code
quirk, not something this tool can see.

**Stuck on `Waiting for input`.** A permission prompt that was answered in a way that
fires no Notification, or a session that hit a usage limit mid-turn. It clears on the next
prompt or tool call, and times out after two hours.

**Chat and Cowork in the desktop app don't move it.** They don't fire the hooks this runs
on. Only Claude Code sessions do: the desktop app's Code mode, or `claude` in a terminal.

**It shows the wrong model.** The model is read from the last main-thread assistant turn
in the transcript. If a session hasn't produced one yet, the previous value is held rather
than blanked — so right after a `/model` switch it can lag by one turn. It corrects itself
as soon as the new model replies.

**Removing it completely.**

```bash
clauding uninstall        # hooks, indicator, and ~/.claude/clauding
uv tool uninstall clauding
```

Your `~/.claude/settings.json` keeps every hook that wasn't ours. The pre-install backup
stays at `~/.claude/settings.json.bak-clauding` if you want to compare.

---
Back to the [README](README.md).
