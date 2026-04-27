"""
variant_picker.py — Win+V-style popup to pick a text variant.

Shows all available variants for the current stack entry in a dark,
semi-transparent popup. The user clicks one to copy it, or presses
ESC to close without changes.

FIX (Audit F-02): Uses tk.Toplevel owned by the global TkManager instead of
creating a new tk.Tk(), which violated design decision #1 (single Tk root)
and could cause tkinter crashes.
"""

from __future__ import annotations

import ctypes
import logging
import threading
import tkinter as tk
from typing import Callable, TYPE_CHECKING

from contextcruncher.feedback import get_tk_manager
from contextcruncher.token_counter import count_tokens

try:
    from pynput import keyboard as _pyk
    _pynput_available = True
except Exception:  # pragma: no cover — defensive, pynput is a hard dep
    _pynput_available = False

if TYPE_CHECKING:
    from contextcruncher.stack import Variant

log = logging.getLogger(__name__)


def _safe_token_count(text: str) -> int:
    """Return count_tokens(text), falling back to 0 on any failure.

    The picker must never crash because tiktoken blew up — this is pure
    display metadata.
    """
    try:
        return count_tokens(text or "")
    except Exception:
        log.debug("variant_picker: token count failed", exc_info=True)
        return 0

# -----------------------------------------------------------------------
# Dark theme — synchronized with settings.py, search_picker.py and the
# tray menu so the variant picker doesn't look like a separate application.
# Previous palette (#1a1a2e / #e94560 / #16213e) was a blue/magenta variant
# that didn't match the rest of the ContextCruncher UI — same fix that
# was applied to search_picker.py in v2.0.1.
# -----------------------------------------------------------------------
_BG = "#121212"          # matches settings.py _BG
_BG_ITEM = "#1e1e1e"     # matches settings.py _BG_FIELD
_BG_HOVER = "#2d2d2d"    # matches settings.py _BG_ACTIVE
_BG_ACTIVE = "#D9060D"   # app accent red (was magenta #e94560)
_FG = "#ffffff"
_FG_DIM = "#888888"      # matches settings.py _FG_DIM
_ACCENT = "#D9060D"      # app accent red


_picker_active = False
# Module-level holder for the pynput global ESC listener so we can stop it
# on close (avoids leaking listener threads and double-bindings on reopen).
_esc_listener: object = None

def show_variant_picker(
    variants: list["Variant"],
    active_index: int,
    on_select: Callable[[int], None],
) -> None:
    """Show the variant picker popup in a background thread.

    Args:
        variants: List of Variant objects to display.
        active_index: The currently active variant index (highlighted).
        on_select: Callback with the chosen variant index. Not called on ESC.
    """
    global _picker_active
    if _picker_active:
        return
    if not variants or len(variants) <= 1:
        return
    _picker_active = True
    get_tk_manager().schedule(
        _create_picker, variants, active_index, on_select,
    )


def _create_picker(
    variants: list["Variant"],
    active_index: int,
    on_select: Callable[[int], None],
) -> None:
    """Build the variant picker as a Toplevel on TkUIThread."""
    mgr = get_tk_manager()
    if mgr.root is None:
        return
    root = tk.Toplevel(mgr.root)
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.attributes("-alpha", 0.95)
    root.configure(bg=_BG)

    state = {"sel": active_index}
    
    _is_closed = False
    def _close_picker(e=None):
        nonlocal _is_closed
        if _is_closed:
            return
        _is_closed = True
        global _picker_active, _esc_listener
        _picker_active = False
        # Stop the global ESC listener (started further below) so it doesn't
        # leak its thread or fire again after the picker is gone.
        if _esc_listener is not None:
            try:
                _esc_listener.stop()  # type: ignore[attr-defined]
            except Exception:
                pass
            _esc_listener = None
        try:
            root.destroy()
        except tk.TclError:
            # Window was already destroyed (e.g. focus-out after Escape).
            # Any other exception should bubble — swallowing hid real bugs.
            pass

    # ── Title bar ──
    title_frame = tk.Frame(root, bg=_BG, padx=16, pady=10)
    title_frame.pack(fill=tk.X)
    tk.Label(
        title_frame,
        text="📋  ContextCruncher",
        font=("Segoe UI", 13, "bold"),
        fg=_ACCENT,
        bg=_BG,
    ).pack(side=tk.LEFT)

    # Explicit ✕ close button — previously the only way out was ESC, but
    # ESC was unreliable when the picker hadn't captured focus (see
    # _esc_listener + focus-stealing block below). A clickable button is
    # always available regardless of focus state. Same pattern as
    # search_picker.py.
    close_btn = tk.Label(
        title_frame,
        text="  ✕  ",
        font=("Segoe UI", 13, "bold"),
        fg=_FG_DIM,
        bg=_BG,
        cursor="hand2",
    )
    close_btn.pack(side=tk.RIGHT, padx=(10, 0))
    close_btn.bind("<Button-1>", _close_picker)
    close_btn.bind("<Enter>", lambda _e: close_btn.config(fg=_ACCENT))
    close_btn.bind("<Leave>", lambda _e: close_btn.config(fg=_FG_DIM))

    tk.Label(
        title_frame,
        text="↑/↓ = Move   Enter = Select   ESC = Close",
        font=("Segoe UI", 9),
        fg=_FG_DIM,
        bg=_BG,
    ).pack(side=tk.RIGHT)

    # ── Separator ──
    sep = tk.Frame(root, bg=_ACCENT, height=1)
    sep.pack(fill=tk.X, padx=16)

    # ── Variant items ──
    items_frame = tk.Frame(root, bg=_BG, padx=8, pady=8)
    items_frame.pack(fill=tk.BOTH, expand=True)

    item_widgets = []

    def _make_select_handler(idx: int):
        def handler(_event=None):
            _close_picker()
            on_select(idx)
        return handler

    def _make_hover_enter(idx: int):
        def handler(_event=None):
            state["sel"] = idx
            update_selection()
        return handler

    # Pre-compute token counts once so each row shows the exact value
    # without re-encoding when the user hovers.
    token_counts = [_safe_token_count(v.text) for v in variants]

    for i, variant in enumerate(variants):
        frame = tk.Frame(items_frame, padx=12, pady=8, cursor="hand2")
        frame.pack(fill=tk.X, pady=2)

        lbl = tk.Label(frame, anchor="w")
        lbl.pack(side=tk.LEFT)

        savings_lbl = None
        if variant.saved_percent > 0:
            savings_text = f"-{variant.saved_percent:.0f}%"
            savings_lbl = tk.Label(frame, text=savings_text, anchor="e")
            savings_lbl.pack(side=tk.RIGHT, padx=(10, 0))

        # Token count column (always shown, even for the Original variant)
        tokens_lbl = tk.Label(
            frame, text=f"{token_counts[i]:,} tok", anchor="e",
        )
        tokens_lbl.pack(side=tk.RIGHT, padx=(10, 0))

        preview = variant.text.replace("\n", " ").strip()
        if len(preview) > 60:
            preview = preview[:57] + "..."
        preview_lbl = tk.Label(frame, text=preview, anchor="w")
        preview_lbl.pack(fill=tk.X, padx=(20, 0))

        item_widgets.append((frame, lbl, preview_lbl, savings_lbl, tokens_lbl))

        # Mouse bindings
        click_handler = _make_select_handler(i)
        extra = ((savings_lbl,) if savings_lbl else ()) + (tokens_lbl,)
        for widget in (frame, lbl, preview_lbl) + extra:
            widget.bind("<Button-1>", click_handler)
            widget.bind("<Enter>", _make_hover_enter(i))

    def update_selection():
        for i, (f, l, p, sl, tl) in enumerate(item_widgets):
            is_active = (i == state["sel"])
            bg = _BG_ACTIVE if is_active else _BG_ITEM
            f.config(bg=bg)

            marker = "▸ " if is_active else "   "
            l.config(
                bg=bg,
                text=f"{marker}{variants[i].label}",
                font=("Segoe UI", 11, "bold" if is_active else "normal"),
                fg=_FG
            )

            p.config(
                bg=bg,
                # Active row is red (#D9060D) — use near-white for readability.
                # Old value #ffccdd was a pink meant to sit on magenta bg.
                fg="#ffe0e0" if is_active else _FG_DIM,
                font=("Segoe UI", 9)
            )

            if sl:
                sl.config(
                    bg=bg,
                    fg=_FG if is_active else "#00ff88",
                    font=("Segoe UI", 10, "bold")
                )

            tl.config(
                bg=bg,
                fg=_FG if is_active else _FG_DIM,
                font=("Segoe UI", 10),
            )

    def on_up(e):
        if state["sel"] > 0:
            state["sel"] -= 1
            update_selection()

    def on_down(e):
        if state["sel"] < len(variants) - 1:
            state["sel"] += 1
            update_selection()

    def on_enter(e):
        _close_picker()
        on_select(state["sel"])

    root.bind("<Up>", on_up)
    root.bind("<Down>", on_down)
    root.bind("<Return>", on_enter)

    # Initial paint
    update_selection()

    # ── ESC to close ──
    # tk.bind_all only fires when the Tk app has OS-level keyboard focus.
    # With overrideredirect(True) + aggressive focus-stealing the picker's
    # focus can be reclaimed by the previous foreground app before the
    # user presses ESC. A pynput global key listener bypasses Tk's focus
    # chain entirely — ESC always closes the picker, no matter which
    # window owns the foreground. Same pattern as search_picker.py.
    root.bind_all("<Escape>", _close_picker)
    # We consciously REMOVED <FocusOut> here, because Windows focus-stealing
    # hacks often immediately trigger a FocusOut event, closing the window
    # before the user sees it. Now it stays open until explicitly closed.

    global _esc_listener
    if _pynput_available:
        def _on_global_press(key):
            if key == _pyk.Key.esc:
                # Hop onto TkUIThread before touching any Tk state.
                get_tk_manager().schedule(_close_picker)
                return False  # stop the listener after the first ESC
            return True

        _esc_listener = _pyk.Listener(on_press=_on_global_press)
        try:
            _esc_listener.daemon = True  # type: ignore[attr-defined]
            _esc_listener.start()
        except Exception:
            _esc_listener = None

    # ── Position: center of screen ──
    # Hide window while moving it to prevent flickering
    root.withdraw()
    root.update_idletasks()
    
    w = max(root.winfo_reqwidth(), 450)
    h = root.winfo_reqheight()
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    x = (sw - w) // 2
    y = (sh - h) // 2
    root.geometry(f"{w}x{h}+{x}+{y}")
    
    root.deiconify()

    # ── Force Aggressive Focus Stealing ──
    # Because this is spawned via a background global hotkey, Windows 
    # blocks normal focus_force(). We use ctypes to bypass this restriction.
    root.lift()
    root.attributes("-topmost", True)
    root.focus_force()

    try:
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        
        fg_hwnd = user32.GetForegroundWindow()
        fg_thread = user32.GetWindowThreadProcessId(fg_hwnd, None)
        current_thread = kernel32.GetCurrentThreadId()
        
        if fg_hwnd and fg_thread != current_thread:
            # Temporarily attach our input processing to the foreground active window
            user32.AttachThreadInput(current_thread, fg_thread, True)
            user32.SetForegroundWindow(hwnd)
            user32.SetFocus(hwnd)
            user32.AttachThreadInput(current_thread, fg_thread, False)
        else:
            user32.SetForegroundWindow(hwnd)
            user32.SetFocus(hwnd)
    except Exception:
        pass
