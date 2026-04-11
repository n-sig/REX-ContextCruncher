"""
Clipboard Monitor — Polls the Windows Clipboard safely.

Uses ctypes and user32.GetClipboardSequenceNumber() to check if the clipboard 
content has changed. If it changes and Auto-Crunch is active, evaluates the content,
minifies it, and writes it back while tracking its own sequence updates.
"""

from __future__ import annotations

import time
import threading
import ctypes
import pyperclip
from typing import Callable
from datetime import datetime

class ClipboardMonitor:
    def __init__(self, check_interval: float = 0.5, on_clipboard_changed: Callable[[str], str] = None) -> None:
        """
        :param check_interval: How often to poll the sequence number.
        :param on_clipboard_changed: A callback that receives the current text and 
                                     returns the minified text if it should be overwritten.
                                     Return None to do nothing.
        """
        self.check_interval = check_interval
        self.on_clipboard_changed = on_clipboard_changed
        self.is_running = False
        self._thread: threading.Thread | None = None
        
        self.get_seq = ctypes.windll.user32.GetClipboardSequenceNumber
        self.last_seq = self.get_seq()
        
        # A flag so we know the next N clipboard changes are our own writes
        self._ignore_next_changes = 0

    def start(self) -> None:
        if self.is_running:
            return
        self.is_running = True
        self.last_seq = self.get_seq()
        self._thread = threading.Thread(target=self._run, daemon=True, name="ClipboardMonitorThread")
        self._thread.start()

    def stop(self) -> None:
        self.is_running = False

    def _run(self) -> None:
        while self.is_running:
            time.sleep(self.check_interval)
            
            try:
                current_seq = self.get_seq()
                if current_seq == 0 or current_seq == self.last_seq:
                    continue

                # The clipboard changed!
                self.last_seq = current_seq

                if self._ignore_next_changes > 0:
                    # Ignore the change since we just wrote to the clipboard ourselves.
                    self._ignore_next_changes -= 1
                    continue

                if not self.on_clipboard_changed:
                    continue
                
                # Give the OS a tiny fraction of a second to release locks if needed
                time.sleep(0.05)
                
                try:
                    text = pyperclip.paste()
                except Exception:
                    # pyperclip might fail if another program is holding the clipboard open
                    continue

                if not text or not str(text).strip():
                    continue

                # Invoke the callback
                new_text = self.on_clipboard_changed(str(text))
                
                if new_text is not None and new_text != str(text):
                    # Write the minified text back.
                    # FIX (Bug #4): increment _ignore_next_changes BEFORE writing
                    # so the monitor skips its own write on the very next poll.
                    # pyperclip.copy() can trigger 1–2 sequence-number increments
                    # depending on the clipboard implementation; setting 2 is safe.
                    try:
                        self._ignore_next_changes += 2
                        pyperclip.copy(new_text)

                        # Give the OS a moment to settle, then update last_seq.
                        time.sleep(0.05)
                        self.last_seq = self.get_seq()
                    except Exception:
                        # If the write failed, undo the counter increment.
                        self._ignore_next_changes = max(0, self._ignore_next_changes - 2)
                        
            except Exception as e:
                # Catch-all to prevent monitor thread from crashing
                print(f"ClipboardMonitor error: {e}")

