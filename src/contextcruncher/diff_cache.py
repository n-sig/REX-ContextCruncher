"""
diff_cache.py — In-memory content cache for delta tracking.

Stores SHA-256 hashes mapped to full text content, enabling diff_crunch
to return only the changes on repeated loads of the same file or text.

The cache lives entirely in RAM and is discarded when the MCP server
process exits.  No disk I/O, no persistence.
"""

from __future__ import annotations

import difflib
import hashlib
import time
from collections import OrderedDict

_MAX_CACHE_SIZE = 100


class DiffCache:
    """In-memory text cache keyed by content hash."""

    def __init__(self) -> None:
        self._cache: OrderedDict[str, str] = OrderedDict()      # hash → content
        self._timestamps: OrderedDict[str, float] = OrderedDict()  # hash → epoch

    def store(self, text: str) -> str:
        """Store *text* and return a short hash ID (16 hex chars).

        When the cache exceeds ``_MAX_CACHE_SIZE`` entries the oldest
        entry is evicted (LRU).
        """
        h = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16]
        # Move to end if already present (refresh LRU position).
        if h in self._cache:
            self._cache.move_to_end(h)
            self._timestamps.move_to_end(h)
        self._cache[h] = text
        self._timestamps[h] = time.time()
        # Evict oldest entry when over limit.
        while len(self._cache) > _MAX_CACHE_SIZE:
            self._cache.popitem(last=False)
            self._timestamps.popitem(last=False)
        return h

    def get(self, hash_id: str) -> str | None:
        """Retrieve cached content by *hash_id*, or ``None`` if missing."""
        return self._cache.get(hash_id)

    def compute_diff(self, old_hash: str, new_text: str) -> dict:
        """Compute a unified diff between the cached version and *new_text*.

        Returns a dict with:
          - changes_text:  unified diff string
          - lines_added:   count of added lines
          - lines_removed: count of removed lines
          - change_type:   "modified", "added", or "removed"
        """
        old_text = self._cache.get(old_hash, "")
        if not old_text:
            return {
                "changes_text": new_text,
                "lines_added": len(new_text.splitlines()),
                "lines_removed": 0,
                "change_type": "full",
            }

        old_lines = old_text.splitlines(keepends=True)
        new_lines = new_text.splitlines(keepends=True)

        diff = list(difflib.unified_diff(old_lines, new_lines, n=3))
        added = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
        removed = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))

        if added == 0 and removed == 0:
            change_type = "unchanged"
        elif added and removed:
            change_type = "modified"
        elif added:
            change_type = "added"
        else:
            change_type = "removed"

        return {
            "changes_text": "".join(diff),
            "lines_added": added,
            "lines_removed": removed,
            "change_type": change_type,
        }

    def size(self) -> int:
        """Return the number of cached entries."""
        return len(self._cache)
