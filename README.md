# 🦖 ContextCruncher

<div align="center">
  <img src="assets/CC.png" alt="ContextCruncher Logo" width="75%" />
</div>

**AI-optimized clipboard manager with screen OCR, token compression, and MCP server — no cloud, no admin, everything stays in RAM.**

> 🚀 **v0.1.0-alpha** — First alpha release. Core features are complete and crash-prone threading issues have been resolved. See the [Changelog](#-changelog) for details.

---

## ✨ Features

- **Instant OCR** — Select any area on screen; text is recognized in under 1 second using the native Windows OCR engine (no internet required)
- **AI Token Compression** — 4-level text compression system that saves up to 53% tokens for LLMs (GPT, Claude, Gemini) — verified with tiktoken benchmarks
- **Multi-Variant System** — Every entry stores multiple compression variants. Cycle through them with a single hotkey or use the Win+V-style popup picker
- **Clipboard Stack** — Every scan is pushed onto a history stack (up to 50 entries). Navigate freely and paste any entry with a single keystroke
- **Auto-Crunch Monitor** — Always runs in the background to capture all clipboard copies to your local stack for instant crunching. Turn on Auto-Crunch to actively compress and overwrite the live OS clipboard.
- **Zero-Trust Security Scanner** — Built-in redactor automatically wipes out common secrets (API keys, JWTs, Webhooks) before processing any text.
- **JSON/XML Skeletonizer** — Intelligently shrinks large datasets by keeping structure but cropping massive repetitive string values (great for API logs).
- **MCP Server** — 14 MCP tools let AI agents read your screen, search clipboard history, compress text/files/directories, skeletonize payloads, and count tokens.
- **Token Counter** — Real LLM token counts via tiktoken (cl100k_base) for accurate cost estimation
- **Multi-Monitor** — Full DPI-aware support for multi-monitor setups
- **Multi-Language** — Automatically detects installed Windows language packs and prioritizes EU languages (DE, EN, FR, ES, IT, PL, NL, PT). Preferred language can be set in Settings.
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
| `Ctrl+Alt+C` | Compress clipboard content with AI token optimizer |
| `Ctrl+Shift+↑` | Navigate to a newer stack entry |
| `Ctrl+Shift+↓` | Navigate to an older stack entry |
| `Alt+C` | Toggle Popup Variant Picker to instantly select any compression variant |
| `Ctrl+Shift+→` | Cycle through text variants (legacy inline cycling) |

All hotkeys are fully customizable in Settings. Individual hotkeys can be cleared with the `×` button next to each binding.

---

## 🤖 AI Token Compression

ContextCruncher uses a 4-level compression system optimized for LLM token efficiency:

| Level | Name | Description | Token Savings* |
|---|---|---|---|
| 1 | 🪶 Light | Whitespace normalization only — safe for code | ~2% |
| 2 | 🦖 Token-Cruncher | URLs, markdown, filler phrases. Great for prose. | ~23% |
| 3 | 💀 Annihilator | Strips comments, timestamps, paths, dedup. Logs/data. | ~30% |
| 4 | ☢️ Experimental | Maximum density. Bullets→CSV, punct removal, Bag-Of-Words. | ~55% |

*\* Measured with tiktoken cl100k\_base across 5 sample categories. Run `python evals/run_eval.py` to reproduce.*

### Multi-Variant Selection

Every text entry automatically pre-computes all meaningful compression levels. Switch between them instantly using the **Popup Variant Picker** (default hotkey: `Alt+C`).

The Popup Picker instantly appears (bypassing Windows focus locks), grabs keyboard input, and lets you `↑`/`↓` and `Enter` your desired variant natively, just like the `Win+V` menu.

---

## 🔌 MCP Server (Model Context Protocol)

ContextCruncher exposes a powerful MCP server with 14 tools that AI agents can use directly.

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

### Available Tools (14)

| Tool | Description |
|---|---|
| `ocr_scan_region` | Interactive screen region OCR |
| `screenshot_full` | Full-screen OCR (no user interaction) |
| `read_clipboard` | Read current clipboard content |
| `crunch_text` | Compress text with token stats |
| `crunch_file` | Read & compress any file |
| `crunch_directory` | Recursively compress entire directory |
| `skeletonize_json` | Compress large JSON/XML data by truncating long string values |
| `count_text_tokens` | Count exact LLM tokens (tiktoken) |
| `get_brevity_prompt` | Output-brevity system prompt (~70% shorter AI responses) |
| `search_stack` | Search clipboard/OCR history |
| `ocr_get_stack` | Return entire history |
| `ocr_get_current` | Return current entry |
| `ocr_push_text` | Push text to clipboard |
| `ocr_clear_stack` | Clear history |

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

### v0.2.0-beta — The Zero-Friction Update

**New Features:**
- **Zero-Trust Security Scanner** — A powerful regex-driven secret redactor that proactively suppresses sensitive API keys (OpenAI, AWS, GitHub) before they ever get near LLM outputs.
- **JSON/XML Skeletonizer** — Radically trims monstrous payloads by preserving the schema but clamping massive string values down to minimal bytes.
- **Aggressive Popup Variant Picker** — Completely rewrote the UI variant cycling into a professional `Win+V` style modal overlay using `ctypes` focus-stealing to immediately accept keyboard input from any application window.
- **UI Localization** — Rebuilt the UI components from German back to fully professional English.

**Critical fixes:**
- **Clipboard Monitor Logic Overhaul** — The monitor now correctly monitors ALL sequential clipboard events and pushes all copies into your history RAM stack regardless of whether Auto-Crunch is turned on/off. Removed the flawed double-increment `_ignore_next_changes` logic that caused genuine `Ctrl+C` inputs to be randomly discarded.
- **Automated Process Killing** — Resolved `Access is denied` (WinError 5) failures in Pyinstaller builds by safely terminating active ContextCruncher instances within the `build.spec`/compilation pipeline.
- **Tkinter threading crash (was #1 cause of silent crashes)** — All UI windows (toast, flash, overlay, settings) now run as `Toplevel` children of a single persistent `tk.Tk()` root on a dedicated `TkUIThread`. Creating multiple `tk.Tk()` instances across threads was the primary source of `RuntimeError: main thread is not in main loop` crashes.
- **Hotkey recorder listener leak** — The pynput `kb.Listener` used for recording hotkeys in Settings now correctly stops when only modifier keys are released (previously it ran forever, intercepting all keyboard input and breaking global hotkeys until restart).
- **Double-scan crash** — Rapid double-pressing the scan hotkey no longer opens two overlays simultaneously. A lock prevents concurrent scans.

---

## 🗺️ Roadmap

### 🖼️ Image Cruncher (Planned)

Vision models like GPT-4o and Claude charge per **image tile** (typically 512×512 px). A 520×520 image costs 4 tiles; a smart resize to 512×512 drops it to 1 tile — same quality, fraction of the cost.

**Planned features:**

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
- **No persistent history** — The stack is cleared when the application exits (by design)
- **Level 4 compression** — Experimental vowel-removal mode produces output most AIs cannot interpret correctly

---

## 📄 License

[MIT](LICENSE) — free for personal and commercial use.
