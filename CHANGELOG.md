# Changelog

All notable changes to ContextCruncher are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Dates are ISO 8601.

## [2.0.0] — 2026-04-19

The AI-Compression release. Adds opt-in LLM-based semantic compression,
fixes a destructive bug in deterministic compression of raw source code,
and introduces a fidelity-focused benchmark for AI instruction files.

### Added

- **`ai_compress` MCP tool** — LLM-based semantic compression that wraps
  `prompt_optimizer.compress()`. Signature:
  `ai_compress(text, aggressive=False, provider="", model="") -> dict`.
  Returns `compressed_text`, `provider`, `model`, `original_tokens`,
  `compressed_tokens`, `saved_percent`, `latency_ms`, `warnings`,
  `aggressive`, and `error` on failure. Total MCP tool count: **23**.
- **Code-safe compression mode (`code_safe_mode`)** — `text_processor.py`
  gains `_detect_raw_code_language()` which identifies unfenced Python /
  JavaScript / generic code from structural signals (`def`, `class`,
  `import`, `const`/`let`/`var`, arrow functions, semicolons/braces).
  When `content_type` starts with `code_`, the destructive prose phases
  (`_phase_trim`, `_phase_optimize`, `_phase_telegraphic`,
  `_phase_structural`) are skipped, and both `_phase_normalize` and
  `FINALIZE` switch to indentation-preserving whitespace regexes.
- **CLAUDE.md fidelity benchmark** — `evals/claude_md_benchmark.py`
  measures preservation rates (not just token savings) for filenames,
  `NEVER`/`ALWAYS`-style constraint keywords, CLI commands, and
  backtick-quoted identifiers. Runs `minify_for_ai` and `smart_route`
  head-to-head on the project's own `CLAUDE.md` by default; supports
  `--input FILE` and `--json PATH`.

### Fixed

- **BUG-13 — Indentation / identifier loss on raw source code.**
  Deterministic compression was previously classifying unfenced Python
  as `prose`, which triggered `_phase_trim` (strips leading indent),
  stop-word filtering (drops single-letter parameters like `a`, `b`),
  synonym substitution inside string literals (`between` → `btwn`),
  and a multi-space collapse in `FINALIZE` that reduced 4-space indent
  to 1 space. All four failure modes are now prevented in code-safe
  mode, and the output is verified via `ast.parse` round-trip in the
  new regression test suite.

### Tests

- Added `tests/test_bug13_code_safe.py` (14 tests) — detector unit
  tests, full-pipeline preservation (indent, params, string literals,
  `ast.parse` round-trip, techniques list), and a prose-regression
  guard ensuring prose savings remain above 10%.
- Added `tests/test_mcp_ai_compress.py` (13 tests) — AST-based
  structural validation (always runs, no heavy imports) + functional
  tests with mocked `po_compress` covering empty/whitespace input,
  success path, `aggressive` flag forwarding, provider/model
  overrides, provider error surfacing, and warning propagation.
- **Total: 444 passed · 10 skipped · 0 failed.**

### Docs

- Updated `CLAUDE.md`: tool count 22 → 23, added design decision #11
  (code-safe compression mode), v2.0 Phase 3 test-file table.
- Updated `README.md`: v2.0 banner, `ai_compress` row in MCP tool
  table, new *Code-Safe Mode* and *Hybrid AI-Compression* sections in
  the AI Token Compression chapter, expanded changelog.
- Updated `SECURITY.md`: new *Hybrid Neuro-Symbolic Compression* and
  *Opt-In LLM Compression* sections documenting the 4-layer
  protective extraction and the trust boundary of `httpx`.

## [1.0.0] — Phase 1 + Phase 2

Hybrid neuro-symbolic extraction and provider UX. Lays the groundwork
for the v2.0 `ai_compress` tool.

### Added

- **4-layer protective extraction** in `prompt_optimizer.py` —
  extracts code blocks, tables, file/URL references, and
  `NEVER`/`ALWAYS` constraint keywords before sending prose to an LLM;
  stitches them back in byte-exact after the rewrite.
- **`agent_config` content-type** in `content_router.py` — detects
  CLAUDE.md / AGENTS.md / GEMINI.md by filename, content heuristics,
  and German keyword density; routes such files through a
  skeleton-skip variant of `smart_route`.
- **Friendly provider error messages** — `_friendly_provider_error()`
  translates raw `httpx` failures (Timeout / 401 / 404 / 429 /
  ConnectError) into actionable German-English hybrid messages.
- **Ollama connection probe** — `probe_ollama()` pings a local Ollama
  daemon and lists installed models; drives the *Test Connection*
  button in Settings.
- **UX polish** — `__version__` exported, shown in the tray menu and
  settings dialog; AI-compression warnings surfaced as toasts; variant
  picker shows compression level + token count.

### Tests

- `test_prompt_optimizer_compress.py` — full `compress()` flow with
  mocked providers, security redaction, hybrid extraction round-trip,
  content-type hints, and validation warnings.
- `test_prompt_optimizer_extractors.py` — the 4 extractors plus
  `_validate_compression`.
- `test_content_router.py` (extended) — `agent_config` detection and
  skeleton-skip routing.
- `test_phase2_ux.py` — `__version__` export, all branches of
  `_friendly_provider_error`, all `probe_ollama` outcomes.

### Fixed (code audit)

- **F-01 / F-02 / F-03** — `search_picker.py`, `variant_picker.py`,
  and `ui/heatmap.py` each created their own `tk.Tk()` root, violating
  design decision #1 (single Tk root). All three now use
  `get_tk_manager().schedule()` + `tk.Toplevel`.
- **F-04 / F-05** — `mcp_server.py:search_stack()` and
  `resource_clipboard_history()` reached into `_stack._items`
  directly. Replaced with the public `_stack.get_entry(i)` API.
- **F-06 / F-07** — `tray.py` and `search_picker.py` had the same
  private-attribute access; fixed identically.
- **F-08** — Removed a dead `_REPEATED_PUNCT` definition in
  `text_processor.py` (escaped backslash, non-functional).
- **F-09** — Removed a duplicate `"approximately": "~"` entry in the
  `SYNONYMS` dict.

## [0.2.0-beta] — 2025 Zero-Friction Update

### Added

- **Full-Screen OCR** (`Ctrl+Alt+F`) — captures the entire primary
  monitor; shares the `_scan_active` lock with region OCR.
- **Token cost estimator** — per-model cost in micro-dollar cents for
  GPT-4o, GPT-4o mini, o3 mini, Claude 3.5 Sonnet / Haiku, Claude 3
  Opus. `count_text_tokens` returns `cost_estimates_usc`.
- **Context window warning** — toast when compressed text exceeds
  `context_warn_pct` (default 75%) of any supported model's window.
- **Mouse side-button hotkeys** (FR-04) — X1 / X2 bindable via
  Settings; separate `_MouseHotkeyListener` starts only when at least
  one mouse binding is configured.
- **Zero-Trust Security Scanner** — two-pass: named patterns (AWS,
  Stripe, OpenAI, Anthropic, JWT, Bearer, ...) + Shannon-entropy
  (≥ 4.5) catch-all. False-positive guard for pure-lowercase strings.
- **Code / JSON / XML / YAML skeletonizer** — preserves structure,
  clamps oversized string values. Tree-sitter based JS/TS function
  blanking.
- **Clipboard monitor** with `debounce_delay=0.3s` and
  `min_text_length` guard (5 chars).
- **Search picker** (`Ctrl+Shift+F`), **pinned stack** (up to 10
  entries), **popup variant picker** (Win+V-style).
- **AI Prompt Optimizer** (FR-05, opt-in, `httpx`) with 5 built-in
  profiles and custom profile support.
- **Content router** with smart content-type detection and routing.
- **Diff cache** for delta-only context loading.

### Fixed

- Security scanner false positives on pure-lowercase prose.
- Stack counter no longer triggered by sub-5-char IDE background
  writes.
- Rapid `Ctrl+C` bursts collapsed via debounce into a single
  callback.
- OCR selections under 96 px height now get padded instead of
  returning empty results; padding color derived from image corner.
- OCR language setting added to Settings UI; `get_available_languages`
  queries the Windows OCR engine.
- Duplicate hotkey bindings blocked at save time by
  `find_hotkey_collision()`.
- Dev-mode autostart registry value now stores
  `"python.exe" "main.py"` instead of a bare `.py` path.

### Fixed (from v0.1.x)

- Tokenizer mismatch — heatmap calculates per-model.
- Tkinter threading crash — single `tk.Tk()` on `TkUIThread`.
- Hotkey recorder listener leak on modifier-only release.
- Double-scan crash — `_scan_active` threading.Event.
- Auto-Crunch ping-pong loop — `_ignore_next_changes += 2` guard.
- Singleton guard — Windows Named Mutex.

### Tests

- 333 passed at release (229 at v0.2.0 tag, expanded since).

---

[2.0.0]: #200--2026-04-19
[1.0.0]: #100--phase-1--phase-2
[0.2.0-beta]: #020-beta--2025-zero-friction-update
