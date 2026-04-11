"""
overlay.py — Transparent full-screen selection rectangle.

FIX (Bug #1): Uses tk.Toplevel owned by the global TkManager instead of
creating a new tk.Tk() on each scan call, which caused multi-root tkinter
crashes.

FIX (Bug #8): DPI-awareness is now set once at application startup in
main.py — not here on every scan.

The function blocks the calling (background) thread via threading.Event
until the user finishes the selection or presses ESC.
"""

from __future__ import annotations

import ctypes
import logging
import threading
from typing import Callable

import tkinter as tk
from PIL import ImageGrab

from ocrclipstack.feedback import get_tk_manager

log = logging.getLogger(__name__)


def select_region(callback: Callable[..., None]) -> None:
    """Show a full-screen overlay and let the user draw a selection rectangle.

    Blocks the calling thread until the overlay is closed.  Then calls
    *callback(image, bbox)* with the captured PIL Image and bounding box,
    or *callback(None, None)* on cancel / too-small selection.
    """
    done = threading.Event()

    def _create() -> None:
        root = get_tk_manager().root
        if root is None:
            log.error("overlay: TkManager root is None — cannot show overlay")
            callback(None, None)
            done.set()
            return

        # Virtual screen dimensions (all monitors combined)
        user32 = ctypes.windll.user32
        vx = user32.GetSystemMetrics(76)   # SM_XVIRTUALSCREEN
        vy = user32.GetSystemMetrics(77)   # SM_YVIRTUALSCREEN
        vw = user32.GetSystemMetrics(78)   # SM_CXVIRTUALSCREEN
        vh = user32.GetSystemMetrics(79)   # SM_CYVIRTUALSCREEN

        win = tk.Toplevel(root)
        win.geometry(f"{vw}x{vh}+{vx}+{vy}")
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.attributes("-alpha", 0.3)
        win.configure(bg="black", cursor="cross")

        canvas = tk.Canvas(win, bg="black", highlightthickness=0)
        canvas.pack(fill=tk.BOTH, expand=True)

        state: dict = {"start_x": 0, "start_y": 0, "rect_id": None}

        def on_press(event: tk.Event) -> None:
            state["start_x"] = event.x_root
            state["start_y"] = event.y_root

        def on_drag(event: tk.Event) -> None:
            if state["rect_id"]:
                canvas.delete(state["rect_id"])
            sx = state["start_x"] - win.winfo_rootx()
            sy = state["start_y"] - win.winfo_rooty()
            ex = event.x_root - win.winfo_rootx()
            ey = event.y_root - win.winfo_rooty()
            state["rect_id"] = canvas.create_rectangle(
                sx, sy, ex, ey, outline="lime", width=2
            )

        def on_release(event: tk.Event) -> None:
            x1 = min(state["start_x"], event.x_root)
            y1 = min(state["start_y"], event.y_root)
            x2 = max(state["start_x"], event.x_root)
            y2 = max(state["start_y"], event.y_root)
            win.destroy()

            if abs(x2 - x1) < 3 or abs(y2 - y1) < 3:
                callback(None, None)
                done.set()
                return

            bbox = (x1, y1, x2, y2)
            try:
                image = ImageGrab.grab(bbox=bbox, all_screens=True)
            except Exception:
                log.exception("overlay: ImageGrab failed")
                callback(None, None)
                done.set()
                return
            callback(image, bbox)
            done.set()

        def on_escape(_event: tk.Event) -> None:
            win.destroy()
            callback(None, None)
            done.set()

        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<B1-Motion>", on_drag)
        canvas.bind("<ButtonRelease-1>", on_release)
        win.bind("<Escape>", on_escape)
        win.focus_force()

    get_tk_manager().schedule(_create)
    done.wait()  # Block calling thread until selection is complete
