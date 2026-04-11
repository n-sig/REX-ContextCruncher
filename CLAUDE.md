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
├── token_counter.py     # tiktoken-based token counting
├── mcp_server.py        # MCP server (13 tools + 2 resources)
├── ocr.py               # Windows OCR engine wrapper
├── overlay.py           # Screen region selection overlay
├── clipboard.py         # Clipboard read/write
├── clipboard_monitor.py # Auto-Crunch clipboard monitoring
├── normalize.py         # Number/IBAN/phone compact variants
├── feedback.py          # Toast notifications + flash overlay
├── config.py            # JSON settings persistence
├── settings.py          # Settings GUI window
├── hotkeys.py           # Hotkey recording/parsing
├── tray.py              # System tray icon + menu
└── variant_picker.py    # Win+V-style popup picker
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

## MCP Server

The MCP server runs as standalone process via stdio transport. 13 tools available:

| Tool | Purpose |
|---|---|
| `ocr_scan_region` | Interactive screen OCR |
| `screenshot_full` | Full-screen OCR |
| `read_clipboard` | Read clipboard |
| `crunch_text` | Compress text (level 1-4) |
| `crunch_file` | Compress a file |
| `crunch_directory` | Compress entire directory |
| `count_text_tokens` | Count LLM tokens |
| `get_brevity_prompt` | Output-brevity system prompt |
| `search_stack` | Search history |
| `ocr_get_stack` | Get full history |
| `ocr_get_current` | Get current entry |
| `ocr_push_text` | Push to clipboard + stack |
| `ocr_clear_stack` | Clear history |

## Compression Levels

| Level | Name | Token Savings | Safe for Code? |
|---|---|---|---|
| 1 | 🪶 Light | ~10% | ✅ Yes |
| 2 | 🦖 Token-Cruncher | ~25% | ⚠️ Prose only |
| 3 | 💀 Annihilator | ~45% | ❌ No |
| 4 | ☢️ Experimental | ~60% | ❌ No |

## Testing

```bash
python -m pytest tests/ -v
python evals/run_eval.py  # Benchmark with tiktoken token counts
```

## Important: Threading

- Global hotkeys run on the main thread (pynput)
- All Tkinter UI runs on `TkUIThread`
- OCR and clipboard operations can be called from any thread
- `_ignore_next_changes` counter prevents Auto-Crunch feedback loops
