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
| **Capture screen regions** | Only when the user initiates an OCR scan or full-screen capture. No background screenshots. |
| **Run a local MCP server** | Stdio-based, no network listener. Only communicates with the parent AI process. |
| **Scan for secrets** | The built-in security scanner automatically redacts API keys, JWTs, and high-entropy tokens before any processing. Redaction is local and deterministic — nothing is logged or transmitted. |

## Built-in Secret Redaction

ContextCruncher includes a two-pass security scanner that runs automatically during AI compression:

- **Pass 1 — Named patterns:** AWS secret keys, Stripe keys, OpenAI/Anthropic API keys, GitHub tokens, Bearer tokens, JWTs, generic webhooks, and more.
- **Pass 2 — Entropy catch-all:** Any token with Shannon entropy ≥ 4.5 and sufficient character-type diversity (uppercase + digits or special characters) is redacted as an unknown secret.
- **False-positive guard:** Pure lowercase strings (e.g. regular prose) are never flagged regardless of entropy.

Redacted values are replaced with labelled placeholders such as `[AWS_SECRET_REDACTED]` or `[HIGH_ENTROPY_SECRET_REDACTED]`.

## Comparison: ContextCruncher vs Cloud-Based Compression

| Feature | ContextCruncher | Cloud-based tools |
|---|---|---|
| Data leaves machine? | **Never** | Yes (API calls) |
| Requires API key? | **No** | Yes |
| Works offline? | **Yes** | No |
| Deterministic output? | **Yes** (same input → same output) | No (LLM-dependent) |
| Costs per compression? | **$0** | Token fees apply |
| Secret redaction? | **Yes** (local, automatic) | Varies |
| Auditable? | **Yes** (open source, local) | Partial (closed API) |

## Mouse Hotkeys & Input Capture

When mouse side-button hotkeys (X1 / X2) are configured, a `pynput.mouse.Listener` runs in a background daemon thread. It only fires callbacks on the specific configured buttons — all other mouse input is ignored and never recorded or stored. The listener is stopped immediately when the app exits or when mouse bindings are removed in Settings.

## Vulnerability Reporting

If you discover a security vulnerability, please report it responsibly:
- Open a **GitHub Security Advisory** in the repository (private disclosure)
- **Do NOT** open a public issue for security vulnerabilities

## Dependency Trust

| Dependency | Purpose | Trust Level |
|---|---|---|
| `pynput` | Keyboard + optional mouse side-button hotkeys | ⚠️ Input access (required for hotkeys only) |
| `Pillow` | Image processing for OCR + full-screen capture | ✅ Well-audited, no network |
| `pyperclip` | Cross-platform clipboard read/write | ✅ No network |
| `pystray` | System tray icon | ✅ No network |
| `winrt-*` | Windows OCR engine binding | ✅ Microsoft first-party |
| `mcp` | MCP protocol server | ✅ Stdio only, no network listener |
| `tiktoken` | Token counting + cost estimation (optional) | ✅ OpenAI tokenizer, fully offline after first download |
