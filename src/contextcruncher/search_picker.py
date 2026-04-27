"""
search_picker.py — Win+V-style popup to search the clipboard stack.

Shows a search entry and filters the Context Cruncher stack in a semi-transparent popup.
Pressing Enter calls the on_select callback with the chosen stack index.

FIX (Audit F-01): Uses tk.Toplevel owned by the global TkManager instead of
creating a new tk.Tk(), which violated design decision #1 (single Tk root)
and could cause tkinter crashes.
"""

from __future__ import annotations

import ctypes
import threading
import tkinter as tk
from typing import Callable, TYPE_CHECKING

from contextcruncher.feedback import get_tk_manager, show_toast

try:
    from pynput import keyboard as _pyk
    _pynput_available = True
except Exception:  # pragma: no cover — defensive, pynput is a hard dep
    _pynput_available = False

if TYPE_CHECKING:
    from contextcruncher.stack import TextStack

# -----------------------------------------------------------------------
# Dark theme — synchronized with settings.py and the tray menu so the
# Stack Search doesn't look like a separate application. Previous palette
# (#1a1a2e / #e94560 / #16213e) was a blue/magenta variant that didn't
# match the rest of the ContextCruncher UI.
# -----------------------------------------------------------------------
_BG = "#121212"          # matches settings.py _BG
_BG_ITEM = "#1e1e1e"     # matches settings.py _BG_FIELD
_BG_HOVER = "#2d2d2d"    # matches settings.py _BG_ACTIVE
_BG_ACTIVE = "#D9060D"   # app accent red (was magenta #e94560)
_FG = "#ffffff"
_FG_DIM = "#888888"      # matches settings.py _FG_DIM
_ACCENT = "#D9060D"      # app accent red
_ENTRY_BG = "#1e1e1e"

_picker_active = False
# Module-level holder for the pynput global ESC listener so we can stop it
# on close (avoids leaking listener threads and double-bindings on reopen).
_esc_listener: object = None


def show_search_picker(
    stack: "TextStack",
    on_select: Callable[[int], None],
    on_select_pinned: Callable[[int], None] | None = None,
) -> None:
    """Show the stack search picker popup in a background thread.

    Args:
        stack: The TextStack containing entries.
        on_select: Callback with the chosen original stack index. Not called on ESC.
        on_select_pinned: Callback with the chosen pinned item index.
    """
    global _picker_active
    if _picker_active:
        return
    if stack.size() == 0 and not stack.get_pinned_items():
        # No history and no pinned items — tell the user instead of
        # silently eating the hotkey.
        show_toast("Clipboard stack is empty")
        return
    _picker_active = True
    get_tk_manager().schedule(
        _create_picker, stack, on_select, on_select_pinned,
    )


def _create_picker(
    stack: "TextStack",
    on_select: Callable[[int], None],
    on_select_pinned: Callable[[int], None] | None = None,
) -> None:
    """Build the search picker as a Toplevel on TkUIThread."""
    mgr = get_tk_manager()
    if mgr.root is None:
        return
    root = tk.Toplevel(mgr.root)
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.attributes("-alpha", 0.95)
    root.configure(bg=_BG)

    # Convert stack context once and keep references to original indices
    # We display them reverse chronologically (newest at index 0 in list but last in queue)
    all_items = []
    # 1. Add Pinned Items (if any)
    pinned_items = stack.get_pinned_items()
    for i, entry in enumerate(pinned_items):
        corpus = (entry.original + " " + (entry.compact or "") + " " + (entry.label or "")).lower()
        savings = entry.saved_percent()
        preview = entry.original.replace("\n", " ").strip()
        if entry.compact:
            preview_tmp = entry.compact.replace("\n", " ").strip()
            if preview_tmp:
                preview = preview_tmp
        all_items.append({
            "type": "pinned",
            "idx": i,
            "corpus": corpus,
            "preview": preview,
            "savings": savings,
            "label": f"📌 {entry.label or 'Pinned'}"
        })

    # 2. Add History Items (via public API)
    stack_size = stack.size()
    orig_items = [stack.get_entry(i) for i in range(stack_size)]
    for i, entry in enumerate(reversed(orig_items)):
        actual_idx = len(orig_items) - 1 - i
        # Prepare search corpus
        corpus = (entry.original + " " + (entry.compact or "") + " " + (entry.label or "")).lower()
        
        # Determine highest saving text
        savings = entry.saved_percent()
        preview = entry.original.replace("\n", " ").strip()
        if entry.compact:
            # We show compact instead if available to reflect the "best" payload
            preview_tmp = entry.compact.replace("\n", " ").strip()
            if preview_tmp:
                preview = preview_tmp
                
        all_items.append({
            "type": "history",
            "idx": actual_idx,
            "corpus": corpus,
            "preview": preview,
            "savings": savings,
            "label": entry.label or f"Scan {actual_idx+1}"
        })

    state = {
        "sel_idx": 0,
        "filtered": list(all_items)
    }

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
        except:
            pass

    # ── Title bar and Entry ──
    title_frame = tk.Frame(root, bg=_BG, padx=16, pady=10)
    title_frame.pack(fill=tk.X)

    tk.Label(
        title_frame,
        text="🔎 Stack Search",
        font=("Segoe UI", 13, "bold"),
        fg=_ACCENT,
        bg=_BG,
    ).pack(side=tk.LEFT)

    # Explicit ✕ close button — previously the only way out was ESC, but
    # ESC was unreliable when the picker hadn't captured focus (see
    # _esc_listener + focus-stealing block below). A clickable button is
    # always available regardless of focus state.
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
        text="↑/↓ = Move   Enter = Variants   ESC = Close",
        font=("Segoe UI", 9),
        fg=_FG_DIM,
        bg=_BG,
    ).pack(side=tk.RIGHT)

    # The Search Entry
    entry_var = tk.StringVar()
    entry_frame = tk.Frame(root, bg=_BG, padx=16, pady=4)
    entry_frame.pack(fill=tk.X)
    search_entry = tk.Entry(
        entry_frame,
        textvariable=entry_var,
        font=("Segoe UI", 12),
        bg=_ENTRY_BG,
        fg=_FG,
        insertbackground=_FG,
        relief=tk.FLAT
    )
    search_entry.pack(fill=tk.X, ipady=4)
    # Search bottom line
    tk.Frame(entry_frame, bg=_ACCENT, height=1).pack(fill=tk.X)

    # ── Separator ──
    sep = tk.Frame(root, bg=_ACCENT, height=1)
    sep.pack(fill=tk.X, padx=16, pady=(8, 0))

    # ── Items Frame ──
    items_frame = tk.Frame(root, bg=_BG, padx=8, pady=8)
    items_frame.pack(fill=tk.BOTH, expand=True)
    
    # Store dynamic widgets
    item_widgets = []
    
    def _make_select_handler(visible_idx: int):
        def handler(_event=None):
            if visible_idx < len(state["filtered"]):
                item = state["filtered"][visible_idx]
                actual_idx = item["idx"]
                _close_picker()
                if item.get("type", "history") == "pinned" and on_select_pinned:
                    on_select_pinned(actual_idx)
                else:
                    on_select(actual_idx)
        return handler

    def _make_hover_enter(visible_idx: int):
        def handler(_event=None):
            if visible_idx < len(state["filtered"]):
                state["sel_idx"] = visible_idx
                update_selection()
        return handler

    # We only create a maximum number of labels to avoid huge lag
    MAX_ITEMS_DISPLAY = 8
    
    for i in range(MAX_ITEMS_DISPLAY):
        frame = tk.Frame(items_frame, padx=12, pady=8, cursor="hand2")
        frame.pack(fill=tk.X, pady=2)
        
        lbl = tk.Label(frame, anchor="w", font=("Segoe UI", 11), fg=_FG)
        lbl.pack(side=tk.LEFT)
        
        savings_lbl = tk.Label(frame, anchor="e", font=("Segoe UI", 10, "bold"))
        savings_lbl.pack(side=tk.RIGHT, padx=(10, 0))
        
        preview_lbl = tk.Label(frame, anchor="w", font=("Segoe UI", 9))
        preview_lbl.pack(fill=tk.X, padx=(20, 0))
        
        # Hide them initially
        frame.pack_forget()

        item_widgets.append((frame, lbl, preview_lbl, savings_lbl))

        # We will rebind these handlers dynamically since `visible_idx` is fixed for the widget row
        click_handler = _make_select_handler(i)
        for widget in (frame, lbl, preview_lbl, savings_lbl):
            widget.bind("<Button-1>", click_handler)
            widget.bind("<Enter>", _make_hover_enter(i))

    def render_list():
        # Hide all
        for f, _, _, _ in item_widgets:
            f.pack_forget()
            
        # Draw filtered
        for i in range(min(len(state["filtered"]), MAX_ITEMS_DISPLAY)):
            f, l, p, sl = item_widgets[i]
            
            item = state["filtered"][i]
            preview = item["preview"]
            if len(preview) > 60:
                preview = preview[:57] + "..."
            
            p.config(text=preview)
            
            savings = item["savings"]
            if savings > 0:
                sl.config(text=f"-{savings:.0f}%")
            else:
                sl.config(text="")
            
            # Show the frame
            f.pack(fill=tk.X, pady=2)
        
        # Sanitize cursor
        if len(state["filtered"]) == 0:
            state["sel_idx"] = 0
        elif state["sel_idx"] >= len(state["filtered"]):
            state["sel_idx"] = min(state["sel_idx"], len(state["filtered"]) - 1)
            
        update_selection()

    def update_selection():
        for i in range(min(len(state["filtered"]), MAX_ITEMS_DISPLAY)):
            f, l, p, sl = item_widgets[i]
            is_active = (i == state["sel_idx"])
            bg = _BG_ACTIVE if is_active else _BG_ITEM
            f.config(bg=bg)
            
            item = state["filtered"][i]
            marker = "▸ " if is_active else "   "
            l.config(
                bg=bg, 
                text=f"{marker}{item['label']}",
                font=("Segoe UI", 11, "bold" if is_active else "normal"),
                fg=_FG
            )
            
            p.config(
                bg=bg, 
                fg="#ffccdd" if is_active else _FG_DIM,
            )
            
            sl.config(
                bg=bg, 
                fg=_FG if is_active else "#00ff88",
            )

    def on_search_change(*args):
        query = entry_var.get().strip().lower()
        if not query:
            state["filtered"] = list(all_items)
        else:
            state["filtered"] = [item for item in all_items if query in item["corpus"]]
        
        state["sel_idx"] = 0
        render_list()

    entry_var.trace_add("write", on_search_change)

    def on_up(e):
        if state["sel_idx"] > 0:
            state["sel_idx"] -= 1
            update_selection()
        return "break"

    def on_down(e):
        max_bound = min(len(state["filtered"]), MAX_ITEMS_DISPLAY) - 1
        if state["sel_idx"] < max_bound:
            state["sel_idx"] += 1
            update_selection()
        return "break"

    def on_enter(e):
        if state["filtered"] and state["sel_idx"] < len(state["filtered"]):
            item = state["filtered"][state["sel_idx"]]
            actual_idx = item["idx"]
            _close_picker()
            if item.get("type", "history") == "pinned" and on_select_pinned:
                on_select_pinned(actual_idx)
            else:
                on_select(actual_idx)
        return "break"

    search_entry.bind("<Up>", on_up)
    search_entry.bind("<Down>", on_down)
    search_entry.bind("<Return>", on_enter)

    # ── Initial Paint ──
    render_list()
    search_entry.focus_set()

    # ── ESC to close ──
    # tk.bind_all only fires when the Tk app has OS-level keyboard focus.
    # With overrideredirect(True) + aggressive focus-stealing the picker's
    # focus is often reclaimed by the previous foreground app before the
    # user can press ESC, which is why the user reported "ESC nur nach
    # Klick auf Stack Search". A pynput global key listener bypasses Tk's
    # focus chain entirely — ESC always closes the picker, no matter which
    # window owns the foreground.
    root.bind_all("<Escape>", _close_picker)

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
    root.withdraw()
    root.update_idletasks()
    
    w = max(root.winfo_reqwidth(), 550)
    h = root.winfo_reqheight()
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    x = (sw - w) // 2
    y = (sh - h) // 2
    # Ensure it's not taller than needed if less than MAX items
    root.geometry(f"{w}x{h}+{x}+{y}")
    
    root.deiconify()

    # ── Force Aggressive Focus Stealing ──
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
            user32.AttachThreadInput(current_thread, fg_thread, True)
            user32.SetForegroundWindow(hwnd)
            user32.SetFocus(hwnd)
            user32.AttachThreadInput(current_thread, fg_thread, False)
        else:
            user32.SetForegroundWindow(hwnd)
            user32.SetFocus(hwnd)
    except Exception:
        pass
