# REX-ContextCruncher

<div align="center">
  <img src="assets/CC.png" alt="ContextCruncher Logo" width="75%" />
</div>

**AI-optimized clipboard manager with screen OCR, token compression, and MCP server — no cloud, no admin, everything stays in RAM.**

> 🚀 **v0.2.0-beta** — The Zero-Friction Update. All critical bugs resolved, four new features shipped. See the [Changelog](#-changelog) for details.

---

## ✨ Features

- **Instant OCR** — Select any area on screen; text is recognized in under 1 second using the native Windows OCR engine (no internet required)
- **Full-Screen OCR** — Capture the entire primary monitor in one keystroke (`Ctrl+Alt+F`) — no selection needed
- **AI Token Compression** — 4-level compression system that saves up to 60% tokens for LLMs (GPT, Claude, Gemini) — verified with tiktoken benchmarks
- **Multi-Variant System** — Every entry stores multiple compression variants. Cycle through them with a single hotkey or use the Win+V-style popup picker
- **Clipboard Stack** — Every scan is pushed onto a history stack (up to 50 entries). Navigate freely and paste any entry with a single keystroke. **New:** Pin up to 10 entries to make them survive application restarts!
- **Search Overlay** — Press `Ctrl+Shift+F` to search through your stack history and pinned elements interactively.
- **Auto-Crunch Monitor** — Always runs in the background to capture all clipboard copies to your local stack for instant crunching. Turn on Auto-Crunch to actively compress and overwrite the live OS clipboard.
- **Zero-Trust Security Scanner** — Built-in redactor automatically wipes out common secrets (API keys, JWTs, Webhooks, AWS/Stripe/OpenAI keys) before processing any text. Shannon-entropy catch-all for unknown secrets.
- **Code & Payload Skeletonizer** — Intelligently shrinks large datasets by keeping structure but cropping massive repetitive string values (JSON/XML/YAML) and uses `tree-sitter` for robust JavaScript/TypeScript function blanking.
- **Token Cost Estimator** — Real-time cost estimate in micro-cents per model (GPT-4o, Claude, o3 mini) displayed in the Token Heatmap window. Tracks precisely decoupled tokens for GPT (`o200k_base`) and Claude (`cl100k_base` estimation).
- **Context Window Warning** — Toast alert when compressed text exceeds the configurable threshold (default 75%) of any supported model's context window.
- **MCP Server** — 22 MCP tools let AI agents read your screen, search clipboard history, compress text/files/directories, skeletonize payloads, count tokens, get per-model cost estimates, manage context intelligently, and optimize prompts via LLM.
- **AI Context Manager** — Smart context tools for AI agents: `smart_crunch` routes content through optimal compression pipelines, `budget_loader` loads files to exact token counts, `diff_crunch` sends only what changed, and `context_pack` bundles multiple files into a single budget-constrained context block with keyword relevance ranking.
- **AI Prompt Optimizer** — Rewrites raw text into structured, role-optimized prompts using configurable LLM backends (OpenAI, Anthropic, Ollama). 5 built-in profiles + custom profile support.
- **Mouse Hotkeys** — Side mouse buttons (X1 / X2) can be assigned to any action via the Settings UI.
- **Multi-Monitor** — Full DPI-aware support for multi-monitor setups
- **Multi-Language OCR** — Automatically detects installed Windows language packs and prioritizes EU languages (DE, EN, FR, ES, IT, PL, NL, PT). Preferred language can be set in Settings.
- **Visual & Audio Feedback** — Green flash overlay + system beep on successful scan; distinct tone when no text is found
- **System Tray** — Runs quietly in the taskbar with a status menu showing the current entry and stack size
- **Zero Footprint** — No files written, no network access, no admin privileges, no telemetry
- **Singleton Guard** — Only one instance can run at a time; a second launch shows a friendly message instead of conflicting

---

## 📥 Installation

1. Go to the [Releases](../../releases) page
2. Download `ContextCruncher.exe`
3. Run it — the icon appears in your system tray
4. Done. No Python installation needed.

📖 **New to ContextCruncher?** Read the **[GUI User Guide](docs/user-guide.md)** for a full walkthrough of all features.

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
| `Ctrl+Alt+S` | Open selection overlay → OCR scan → push to stack |
| `Ctrl+Alt+F` | Full-screen OCR — captures entire primary monitor |
| `Ctrl+Alt+C` | Compress clipboard content with AI token optimizer |
| `Ctrl+Shift+↑` | Navigate to a newer stack entry |
| `Ctrl+Shift+↓` | Navigate to an older stack entry |
| `Ctrl+Shift+→` | Cycle through text variants |
| `Ctrl+Shift+F` | Open Search Overlay to find stack history/pins |
| `Alt+H` | Open Token Heatmap window |

All hotkeys are fully customizable in Settings. Individual hotkeys can be cleared with the `×` button next to each binding. **Mouse side buttons (X1 / X2) can also be assigned to any action.**

---

## 🤖 AI Token Compression

ContextCruncher uses a 3-level compression system optimized for LLM token efficiency:

| Level | Name | Description | Token Savings* |
|---|---|---|---|
| 1 | 🪶 Light | Whitespace normalization only — safe for code | ~2% |
| 2 | 🦖 Token-Cruncher | URLs, markdown, filler phrases. Great for prose. | ~23% |
| 3 | 💀 Annihilator | Strips comments, timestamps, paths, dedup. Logs/data. | ~30% |

*\* Measured with tiktoken cl100k\_base across 5 sample categories. Run `python evals/run_eval.py` to reproduce.*

### Multi-Variant Selection

Every text entry automatically pre-computes all meaningful compression levels. Switch between them instantly using the **Popup Variant Picker** (default hotkey: `Alt+C`).

The Popup Picker instantly appears (bypassing Windows focus locks), grabs keyboard input, and lets you `↑`/`↓` and `Enter` your desired variant natively, just like the `Win+V` menu.

---

## 🔌 MCP Server (Model Context Protocol)

ContextCruncher exposes a powerful MCP server with **22 tools** that AI agents can use directly.

### Quick Setup

```bash
# Auto-register in all detected AI tools
python setup_mcp.py --all

# Or pick specific tools
python setup_mcp.py --claude
python setup_mcp.py --cursor
```

Or register manually in your AI client config:

```json
{
  "mcpServers": {
    "contextcruncher": {
      "command": ["python", "-m", "contextcruncher.mcp_server"]
    }
  }
}
```

📖 **Full setup guide including Ollama:** [`docs/mcp-setup.md`](docs/mcp-setup.md)  
📖 **All tools with examples:** [`docs/tools-reference.md`](docs/tools-reference.md)  
📖 **GUI user guide (tray, OCR, hotkeys, compression):** [`docs/user-guide.md`](docs/user-guide.md)

### Available Tools (22)

#### Core Tools

| Tool | Description |
|---|---|
| `ocr_scan_region` | Interactive screen region OCR |
| `screenshot_full` | Full-screen OCR (no user interaction) |
| `read_clipboard` | Read current clipboard content |
| `crunch_text` | Compress text with token stats |
| `crunch_file` | Read & compress any file |
| `crunch_directory` | Recursively compress entire directory |
| `crunch_code_skeleton` | Skeleton of code (signatures only) |
| `crunch_file_skeleton` | Skeleton of JSON/XML/YAML file from disk |
| `count_text_tokens` | Count exact LLM tokens + per-model cost estimates |
| `get_brevity_prompt` | Output-brevity system prompt (~70% shorter AI responses) |
| `search_stack` | Search clipboard/OCR history |
| `ocr_get_current` | Return current entry |
| `ocr_push_text` | Push text to clipboard |
| `ocr_clear_stack` | Clear history |

#### 🧠 AI Context Manager Tools

| Tool | Description |
|---|---|
| `smart_crunch` | Intelligently compress text based on content type + agent intent |
| `explain_compression` | Preview what each compression strategy would do (no mutation) |
| `budget_loader` | Load a file into exactly N tokens with auto-detected priority |
| `diff_crunch` | Only return what changed since the last load (delta caching) |
| `context_pack` | Pack multiple files into one context block within a token budget |

`count_text_tokens` returns `cost_estimates_usc` — per-model cost in micro-dollar cents (µ¢) for GPT-4o, GPT-4o mini, o3 mini, Claude 3.5 Sonnet, Claude 3.5 Haiku, and Claude 3 Opus.

`context_pack` accepts a `question` parameter for keyword-based relevance ranking — files matching more keywords from the question get a larger share of the token budget.

#### 🎯 AI Prompt Optimizer Tools

| Tool | Description |
|---|---|
| `optimize_prompt` | Rewrite text into a structured, role-optimized LLM prompt |
| `list_optimizer_profiles` | List all available optimizer profiles (built-in + custom) |
| `manage_optimizer_profile` | Create/delete profiles or configure API keys |

`optimize_prompt` supports 3 providers: **OpenAI**, **Anthropic**, and **Ollama** (local). Configure API keys via `manage_optimizer_profile` with `action="set_keys"`.

### MCP Resources

| Resource URI | Description |
|---|---|
| `clipboard://current` | The user's current clipboard content |
| `clipboard://history` | Recent clipboard/OCR history entries |

---

## 🌍 Language Support

ContextCruncher uses the **native Windows OCR engine** (`Windows.Media.Ocr`). It automatically detects all language packs installed on your system and prioritizes European languages. A preferred language can be pinned in Settings.

| Language | Tag |
|---|---|
| Deutsch | `de` |
| English | `en` |
| Français | `fr` |
| Español | `es` |
| Italiano | `it` |
| Polski | `pl` |
| Nederlands | `nl` |
| Português | `pt` |

**To add more languages:** Go to *Settings → Time & Language → Language & Region → Add a language* and enable the OCR / handwriting features for the desired language pack.

---

## 🔒 Security & Privacy

ContextCruncher is designed with a **zero-trust, zero-footprint** philosophy:

- ❌ **No network access** — All OCR processing is local. No networking libraries imported.
- ❌ **No file I/O for scanned data** — All recognized text is stored exclusively in RAM.
- ❌ **No admin privileges** — Runs entirely in user-space.
- ✅ **Secret Redaction** — Automatically scrubs API Keys, JWTs, Webhooks, and internal tokens during AI crunching.
- ✅ **Crash log** — A rotating `app.log` (max 2 MB) is written to `%APPDATA%\contextcruncher\` to help diagnose issues. It never contains clipboard content — only event names and error traces.
- ✅ **Open source** — MIT licensed. Audit the code yourself.

---

## 📋 Changelog

> Full changelog with audit fixes: [`CHANGELOG.md`](CHANGELOG.md)

### v0.2.0-beta — The Zero-Friction Update

**New Features:**
- **Full-Screen OCR** (`Ctrl+Alt+F`) — Captures the entire primary monitor without any selection overlay. Wired into the same `_scan_active` lock as region OCR — no concurrent scans possible.
- **Token Cost Estimator** — The Token Heatmap window now shows per-model cost estimates in micro-cents (µ¢) for GPT-4o, GPT-4o mini, o3 mini, Claude 3.5 Sonnet, Claude 3.5 Haiku, and Claude 3 Opus. The `count_text_tokens` MCP tool also returns `cost_estimates_usc`.
- **Context Window Warning** — After every AI Compact operation a toast is shown if the result exceeds a configurable threshold (default 75%) of any supported model's context window. The Token Heatmap shows color-coded progress bars per model (green < 50%, yellow < 75%, red ≥ 75%).
- **Exact Multi-Tokenizer Tracking** — Support for exact multi-tokenizer computation (`o200k_base` for OpenAI models, separated estimations for Claude).
- **Mouse Side-Button Hotkeys** — X1 (Browser Back) and X2 (Browser Forward) buttons can now be bound to any action in Settings. A dedicated `_MouseHotkeyListener` runs only when at least one mouse binding is active.
- **Zero-Trust Security Scanner** — A powerful two-pass secret redactor: named patterns for AWS, Stripe, OpenAI/Anthropic keys, JWTs, Bearer tokens; plus Shannon-entropy (≥ 4.5) catch-all for unknown secrets. Pure lowercase strings are never flagged as false positives.
- **Code/Data Skeletonizer** — Radically trims monstrous payloads by preserving structure but clamping long string values (JSON/XML/YAML) and uses a Depth-First Search `tree-sitter` integration to safely clear up JS/TS function bodies without corrupting arrow functions or generic syntax.
- **Aggressive Popup Variant Picker** — Professional `Win+V` style modal overlay using `ctypes` focus-stealing to immediately accept keyboard input from any application window.
- **Search Overlay & Pinned Stack** — Visually search (`Ctrl+Shift+F`) older history entries or pin up to 10 entries via the system tray so they survive application restarts. Pinned items rank as top favorites in the search overlay.

**Bug Fixes (v0.2.0):**
- **Security Scanner** — Added Shannon-entropy fallback and 15+ named patterns (AWS, Stripe, OpenAI, Anthropic, Bearer tokens). Pangram false-positive guard for pure-lowercase strings.
- **Stack Counter** — Clipboard events shorter than 5 characters (e.g. IDE background writes) are now ignored via `min_text_length` guard.
- **Clipboard Debounce** — Rapid `Ctrl+C` bursts no longer trigger multiple compressions. `debounce_delay=0.3s` collapses bursts into a single callback.
- **OCR Small Selections** — Minimum height raised to 96 px, padding increased to 24 px, background color derived from image corner pixel instead of hard-coded white.
- **OCR Language Setting** — Language selector added to Settings UI; `get_available_languages()` queries the Windows OCR engine and maps BCP-47 tags to display names.
- **Hotkey Collision Check** — `find_hotkey_collision()` in `config.py` prevents duplicate bindings from being saved. The Settings UI shows a red error and aborts save on conflict.
- **Autostart (Dev Mode)** — Registry Run key now stores `"python.exe" "main.py"` instead of a bare `.py` path, allowing Windows to start the app regardless of PATH configuration.

**Critical fixes (v0.1.x):**
- **Tokenizer mismatch** — Heatmap now calculates metrics per individual model logic instead of applying universal tokens.
- **Tkinter threading crash** — All UI windows run as `Toplevel` children of a single persistent `tk.Tk()` root on a dedicated `TkUIThread`.
- **Hotkey recorder listener leak** — pynput listener now correctly stops on modifier-only release.
- **Double-scan crash** — `_scan_active` threading.Event prevents concurrent region + full-screen scans.
- **Auto-Crunch ping-pong loop** — `_ignore_next_changes += 2` before clipboard write prevents feedback loops.
- **Singleton guard** — Windows Named Mutex prevents multiple instances.

---

## 🗺️ Roadmap

> Full roadmap: [`docs/roadmap.md`](docs/roadmap.md)

### ✅ Recently Shipped

| Feature | Status | Details |
|---|---|---|
| **AI Context Manager** | ✅ v0.2.0 | `smart_crunch`, `budget_loader`, `diff_crunch`, `context_pack`, `explain_compression` — 5 tools for intelligent context engineering |
| **AI Prompt Optimizer** | ✅ v0.2.0 | `optimize_prompt`, `list_optimizer_profiles`, `manage_optimizer_profile` — rewrite text into structured prompts via OpenAI, Anthropic, or Ollama |

### 🔜 Next Up

#### 🗺️ `repo_map` — Intelligent Codebase Map

A single tool call that gives the AI a **structural overview of an entire repository** within a token budget. Instead of blindly loading files, the AI gets a compressed map showing every file, its purpose, key signatures, and line count — all fitted into e.g. 2,000 tokens.

| Aspect | Details |
|---|---|
| **Input** | Directory path + token budget |
| **Output** | File tree with per-file summaries (purpose, LOC, key exports) |
| **Uses** | Existing skeletonizer + token counter — zero new dependencies |
| **Value** | AI understands a 50K-token repo in 500 tokens. Perfect entry point before `context_pack` or `budget_loader`. |

### 🖼️ Image Cruncher (Planned)

Vision models like GPT-4o and Claude charge per **image tile** (typically 512×512 px). A 520×520 image costs 4 tiles; a smart resize to 512×512 drops it to 1 tile — same quality, fraction of the cost.

| Feature | What it does | Benefit |
|---|---|---|
| **Smart Resize** | Scales to max 1024px or 1560px (AI sweet spot) | Saves massive vision tokens and money |
| **Grayscale Mode** | Converts to B&W (optional) | Smaller file, sufficient for code/text OCR |
| **Format Conversion** | PNG/TIFF → WebP or JPEG | Faster upload, less bandwidth |
| **Metadata Stripping** | Removes EXIF data (GPS, camera info) | Privacy + smaller file |

### 🖥️ Desktop Application (Planned)

- **Visual clipboard history** with thumbnails and text previews
- **Side-by-side variant comparison** — see Original vs. AI Lv.3 at a glance
- **Image cruncher controls** — resize sliders, format picker, quality preview
- **Drag & drop** — drop files or images directly into the window
- **Statistics dashboard** — track total tokens saved, compression ratios over time

---

## 🛠️ Development

### Prerequisites

- Python 3.11+
- Windows 10 (1903+) or Windows 11
- At least one OCR language pack installed

### Setup

```bash
pip install -r requirements.txt
python src/contextcruncher/main.py
```

### Run Tests

```bash
python -m pytest tests/ -v
```

### Run Benchmarks

```bash
python evals/run_eval.py                     # Built-in samples
python evals/run_eval.py --input myfile.txt  # Custom file
python evals/run_eval.py --dir ./docs        # Entire directory
python evals/run_eval.py --json results.json # Save JSON results
```

### Setup MCP in AI Tools

```bash
python setup_mcp.py --all      # Auto-register everywhere
python setup_mcp.py --claude   # Claude Desktop only
python setup_mcp.py --cursor   # Cursor only
```

### Build Executable

```bash
pip install pyinstaller
pyinstaller build.spec
# Output: dist/ContextCruncher.exe
```

---

## ⚠️ Known Limitations

- **Windows only** — Requires Windows 10 (version 1903+) or Windows 11 for the native OCR engine
- **Language packs required** — OCR quality depends on the Windows language packs installed
- **No persistent history for general entries** — The stack is cleared when the application exits (by design). Only your 10 explicitly pinned shortcuts are saved persistently via JSON.

---

## 📄 License

[MIT](LICENSE) — free for personal and commercial use.
