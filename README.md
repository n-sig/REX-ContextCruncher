# 🦖 ContextCruncher

<div align="center">
  <img src="assets/CC.png" alt="ContextCruncher Logo" width="75%" />
</div>

**AI-optimized clipboard manager with screen OCR, token compression, and MCP server — no cloud, no admin, everything stays in RAM.**

> 🚀 **v0.1.0-alpha** — First alpha release. Core features are complete and crash-prone threading issues have been resolved. See the [Changelog](#-changelog) for details.

---

## ✨ Features

- **Instant OCR** — Select any area on screen; text is recognized in under 1 second using the native Windows OCR engine (no internet required)
- **AI Token Compression** — 4-level text compression system that saves up to 45% tokens for LLMs (GPT, Claude, Gemini)
- **Multi-Variant System** — Every entry stores multiple compression variants. Cycle through them with a single hotkey or use the Win+V-style popup picker
- **Clipboard Stack** — Every scan is pushed onto a history stack (up to 50 entries). Navigate freely and paste any entry with a single keystroke
- **Auto-Crunch Monitor** — Automatically compresses every clipboard copy in real-time with full variant support and visual feedback
- **MCP Server** — Model Context Protocol integration lets AI agents read your screen, search clipboard history, and compress text directly
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
python src/ocrclipstack/main.py
```

---

## ⌨️ Hotkeys

| Hotkey | Action |
|---|---|
| `Ctrl+Alt+S` | Open selection overlay → OCR scan → push to stack |
| `Ctrl+Alt+C` | Compress clipboard content with AI token optimizer |
| `Ctrl+Shift+↑` | Navigate to a newer stack entry |
| `Ctrl+Shift+↓` | Navigate to an older stack entry |
| `Ctrl+Shift+→` | Cycle through text variants (or open popup picker) |

All hotkeys are fully customizable in Settings. Individual hotkeys can be cleared with the `×` button next to each binding.

---

## 🤖 AI Token Compression

ContextCruncher uses a 4-level compression system optimized for LLM token efficiency:

| Level | Name | Description | Token Savings |
|---|---|---|---|
| 1 | Light | Whitespace normalization only — safe for code | ~10% |
| 2 | Token-Cruncher | Removes stop words (DE + EN) | ~25% |
| 3 | Annihilator | Boilerplate removal + Bag-of-Words deduplication | ~45% |
| 4 | Experimental | Vowel removal — **NOT AI-compatible!** Use at own risk. | ~60% |

### Multi-Variant Cycling

Every text entry automatically pre-computes all meaningful compression levels. Switch between them instantly:

- **Cycle Key (default):** `Ctrl+Shift+→` steps through: `Original → Compact → AI Lv.1 → Lv.2 → Lv.3 → ⚠ Lv.4`
- **Popup Picker (optional):** Enable in Settings → shows a Win+V-style dark popup with all variants, savings percentages, and text previews

---

## 🔌 MCP Server (Model Context Protocol)

ContextCruncher exposes an MCP server that AI agents can use directly. Register it in your AI client config:

```json
{
  "mcpServers": {
    "contextcruncher": {
      "command": ["python", "-m", "ocrclipstack.mcp_server"]
    }
  }
}
```

### Available Tools

| Tool | Description |
|---|---|
| `ocr_scan_region` | Prompt user to select a screen region for OCR |
| `screenshot_full` | OCR the entire visible screen without user interaction |
| `read_clipboard` | Read the current system clipboard content |
| `crunch_text` | Compress text for token-efficient AI consumption |
| `search_stack` | Search through clipboard/OCR history |
| `ocr_get_stack` | Return the entire history stack |
| `ocr_get_current` | Return the currently selected stack entry |
| `ocr_push_text` | Push text to clipboard and stack |
| `ocr_clear_stack` | Clear the history stack |

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
- ✅ **Crash log** — A rotating `app.log` (max 2 MB) is written to `%APPDATA%\OCRClipStack\` to help diagnose issues. It never contains clipboard content — only event names and error traces.
- ✅ **Open source** — MIT licensed. Audit the code yourself.

---

## 📋 Changelog

### v0.1.0-alpha — First Alpha Release

**Critical fixes:**
- **Tkinter threading crash (was #1 cause of silent crashes)** — All UI windows (toast, flash, overlay, settings) now run as `Toplevel` children of a single persistent `tk.Tk()` root on a dedicated `TkUIThread`. Creating multiple `tk.Tk()` instances across threads was the primary source of `RuntimeError: main thread is not in main loop` crashes.
- **Hotkey recorder listener leak** — The pynput `kb.Listener` used for recording hotkeys in Settings now correctly stops when only modifier keys are released (previously it ran forever, intercepting all keyboard input and breaking global hotkeys until restart).
- **Double-scan crash** — Rapid double-pressing the scan hotkey no longer opens two overlays simultaneously. A lock prevents concurrent scans.

**Other fixes:**
- **Auto-Crunch ping-pong loop** — `_ignore_next_changes` is now incremented before writing back to the clipboard, preventing the monitor from re-processing its own writes.
- **Stack navigation feedback** — Navigating at the boundary of the stack no longer triggers a success beep and toast when nothing changed.
- **`saved_percent` accuracy** — Token savings percentage is now calculated after XML wrapping, not before.
- **OCR language setting** — The language preference in Settings is now actually passed to the OCR engine (it was previously ignored).
- **DPI awareness** — Set once at application startup instead of on every scan call.
- **Singleton guard** — A Windows named mutex prevents two instances from running simultaneously and conflicting on hotkeys.
- **Logging** — Structured rotating log written to `%APPDATA%\OCRClipStack\app.log` for crash diagnosis.
- **Public API** — Internal `stack._items` / `stack._cursor` access replaced with `get_entry()` / `set_cursor()`.
- **Settings UX** — Added `×` clear button for each hotkey binding.

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
python src/ocrclipstack/main.py
```

### Run Tests

```bash
python -m pytest tests/ -v
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
