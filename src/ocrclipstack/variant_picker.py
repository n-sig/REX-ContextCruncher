"""
variant_picker.py — Win+V-style popup to pick a text variant.

Shows all available variants for the current stack entry in a dark,
semi-transparent popup. The user clicks one to copy it, or presses
ESC to close without changes.
"""

from __future__ import annotations

import threading
import tkinter as tk
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from ocrclipstack.stack import Variant

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
    if not variants or len(variants) <= 1:
        return
    threading.Thread(
        target=_picker_thread,
        args=(variants, active_index, on_select),
        daemon=True,
    ).start()


def _picker_thread(
    variants: list["Variant"],
    active_index: int,
    on_select: Callable[[int], None],
) -> None:
    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.attributes("-alpha", 0.95)
    root.configure(bg=_BG)

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
        text="ESC = schließen",
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

    def _make_select_handler(idx: int):
        def handler(_event=None):
            root.destroy()
            on_select(idx)
        return handler

    for i, variant in enumerate(variants):
        is_active = (i == active_index)
        bg = _BG_ACTIVE if is_active else _BG_ITEM

        frame = tk.Frame(items_frame, bg=bg, padx=12, pady=8, cursor="hand2")
        frame.pack(fill=tk.X, pady=2)

        # Left side: marker + label
        marker = "▸ " if is_active else "   "
        label_text = f"{marker}{variant.label}"
        lbl = tk.Label(
            frame,
            text=label_text,
            font=("Segoe UI", 11, "bold" if is_active else "normal"),
            fg=_FG,
            bg=bg,
            anchor="w",
        )
        lbl.pack(side=tk.LEFT)

        # Right side: savings info
        if variant.saved_percent > 0:
            savings_text = f"-{variant.saved_percent:.0f}%"
            savings_lbl = tk.Label(
                frame,
                text=savings_text,
                font=("Segoe UI", 10, "bold"),
                fg="#00ff88" if not is_active else _FG,
                bg=bg,
                anchor="e",
            )
            savings_lbl.pack(side=tk.RIGHT, padx=(10, 0))

        # Preview text
        preview = variant.text.replace("\n", " ").strip()
        if len(preview) > 60:
            preview = preview[:57] + "..."
        preview_lbl = tk.Label(
            frame,
            text=preview,
            font=("Segoe UI", 9),
            fg=_FG_DIM if not is_active else "#ffccdd",
            bg=bg,
            anchor="w",
        )
        preview_lbl.pack(fill=tk.X, padx=(20, 0))

        # Bind click on entire frame and all children
        click_handler = _make_select_handler(i)
        for widget in (frame, lbl, preview_lbl):
            widget.bind("<Button-1>", click_handler)

        # Hover effect
        if not is_active:
            def _enter(e, f=frame, l=lbl, p=preview_lbl):
                f.config(bg=_BG_HOVER)
                l.config(bg=_BG_HOVER)
                p.config(bg=_BG_HOVER)
                # Also update savings label if it exists
                for child in f.winfo_children():
                    child.config(bg=_BG_HOVER)

            def _leave(e, f=frame, l=lbl, p=preview_lbl, orig_bg=bg):
                f.config(bg=orig_bg)
                l.config(bg=orig_bg)
                p.config(bg=orig_bg)
                for child in f.winfo_children():
                    child.config(bg=orig_bg)

            frame.bind("<Enter>", _enter)
            frame.bind("<Leave>", _leave)

    # ── ESC to close ──
    root.bind("<Escape>", lambda e: root.destroy())
    # Also close on focus loss
    root.bind("<FocusOut>", lambda e: root.after(200, root.destroy))

    # ── Position: center of screen ──
    root.update_idletasks()
    w = max(root.winfo_reqwidth(), 380)
    h = root.winfo_reqheight()
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    x = (sw - w) // 2
    y = (sh - h) // 2
    root.geometry(f"{w}x{h}+{x}+{y}")

    # Force focus
    root.focus_force()

    root.mainloop()
