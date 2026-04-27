"""
TextStack — In-memory, session-based history stack for scanned texts.

No file I/O, no persistence. All data stays in RAM and is discarded on exit.

Each entry stores multiple variants of the same text (original, compact numbers,
AI-compressed levels). The user can cycle through them with a single hotkey
or pick from a popup.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field, asdict
import os
import json
import logging
import time
from contextcruncher.config import _APP_DIR

logger = logging.getLogger(__name__)

MAX_STACK_SIZE = 50
MAX_PINNED_SIZE = 10
PINNED_PATH = os.path.join(_APP_DIR, "pinned.json")

# Dedup window for push_variants(): reject an incoming entry whose original
# text matches any of the N most-recent entries. Protects against Auto-Crunch
# ping-pong (A → compressed(A) → A re-paste) and accidental re-copies of the
# same source while the user moves text between windows.
_DEDUP_WINDOW = 10


@dataclass
class Variant:
    """A single text variant with a label and saving statistics."""
    label: str
    text: str
    saved_percent: float = 0.0


@dataclass
class _Entry:
    """A single stack entry holding multiple text variants."""
    variants: list[Variant] = field(default_factory=list)
    active_index: int = 0
    # Unix timestamp (seconds) when this entry was created. Used by the
    # tray menu to render a relative "freshness" hint like "now" / "2m".
    created_at: float = field(default_factory=time.time)

    @property
    def text(self) -> str:
        """Return the currently active variant's text."""
        if not self.variants:
            return ""
        return self.variants[self.active_index].text

    @property
    def original(self) -> str:
        """Return the first (original) variant's text."""
        if not self.variants:
            return ""
        return self.variants[0].text

    @property
    def compact(self) -> str | None:
        """Backwards compat: return the second variant if it exists, else None."""
        if len(self.variants) > 1:
            return self.variants[1].text
        return None

    @property
    def label(self) -> str:
        if self.variants:
            return self.variants[self.active_index].label
        return ""

    def saved_percent(self) -> float:
        if self.variants:
            return self.variants[self.active_index].saved_percent
        return 0.0

    @property
    def active_variant(self) -> Variant | None:
        """Return the currently active Variant object."""
        if not self.variants:
            return None
        return self.variants[self.active_index]

    def cycle(self) -> Variant | None:
        """Advance to the next variant (wrapping around). Returns the new active Variant.
        Returns None if there is only one variant (nothing to cycle).
        """
        if len(self.variants) <= 1:
            return None
        self.active_index = (self.active_index + 1) % len(self.variants)
        return self.variants[self.active_index]

    def set_variant(self, index: int) -> Variant | None:
        """Set a specific variant by index. Returns the Variant or None."""
        if 0 <= index < len(self.variants):
            self.active_index = index
            return self.variants[self.active_index]
        return None

    @property
    def mode_label(self) -> str:
        """Return a short indicator for the current mode."""
        if len(self.variants) <= 1:
            return ""
        v = self.variants[self.active_index]
        return f"  [{v.label}]"

    # Backwards compat shim
    @property
    def use_compact(self) -> bool:
        return self.active_index > 0

    @use_compact.setter
    def use_compact(self, value: bool) -> None:
        if value and len(self.variants) > 1:
            self.active_index = 1
        else:
            self.active_index = 0

    @classmethod
    def from_dict(cls, data: dict) -> _Entry:
        variants = [Variant(**v) for v in data.get("variants", [])]
        return cls(variants=variants, active_index=data.get("active_index", 0))

    def to_dict(self) -> dict:
        return {
            "variants": [asdict(v) for v in self.variants],
            "active_index": self.active_index
        }


class TextStack:
    """LIFO stack with a navigable cursor and a fixed maximum size (FIFO eviction)."""

    def __init__(self, max_size: int = MAX_STACK_SIZE, min_length: int = 0) -> None:
        """
        :param max_size: Maximum number of entries before oldest are evicted.
        :param min_length: Minimum character length (stripped) for an entry to be
            accepted.  Entries shorter than this are silently dropped.  Defaults
            to 0 (no minimum).  Set to 5 (same as ClipboardMonitor's default) to
            keep filtering behaviour consistent across all entry paths (clipboard,
            MCP tools, hotkeys, etc.).
        """
        self._items: deque[_Entry] = deque(maxlen=max_size)
        self._pinned_items: deque[_Entry] = deque(maxlen=MAX_PINNED_SIZE)
        self._cursor: int = 0
        self._min_length: int = max(0, min_length)
        self._load_pinned()

    def _load_pinned(self) -> None:
        try:
            if os.path.isfile(PINNED_PATH):
                with open(PINNED_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data:
                        self._pinned_items.append(_Entry.from_dict(item))
        except Exception as e:
            logger.warning(f"Failed to load pinned items: {e}")

    def _save_pinned(self) -> None:
        try:
            os.makedirs(_APP_DIR, exist_ok=True)
            with open(PINNED_PATH, "w", encoding="utf-8") as f:
                data = [item.to_dict() for item in self._pinned_items]
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Failed to save pinned items: {e}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def push_variants(self, variants: list[Variant]) -> None:
        """Push an entry with pre-computed variants onto the stack.

        The first variant should be the original text. Subsequent variants
        are alternative views (compact, AI-compressed, etc.).
        """
        if not variants or not variants[0].text:
            return

        # min_length guard — mirrors ClipboardMonitor's min_text_length so that
        # all entry paths (clipboard, MCP, hotkeys) enforce the same floor.
        if self._min_length > 0 and len(variants[0].text.strip()) < self._min_length:
            logger.debug(
                "TextStack: ignoring short entry (%d chars < min %d)",
                len(variants[0].text.strip()), self._min_length,
            )
            return

        # Dedup — reject if the new original matches any of the _DEDUP_WINDOW
        # most-recent entries. Fixes Auto-Crunch ping-pong (Bild 1) where the
        # same source text kept landing in the stack twice because the check
        # only looked at index 0.
        new_text = variants[0].text
        dedup_limit = min(_DEDUP_WINDOW, len(self._items))
        for i in range(dedup_limit):
            if self._items[i].original == new_text:
                # Move the existing entry to the front so recency stays
                # correct instead of silently dropping the re-copy.
                if i != 0:
                    existing = self._items[i]
                    del self._items[i]
                    self._items.appendleft(existing)
                self._cursor = 0
                return

        self._items.appendleft(_Entry(variants=variants))
        self._cursor = 0

    def push(self, text: str, compact: str | None = None) -> None:
        """Legacy push: original text + optional compact variant.

        Prefer push_variants() for new code.
        """
        if not text:
            return
        variants = [Variant(label="Original", text=text)]
        if compact:
            variants.append(Variant(label="Compact", text=compact))
        self.push_variants(variants)

    def current(self) -> str | None:
        """Return the text at the current cursor position, or *None* if empty."""
        if not self._items:
            return None
        return self._items[self._cursor].text

    def current_entry(self) -> _Entry | None:
        """Return the current entry, or None if empty."""
        if not self._items:
            return None
        return self._items[self._cursor]

    def navigate(self, direction: int) -> str | None:
        """Move the cursor: +1 = older, -1 = newer.

        FIX (Bug #5): Returns the new current text only when the cursor
        actually moved.  Returns *None* when already at the boundary so
        callers can suppress the success beep / toast.
        """
        if not self._items:
            return None
        new_pos = self._cursor + direction
        if 0 <= new_pos < len(self._items):
            self._cursor = new_pos
            return self.current()
        return None  # Already at boundary — nothing changed

    def cycle_variant(self) -> Variant | None:
        """Cycle the current entry to its next variant.

        Returns the new active Variant, or None if there's only one variant.
        """
        if not self._items:
            return None
        return self._items[self._cursor].cycle()

    def set_variant(self, index: int) -> Variant | None:
        """Set a specific variant on the current entry by index."""
        if not self._items:
            return None
        return self._items[self._cursor].set_variant(index)

    def has_compact(self) -> bool:
        """Return True if the current entry has more than one variant."""
        if not self._items:
            return False
        return len(self._items[self._cursor].variants) > 1

    def clear(self) -> None:
        """Remove all entries and reset the cursor."""
        self._items.clear()
        self._cursor = 0

    def get_entry(self, index: int) -> _Entry | None:
        """Return the entry at *index*, or None if out of bounds."""
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def set_cursor(self, index: int) -> bool:
        """Move the cursor to *index*.  Returns True on success.

        Added for Bug #9 fix: replaces direct ``_cursor`` mutation in
        main.py and tray.py.
        """
        if 0 <= index < len(self._items):
            self._cursor = index
            return True
        return False

    def size(self) -> int:
        """Return the number of entries in the stack."""
        return len(self._items)

    def pinned_size(self) -> int:
        return len(self._pinned_items)

    def get_pinned_items(self) -> list[_Entry]:
        return list(self._pinned_items)

    def pin_current(self) -> bool:
        """Pin the current stack entry."""
        if not self._items:
            return False
        entry = self._items[self._cursor]
        for p in self._pinned_items:
            if p.original == entry.original:
                return False
        # Create a deep-ish copy 
        self._pinned_items.append(_Entry.from_dict(entry.to_dict()))
        self._save_pinned()
        return True

    def unpin(self, index: int) -> bool:
        if 0 <= index < len(self._pinned_items):
            del self._pinned_items[index]
            self._save_pinned()
            return True
        return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def label(self) -> str:
        """Return a human-readable label like ``[2/5] Hello World... [AI Lv.2]``."""
        if not self._items:
            return "[0/0]"
        entry = self._items[self._cursor]
        preview = entry.text
        if len(preview) > 40:
            preview = preview[:37] + "..."
        mode = entry.mode_label
        return f"[{self._cursor + 1}/{len(self._items)}] {preview}{mode}"
