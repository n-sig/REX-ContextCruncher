# Changelog

All notable changes to ContextCruncher are documented in this file.

## [Unreleased] — Code Audit Fixes

### Fixed

- **F-01 (P1):** `search_picker.py` created a new `tk.Tk()` root instead of
  using `TkManager.Toplevel`, violating design decision #1 (single Tk root).
  Refactored to use `get_tk_manager().schedule()` + `tk.Toplevel`.
- **F-02 (P1):** `variant_picker.py` same issue as F-01. Fixed identically.
- **F-03 (P1):** `ui/heatmap.py` same issue as F-01. Fixed identically.
- **F-04 (P2):** `mcp_server.py:search_stack()` accessed `_stack._items`
  directly. Replaced with `_stack.get_entry(i)` via public API.
- **F-05 (P2):** `mcp_server.py:resource_clipboard_history()` same issue.
  Fixed identically.
- **F-06 (P2):** `tray.py` accessed `self._stack._items[i]` directly.
  Replaced with `self._stack.get_entry(i)`.
- **F-07 (P2):** `search_picker.py` accessed `stack._items` directly.
  Replaced with `stack.get_entry(i)` via `range(stack.size())`.
- **F-08 (P3):** `text_processor.py` had a dead `_REPEATED_PUNCT` definition
  at line 184 (escaped backslash, non-functional). Removed; line 205 is the
  correct definition.
- **F-09 (P3):** `text_processor.py` SYNONYMS dict contained a duplicate
  `"approximately": "~"` entry. Removed the duplicate.

### Documentation

- Marked all 6 legacy bug entries as fixed (were stale "Offen").
- Created per-finding bug documentation.
- Created this CHANGELOG.md.

## [0.2.0-beta] — Prior Release

### Added

- Security scanner (two-pass: named regex + Shannon entropy)
- Code/JSON/XML/YAML skeletonizer
- Clipboard monitor with debounce
- Full-screen OCR hotkey (FR-01)
- Token cost estimates (FR-02)
- Context window usage warnings (FR-03)
- Mouse side-button hotkeys (FR-04)
- AI Prompt Optimizer (FR-05, opt-in, httpx)
- Content router with smart detection
- Diff cache for delta tracking
- Search picker (Win+V-style search)
- Pinned items with persistence
- 333 tests (229 at release, expanded since)
