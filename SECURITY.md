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
| **Use cloud-based compression by default** | ContextCruncher compresses **locally with deterministic algorithms** by default. The v2.0 `ai_compress` MCP tool is the single exception: an **opt-in** LLM call (OpenAI / Anthropic / Ollama) that is off by default and never invoked unless an agent explicitly calls it. See [Opt-In LLM Compression](#opt-in-llm-compression-v20) below. |

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

## Hybrid Neuro-Symbolic Compression (v2.0)

The `ai_compress` MCP tool and the `prompt_optimizer` module share a **4-layer protective extraction** that runs *before* any text is sent to an LLM. This ensures high-signal elements survive the rewrite regardless of how aggressively the model compresses prose:

| Layer | What is extracted | Why it matters |
|---|---|---|
| **1. Code blocks** | Fenced (```` ``` ````) and inline (`` ` ``) code regions | LLMs routinely break indentation, drop single-letter parameters, or "helpfully" reformat code. Extraction swaps them out to placeholders, so the original bytes are re-inserted verbatim after the LLM returns. |
| **2. Tables** | Markdown tables (pipe-separated rows) | Tables carry structured data where column alignment and every cell matter. Row-order and content are preserved byte-for-byte. |
| **3. File / URL references** | Paths (`src/foo.py`), URLs, CLI invocations | Breaks in paths or commands silently poison agent workflows. References are pinned and restored. |
| **4. Constraint keywords** | `NEVER` / `ALWAYS` / `MUST NOT` / `DO NOT` (EN + DE: `IMMER` / `NIEMALS` / `MUSS` / `DARF NICHT` / `KEIN*`) | A CLAUDE.md loses its meaning if `NEVER use localStorage` becomes `avoid localStorage`. Constraint keyword density is preserved. |

After extraction, only the remaining prose (typically 40–70% of the input) is sent to the configured LLM. The protected regions are stitched back in byte-exact. The `ai_compress` response includes a `warnings` field that flags any suspected round-trip loss (e.g. `Constraint 'NEVER' may be lost`, `Token count grew by 12%`).

## Opt-In LLM Compression (v2.0)

`ai_compress` is the **only** ContextCruncher feature that can make a network call, and it is strictly opt-in:

- **Off by default** — no provider SDKs are imported at startup; `httpx` is lazy-loaded only when the tool is invoked.
- **Explicit invocation** — only runs when an AI agent calls the `ai_compress` MCP tool. No automatic background use.
- **Local-first provider** — Ollama (fully local) is supported; OpenAI / Anthropic require explicit API keys configured via `manage_optimizer_profile`.
- **Secret scanner runs first** — the same two-pass redactor described above runs *before* the text leaves your machine. API keys and high-entropy tokens are replaced with placeholders.
- **No persistent state** — the compressed text and provider response live in memory for the duration of the MCP call only. Nothing is written to disk.
- **Validation warnings** — `_validate_compression` flags round-trip anomalies (token inflation, lost constraints, dropped code fences) so the agent can decide to reject the output.

If you do not call `ai_compress`, ContextCruncher's network-free guarantees are unchanged. All other compression (`crunch_text`, `smart_crunch`, `budget_loader`, `context_pack`, etc.) remains 100% local and deterministic.

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
| `httpx` | **Opt-in** — only loaded when `ai_compress` / `optimize_prompt` is called | ⚠️ Network access when and only when user invokes LLM tools |
| `tree-sitter` / `tree-sitter-javascript` | JS/TS function-body blanking in the skeletonizer (optional) | ✅ No network |
