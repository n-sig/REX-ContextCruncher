# 🦖 ContextCruncher

<div align="center">
  <img src="assets/CC.png" alt="ContextCruncher Logo" width="75%" />
</div>

**AI-optimized clipboard manager with screen OCR, token compression, and MCP server — no cloud, no admin, everything stays in RAM.**

> ⚠️ **Early Alpha** — This project is under active development. Expect crashes, incomplete features, and breaking changes. Contributions and bug reports are welcome!

---

## ✨ Features

- **Instant OCR** — Select any area on screen; text is recognized in under 1 second using the native Windows OCR engine (no internet required)
- **AI Token Compression** — 4-level text compression system that saves up to 45% tokens for LLMs (GPT, Claude, Gemini)
- **Multi-Variant System** — Every entry stores multiple compression variants. Cycle through them with a single hotkey or use the Win+V-style popup picker
- **Clipboard Stack** — Every scan is pushed onto a history stack (up to 50 entries). Navigate freely and paste any entry with a single keystroke
- **Auto-Crunch Monitor** — Automatically compresses every clipboard copy in real-time with full variant support and visual feedback
- **MCP Server** — Model Context Protocol integration lets AI agents read your screen, search clipboard history, and compress text directly
- **Multi-Monitor** — Full DPI-aware support for multi-monitor setups
- **Multi-Language** — Automatically detects installed Windows language packs and prioritizes EU languages (DE, EN, FR, ES, IT, PL, NL, PT)
- **Visual & Audio Feedback** — Green flash overlay + system beep on successful scan; distinct tone when no text is found
- **System Tray** — Runs quietly in the taskbar with a status menu showing the current entry and stack size
- **Zero Footprint** — No files written, no network access, no admin privileges, no telemetry

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

ContextCruncher uses the **native Windows OCR engine** (`Windows.Media.Ocr`). It automatically detects all language packs installed on your system and prioritizes European languages:

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
- ❌ **No telemetry or logging** — Screen content is never logged, cached, or transmitted.
- ✅ **Open source** — MIT licensed. Audit the code yourself.

---

## 🗺️ Roadmap

### 🖼️ Image Cruncher (Planned)

Vision models like GPT-4o and Claude charge per **image tile** (typically 512×512 px). A 520×520 image costs 4 tiles; a smart resize to 512×512 drops it to 1 tile — same quality, fraction of the cost.

Most AIs also downsample internally (Claude caps at 1560px, GPT-4o at 2048px), so uploading raw 4000px smartphone photos wastes bandwidth and money.

**Planned features:**

| Feature | What it does | Benefit |
|---|---|---|
| **Smart Resize** | Scales to max 1024px or 1560px (AI sweet spot) | Saves massive vision tokens and money |
| **Grayscale Mode** | Converts to B&W (optional) | Smaller file, sufficient for code/text OCR |
| **Format Conversion** | PNG/TIFF → WebP or JPEG | Faster upload, less bandwidth |
| **Metadata Stripping** | Removes EXIF data (GPS, camera info) | Privacy + smaller file |

**Example flow:** User copies a screenshot → presses hotkey → ContextCruncher resizes to 1560px, compresses to 80% WebP, strips EXIF → `"✓ Image crunched (2.4MB → 180KB)"` → ready to paste into any AI chat.

> ⚠️ **Not recommended** for images with very fine text (e.g. large schematics, dense spreadsheets) — aggressive compression can hurt OCR quality.

### 🖥️ Desktop Application (Planned)

The current version is a tray-only tool. A full windowed application with a proper GUI is planned:

- **Visual clipboard history** with thumbnails and text previews
- **Side-by-side variant comparison** — see Original vs. AI Lv.3 at a glance
- **Image cruncher controls** — resize sliders, format picker, quality preview
- **Drag & drop** — drop files or images directly into the window
- **Statistics dashboard** — track total tokens saved, compression ratios over time

### 🐛 Known Issues (Alpha)

- Application may crash in certain edge cases — stability improvements are in progress
- Some hotkey combinations may not register reliably on all keyboard layouts
- Auto-Crunch monitor can interfere with clipboard operations in some applications
- Level 4 (Experimental) produces output that most AIs cannot interpret correctly
- UI threading model needs migration to a single-thread message queue for full stability

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

---

## 📄 License

[MIT](LICENSE) — free for personal and commercial use.
