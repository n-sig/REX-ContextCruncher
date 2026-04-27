# REX-ContextCruncher

<div align="center">
  <img src="assets/CC.png" alt="ContextCruncher Logo" width="75%" />
</div>

**AI-optimized clipboard manager with screen OCR, token compression, and MCP server — no cloud, no admin, everything stays in RAM.**

> 🚀 **v2.0.1** — AltGr-safe hotkey defaults, Settings empty-render fix, toast stacking, ping-pong dedup, red-themed UI. See the [Changelog](CHANGELOG.md).

---

## ✨ Features

- **Instant OCR** — Select any area or capture the full screen; text recognized in <1s via native Windows OCR (offline)
- **AI Token Compression** — Content-type-aware pipeline saves 25–45% tokens for LLMs while preserving code 1:1
- **Clipboard Stack** — History of up to 50 entries with multi-variant compression, pin up to 10 entries across restarts
- **Search Overlay** — Interactive search through stack history and pinned elements
- **Zero-Trust Security Scanner** — Automatic redaction of API keys, JWTs, webhooks, AWS/Stripe/OpenAI tokens + Shannon-entropy catch-all
- **Code Skeletonizer** — Structural shrinking of JSON/XML/YAML payloads + `tree-sitter` JS/TS function blanking
- **Token Cost Estimator** — Real-time cost in micro-cents per model (GPT-4o, Claude, o3 mini) with context window warnings
- **MCP Server** — 23 tools for AI agents: OCR, compression, context management, prompt optimization, cost estimation
- **AI Prompt Optimizer** — LLM-based prompt rewriting via OpenAI, Anthropic, or Ollama (opt-in)
- **Mouse Hotkeys** — Side buttons (X1/X2) assignable to any action
- **Multi-Monitor & Multi-Language OCR** — DPI-aware, auto-detects Windows language packs
- **Zero Footprint** — No files written, no network access*, no admin, no telemetry

> \**By default.* Opt-in AI tools (`ai_compress`, `optimize_prompt`) make calls to the configured LLM provider when explicitly invoked. See [SECURITY.md](SECURITY.md).

---

## 📥 Installation

1. Download `ContextCruncher.exe` from the [Releases](../../releases) page
2. Run it — icon appears in your system tray
3. Done. No Python needed.

📖 **[GUI User Guide](docs/user-guide.md)** — full walkthrough of all features

### Build from Source

```bash
git clone https://github.com/n-sig/ContextCruncher.git
cd ContextCruncher
pip install -r requirements.txt
python src/contextcruncher/main.py
```

---

## ⌨️ Hotkeys

| Hotkey | Action |
|---|---|
| `Ctrl+Shift+1` | Full-screen OCR |
| `Ctrl+Shift+2` | Region select → OCR → push to stack |
| `Ctrl+Shift+A` | Compress clipboard with AI token optimizer |
| `Ctrl+Shift+PageUp/Down` | Navigate stack entries |
| `Ctrl+Shift+Space` | Search Overlay |
| `Ctrl+Shift+H` | Token Heatmap |

All hotkeys fully customizable in Settings. Mouse side buttons supported.

---

## 🔌 MCP Server (23 Tools)

```bash
python setup_mcp.py --all      # Auto-register in Claude, Cursor, etc.
python setup_mcp.py --claude    # Claude Desktop only
```

Or manually add to your AI client config:

```json
{
  "mcpServers": {
    "contextcruncher": {
      "command": ["python", "-m", "contextcruncher.mcp_server"]
    }
  }
}
```

📖 **[MCP Setup Guide](docs/mcp-setup.md)** · **[All Tools Reference](docs/tools-reference.md)**

### Core Tools

| Tool | Description |
|---|---|
| `ocr_scan_region` | Interactive screen region OCR |
| `screenshot_full` | Full-screen OCR |
| `read_clipboard` | Read current clipboard |
| `crunch_text` | Compress text with token stats |
| `crunch_file` / `crunch_directory` | Compress file or entire directory |
| `crunch_code_skeleton` / `crunch_file_skeleton` | Skeleton of code or data file |
| `count_text_tokens` | Token count + per-model cost estimates |
| `get_brevity_prompt` | Output-brevity system prompt |
| `search_stack` | Search clipboard history |
| `ocr_get_current` / `ocr_push_text` / `ocr_clear_stack` | Stack management |

### AI Context Manager

| Tool | Description |
|---|---|
| `smart_crunch` | Content-type-aware intelligent compression |
| `explain_compression` | Preview compression strategies (read-only) |
| `budget_loader` | Load file into exactly N tokens |
| `diff_crunch` | Delta-only updates since last load |
| `context_pack` | Pack multiple files into one budget-constrained block |

### AI Prompt Optimizer

| Tool | Description |
|---|---|
| `optimize_prompt` | Rewrite text into structured LLM prompt |
| `ai_compress` | LLM-based semantic compression (opt-in) |
| `list_optimizer_profiles` | List available profiles |
| `manage_optimizer_profile` | Create/delete profiles, configure API keys |

---

## 🔒 Security & Privacy

- ❌ No network access by default — all OCR and compression is local
- ❌ No file I/O for scanned data — everything in RAM only
- ❌ No admin privileges required
- ✅ Automatic secret redaction (API keys, JWTs, webhooks, entropy catch-all)
- ✅ Context-sensitive IP and UUID redaction (won't damage version strings or URLs)
- ✅ Crash log (`%APPDATA%\contextcruncher\app.log`, max 2 MB) — never contains clipboard content
- ✅ Open source — [MIT License](LICENSE)

---

## 🛠️ Development

**Requirements:** Python 3.11+ · Windows 10 (1903+) or 11 · OCR language pack installed

```bash
pip install -r requirements.txt          # Install dependencies
python src/contextcruncher/main.py       # Run
python -m pytest tests/ -v              # Run tests (504 passed)
python evals/run_eval.py                # Compression benchmarks
pyinstaller build.spec                  # Build .exe → dist/ContextCruncher.exe
```

---

## ⚠️ Known Limitations

- **Windows only** — requires native Windows OCR engine (10 v1903+ / 11)
- **Language packs required** — OCR quality depends on installed Windows language packs
- **No persistent history** — stack clears on exit (by design); only 10 pinned entries are saved

---

## 📋 Changelog

See **[CHANGELOG.md](CHANGELOG.md)** for the full release history.

## 📄 License

[MIT](LICENSE) — free for personal and commercial use.
