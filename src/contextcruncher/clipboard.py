"""
Clipboard management — set clipboard content and simulate Ctrl+V.

Uses pyperclip for clipboard access and pynput for key simulation.
"""

from __future__ import annotations

import time

import pyperclip
from pynput.keyboard import Controller, Key

_keyboard = Controller()


def set_clipboard(text: str) -> None:
    """Copy *text* to the system clipboard."""
    pyperclip.copy(text)


def paste() -> None:
    """Simulate a Ctrl+V keystroke to paste from the clipboard.

    A tiny delay is inserted so the target application can register the
    clipboard change before the paste event arrives.
    """
    time.sleep(0.05)
    _keyboard.press(Key.ctrl)
    _keyboard.press("v")
    _keyboard.release("v")
    _keyboard.release(Key.ctrl)
