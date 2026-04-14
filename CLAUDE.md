# CLAUDE.md

This file provides guidance to Claude Code and other AI agents working with this repository.

## Project Overview

**ContextCruncher** is an AI-optimized clipboard manager for Windows with screen OCR, multi-level token compression, and an MCP server. Everything runs locally — no cloud, no admin, no network.

- **Language:** Python 3.11+
- **Platform:** Windows 10 (1903+) / Windows 11
- **GUI:** Tkinter (system tray + overlays)
- **OCR Engine:** Native Windows OCR (`winrt-Windows.Media.Ocr`)

## Architecture

```
src/contextcruncher/
├── main.py              # Entry point, TkUIThread, hotkey registration
├── stack.py             # TextStack with multi-variant support
├── text_processor.py    # 4-level AI token compression engine
├── token_counter.py     # tiktoken token counting + cost/context estimates
├── mcp_server.py        # MCP server (15 tools + 2 resources)
├── ocr.py               # Windows OCR engine wrapper (language support)
├── overlay.py           # Screen region selection overlay
├── clipboard.py         # Clipboard read/write
├── clipboard_monitor.py # Auto-Crunch clipboard monitoring (debounced)
├── normalize.py         # Number/IBAN/phone compact variants
├── feedback.py          # Toast notifications + flash overlay
├── config.py            # JSON settings persistence + hotkey helpers
├── settings.py          # Settings GUI window (incl. mouse hotkeys)
├── hotkeys.py           # Global hotkey manager (keyboard + mouse X1/X2)
├── tray.py              # System tray icon + menu
├── variant_picker.py    # Win+V-style popup picker
└── ui/
    └── heatmap.py       # Token heatmap window (cost + context bars)
```

## Common Commands

```bash
# Run from source
python src/contextcruncher/main.py

# Run tests
python -m pytest tests/ -v

# Run compression benchmarks
python evals/run_eval.py

# Build executable
pyinstaller build.spec

# Setup MCP in AI tools
python setup_mcp.py --all
```

## Key Design Decisions

1. **Single Tk root on dedicated thread:** All Tkinter UI runs on `TkUIThread`. Never create additional `tk.Tk()` instances. Always use `Toplevel`.
2. **In-memory only:** `TextStack` uses `deque(maxlen=50)`. No disk persistence by design.
3. **Deterministic compression:** `minify_for_ai()` is a pure function. Same input always produces same output. No LLM calls for compression.
4. **Variant system:** Each stack entry stores multiple pre-computed variants (Original → Compact → AI Lv.1-4). No on-demand computation.
5. **Zero network:** No HTTP/networking libraries imported anywhere in the project.
6. **Mouse hotkeys via separate listener:** `_MouseHotkeyListener` wraps `pynput.mouse.Listener` and is only started when at least one `<mouse_x1>`/`<mouse_x2>` binding is configured. Keyboard and mouse listeners are strictly separated in `HotkeyManager`.
7. **Autostart command (dev vs. frozen):** `_get_autostart_command()` in `config.py` builds `"python.exe" "script.py"` in dev mode and `"app.exe"` in frozen mode. Never write a bare `.py` path to the registry.
8. **Clipboard debounce:** `ClipboardMonitor` uses `debounce_delay=0.3s` by default. Pass `debounce_delay=0` to restore immediate behavior (useful in tests).
9. **OCR minimum size:** `_MIN_OCR_HEIGHT = 96px`, `_OCR_PADDING = 24px`. Background padding color is derived from the image corner pixel — never hard-coded white.
10. **Security scanner two-pass:** Pass 1 runs named regex patterns (AWS, Stripe, OpenAI, etc.); Pass 2 applies Shannon entropy ≥ 4.5 as catch-all. Pure lowercase strings are never flagged.

## Hotkeys (defaults)

| Action | Default combo |
|---|---|
| Scan Region | `Ctrl+Alt+S` |
| Full Screen OCR | `Ctrl+Alt+F` |
| AI Compact | `Ctrl+Alt+C` |
| Newer ↑ | `Ctrl+Shift+↑` |
| Older ↓ | `Ctrl+Shift+↓` |
| Variants ↔ | `Ctrl+Shift+→` |
| Token Heatmap | `Alt+H` |

Mouse side buttons (`<mouse_x1>`, `<mouse_x2>`) can also be assigned to any action via the Settings UI.

## MCP Server

The MCP server runs as standalone process via stdio transport. **15 tools** available:

| Tool | Purpose |
|---|---|
| `ocr_scan_region` | Interactive screen OCR |
| `screenshot_full` | Full-screen OCR (FR-01) |
| `read_clipboard` | Read clipboard |
| `crunch_text` | Compress text (level 1-4) |
| `crunch_file` | Compress a file |
| `crunch_directory` | Compress entire directory |
| `crunch_code_skeleton` | Skeleton of code file |
| `crunch_file_skeleton` | Skeleton of JSON/XML/YAML file |
| `count_text_tokens` | Count LLM tokens + cost estimates |
| `get_brevity_prompt` | Output-brevity system prompt |
| `search_stack` | Search history |
| `ocr_get_stack` | Get full history |
| `ocr_get_current` | Get current entry |
| `ocr_push_text` | Push to clipboard + stack |
| `ocr_clear_stack` | Clear history |

`count_text_tokens` returns `cost_estimates_usc` (micro-dollar cents per model) in addition to token counts.

## Compression Levels

| Level | Name | Token Savings | Safe for Code? |
|---|---|---|---|
| 1 | 🪶 Light | ~10% | ✅ Yes |
| 2 | 🦖 Token-Cruncher | ~25% | ⚠️ Prose only |
| 3 | 💀 Annihilator | ~45% | ❌ No |
| 4 | ☢️ Experimental | ~60% | ❌ No |

## Token Cost & Context Window (token_counter.py)

`COST_TABLE` — USD per 1M input tokens (as of 2025):

| Model | $/1M tokens |
|---|---|
| GPT-4o | $2.50 |
| GPT-4o mini | $0.15 |
| o3 mini | $1.10 |
| Claude 3.5 Sonnet | $3.00 |
| Claude 3.5 Haiku | $0.80 |
| Claude 3 Opus | $15.00 |

`CONTEXT_WINDOW_TABLE` — context window sizes:

| Model | Tokens |
|---|---|
| GPT-4o / GPT-4o mini | 128,000 |
| o3 mini / Claude 3.5 Sonnet / Haiku / Opus | 200,000 |

Context window warning threshold: `context_warn_pct` in `config.json` (default: 75%). A toast is shown after AI Compact if the result exceeds the threshold for any model.

## Security Scanner (security_scanner.py)

Two-pass architecture:
- **Pass 1:** Named regex patterns — AWS secret keys, Stripe keys, OpenAI/Anthropic API keys, generic `Bearer` tokens, etc.
- **Pass 2:** Shannon entropy ≥ 4.5 as catch-all for unknown high-entropy secrets.
- **False-positive guard:** `_looks_like_secret()` requires character-type diversity (upper + digit or special). Pure lowercase strings are never flagged.

## Testing

```bash
python -m pytest tests/ -v
python evals/run_eval.py  # Benchmark with tiktoken token counts
```

**Test suite status (v0.2.0-beta):** 229 passed · 3 skipped (WinRT/Windows-only) · 0 failed

Key test files added in v0.2.0:

| File | Coverage |
|---|---|
| `test_security_scanner.py` | BUG-01: entropy + named patterns |
| `test_skeletonizer.py` | BUG-02: JSON/XML/YAML skeleton |
| `test_clipboard_monitor.py` | BUG-03: min_text_length guard |
| `test_ocr_languages.py` | BUG-04: language list + settings |
| `test_hotkey_collision.py` | BUG-05: collision detection |
| `test_ocr_upscale.py` | BUG-06: small selection padding |
| `test_clipboard_debounce.py` | BUG-07: debounce logic |
| `test_autostart_command.py` | BUG-08: dev-mode registry value |
| `test_fr01_screenshot_hotkey.py` | FR-01: full-screen OCR hotkey |
| `test_fr02_cost_estimate.py` | FR-02: cost estimation |
| `test_fr03_context_window.py` | FR-03: context window warning |
| `test_fr04_mouse_hotkeys.py` | FR-04: mouse side-button hotkeys |

**Isolation note for mouse tests:** `test_fr04_mouse_hotkeys.py` unconditionally overwrites `sys.modules["pynput"]` and `sys.modules["pynput.mouse"]` and calls `importlib.reload()` on `contextcruncher.hotkeys` to prevent test-order pollution from other pynput stubs.

## Important: Threading

- Global hotkeys run in daemon threads (pynput keyboard + optional mouse listener)
- All Tkinter UI runs on `TkUIThread`
- OCR and clipboard operations can be called from any thread
- `_ignore_next_changes` counter prevents Auto-Crunch feedback loops
- `_scan_active` threading.Event prevents concurrent OCR scans (region and full-screen share the same lock)
