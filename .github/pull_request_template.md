<!-- clauding does one thing: show whether Claude Code is working, waiting on you, or idle,
     and on which model. Keep PRs small, focused, and tested. -->

## What this changes


## Issue
<!-- Link the issue this addresses, if there is one. Bug fixes are welcome without one. -->

## How you tested it
This is the part I actually read. `pytest` passing is necessary, not sufficient — the
interesting failures are in states the tests can't reach. Be specific about what you did
and what you saw.

- [ ] `pytest` passes
- [ ] Exercised against a real Claude Code session, not only fabricated state files
- **Which states did you see?** <!-- idle / clauding / waiting for input -->
- **Terminal, or the desktop app's Code mode?**
- **What you did and what you saw:**

## Checklist
- [ ] Built off the latest `main`.
- [ ] One focused change, not a bundle of unrelated edits.
- [ ] For anything visual: a screenshot of the menu bar, in both light and dark.
- [ ] No new network calls, and no new work in the hook path.
- [ ] I read [CONTRIBUTING.md](../blob/main/CONTRIBUTING.md) and this fits the scope.
