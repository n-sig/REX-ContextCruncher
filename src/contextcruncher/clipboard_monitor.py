"""
Clipboard Monitor — Polls the Windows Clipboard safely.

Uses ctypes and user32.GetClipboardSequenceNumber() to check if the clipboard
content has changed.  If it changes and Auto-Crunch is active, evaluates the
content, minifies it, and writes it back while tracking its own sequence
updates.

BUG-03 fix: added *min_text_length* guard (default 5) so that very short
clipboard events produced by background applications (IDEs, browsers, Teams,
…) do not inflate the stack counter.

BUG-07 fix: added *debounce_delay* (default 0.3 s).  Rapid clipboard changes
(e.g. three Ctrl+C in quick succession) only trigger one processing pass for
the final settled state, preventing Level 3/4 compression from blocking the
monitor thread for every intermediate change.
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
        debounce_delay: float = 0.3,
    ) -> None:
        """
        :param check_interval:
            How often (seconds) to poll the clipboard sequence number.
        :param on_clipboard_changed:
            Callback that receives the current clipboard text and returns the
            replacement text if the clipboard should be overwritten, or *None*
            to leave it unchanged.
        :param min_text_length:
            Minimum length (characters, after stripping) a clipboard entry must
            have before the callback is invoked.  Prevents background
            applications from flooding the stack with very short writes.
            Default: 5.  Set to 0 to disable.
        :param debounce_delay:
            Seconds the clipboard must remain unchanged before the callback is
            fired.  Prevents Level 3/4 compression from running for every
            intermediate state when the user copies rapidly.
            Default: 0.3 s.  Set to 0 to disable and restore the original
            "process immediately" behaviour.
        """
        self.check_interval = check_interval
        self.on_clipboard_changed = on_clipboard_changed
        self.min_text_length = max(0, min_text_length)
        self.debounce_delay = max(0.0, debounce_delay)
        self.is_running = False
        self._thread: threading.Thread | None = None

        self.get_seq = ctypes.windll.user32.GetClipboardSequenceNumber
        self.last_seq = self.get_seq()

    # -----------------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------------

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

    # -----------------------------------------------------------------------
    # Poll loop
    # -----------------------------------------------------------------------

    def _run(self) -> None:
        # Debounce state — kept as local variables so they are private to this
        # thread invocation and require no locking.
        _debounce_seq: int | None = None    # seq number we are waiting to process
        _debounce_time: float | None = None  # wall-clock time we first noticed it

        while self.is_running:
            time.sleep(self.check_interval)

            try:
                current_seq = self.get_seq()
                if current_seq == 0:
                    continue

                if current_seq != self.last_seq:
                    # ── Clipboard has changed since last processed ────────────
                    if self.debounce_delay <= 0:
                        # Debouncing disabled — fall through to process right now
                        # (preserves original behaviour when debounce_delay=0).
                        pass

                    elif current_seq != _debounce_seq:
                        # A new (or changed) value — start the debounce clock.
                        _debounce_seq = current_seq
                        _debounce_time = time.time()
                        continue  # do not process yet

                    else:
                        # Same pending value — check whether the window has closed.
                        elapsed = time.time() - (_debounce_time or 0.0)
                        if elapsed < self.debounce_delay:
                            continue  # still within debounce window — keep waiting
                        # Debounce window closed → fall through to process

                else:
                    # Clipboard unchanged since last processed → nothing to do.
                    continue

                # ── Ready to process ─────────────────────────────────────────
                # Commit the sequence number and clear debounce state *before*
                # reading the clipboard so that our own potential write-back
                # does not re-trigger processing on the next poll.
                self.last_seq = current_seq
                _debounce_seq = None
                _debounce_time = None

                if not self.on_clipboard_changed:
                    continue

                # Give the OS a brief moment to release clipboard locks.
                time.sleep(0.05)

                try:
                    text = pyperclip.paste()
                except Exception:
                    # pyperclip may fail if another process holds the clipboard.
                    continue

                # Guard 1 — skip truly empty clipboard content.
                if not text or not str(text).strip():
                    continue

                text = str(text)

                # Guard 2 (BUG-03) — skip very short content from background apps.
                if self.min_text_length > 0 and len(text.strip()) < self.min_text_length:
                    logger.debug(
                        "ClipboardMonitor: ignoring short entry (%d chars < min %d)",
                        len(text.strip()), self.min_text_length,
                    )
                    continue

                # Invoke the callback.
                new_text = self.on_clipboard_changed(text)

                if new_text is not None and new_text != text:
                    # Write the processed text back to the clipboard.
                    try:
                        pyperclip.copy(new_text)
                        # Sync last_seq so our own write is not re-processed.
                        time.sleep(0.05)
                        self.last_seq = self.get_seq()
                    except Exception:
                        pass

            except Exception as exc:
                logger.error("ClipboardMonitor error: %s", exc)
