"""
System tray icon and context menu.

Shows scan action with hotkey hint, recent history entries (clickable),
compact submenus for number entries, settings shortcut, and exit.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Callable

from PIL import Image, ImageDraw
import pystray

from contextcruncher import __version__
from contextcruncher.stack import TextStack
from contextcruncher.config import hotkey_display_name

_ICON_PATH = os.path.join(os.path.dirname(__file__), "assets", "icon.png")
_MAX_HISTORY_ITEMS = 8  # Show at most this many items in the tray menu.


def _freshness_bar(index: int) -> str:
    """Return a Unicode density char that encodes the entry's age by position.

    pystray cannot render per-item background colors (no owner-draw support),
    so we simulate the "newest = bright, oldest = faded" gradient with a
    monochrome block character. Index 0 is newest (solid █), position >6
    is deepest gray (░). This gives the user a peripheral visual cue at a
    glance without relying on item numbers.
    """
    if index <= 1:
        return "█"   # full — newest 2
    if index <= 3:
        return "▓"   # dark shade
    if index <= 6:
        return "▒"   # medium shade
    return "░"       # light shade — oldest


def _relative_time(ts: float) -> str:
    """Format a Unix timestamp as a short relative age hint ('now', '5s', '2m', '1h', '3d')."""
    delta = time.time() - ts
    if delta < 10:
        return "now"
    if delta < 60:
        return f"{int(delta)}s"
    if delta < 3600:
        return f"{int(delta / 60)}m"
    if delta < 86400:
        return f"{int(delta / 3600)}h"
    return f"{int(delta / 86400)}d"


def _generate_icon(size: int = 64) -> Image.Image:
    """Programmatically generate a simple green camera/text icon."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = size // 8
    draw.rounded_rectangle(
        [margin, margin + size // 6, size - margin, size - margin],
        radius=size // 10,
        fill=(217, 6, 13, 255),  # #D9060D
    )
    cx, cy = size // 2, size // 2 + size // 16
    r = size // 6
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 255, 255, 220))
    draw.ellipse(
        [cx - r // 2, cy - r // 2, cx + r // 2, cy + r // 2],
        fill=(217, 6, 13, 255),
    )
    bw = size // 4
    bh = size // 8
    bx = size // 2 - bw // 2
    by = margin
    draw.rectangle([bx, by, bx + bw, by + bh], fill=(217, 6, 13, 255))
    return img


def _load_icon() -> Image.Image:
    abs_path = os.path.normpath(_ICON_PATH)
    if os.path.isfile(abs_path):
        try:
            return Image.open(abs_path).convert("RGBA")
        except Exception:
            pass
    return _generate_icon()


def _truncate(text: str, max_len: int = 45) -> str:
    """Truncate text for menu display."""
    text = text.replace("\n", " ").strip()
    if len(text) > max_len:
        return text[:max_len - 1] + "…"
    return text


class TrayApp:
    """System-tray wrapper around pystray."""

    def __init__(
        self,
        stack: TextStack,
        on_scan: Callable[[], None] | None = None,
        on_clear: Callable[[], None] | None = None,
        on_quit: Callable[[], None] | None = None,
        on_settings: Callable[[], None] | None = None,
        on_select_entry: Callable[[int], None] | None = None,
        on_select_compact: Callable[[int], None] | None = None,
        on_select_pinned_entry: Callable[[int], None] | None = None,
        on_select_pinned_compact: Callable[[int], None] | None = None,
        on_ai_compact: Callable[[], None] | None = None,
        on_search_stack: Callable[[], None] | None = None,
        on_toggle_auto_crunch: Callable[[bool], None] | None = None,
        on_snipping: Callable[[], None] | None = None,
        hotkey_bindings: dict[str, str] | None = None,
    ) -> None:
        self._stack = stack
        self._on_scan = on_scan
        self._on_clear = on_clear
        self._on_quit = on_quit
        self._on_settings = on_settings
        self._on_select_entry = on_select_entry
        self._on_select_compact = on_select_compact
        self._on_select_pinned_entry = on_select_pinned_entry
        self._on_select_pinned_compact = on_select_pinned_compact
        self._on_ai_compact = on_ai_compact
        self._on_search_stack = on_search_stack
        self._on_toggle_auto_crunch = on_toggle_auto_crunch
        self._on_snipping = on_snipping
        self._hotkeys = hotkey_bindings or {}
        self._icon: pystray.Icon | None = None
        
        # Load initial config states
        from contextcruncher.config import load_config
        cfg = load_config()
        self._auto_crunch_enabled = cfg.get("auto_crunch", False)
        self._toggle_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Menu builder
    # ------------------------------------------------------------------

    def _build_menu(self) -> pystray.Menu:
        items: list[pystray.MenuItem | pystray.Menu] = []

        # ── Version header (informational, disabled) ──
        items.append(pystray.MenuItem(
            f"ContextCruncher v{__version__}", lambda: None, enabled=False,
        ))
        items.append(pystray.Menu.SEPARATOR)

        # ── Primary action: Scan ──
        scan_key = self._hotkeys.get("scan", "")
        scan_label = f"🖨️  OCR Snipping"
        if scan_key:
            scan_label += f"    {hotkey_display_name(scan_key)}"
        items.append(pystray.MenuItem(scan_label, self._handle_scan, default=True))

        snip_key = self._hotkeys.get("snipping", "")
        snip_label = f"📸  Image Snipping"
        if snip_key:
            snip_label += f"    {hotkey_display_name(snip_key)}"
        items.append(pystray.MenuItem(snip_label, self._handle_snipping))

        ai_key = self._hotkeys.get("ai_compact", "")
        ai_label = f"🤖  AI-Crunch Clipboard"
        if ai_key:
            ai_label += f"    {hotkey_display_name(ai_key)}"
        items.append(pystray.MenuItem(ai_label, self._handle_ai_compact))

        search_key = self._hotkeys.get("search_stack", "")
        search_label = f"🔎  Search Stack"
        if search_key:
            search_label += f"    {hotkey_display_name(search_key)}"
        items.append(pystray.MenuItem(search_label, self._handle_search_stack))

        # ── Auto-Crunch Toggle ──
        ac_mark = "✅" if self._auto_crunch_enabled else "❌"
        items.append(pystray.MenuItem(f"🔄  Auto-Crunch Monitor: {ac_mark}", self._handle_toggle_auto_crunch))

        items.append(pystray.Menu.SEPARATOR)

        # ── Pin Current Action ──
        if self._stack.size() > 0:
            curr_entry = self._stack.current_entry()
            if curr_entry:
                is_pinned = any(p.original == curr_entry.original for p in self._stack.get_pinned_items())
                if not is_pinned and self._stack.pinned_size() < 10:
                    items.append(pystray.MenuItem("📌  Pin Current Entry", self._handle_pin_current))
                elif is_pinned:
                    items.append(pystray.MenuItem("📌  Current Entry Pinned", lambda: None, enabled=False))
                elif self._stack.pinned_size() >= 10:
                    items.append(pystray.MenuItem("📌  Pin Limit Reached (10/10)", lambda: None, enabled=False))
            
        items.append(pystray.Menu.SEPARATOR)

        # ── Pinned items ──
        pinned_size = self._stack.pinned_size()
        if pinned_size > 0:
            items.append(pystray.MenuItem(f"📌  Pinned ({pinned_size}/10):", None, enabled=False))
            def make_entry_cb_pinned(j: int):
                return lambda icon, item: self._on_select_pinned_entry(j) if self._on_select_pinned_entry else None
            def make_compact_cb_pinned(j: int):
                return lambda icon, item: self._on_select_pinned_compact(j) if self._on_select_pinned_compact else None
            def make_unpin_cb(j: int):
                return lambda icon, item: self._handle_unpin(j)
                
            for i in range(pinned_size):
                entry = self._stack.get_pinned_items()[i]
                preview = _truncate(entry.original)
                unpin_item = pystray.MenuItem("❌  Unpin", make_unpin_cb(i))
                if entry.compact is not None:
                    compact_preview = _truncate(entry.compact)
                    sub = pystray.Menu(
                        pystray.MenuItem(f"📄  Original: {preview}", make_entry_cb_pinned(i)),
                        pystray.MenuItem(f"🔢  Compact: {compact_preview}", make_compact_cb_pinned(i)),
                        pystray.Menu.SEPARATOR,
                        unpin_item
                    )
                    marker = " ✎" if entry.compact else ""
                    items.append(pystray.MenuItem(f"📌  {preview}{marker}", sub))
                else:
                    sub = pystray.Menu(
                        pystray.MenuItem(f"📄  Original: {preview}", make_entry_cb_pinned(i)),
                        pystray.Menu.SEPARATOR,
                        unpin_item
                    )
                    items.append(pystray.MenuItem(f"📌  {preview}", sub))
            items.append(pystray.Menu.SEPARATOR)

        # ── History entries ──
        size = self._stack.size()
        if size == 0:
            items.append(pystray.MenuItem("... stack is empty ...", lambda: None, enabled=False))
        else:
            items.append(pystray.MenuItem(
                f"📋  Recent scans ({size}):",
                None, enabled=False,
            ))
            # Helper closures to bypass pystray's strict parameter reflection
            def make_entry_cb(j: int):
                return lambda icon, item: self._on_select_entry(j)

            def make_compact_cb(j: int):
                return lambda icon, item: self._on_select_compact(j)

            # Show the most recent entries.
            # Layout: "<bar>  <preview>  · <age>" — no numbering.
            # The freshness bar encodes position-age visually (█ newest → ░ oldest),
            # and the relative time stamp ("now", "2m", "1h") makes it explicit.
            for i in range(min(size, _MAX_HISTORY_ITEMS)):
                entry = self._stack.get_entry(i)
                preview = _truncate(entry.original, max_len=38)
                bar = _freshness_bar(i)
                reltime = _relative_time(entry.created_at)

                if entry.compact is not None:
                    # Entry has compact variant → submenu.
                    compact_preview = _truncate(entry.compact)
                    sub = pystray.Menu(
                        pystray.MenuItem(
                            f"📄  Original: {preview}",
                            make_entry_cb(i),
                        ),
                        pystray.MenuItem(
                            f"🔢  Compact: {compact_preview}",
                            make_compact_cb(i),
                        ),
                    )
                    marker = " ✎"
                    items.append(pystray.MenuItem(
                        f"{bar}  {preview}{marker}  · {reltime}",
                        sub,
                    ))
                else:
                    # Regular entry → click to copy.
                    items.append(pystray.MenuItem(
                        f"{bar}  {preview}  · {reltime}",
                        make_entry_cb(i),
                    ))

        items.append(pystray.Menu.SEPARATOR)

        # ── Stack clear ──
        if size > 0:
            items.append(pystray.MenuItem(
                f"🗑️  Clear Stack ({size} entries)",
                self._handle_clear,
            ))
            items.append(pystray.Menu.SEPARATOR)

        # ── Settings ──
        items.append(pystray.MenuItem("⚙  Settings...", self._handle_settings))

        items.append(pystray.Menu.SEPARATOR)

        # ── Quit ──
        items.append(pystray.MenuItem("❌  Quit", self._handle_quit))

        return pystray.Menu(*items)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _handle_pin_current(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        self._stack.pin_current()
        self.update_menu()
        
    def _handle_unpin(self, index: int) -> None:
        self._stack.unpin(index)
        self.update_menu()

    def _handle_scan(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        if self._on_scan:
            self._on_scan()

    def _handle_snipping(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        if self._on_snipping:
            self._on_snipping()

    def _handle_ai_compact(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        if self._on_ai_compact:
            self._on_ai_compact()

    def _handle_search_stack(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        if self._on_search_stack:
            self._on_search_stack()

    def _handle_toggle_auto_crunch(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        with self._toggle_lock:
            self._auto_crunch_enabled = not self._auto_crunch_enabled
            if self._on_toggle_auto_crunch:
                self._on_toggle_auto_crunch(self._auto_crunch_enabled)
        self.update_menu()

    def _handle_clear(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        if self._on_clear:
            self._on_clear()
            self.update_menu()

    def _handle_settings(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        if self._on_settings:
            # Thread is REQUIRED: open_settings() blocks via done_event.wait(),
            # which would freeze the pystray message loop.  Thread-safe because
            # open_settings() dispatches all Tk work through
            # get_tk_manager().schedule(), never creating widgets on this thread.
            threading.Thread(target=self._on_settings, daemon=True).start()

    def _handle_quit(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        if self._on_quit:
            self._on_quit()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        image = _load_icon()
        self._icon = pystray.Icon(
            name="ContextCruncher",
            icon=image,
            title=f"ContextCruncher v{__version__} - {self._stack.size()} entries",
            menu=self._build_menu(),
        )
        self._icon.run()

    def stop(self) -> None:
        if self._icon:
            self._icon.stop()

    def update_menu(self) -> None:
        if self._icon:
            self._icon.title = f"ContextCruncher v{__version__} - {self._stack.size()} entries"
            self._icon.menu = self._build_menu()
            self._icon.update_menu()

    def start_threaded(self) -> threading.Thread:
        t = threading.Thread(target=self.start, daemon=True)
        t.start()
        return t
