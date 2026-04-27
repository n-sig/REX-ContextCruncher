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


def set_clipboard_image(image) -> None:
    """Copy a PIL Image to the Windows clipboard."""
    import win32clipboard
    import io
    output = io.BytesIO()
    image.convert("RGB").save(output, "BMP")
    data = output.getvalue()[14:]  # BMP file header is 14 bytes
    output.close()
    
    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
    win32clipboard.CloseClipboard()


def save_image_to_desktop(image) -> str:
    """Save a PIL Image as JPG to the user's Desktop and return the path."""
    import os
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    filename = os.path.join(desktop, f"Snip_{int(time.time())}.jpg")
    image.convert("RGB").save(filename, "JPEG", quality=95)
    return filename
