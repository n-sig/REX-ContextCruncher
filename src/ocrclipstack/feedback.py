"""
Feedback — visual and audible cues after a scan.

Visual:  Brief green flash overlay over the scanned region.
Audible: System beep via winsound (stdlib, Windows-only).
"""

from __future__ import annotations

import threading
import tkinter as tk

try:
    import winsound
except ImportError:
    winsound = None  # type: ignore[assignment]


# ------------------------------------------------------------------
# Audio
# ------------------------------------------------------------------

def beep_success() -> None:
    """Short high-pitched beep for a successful scan."""
    if winsound:
        threading.Thread(
            target=lambda: winsound.Beep(1000, 80), daemon=True
        ).start()


def beep_empty() -> None:
    """Low-pitched beep when OCR returned no text."""
    if winsound:
        threading.Thread(
            target=lambda: winsound.Beep(400, 150), daemon=True
        ).start()


# ------------------------------------------------------------------
# Visual — green flash overlay
# ------------------------------------------------------------------

def flash_region(bbox: tuple[int, int, int, int] | None) -> None:
    """Show a semi-transparent green rectangle over *bbox* for ~300 ms.

    *bbox* is (x1, y1, x2, y2) in screen coordinates.  If None, do nothing.
    Runs on a background thread so it never blocks the main logic.
    """
    if bbox is None:
        return
    threading.Thread(target=_flash_thread, args=(bbox,), daemon=True).start()


def _flash_thread(bbox: tuple[int, int, int, int]) -> None:
    x1, y1, x2, y2 = bbox
    w = x2 - x1
    h = y2 - y1
    if w < 1 or h < 1:
        return

    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.attributes("-alpha", 0.35)
    root.geometry(f"{w}x{h}+{x1}+{y1}")
    root.configure(bg="#00ff00")

    # Close after 300 ms.
    root.after(300, root.destroy)
    root.mainloop()


# ------------------------------------------------------------------
# Visual — Toast notification (for stack navigation)
# ------------------------------------------------------------------

def show_toast(text: str) -> None:
    """Show a semi-transparent dark popup at the bottom of the screen
    containing the *text*. Disappears after 1.5 seconds.
    """
    if not text:
        return
    threading.Thread(target=_toast_thread, args=(text,), daemon=True).start()


def _toast_thread(text: str) -> None:
    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.attributes("-alpha", 0.85)
    root.configure(bg="#222222")

    lbl = tk.Label(
        root,
        text=text,
        fg="white",
        bg="#222222",
        font=("Segoe UI", 16, "bold"),
        padx=30,
        pady=15
    )
    lbl.pack()

    # Calculate required size
    root.update_idletasks()
    w = root.winfo_reqwidth()
    h = root.winfo_reqheight()
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()

    # Position horizontally centered, somewhat above the bottom edge
    x = (sw - w) // 2
    y = sh - h - 150
    root.geometry(f"+{x}+{y}")

    root.after(1500, root.destroy)
    root.mainloop()
