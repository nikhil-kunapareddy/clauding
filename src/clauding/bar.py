"""The menu bar indicator.

Three states, one line of text each:

    idle      ✦ Opus 5 · xhigh            dim spark
    clauding  ✦ Clauding… Opus 5 · xhigh  orange spark
    waiting   ● Waiting for input         amber dot

The text is deliberately stable — model and effort don't change within a session, so
the item's width barely moves. Per-tool detail (Editing, Reading, …) is left out on
purpose: it would flicker and resize the item, shoving every icon to its left.

No .app bundle is involved. A plain process can own an NSStatusItem as long as it sets
an accessory activation policy, which is also what keeps it out of the Dock.
"""

from __future__ import annotations

import os

import objc
from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSBezierPath,
    NSColor,
    NSCompositingOperationDestinationIn,
    NSFont,
    NSImage,
    NSImageLeading,
    NSMakeRect,
    NSMenu,
    NSMenuItem,
    NSRectFill,
    NSRunLoop,
    NSStatusBar,
    NSTimer,
    NSVariableStatusItemLength,
)
from Foundation import NSData, NSObject, NSSize

from .hook import PID_FILE
from .logo import spark_png
from .paths import BASE_DIR, QUIT_MARKER
from .sessions import CLAUDING, IDLE, WAITING, Session, SessionStore, pid_alive

POLL_INTERVAL = 0.5  # seconds; nothing animates, so this only has to feel immediate
ICON_SIZE = 16.0

BRAND_ORANGE = (0.851, 0.467, 0.341)  # #d97757, Anthropic's accent
AMBER = (0.95, 0.73, 0.18)  # the "needs you" yellow


def _color(rgb: tuple[float, float, float]) -> NSColor:
    return NSColor.colorWithSRGBRed_green_blue_alpha_(*rgb, 1.0)


def bar_text(state: str, label: str) -> str:
    """The text beside the icon. Empty is valid — then only the icon shows."""
    if state == WAITING:
        return "Waiting for input"
    if state == CLAUDING:
        return f"Clauding… {label}".strip()
    return label


def _tinted(mask: NSImage, color: NSColor, size: float) -> NSImage:
    """The spark mask filled with a colour.

    The asset is an alpha mask rather than artwork, so it's tinted at runtime: fill the
    whole box, then keep only the pixels the mask covers.
    """
    image = NSImage.alloc().initWithSize_(NSSize(size, size))
    image.lockFocus()
    rect = NSMakeRect(0, 0, size, size)
    color.set()
    NSRectFill(rect)
    mask.drawInRect_fromRect_operation_fraction_(
        rect, NSMakeRect(0, 0, 0, 0), NSCompositingOperationDestinationIn, 1.0
    )
    image.unlockFocus()
    return image


def _dot(color: NSColor, size: float) -> NSImage:
    """A filled circle, for the state where the spark would understate things."""
    image = NSImage.alloc().initWithSize_(NSSize(size, size))
    image.lockFocus()
    color.set()
    inset = size * 0.28
    NSBezierPath.bezierPathWithOvalInRect_(
        NSMakeRect(inset / 2, inset / 2, size - inset, size - inset)
    ).fill()
    image.unlockFocus()
    return image


class Indicator(NSObject):
    """Owns the status item and the poll timer."""

    def init(self):
        self = objc.super(Indicator, self).init()
        if self is None:
            return None
        self._store = SessionStore()
        self._mask = NSImage.alloc().initWithData_(NSData.dataWithBytes_length_(spark_png(), len(spark_png())))
        self._mask.setSize_(NSSize(ICON_SIZE, ICON_SIZE))
        self._icons: dict[tuple[str, bool], NSImage] = {}
        self._shown: tuple[str, str] | None = None

        bar = NSStatusBar.systemStatusBar()
        self._item = bar.statusItemWithLength_(NSVariableStatusItemLength)
        button = self._item.button()
        button.setImagePosition_(NSImageLeading)
        button.setFont_(NSFont.menuBarFontOfSize_(0))

        menu = NSMenu.alloc().init()
        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Quit", "quit:", "q")
        quit_item.setTarget_(self)
        menu.addItem_(quit_item)
        self._item.setMenu_(menu)

        self._render(IDLE, "", None)
        return self

    @objc.python_method
    def _icon(self, state: str) -> NSImage:
        """The icon for a state, cached per appearance.

        Dark and light menu bars need different resting greys, and a cached NSImage has
        already resolved its colour, so the appearance is part of the cache key.
        """
        dark = (
            NSApplication.sharedApplication()
            .effectiveAppearance()
            .bestMatchFromAppearancesWithNames_(["NSAppearanceNameAqua", "NSAppearanceNameDarkAqua"])
            == "NSAppearanceNameDarkAqua"
        )
        key = (state, dark)
        if key not in self._icons:
            if state == WAITING:
                self._icons[key] = _dot(_color(AMBER), ICON_SIZE)
            elif state == CLAUDING:
                self._icons[key] = _tinted(self._mask, _color(BRAND_ORANGE), ICON_SIZE)
            else:
                resting = NSColor.colorWithWhite_alpha_(1.0 if dark else 0.0, 0.55)
                self._icons[key] = _tinted(self._mask, resting, ICON_SIZE)
        return self._icons[key]

    @objc.python_method
    def _render(self, state: str, label: str, session: Session | None) -> None:
        """Push a state to the status item, skipping no-op redraws."""
        text = bar_text(state, label)
        if self._shown == (state, text):
            return
        self._shown = (state, text)
        button = self._item.button()
        button.setImage_(self._icon(state))
        button.setTitle_(text)
        button.setToolTip_(self._tooltip(state, session))

    @objc.python_method
    def _tooltip(self, state: str, session: Session | None) -> str:
        """The full detail the bar text abbreviates."""
        if session is None:
            return "clauding — no Claude Code session"
        words = {IDLE: "Idle", CLAUDING: "Clauding…", WAITING: "Waiting for input"}
        lines = [f"{session.project or 'session'} — {words.get(state, state)}"]
        model, effort = self._store.reader.get(session.id, session.transcript)
        if model:
            lines.append(model + (f" · effort {effort}" if effort else ""))
        if session.cwd:
            lines.append(session.cwd)
        return "\n".join(lines)

    def tick_(self, _timer) -> None:
        found = self._store.refresh()
        if found is None:
            self._render(IDLE, "", None)
            return
        session, state = found
        label = self._store.reader.label(session.id, session.transcript)
        self._render(state, label, session)

    def quit_(self, _sender) -> None:
        # The marker is what stops the next hook from starting us straight back up.
        try:
            BASE_DIR.mkdir(parents=True, exist_ok=True)
            QUIT_MARKER.touch()
        except OSError:
            pass
        _release_pid_file()
        NSApplication.sharedApplication().terminate_(self)


def _claim_pid_file() -> bool:
    """Record our pid so hooks can tell whether we're up. False if one of us already is."""
    try:
        existing = int(PID_FILE.read_text().strip())
        if existing != os.getpid() and pid_alive(existing):
            return False
    except (OSError, ValueError):
        pass
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))
    return True


def _release_pid_file() -> None:
    try:
        if int(PID_FILE.read_text().strip()) == os.getpid():
            PID_FILE.unlink()
    except (OSError, ValueError):
        pass


def run() -> int:
    """Run the indicator until quit. Returns a process exit status."""
    if not _claim_pid_file():
        print("clauding is already running.")
        return 0
    try:
        QUIT_MARKER.unlink()  # an explicit start overrides an earlier Quit
    except OSError:
        pass

    app = NSApplication.sharedApplication()
    # Accessory, not regular: no Dock icon, no menu bar of our own, no window.
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    indicator = Indicator.alloc().init()
    timer = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(
        POLL_INTERVAL, indicator, "tick:", None, True
    )
    # Common mode so polling continues while a menu is tracking.
    NSRunLoop.currentRunLoop().addTimer_forMode_(timer, "kCFRunLoopCommonModes")
    indicator.tick_(None)
    try:
        app.run()
    finally:
        _release_pid_file()
    return 0
