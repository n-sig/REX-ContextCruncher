"""
Overlay — Transparent full-screen selection rectangle using tkinter.

Opens instantly on scan hotkey, closes after selection or ESC.
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable

from PIL import ImageGrab


import ctypes

def select_region(callback: Callable[..., None]) -> None:
    """Show a full-screen overlay and let the user draw a selection rectangle.

    When the user releases the mouse, a PIL Image of the selected region is
    captured and passed to *callback(image, bbox)*.  If the user presses ESC,
    *callback(None, None)* is called.

    This function blocks until the overlay is closed.
    """
    # Ensure DPI awareness so coordinates exactly match raw screen pixels
    # across multiple monitors with potentially different scaling.
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    root = tk.Tk()

    # Get the bounding box of all monitors combined (the virtual screen)
    user32 = ctypes.windll.user32
    vx = user32.GetSystemMetrics(76)  # SM_XVIRTUALSCREEN
    vy = user32.GetSystemMetrics(77)  # SM_YVIRTUALSCREEN
    vw = user32.GetSystemMetrics(78)  # SM_CXVIRTUALSCREEN
    vh = user32.GetSystemMetrics(79)  # SM_CYVIRTUALSCREEN

    # Position the overlay exactly over the entire virtual screen.
    root.geometry(f"{vw}x{vh}+{vx}+{vy}")
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.attributes("-alpha", 0.3)
    root.configure(bg="black", cursor="cross")

    canvas = tk.Canvas(root, bg="black", highlightthickness=0)
    canvas.pack(fill=tk.BOTH, expand=True)

    state = {"start_x": 0, "start_y": 0, "rect_id": None}

    def on_press(event: tk.Event) -> None:
        state["start_x"] = event.x_root
        state["start_y"] = event.y_root

    def on_drag(event: tk.Event) -> None:
        if state["rect_id"]:
            canvas.delete(state["rect_id"])
        # Convert root coords to canvas coords.
        sx = state["start_x"] - root.winfo_rootx()
        sy = state["start_y"] - root.winfo_rooty()
        ex = event.x_root - root.winfo_rootx()
        ey = event.y_root - root.winfo_rooty()
        state["rect_id"] = canvas.create_rectangle(
            sx, sy, ex, ey,
            outline="lime", width=2,
        )

    def on_release(event: tk.Event) -> None:
        x1 = min(state["start_x"], event.x_root)
        y1 = min(state["start_y"], event.y_root)
        x2 = max(state["start_x"], event.x_root)
        y2 = max(state["start_y"], event.y_root)
        root.destroy()

        if abs(x2 - x1) < 3 or abs(y2 - y1) < 3:
            # Selection too small — treat as cancel.
            callback(None, None)
            return

        # Capture exactly what the user selected. Synthetic padding is applied
        # later in ocr.py to give the OCR engine breathing room.
        bbox = (x1, y1, x2, y2)
        image = ImageGrab.grab(bbox=bbox, all_screens=True)
        callback(image, bbox)

    def on_escape(_event: tk.Event) -> None:
        root.destroy()
        callback(None, None)

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    root.bind("<Escape>", on_escape)

    root.mainloop()
