"""
feedback.py — Visual and audible cues after a scan.

FIX (Bug #1): All tkinter windows are now Toplevel children of a single
persistent hidden tk.Tk() root that lives on its own dedicated thread
(TkUIThread).  Creating multiple tk.Tk() instances across threads was
the primary cause of silent crashes and RuntimeError: main thread is
not in main loop.

Public API (unchanged for callers):
    beep_success(), beep_empty()
    flash_region(bbox)
    show_toast(text)

New export used by overlay.py and settings.py:
    get_tk_manager() -> _TkManager
"""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from typing import Callable

log = logging.getLogger(__name__)

try:
    import winsound
except ImportError:
    winsound = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# TkManager — single tkinter root + mainloop on its own thread
# ---------------------------------------------------------------------------

class _TkManager:
    """Owns the one-and-only ``tk.Tk()`` root and runs its mainloop on a
    dedicated daemon thread (TkUIThread).

    All other modules **must** dispatch tkinter operations via
    :meth:`schedule` so they execute on TkUIThread.  Never instantiate
    ``tk.Tk()`` anywhere else in the codebase.
    """

    def __init__(self) -> None:
        self._root: tk.Tk | None = None
        self._ready = threading.Event()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="TkUIThread"
        )
        self._thread.start()
        if not self._ready.wait(timeout=5.0):
            log.error("TkManager: tkinter root did not initialize within 5 s")

    def _run(self) -> None:
        try:
            self._root = tk.Tk()
            self._root.withdraw()
            self._root.overrideredirect(True)
            # Position off-screen so it never briefly flashes
            self._root.geometry("1x1+-32000+-32000")
            self._ready.set()
            self._root.mainloop()
        except Exception:
            log.exception("TkManager: mainloop crashed")
            self._ready.set()  # unblock any waiting callers

    def schedule(self, func: Callable, *args) -> None:
        """Thread-safe: enqueue *func(*args)* to run on TkUIThread."""
        if self._root is not None:
            try:
                # root.after(0, ...) is thread-safe in tkinter
                self._root.after(0, self._safe_call, func, args)
            except Exception:
                log.exception("TkManager.schedule: after() call failed")

    def _safe_call(self, func: Callable, args: tuple) -> None:
        try:
            func(*args)
        except Exception:
            log.exception("TkManager: scheduled call raised an exception")

    @property
    def root(self) -> tk.Tk | None:
        return self._root


# Module-level singleton — created lazily on first use
_tk_mgr: _TkManager | None = None
_tk_lock = threading.Lock()


def get_tk_manager() -> _TkManager:
    """Return the global :class:`_TkManager`, creating it on first call."""
    global _tk_mgr
    if _tk_mgr is None:
        with _tk_lock:
            if _tk_mgr is None:
                _tk_mgr = _TkManager()
    return _tk_mgr


# ---------------------------------------------------------------------------
# Audio
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Flash overlay
# ---------------------------------------------------------------------------

def flash_region(bbox: tuple[int, int, int, int] | None) -> None:
    """Schedule a semi-transparent green rectangle over *bbox* for ~300 ms.

    *bbox* is (x1, y1, x2, y2) in screen coordinates.
    Safe to call from any thread.
    """
    if bbox is None:
        return
    get_tk_manager().schedule(_do_flash, bbox)


def _do_flash(bbox: tuple[int, int, int, int]) -> None:
    """Create the flash Toplevel — runs on TkUIThread."""
    x1, y1, x2, y2 = bbox
    w, h = x2 - x1, y2 - y1
    if w < 1 or h < 1:
        return
    root = get_tk_manager().root
    if root is None:
        return
    win = tk.Toplevel(root)
    win.overrideredirect(True)
    win.attributes("-topmost", True)
    win.attributes("-alpha", 0.35)
    win.geometry(f"{w}x{h}+{x1}+{y1}")
    win.configure(bg="#00ff00")
    win.after(300, win.destroy)


# ---------------------------------------------------------------------------
# Toast notification
# ---------------------------------------------------------------------------

def show_toast(text: str) -> None:
    """Show a dark popup at the bottom of the screen for 1.5 s.

    Safe to call from any thread.
    """
    if not text:
        return
    get_tk_manager().schedule(_do_toast, text)


def _do_toast(text: str) -> None:
    """Create the toast Toplevel — runs on TkUIThread."""
    root = get_tk_manager().root
    if root is None:
        return
    win = tk.Toplevel(root)
    win.overrideredirect(True)
    win.attributes("-topmost", True)
    win.attributes("-alpha", 0.85)
    win.configure(bg="#222222")

    lbl = tk.Label(
        win,
        text=text,
        fg="white",
        bg="#222222",
        font=("Segoe UI", 16, "bold"),
        padx=30,
        pady=15,
    )
    lbl.pack()

    win.update_idletasks()
    w = win.winfo_reqwidth()
    h = win.winfo_reqheight()
    sw = win.winfo_screenwidth()
    sh = win.winfo_screenheight()
    x = (sw - w) // 2
    y = sh - h - 150
    win.geometry(f"+{x}+{y}")

    win.after(1500, win.destroy)
