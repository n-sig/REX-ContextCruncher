"""
TextStack — In-memory, session-based history stack for scanned texts.

No file I/O, no persistence. All data stays in RAM and is discarded on exit.

Each entry stores multiple variants of the same text (original, compact numbers,
AI-compressed levels). The user can cycle through them with a single hotkey
or pick from a popup.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

MAX_STACK_SIZE = 50


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

    def toggle(self) -> str | None:
        """Legacy compat: toggle between first two variants."""
        result = self.cycle()
        if result is None:
            return None
        return result.text


class TextStack:
    """LIFO stack with a navigable cursor and a fixed maximum size (FIFO eviction)."""

    def __init__(self, max_size: int = MAX_STACK_SIZE) -> None:
        self._items: deque[_Entry] = deque(maxlen=max_size)
        self._cursor: int = 0

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
        """Move the cursor: +1 = older, -1 = newer. Returns the new current text."""
        if not self._items:
            return None
        new_pos = self._cursor + direction
        if 0 <= new_pos < len(self._items):
            self._cursor = new_pos
        return self.current()

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

    def toggle_compact(self) -> str | None:
        """Legacy: Toggle between original and compact."""
        if not self._items:
            return None
        return self._items[self._cursor].toggle()

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

    def size(self) -> int:
        """Return the number of entries in the stack."""
        return len(self._items)

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
