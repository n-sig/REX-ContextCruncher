"""
Clipboard Monitor — Polls the Windows Clipboard safely.

Uses ctypes and user32.GetClipboardSequenceNumber() to check if the clipboard
content has changed.  If it changes and Auto-Crunch is active, evaluates the
content, minifies it, and writes it back while tracking its own sequence
updates.

BUG-03 fix: added *min_text_length* guard (default 5) so that very short
clipboard events produced by background applications (IDEs, browsers, Teams,
…) do not inflate the stack counter.
"""

from __future__ import annotations

import time
import threading
import ctypes
import logging
import pyperclip
from typing import Callable

logger = logging.getLogger(__name__)


class ClipboardMonitor:
    def __init__(
        self,
        check_interval: float = 0.5,
        on_clipboard_changed: Callable[[str], str | None] | None = None,
        min_text_length: int = 5,
    ) -> None:
        """
        :param check_interval:    How often (seconds) to poll the sequence number.
        :param on_clipboard_changed:
            Callback that receives the current clipboard text and returns the
            replacement text if the clipboard should be overwritten, or *None*
            to leave it unchanged.
        :param min_text_length:
            Minimum length (characters, after stripping) a clipboard entry must
            have before the callback is invoked.  Entries shorter than this
            threshold are silently ignored.  Prevents background applications
            (browsers, IDEs, system tools) from flooding the stack with
            single-character or very short clipboard writes.
            Default: 5.  Set to 0 to disable the filter entirely.
        """
        self.check_interval = check_interval
        self.on_clipboard_changed = on_clipboard_changed
        self.min_text_length = max(0, min_text_length)
        self.is_running = False
        self._thread: threading.Thread | None = None

        self.get_seq = ctypes.windll.user32.GetClipboardSequenceNumber
        self.last_seq = self.get_seq()

    def start(self) -> None:
        if self.is_running:
            return
        self.is_running = True
        self.last_seq = self.get_seq()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="ClipboardMonitorThread"
        )
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

                # The clipboard changed — update sequence before any early-out
                self.last_seq = current_seq

                if not self.on_clipboard_changed:
                    continue

                # Give the OS a tiny fraction of a second to release locks
                time.sleep(0.05)

                try:
                    text = pyperclip.paste()
                except Exception:
                    # pyperclip may fail if another process is holding the clipboard
                    continue

                # Guard 1 — skip truly empty clipboard content
                if not text or not str(text).strip():
                    continue

                text = str(text)

                # Guard 2 (BUG-03) — skip very short content from background apps.
                # Background processes (browsers, IDEs, Teams, etc.) frequently
                # write single characters, URL fragments, or other short strings
                # to the clipboard.  These are usually not intentional user copies
                # and inflate the stack counter without adding useful history.
                if self.min_text_length > 0 and len(text.strip()) < self.min_text_length:
                    logger.debug(
                        "ClipboardMonitor: ignoring short clipboard entry "
                        "(%d chars < min %d)", len(text.strip()), self.min_text_length
                    )
                    continue

                # Invoke the callback
                new_text = self.on_clipboard_changed(text)

                if new_text is not None and new_text != text:
                    # Write the minified text back.
                    try:
                        # Increment BEFORE writing to prevent our own write
                        # from re-triggering the callback on the next poll cycle.
                        self._ignore_write_back = True
                        pyperclip.copy(new_text)
                        # Give the OS a moment to settle, then sync last_seq.
                        time.sleep(0.05)
                        self.last_seq = self.get_seq()
                    except Exception:
                        pass
                    finally:
                        self._ignore_write_back = False

            except Exception as e:
                # Catch-all to prevent the monitor thread from crashing
                logger.error("ClipboardMonitor error: %s", e)
