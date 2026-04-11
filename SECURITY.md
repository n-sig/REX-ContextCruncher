# ContextCruncher Security & Privacy Model

## Philosophy: Zero-Trust, Zero-Footprint

ContextCruncher is designed for people who handle sensitive data — code under NDA, proprietary algorithms, financial data, personal information. Every architectural decision prioritizes data sovereignty.

## What ContextCruncher Does NOT Do

| ❌ We Never | Explanation |
|---|---|
| **Send data over the network** | No HTTP client, no websocket, no DNS lookup. Zero networking libraries imported. |
| **Write clipboard data to disk** | All clipboard/OCR text lives exclusively in RAM. Process exit = data gone. |
| **Require admin privileges** | Runs entirely in user-space. No system-wide hooks, no driver installation. |
| **Collect telemetry** | No analytics, no crash reporting to external services, no usage tracking. |
| **Phone home** | No update checks, no license validation, no cloud dependencies. |
| **Use cloud-based compression** | Unlike tools that send your text to an LLM API for compression, ContextCruncher compresses **locally with deterministic algorithms**. Your code never leaves your machine. |

## What ContextCruncher DOES Do

| ✅ We Do | Details |
|---|---|
| **Write a crash log** | A rotating `app.log` (max 2 MB) at `%APPDATA%\contextcruncher\`. Contains only event names and error stack traces — **never** clipboard content. |
| **Read the clipboard** | Required for compression and monitoring features. Only when explicitly triggered by the user (hotkey or Auto-Crunch toggle). |
| **Capture screen regions** | Only when the user initiates an OCR scan. No background screenshots. |
| **Run a local MCP server** | Stdio-based, no network listener. Only communicates with the parent AI process. |

## Comparison: ContextCruncher vs Cloud-Based Compression

| Feature | ContextCruncher | Cloud-based tools |
|---|---|---|
| Data leaves machine? | **Never** | Yes (API calls) |
| Requires API key? | **No** | Yes |
| Works offline? | **Yes** | No |
| Deterministic output? | **Yes** (same input → same output) | No (LLM-dependent) |
| Costs per compression? | **$0** | Token fees apply |
| Auditable? | **Yes** (open source, local) | Partial (closed API) |

## Vulnerability Reporting

If you discover a security vulnerability, please report it responsibly:
- **Email:** Create a GitHub Security Advisory in the repository
- **Do NOT** open a public issue for security vulnerabilities

## Dependency Trust

| Dependency | Purpose | Trust Level |
|---|---|---|
| `pynput` | Hotkey registration | ⚠️ Keyboard access (required for hotkeys) |
| `Pillow` | Image processing for OCR | ✅ Well-audited, no network |
| `pyperclip` | Cross-platform clipboard | ✅ No network |
| `pystray` | System tray icon | ✅ No network |
| `winrt-*` | Windows OCR engine binding | ✅ Microsoft first-party |
| `mcp` | MCP protocol server | ✅ Stdio only, no network listener |
| `tiktoken` | Token counting (optional) | ✅ OpenAI tokenizer, offline after first download |
