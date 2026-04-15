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
import threading
import tkinter as tk
from typing import Callable, TYPE_CHECKING

from contextcruncher.feedback import get_tk_manager

if TYPE_CHECKING:
    from contextcruncher.stack import Variant

# -----------------------------------------------------------------------
# Dark theme (consistent with settings.py)
# -----------------------------------------------------------------------
_BG = "#1a1a2e"
_BG_ITEM = "#16213e"
_BG_HOVER = "#0f3460"
_BG_ACTIVE = "#e94560"
_FG = "#ffffff"
_FG_DIM = "#8899aa"
_ACCENT = "#e94560"


_picker_active = False

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
        global _picker_active
        _picker_active = False
        try:
            root.destroy()
        except:
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

        preview = variant.text.replace("\n", " ").strip()
        if len(preview) > 60:
            preview = preview[:57] + "..."
        preview_lbl = tk.Label(frame, text=preview, anchor="w")
        preview_lbl.pack(fill=tk.X, padx=(20, 0))

        item_widgets.append((frame, lbl, preview_lbl, savings_lbl))

        # Mouse bindings
        click_handler = _make_select_handler(i)
        for widget in (frame, lbl, preview_lbl) + ((savings_lbl,) if savings_lbl else ()):
            widget.bind("<Button-1>", click_handler)
            widget.bind("<Enter>", _make_hover_enter(i))

    def update_selection():
        for i, (f, l, p, sl) in enumerate(item_widgets):
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
                fg="#ffccdd" if is_active else _FG_DIM,
                font=("Segoe UI", 9)
            )
            
            if sl:
                sl.config(
                    bg=bg, 
                    fg=_FG if is_active else "#00ff88",
                    font=("Segoe UI", 10, "bold")
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
    root.bind_all("<Escape>", _close_picker)
    # We consciously REMOVED <FocusOut> here, because Windows focus-stealing
    # hacks often immediately trigger a FocusOut event, closing the window 
    # before the user sees it. Now it stays open until explicitly closed.

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
