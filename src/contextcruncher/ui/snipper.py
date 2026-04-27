"""
snipper.py — Object-oriented transparent full-screen snipping tool.

Creates an overlay across all monitors, lets the user draw a rectangle,
and captures the selected region using PIL.ImageGrab.
"""

from __future__ import annotations

import ctypes
import logging
import threading
from typing import Callable, Optional, Any

import tkinter as tk
from PIL import ImageGrab

from contextcruncher.feedback import get_tk_manager, show_toast

log = logging.getLogger(__name__)

class SnippingTool:
    """An object-oriented Snipping Tool implementation."""

    def __init__(self, callback: Callable[..., None]) -> None:
        """
        Args:
            callback: Called with (image, bbox) upon successful snipping, 
                      or (None, None) if cancelled.
        """
        self.callback = callback
        self.done = threading.Event()
        self.state: dict[str, Any] = {"start_x": 0, "start_y": 0, "rect_id": None}
        self.win: Optional[tk.Toplevel] = None
        self.canvas: Optional[tk.Canvas] = None

    def start(self) -> None:
        """Start the snipping process. Blocks until complete or cancelled."""
        get_tk_manager().schedule(self._create_overlay)
        self.done.wait()

    def _create_overlay(self) -> None:
        root = get_tk_manager().root
        if root is None:
            log.error("SnippingTool: TkManager root is None — cannot show overlay")
            self.callback(None, None)
            self.done.set()
            return

        # Virtual screen dimensions (all monitors combined)
        user32 = ctypes.windll.user32
        vx = user32.GetSystemMetrics(76)   # SM_XVIRTUALSCREEN
        vy = user32.GetSystemMetrics(77)   # SM_YVIRTUALSCREEN
        vw = user32.GetSystemMetrics(78)   # SM_CXVIRTUALSCREEN
        vh = user32.GetSystemMetrics(79)   # SM_CYVIRTUALSCREEN

        self.win = tk.Toplevel(root)
        self.win.geometry(f"{vw}x{vh}+{vx}+{vy}")
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.3)
        self.win.configure(bg="black", cursor="cross")

        self.canvas = tk.Canvas(self.win, bg="black", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.win.bind("<Escape>", self._on_escape)
        self.win.focus_force()

    def _on_press(self, event: tk.Event) -> None:
        self.state["start_x"] = event.x_root
        self.state["start_y"] = event.y_root

    def _on_drag(self, event: tk.Event) -> None:
        if self.canvas is None or self.win is None:
            return
        if self.state["rect_id"]:
            self.canvas.delete(self.state["rect_id"])
        
        sx = self.state["start_x"] - self.win.winfo_rootx()
        sy = self.state["start_y"] - self.win.winfo_rooty()
        ex = event.x_root - self.win.winfo_rootx()
        ey = event.y_root - self.win.winfo_rooty()
        
        # Red/noticeable rectangle as requested
        self.state["rect_id"] = self.canvas.create_rectangle(
            sx, sy, ex, ey, outline="red", width=2
        )

    def _on_release(self, event: tk.Event) -> None:
        x1 = min(self.state["start_x"], event.x_root)
        y1 = min(self.state["start_y"], event.y_root)
        x2 = max(self.state["start_x"], event.x_root)
        y2 = max(self.state["start_y"], event.y_root)
        
        if self.win:
            self.win.destroy()

        # Handle click without drag (0x0 area) or very small drag
        if abs(x2 - x1) < 3 or abs(y2 - y1) < 3:
            show_toast("Selection too small — drag a larger region")
            self.callback(None, None)
            self.done.set()
            return

        bbox = (x1, y1, x2, y2)
        try:
            image = ImageGrab.grab(bbox=bbox, all_screens=True)
        except Exception:
            log.exception("SnippingTool: ImageGrab failed")
            self.callback(None, None)
            self.done.set()
            return
            
        self.callback(image, bbox)
        self.done.set()

    def _on_escape(self, event: tk.Event) -> None:
        if self.win:
            self.win.destroy()
        self.callback(None, None)
        self.done.set()
