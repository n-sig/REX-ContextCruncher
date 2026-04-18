"""
mcp_server.py — Model Context Protocol server for ContextCruncher.

Exposes ContextCruncher functionality to AI agents (Claude, Gemini, etc.)
via the MCP standard.  Run this as a standalone process:

    python -m contextcruncher.mcp_server

AI clients (e.g. Claude Desktop) can register it in their config:

    {
      "mcpServers": {
        "contextcruncher": {
          "command": ["python", "-m", "contextcruncher.mcp_server"]
        }
      }
    }

Exposed tools (23):
  • ocr_scan_region      — Prompt user to select a screen region, return OCR text.
  • screenshot_full      — OCR the entire visible screen without user interaction.
  • read_clipboard       — Read the current system clipboard content.
  • crunch_text          — Compress text for token-efficient AI consumption.
  • crunch_file          — Read a file from disk and compress it.
  • crunch_directory     — Recursively read and compress an entire directory.
  • crunch_code_skeleton — Strip code/JSON/XML bodies; keep signatures & schema.
  • crunch_file_skeleton — Read a local file and return its skeleton.
  • count_text_tokens    — Count exact LLM tokens (tiktoken cl100k_base).
  • get_brevity_prompt   — System prompt that reduces AI output tokens ~70%.
  • search_stack         — Search through clipboard history or return full stack.
  • ocr_get_current      — Return the currently selected stack entry.
  • ocr_push_text        — Push arbitrary text into the stack.
  • ocr_clear_stack      — Clear the history stack.
  • smart_crunch         — Intelligently compress text based on content type + intent.
  • explain_compression  — Preview what each compression strategy would do.
  • budget_loader        — Load a file into exactly N tokens.
  • diff_crunch          — Only return what changed since the last load.
  • context_pack         — Pack multiple files into one context block within a token budget.
  • optimize_prompt      — Rewrite text into a structured, role-optimized LLM prompt.
  • ai_compress          — LLM-based semantic compression with hybrid structure preservation.
  • list_optimizer_profiles — List all available prompt optimizer profiles.
  • manage_optimizer_profile — Create or delete custom prompt optimizer profiles.
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

# Ensure the package is importable.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print(
        "ERROR: The 'mcp' package is required for the MCP server.\n"
        "Install it with:  pip install mcp",
        file=sys.stderr,
    )
    sys.exit(1)

from contextcruncher.stack import TextStack
from contextcruncher.ocr import recognise, is_ocr_available
from contextcruncher.overlay import select_region
from contextcruncher.clipboard import set_clipboard
from contextcruncher.normalize import compact_variant
from contextcruncher.text_processor import minify_for_ai
from contextcruncher.token_counter import count_tokens, token_stats, cost_estimate, format_cost, truncate_to_budget
from contextcruncher.diff_cache import DiffCache
from contextcruncher.security_scanner import redact_secrets
from contextcruncher.skeletonizer import crunch_skeleton
from contextcruncher.content_router import smart_route, detect_content_type, CrunchResult
from contextcruncher.prompt_optimizer import (
    optimize as po_optimize,
    compress as po_compress,
    list_profiles as po_list_profiles,
    get_profile as po_get_profile,
    save_profile as po_save_profile,
    delete_profile as po_delete_profile,
    save_provider_config as po_save_provider_config,
    get_provider_config as po_get_provider_config,
    LLMProfile,
    OptimizeResult,
    CompressResult,
)
from dataclasses import asdict

import pyperclip

# -----------------------------------------------------------------------
# Shared state (independent of the GUI app — this is a standalone process)
# -----------------------------------------------------------------------
_stack = TextStack()

# Maximum file size for single-file crunch (10 MB)
_MAX_FILE_SIZE = 10 * 1024 * 1024
# Allowed text extensions for directory crunching
_TEXT_EXTENSIONS = {
    ".txt", ".md", ".py", ".js", ".ts", ".jsx", ".tsx", ".json",
    ".yaml", ".yml", ".toml", ".cfg", ".ini", ".log", ".csv",
    ".html", ".css", ".xml", ".sql", ".sh", ".bash", ".ps1",
    ".java", ".c", ".cpp", ".h", ".hpp", ".rs", ".go", ".rb",
    ".swift", ".kt", ".cs", ".r", ".m", ".php", ".lua",
}

mcp = FastMCP(
    "ContextCruncher",
    description=(
        "Your personal screen reading and clipboard intelligence assistant. "
        "Use this tool whenever the user mentions anything on their screen, "
        "asks about text they've copied, wants to read or OCR something visible, "
        "or needs clipboard history. This tool can: "
        "1) Screenshot and OCR any screen region on demand, "
        "2) OCR the entire visible screen without user interaction, "
        "3) Read and search clipboard history, "
        "4) Compress text for token-efficient AI consumption (saves up to 45% tokens), "
        "5) Push prepared text directly to the user's clipboard for pasting, "
        "6) Crunch files and directories for token-efficient context loading, "
        "7) Provide real token counts (tiktoken cl100k_base) for any text, "
        "8) Intelligently route text through optimal compression pipelines (smart_crunch), "
        "9) Preview compression strategies before applying them (explain_compression)."
    ),
)


# -----------------------------------------------------------------------
# Tools
# -----------------------------------------------------------------------

@mcp.tool()
def ocr_scan_region() -> str:
    """Prompt the user to select a screen region with a crosshair overlay.

    The selected area is scanned using the Windows OCR engine and the
    recognized text is returned.  The text is also pushed onto the
    internal history stack and copied to the clipboard.

    Use this when the user wants to OCR a *specific* part of their screen.

    Returns:
        The recognized text, or an error message if OCR is unavailable
        or the user cancelled the selection.
    """
    if not is_ocr_available():
        return "ERROR: Windows OCR engine is not available on this system."

    result: dict[str, str | None] = {"text": None}
    done = threading.Event()

    def _callback(image, bbox) -> None:
        if image is None:
            result["text"] = None
            done.set()
            return
        text = recognise(image)
        if text:
            compact = compact_variant(text)
            _stack.push(text, compact=compact)
            set_clipboard(text)
            result["text"] = text
        done.set()

    # The overlay runs in its own thread (requires tkinter mainloop).
    t = threading.Thread(target=select_region, args=(_callback,), daemon=True)
    t.start()
    done.wait(timeout=30)

    if result["text"]:
        return result["text"]
    return "No text recognized or selection cancelled."


@mcp.tool()
def screenshot_full() -> str:
    """Take a full screenshot and OCR the entire visible screen.

    Use this when the user asks "what's on my screen?",
    "read my screen", "what am I looking at?", or needs
    context about their current view without manual selection.

    Returns all recognized text from the full screen.
    """
    if not is_ocr_available():
        return "ERROR: Windows OCR engine is not available on this system."

    try:
        from PIL import ImageGrab
        img = ImageGrab.grab(all_screens=False)
        text = recognise(img)
        if text:
            _stack.push(text)
            return text
        return "No text could be recognized on screen."
    except Exception as e:
        return f"ERROR: Screenshot failed: {e}"


@mcp.tool()
def read_clipboard() -> str:
    """Read the current system clipboard content.

    Use this whenever the user says "I copied something",
    "check my clipboard", "what did I just copy",
    "process this" (implying clipboard content), or
    references text they have in their clipboard.

    Returns the current clipboard text.
    """
    try:
        text = pyperclip.paste()
        if not text or not text.strip():
            return "Clipboard is empty."
        return text
    except Exception as e:
        return f"ERROR: Could not read clipboard: {e}"


@mcp.tool()
def crunch_text(text: str, level: int = 2) -> dict:
    """Compress text for token-efficient AI consumption.

    Use this when you receive large blocks of text (web scrapes,
    documentation, logs, code) and want to reduce token usage before
    processing. Returns the compressed text and savings statistics.

    This is especially useful for web-scraped content that contains
    navigation elements, footers, and UI boilerplate.

    Args:
        text: The text to compress.
        level: Compression level (1-3):
            1: Light (whitespace only) — safe for code
            2: Token-Cruncher (removes stop words) — great for prose
            3: Annihilator (deduplication + boilerplate removal) — best for web scrapes

    Returns:
        A dict with compressed_text, original_chars, compressed_chars, saved_percent.
    """
    if not text:
        return {"error": "Cannot compress empty text."}

    level = max(1, min(3, level))
    compressed, stats = minify_for_ai(text, level=level)
    token_info = token_stats(text, compressed)
    return {
        "compressed_text": compressed,
        "original_chars": len(text),
        "compressed_chars": len(compressed),
        "token_saved_percent": stats["saved_percent"],
        "content_type": stats["content_type"],
        "techniques_applied": stats["techniques_applied"],
        "level_used": level,
        **token_info,
    }


@mcp.tool()
def search_stack(query: str = "") -> list[dict]:
    """Search through clipboard/OCR history or return the entire stack.

    Use this when the user asks "did I copy something about X?",
    "what did I copy", or wants to recall previous clipboard content.
    Leave query empty to return all entries.

    Args:
        query: Optional search term (case-insensitive). If empty, returns full stack.

    Returns:
        A list of matching entries. Each entry contains index, text, original, and compact.
    """
    entries = []
    q = query.lower() if query else ""
    for i in range(_stack.size()):
        entry = _stack.get_entry(i)
        if entry is None:
            continue
        if not q or q in entry.original.lower():
            entries.append({
                "index": i,
                "text": entry.text,
                "original": entry.original,
                "compact": entry.compact,
            })

    if not entries:
        msg = f"No entries matching '{query}' found." if query else "Stack is empty."
        return [{"message": msg}]
    return entries





@mcp.tool()
def ocr_get_current() -> str:
    """Return the text that is currently selected in the stack.

    This is the text that would be pasted on Ctrl+V.

    Returns:
        The current text, or a message if the stack is empty.
    """
    text = _stack.current()
    if text:
        return text
    return "Stack is empty."


@mcp.tool()
def ocr_push_text(text: str) -> str:
    """Push arbitrary text onto the stack and copy it to the clipboard.

    Use this to prepare text for the user to paste. For example, an AI
    could compose a response and push it so the user can Ctrl+V it into
    any application.

    Args:
        text: The text to push onto the stack.

    Returns:
        Confirmation message.
    """
    if not text:
        return "ERROR: Cannot push empty text."
    _stack.push(text)
    set_clipboard(text)
    return f"Pushed to stack and clipboard ({len(text)} chars): {text[:80]}"


@mcp.tool()
def ocr_clear_stack() -> str:
    """Clear the entire OCR/clipboard history stack.

    Returns:
        Confirmation message.
    """
    count = _stack.size()
    _stack.clear()
    return f"Stack cleared ({count} entries removed)."


@mcp.tool()
def crunch_file(path: str, level: int = 2) -> dict:
    """Read a file from disk and compress it for token-efficient AI consumption.

    Perfect for loading CLAUDE.md, AGENTS.md, README.md, project docs,
    config files, or any text file into your context with minimal token usage.

    Args:
        path: Absolute or relative path to the text file.
        level: Compression level (1-3):
            1: 🪶 Light (whitespace only) — safe for code
            2: 🦖 Token-Cruncher (removes stop words) — great for prose
            3: 💀 Annihilator (deduplication + boilerplate) — best for web/docs

    Returns:
        Dict with compressed_text, token stats, and file metadata.
    """
    p = Path(path).resolve()
    if not p.is_file():
        return {"error": f"File not found: {path}"}
    if p.stat().st_size > _MAX_FILE_SIZE:
        return {"error": f"File too large ({p.stat().st_size:,} bytes). Max: {_MAX_FILE_SIZE:,} bytes."}

    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"error": f"Could not read file: {e}"}

    if not text.strip():
        return {"error": "File is empty."}

    level = max(1, min(3, level))
    compressed, stats = minify_for_ai(text, level=level)
    token_info = token_stats(text, compressed)

    return {
        "file": p.name,
        "compressed_text": compressed,
        "original_chars": len(text),
        "compressed_chars": len(compressed),
        "content_type": stats["content_type"],
        "techniques_applied": stats["techniques_applied"],
        "level_used": level,
        **token_info,
    }


@mcp.tool()
def crunch_directory(path: str, level: int = 2, max_files: int = 20) -> dict:
    """Recursively read all text files in a directory and compress them.

    Ideal for loading an entire project's documentation, config files,
    or source code into your context window with minimal token usage.
    Skips binary files, hidden directories, and common build artifacts.

    Args:
        path: Path to the directory.
        level: Compression level (1-4).
        max_files: Maximum number of files to process (default 20).

    Returns:
        Dict with combined compressed text, per-file stats, and totals.
    """
    p = Path(path).resolve()
    if not p.is_dir():
        return {"error": f"Directory not found: {path}"}

    # Directories to skip
    skip_dirs = {".git", "__pycache__", "node_modules", ".venv", "venv",
                  "dist", "build", ".next", ".cache", ".pytest_cache"}

    files_processed = []
    combined_original = []
    combined_compressed = []
    total_orig_tokens = 0
    total_comp_tokens = 0
    level = max(1, min(3, level))

    for f in sorted(p.rglob("*")):
        if len(files_processed) >= max_files:
            break
        if not f.is_file():
            continue
        if f.suffix.lower() not in _TEXT_EXTENSIONS:
            continue
        if any(skip in f.parts for skip in skip_dirs):
            continue
        if f.stat().st_size > _MAX_FILE_SIZE:
            continue

        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        if not text.strip():
            continue

        compressed, _ = minify_for_ai(text, level=level)
        file_stats = token_stats(text, compressed)

        rel_path = str(f.relative_to(p))
        combined_original.append(f"--- {rel_path} ---\n{text}")
        combined_compressed.append(f"--- {rel_path} ---\n{compressed}")
        total_orig_tokens += file_stats["original_tokens"]
        total_comp_tokens += file_stats["compressed_tokens"]

        files_processed.append({
            "file": rel_path,
            "original_tokens": file_stats["original_tokens"],
            "compressed_tokens": file_stats["compressed_tokens"],
            "saved_percent": file_stats["saved_percent"],
        })

    if not files_processed:
        return {"error": f"No text files found in {path}"}

    total_saved = total_orig_tokens - total_comp_tokens
    total_pct = (total_saved / total_orig_tokens * 100.0) if total_orig_tokens > 0 else 0.0

    return {
        "combined_text": "\n\n".join(combined_compressed),
        "files_processed": len(files_processed),
        "per_file_stats": files_processed,
        "total_original_tokens": total_orig_tokens,
        "total_compressed_tokens": total_comp_tokens,
        "total_tokens_saved": total_saved,
        "total_saved_percent": round(total_pct, 1),
        "level_used": level,
        "summary": f"{len(files_processed)} files: {total_orig_tokens:,} → {total_comp_tokens:,} tokens ({total_pct:.1f}% saved)",
    }


@mcp.tool()
def count_text_tokens(text: str) -> dict:
    """Count the exact number of LLM tokens in a text and estimate input costs.

    Uses tiktoken cl100k_base (GPT-4o / Claude tokenizer) for accurate counts.
    Use this to understand token costs before sending text to an AI.

    Args:
        text: The text to count tokens for.

    Returns:
        Dict with token_count, char_count, efficiency ratio, and per-model
        cost estimates in US cents (FR-02).
    """
    if not text:
        return {"error": "No text provided."}

    tokens = count_tokens(text)
    chars = len(text)
    ratio = round(chars / tokens, 1) if tokens > 0 else 0

    # FR-02 — per-model input cost in US cents (uses precise tokens for GPT, estimate for Claude)
    costs = cost_estimate(text)
    cost_parts = []
    for model, c in costs.items():
        label = f"{model}: {format_cost(c)}"
        if "Claude" in model:
            label += " (~est)"
        cost_parts.append(label)
    cost_summary = "  |  ".join(cost_parts)

    return {
        "token_count": tokens,
        "char_count": chars,
        "chars_per_token": ratio,
        "cost_estimates_usc": costs,   # raw dict for programmatic use
        "summary": (
            f"{tokens:,} tokens ({chars:,} chars, {ratio} chars/token)\n"
            f"💰 {cost_summary}"
        ),
    }


@mcp.tool()
def get_brevity_prompt() -> str:
    """Get a system prompt snippet that instructs the AI to use brief output.

    Reduces AI output tokens by ~50-75%
    by instructing the model to be extremely concise.

    Use this as a system prompt prefix when you want the AI to save output
    tokens. Combine with crunch_text on inputs for maximum savings.

    Returns:
        A system prompt string for brevity mode.
    """
    return (
        "BREVITY MODE ACTIVE. Follow these rules strictly:\n"
        "- Use minimal words. No filler, no fluff, no pleasantries.\n"
        "- Skip explanations the user didn't ask for.\n"
        "- Code: write only the changed parts, not full files.\n"
        "- Lists: use terse bullet points, not paragraphs.\n"
        "- Never repeat the question back. Never say 'Sure!' or 'Great question!'.\n"
        "- If the answer is one word, reply with one word.\n"
        "- Prefer code blocks over prose when showing implementation.\n"
        "- Target: reduce your response length by 70% vs your normal style."
    )


@mcp.tool()
def crunch_code_skeleton(text: str, filename: str = "code.py") -> dict:
    """Creates a semantic skeleton of a code or structured-data file.

    For **code** (Python, JS/TS): strips all function bodies, returning only
    class definitions, interfaces, and function signatures.

    For **structured data** (JSON, XML, YAML): preserves the full key/tag
    hierarchy but truncates long string values and large arrays — keeping the
    schema shape while removing payload noise.

    Crucial for token-efficient repository or API-response mapping (e.g.
    providing an AI with a map of a 5,000-line codebase for ~300 tokens, or
    the schema of a 200 KB API response for ~50 tokens).

    Supported extensions: .py .pyw .js .ts .jsx .tsx .json .xml .yaml .yml
    All other file types are returned unchanged (safe no-op).

    Args:
        text: The raw text content.
        filename: Filename including extension (e.g. ``data.json``, ``main.py``)
                  used to select the correct parser.

    Returns:
        Dict with skeleton_text and token savings stats.
    """
    if not text:
        return {"error": "Cannot skeletonize empty text."}

    text = redact_secrets(text)
    orig_tokens = count_tokens(text)
    
    skeleton = crunch_skeleton(text, filename)
    new_tokens = count_tokens(skeleton)
    
    saved_tokens = max(0, orig_tokens - new_tokens)
    percentage = (saved_tokens / orig_tokens * 100) if orig_tokens > 0 else 0
    
    return {
        "file": filename,
        "skeleton_text": skeleton,
        "original_tokens": orig_tokens,
        "compressed_tokens": new_tokens,
        "saved_tokens": saved_tokens,
        "saved_percent": round(percentage, 1),
    }

@mcp.tool()
def crunch_file_skeleton(path: str) -> dict:
    """Read a local code file and compress it into a semantic skeleton.

    Perfect for loading large project architectures into context.

    Args:
        path: Absolute or relative path to the source code file.

    Returns:
        Dict with skeleton_text and token savings stats.
    """
    p = Path(path).resolve()
    if not p.is_file():
        return {"error": f"File not found: {path}"}
    if p.stat().st_size > _MAX_FILE_SIZE:
        return {"error": f"File too large ({p.stat().st_size:,} bytes)."}

    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"error": f"Could not read file: {e}"}

    return crunch_code_skeleton(text, p.name)


# -----------------------------------------------------------------------
# AI Context Manager tools (Phase 1)
# -----------------------------------------------------------------------

@mcp.tool()
def smart_crunch(text: str, intent: str = "understand",
                 filename: str = "") -> dict:
    """Intelligently compress text based on content type and intent.

    Unlike crunch_text which applies the same strategy to everything,
    smart_crunch detects the content type (code, JSON, logs, prose, etc.)
    and applies the optimal compression pipeline automatically.

    Use this instead of crunch_text when you want the best compression
    without guessing the right level.

    Args:
        text: The text to compress.
        intent: What you need this text for:
            - "understand": Preserve meaning, remove noise (default)
            - "code_review": Keep code structure, remove prose
            - "extract_data": Keep numbers/names/dates, remove narrative
            - "summarize": Maximum reduction, keep key facts only
        filename: Optional filename hint for better content-type detection
                  (e.g. "main.py", "data.json", "server.log").

    Returns:
        Dict with compressed_text, strategy_used, content_type,
        what_was_removed, confidence (0-1), and token savings.
    """
    if not text:
        return {"error": "Cannot compress empty text."}

    result = smart_route(text, intent=intent, filename=filename)
    return asdict(result)


@mcp.tool()
def explain_compression(text: str, filename: str = "") -> dict:
    """Preview what each compression strategy would do — WITHOUT modifying the text.

    Perfect for deciding how aggressively to compress before committing.
    Shows per-intent analysis with token savings, confidence, and what
    would be removed.

    Args:
        text: The text to analyze.
        filename: Optional filename for better content-type detection.

    Returns:
        Dict with detected content_type, per-intent analysis, and
        a recommended intent (best savings with confidence >= 0.85).
    """
    if not text:
        return {"error": "Cannot analyze empty text."}

    content_type = detect_content_type(text, filename)
    original_tokens = count_tokens(text)
    analysis = {}

    for intent in ["understand", "code_review", "extract_data", "summarize"]:
        result = smart_route(text, intent=intent, filename=filename)
        analysis[intent] = {
            "strategy": result.strategy_used,
            "token_savings_percent": result.saved_percent,
            "what_would_be_removed": result.what_was_removed,
            "confidence": result.confidence,
            "result_tokens": result.compressed_tokens,
        }

    # Recommend: highest savings with confidence >= 0.85
    safe_intents = [
        (k, v) for k, v in analysis.items()
        if v["confidence"] >= 0.85
    ]
    if safe_intents:
        recommended = max(safe_intents, key=lambda x: x[1]["token_savings_percent"])
        rec_intent = recommended[0]
        rec_reason = (
            f"Best savings ({recommended[1]['token_savings_percent']:.1f}%) "
            f"with confidence >= 85%"
        )
    else:
        rec_intent = "understand"
        rec_reason = "All strategies have < 85% confidence; defaulting to safest."

    return {
        "content_type": content_type,
        "original_tokens": original_tokens,
        "per_intent_analysis": analysis,
        "recommended_intent": rec_intent,
        "recommendation_reason": rec_reason,
    }


# -----------------------------------------------------------------------
# AI Context Manager tools (Phase 2)
# -----------------------------------------------------------------------

# Module-level diff cache (lives for the duration of the MCP server process)
_diff_cache = DiffCache()


@mcp.tool()
def budget_loader(path: str, token_budget: int = 4000,
                  priority: str = "auto") -> dict:
    """Load a file into exactly N tokens — no more, no less.

    The AI agent specifies how many tokens it can afford, and
    budget_loader returns the maximum useful content within that budget.
    This is like `head -n` but intelligent — it understands structure.

    Args:
        path: Absolute or relative path to a text file.
        token_budget: Maximum tokens to use (default: 4000).
        priority: What to prioritize when cutting:
            - "auto": Detect content type and decide
            - "signatures": Keep function/class signatures (code)
            - "structure": Keep headings + first sentences (docs)
            - "recent": Keep most recent entries (logs)
            - "schema": Keep keys/types, drop values (JSON/YAML)

    Returns:
        Dict with text fit to budget, what was cut, actual token count,
        and whether the full file was included.
    """
    p = Path(path).resolve()
    if not p.is_file():
        return {"error": f"File not found: {path}"}
    if p.stat().st_size > _MAX_FILE_SIZE:
        return {"error": f"File too large ({p.stat().st_size:,} bytes). Max: {_MAX_FILE_SIZE:,}."}

    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"error": f"Could not read file: {e}"}

    if not text.strip():
        return {"error": "File is empty."}

    text = redact_secrets(text)
    original_tokens = count_tokens(text)
    is_full = original_tokens <= token_budget

    # Determine effective priority from content type if "auto"
    effective_priority = priority
    if effective_priority == "auto":
        ct = detect_content_type(text, p.name)
        if ct.startswith("code_"):
            effective_priority = "signatures"
        elif ct.startswith("data_"):
            effective_priority = "schema"
        elif ct == "log":
            effective_priority = "recent"
        else:
            effective_priority = "structure"

    # Apply priority-specific strategy
    strategy_used = effective_priority
    result_text = text

    if not is_full:
        if effective_priority == "signatures":
            result_text = crunch_skeleton(text, p.name)
        elif effective_priority == "schema":
            result_text = crunch_skeleton(text, p.name)
        elif effective_priority == "recent":
            # Keep the last N lines that fit the budget
            lines = text.splitlines()
            lines.reverse()
            collected = []
            for line in lines:
                collected.append(line)
                check = "\n".join(reversed(collected))
                if count_tokens(check) > token_budget:
                    collected.pop()
                    break
            result_text = "\n".join(reversed(collected))
        elif effective_priority == "structure":
            # Keep headings + first sentence of each section
            lines = text.splitlines()
            kept = []
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("#") or not stripped:
                    kept.append(line)
                elif kept and kept[-1].strip().startswith("#"):
                    kept.append(line)  # first line after heading
            result_text = "\n".join(kept) if kept else text

        # Final truncation to exact budget
        result_text, actual_tokens = truncate_to_budget(result_text, token_budget)
    else:
        actual_tokens = original_tokens

    saved = original_tokens - count_tokens(result_text)

    return {
        "file": p.name,
        "text": result_text,
        "is_complete": is_full,
        "priority_used": effective_priority,
        "strategy": strategy_used,
        "original_tokens": original_tokens,
        "result_tokens": count_tokens(result_text),
        "token_budget": token_budget,
        "tokens_saved": saved,
        "summary": (
            f"{p.name}: {original_tokens:,} tokens "
            f"{'(complete)' if is_full else f'→ {count_tokens(result_text):,} tokens ({effective_priority})'}"
        ),
    }


@mcp.tool()
def diff_crunch(text: str, previous_version_id: str = "") -> dict:
    """Only return what changed since the last time this text was seen.

    On the FIRST call, returns the full text and a version_id.
    On SUBSEQUENT calls with the same version_id, returns ONLY the delta.

    In long coding sessions this saves 90%+ tokens on repeated file reads.

    Args:
        text: The current version of the text.
        previous_version_id: The version_id from a previous diff_crunch call.
            Leave empty on first use.

    Returns:
        Dict with either full text (first call) or changes_only (delta),
        a version_id for the next call, and token savings stats.
    """
    if not text:
        return {"error": "Cannot diff empty text."}

    current_tokens = count_tokens(text)
    new_id = _diff_cache.store(text)

    if not previous_version_id or not _diff_cache.get(previous_version_id):
        return {
            "mode": "full",
            "text": text,
            "version_id": new_id,
            "token_count": current_tokens,
            "hint": "Pass version_id in your next call to get only changes.",
        }

    diff_result = _diff_cache.compute_diff(previous_version_id, text)
    diff_tokens = count_tokens(diff_result["changes_text"])

    if diff_result["change_type"] == "unchanged":
        return {
            "mode": "unchanged",
            "version_id": new_id,
            "message": "No changes detected since last version.",
            "token_count": 0,
            "full_tokens": current_tokens,
            "tokens_saved": current_tokens,
            "saved_percent": 100.0,
        }

    # Overhead guard (WARN-002): if the delta is at least as expensive as the
    # full text, skip the diff and return the full text instead.  This happens
    # with very short texts where the unified-diff header alone exceeds the
    # original content length.
    if diff_tokens >= current_tokens:
        return {
            "mode": "full",
            "text": text,
            "version_id": new_id,
            "token_count": current_tokens,
            "hint": "Delta was not smaller than full text; full text returned.",
        }

    saved = current_tokens - diff_tokens
    return {
        "mode": "delta",
        "changes_only": diff_result["changes_text"],
        "change_type": diff_result["change_type"],
        "lines_added": diff_result["lines_added"],
        "lines_removed": diff_result["lines_removed"],
        "version_id": new_id,
        "delta_tokens": diff_tokens,
        "full_tokens": current_tokens,
        "tokens_saved": saved,
        "saved_percent": round(saved / current_tokens * 100, 1) if current_tokens > 0 else 0,
    }


# -----------------------------------------------------------------------
# AI Context Manager tools (Phase 3)
# -----------------------------------------------------------------------

_MIN_TOKENS_PER_FILE = 200  # Below this, a file is too small to be useful


def _relevance_score(text: str, question: str) -> float:
    """Simple keyword-overlap relevance score (0.0–1.0).

    Uses lowercased word-set intersection between *question* and *text*.
    No external dependencies.  Good enough for keyword-based ranking;
    semantic ranking is a future FR-05 upgrade.
    """
    if not question:
        return 1.0
    q_words = set(question.lower().split())
    # Only sample the first 2000 chars for speed on large files
    t_words = set(text[:2000].lower().split())
    if not q_words:
        return 1.0
    overlap = q_words & t_words
    return len(overlap) / len(q_words)


@mcp.tool()
def context_pack(paths: list[str], token_budget: int = 10000,
                 question: str = "") -> dict:
    """Pack multiple files into a single context block within a token budget.

    Files are ranked by relevance to the question (if provided) and each
    gets a proportional share of the token budget.  The result is a single
    ready-to-use context payload with file headers.

    This is the power tool for RAG pipelines and multi-file code review:
    give it 5 files and 8K tokens, and it returns the best possible
    compressed summary of all of them.

    Args:
        paths: List of absolute file paths to include.
        token_budget: Total tokens for ALL files combined (default: 10000).
        question: Optional question to rank file relevance by.
            Files matching more keywords get a larger budget share.

    Returns:
        Dict with packed_context (ready to paste into a prompt),
        per-file allocation details, and overall stats.
    """
    if not paths:
        return {"error": "No file paths provided."}
    if token_budget < _MIN_TOKENS_PER_FILE:
        return {"error": f"Token budget too small (min: {_MIN_TOKENS_PER_FILE})."}

    # 1. Read all files and compute relevance scores
    file_data: list[dict] = []
    for fp in paths:
        p = Path(fp).resolve()
        if not p.is_file():
            continue
        if p.stat().st_size > _MAX_FILE_SIZE:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if not text.strip():
            continue

        text = redact_secrets(text)
        score = _relevance_score(text, question)
        file_data.append({
            "path": str(p),
            "name": p.name,
            "text": text,
            "tokens": count_tokens(text),
            "score": score,
        })

    if not file_data:
        return {"error": "No readable files found in the provided paths."}

    # 2. Sort by relevance (highest first)
    file_data.sort(key=lambda x: x["score"], reverse=True)

    # 3. Allocate budget proportionally to scores
    total_score = sum(f["score"] for f in file_data) or 1.0
    allocations: list[dict] = []

    for f in file_data:
        share = f["score"] / total_score
        alloc = int(token_budget * share)
        if alloc < _MIN_TOKENS_PER_FILE:
            continue  # Skip files with too little budget
        allocations.append({**f, "budget": alloc})

    if not allocations:
        # If scoring eliminated everything, give equal shares
        per_file = token_budget // len(file_data)
        if per_file < _MIN_TOKENS_PER_FILE:
            allocations = [file_data[0]]  # At least include the most relevant
            allocations[0]["budget"] = token_budget
        else:
            for f in file_data:
                allocations.append({**f, "budget": per_file})

    # 4. Compress each file to its budget
    packed_parts: list[str] = []
    file_details: list[dict] = []
    tokens_used = 0

    for alloc in allocations:
        result = smart_route(alloc["text"], intent="understand", filename=alloc["name"])
        compressed = result.compressed_text

        # Truncate to allocated budget
        compressed, actual = truncate_to_budget(compressed, alloc["budget"])

        packed_parts.append(f"--- {alloc['name']} ---\n{compressed}")
        tokens_used += actual

        file_details.append({
            "file": alloc["name"],
            "path": alloc["path"],
            "original_tokens": alloc["tokens"],
            "allocated_budget": alloc["budget"],
            "actual_tokens": actual,
            "relevance_score": round(alloc["score"], 2),
            "strategy": result.strategy_used,
            "is_complete": alloc["tokens"] <= alloc["budget"],
        })

    packed_context = "\n\n".join(packed_parts)
    total_original = sum(f["original_tokens"] for f in file_details)
    saved = total_original - tokens_used

    return {
        "packed_context": packed_context,
        "files_included": len(file_details),
        "files_skipped": len(paths) - len(file_details),
        "token_budget": token_budget,
        "tokens_used": tokens_used,
        "total_original_tokens": total_original,
        "tokens_saved": saved,
        "saved_percent": round(saved / total_original * 100, 1) if total_original > 0 else 0,
        "per_file": file_details,
        "question": question or "(none — equal distribution)",
    }


# -----------------------------------------------------------------------
# AI Prompt Optimizer tools (FR-05.4)
# -----------------------------------------------------------------------

@mcp.tool()
def optimize_prompt(
    text: str,
    profile: str = "general",
    provider: str = "",
    model: str = "",
) -> dict:
    """Rewrite text into a structured, role-optimized LLM prompt.

    Takes raw text and rewrites it into an effective prompt using a
    configurable LLM backend.  The system prompt from the selected
    profile guides the rewrite.

    Requires API keys to be configured (see manage_optimizer_profile)
    or a local Ollama instance for the 'ollama' provider.

    Args:
        text: The raw text to optimize into a prompt.
        profile: Profile name to use (default: 'general').
            Built-in: general, code_reviewer, data_analyst, summarizer, translator.
        provider: Override provider (openai, anthropic, ollama). Empty = use profile default.
        model: Override model name. Empty = use profile default.

    Returns:
        Dict with optimized_prompt, input/output tokens, latency, and profile info.
    """
    result = po_optimize(text, profile_name=profile,
                         provider_override=provider, model_override=model)
    return {
        "optimized_prompt": result.optimized_prompt,
        "profile_used": result.profile_used,
        "provider": result.provider,
        "model": result.model,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "latency_ms": result.latency_ms,
        **(({"error": result.error}) if result.error else {}),
    }


@mcp.tool()
def ai_compress(
    text: str,
    aggressive: bool = False,
    provider: str = "",
    model: str = "",
) -> dict:
    """LLM-based semantic compression with hybrid structure preservation.

    Sends the text to a configured LLM (Ollama / OpenAI / Anthropic) with
    a compression-specific system prompt.  Unlike `crunch_text` — which is
    deterministic and rule-based — `ai_compress` uses semantic understanding
    to compress prose while preserving meaning.

    HYBRID ARCHITECTURE: Before the LLM sees the text, ContextCruncher
    extracts fenced/indented code blocks, markdown tables, inline backtick
    refs, and constraint sentences (NEVER/ALWAYS/MUST NOT/DO NOT) into
    placeholders.  After the LLM returns, originals are reinserted
    verbatim — the LLM can only compress prose between structured blocks.

    SECURITY: Secrets (API keys, tokens) are redacted via the
    security_scanner BEFORE the text leaves the machine.  No exceptions.

    Requires one of:
      • Ollama running locally (`ollama serve`), OR
      • OpenAI API key configured (Settings → AI Compression), OR
      • Anthropic API key configured (Settings → AI Compression).

    Args:
        text: Text to compress.
        aggressive: Use the more aggressive `compress_aggressive` profile
            (default False — uses the standard `compress` profile).
        provider: Override the configured provider ('openai', 'anthropic',
            'ollama'). Empty = use the profile / config default.
        model: Override the model name. Empty = use the profile / config default.

    Returns:
        Dict with compressed_text, token savings, latency, provider/model,
        and any validation warnings from the hybrid extraction round-trip.
    """
    if not text or not text.strip():
        return {"error": "Cannot compress empty text."}

    result: CompressResult = po_compress(
        text,
        aggressive=aggressive,
        provider_override=provider,
        model_override=model,
    )

    response = {
        "compressed_text": result.compressed_text,
        "provider": result.provider,
        "model": result.model,
        "original_tokens": result.original_tokens,
        "compressed_tokens": result.compressed_tokens,
        "saved_percent": result.saved_percent,
        "latency_ms": result.latency_ms,
        "warnings": list(result.warnings),
        "aggressive": aggressive,
    }
    if result.error:
        response["error"] = result.error
    return response


@mcp.tool()
def list_optimizer_profiles() -> dict:
    """List all available prompt optimizer profiles.

    Returns both built-in profiles (general, code_reviewer, data_analyst,
    summarizer, translator) and any custom profiles the user has created.

    Returns:
        Dict with profiles list and provider config status.
    """
    profiles = po_list_profiles()
    config = po_get_provider_config()
    return {
        "profiles": [
            {
                "name": p["name"],
                "provider": p["provider"],
                "model": p["model"],
                "system_prompt_preview": p["system_prompt"][:120] + "..." if len(p["system_prompt"]) > 120 else p["system_prompt"],
                "is_builtin": p.get("is_builtin", False),
            }
            for p in profiles
        ],
        "provider_config": {
            "openai_configured": bool(config.get("openai_api_key")),
            "anthropic_configured": bool(config.get("anthropic_api_key")),
            "ollama_endpoint": config.get("ollama_endpoint", "http://localhost:11434"),
        },
    }


@mcp.tool()
def manage_optimizer_profile(
    action: str,
    name: str = "",
    provider: str = "openai",
    model: str = "gpt-4o-mini",
    system_prompt: str = "",
    temperature: float = 0.3,
    max_output_tokens: int = 2000,
    endpoint: str = "",
    openai_api_key: str = "",
    anthropic_api_key: str = "",
    ollama_endpoint: str = "",
) -> dict:
    """Create, delete custom profiles or configure API keys.

    Actions:
      - 'create': Create or update a custom profile.
      - 'delete': Delete a custom profile (built-in profiles cannot be deleted).
      - 'set_keys': Save API keys and endpoints for providers.

    Args:
        action: 'create', 'delete', or 'set_keys'.
        name: Profile name (required for create/delete).
        provider: LLM provider (openai, anthropic, ollama).
        model: Model name (e.g., gpt-4o-mini, claude-3-haiku-20240307, llama3).
        system_prompt: System instruction for the profile (required for create).
        temperature: Sampling temperature (0.0-1.0, default 0.3).
        max_output_tokens: Max output tokens (default 2000).
        endpoint: Ollama endpoint URL (only for ollama provider).
        openai_api_key: OpenAI API key (only for set_keys action).
        anthropic_api_key: Anthropic API key (only for set_keys action).
        ollama_endpoint: Ollama endpoint URL (only for set_keys action).

    Returns:
        Dict with operation result status.
    """
    if action == "create":
        if not name:
            return {"error": "Profile name is required."}
        if not system_prompt:
            return {"error": "System prompt is required for profile creation."}
        profile = LLMProfile(
            name=name, provider=provider, model=model,
            system_prompt=system_prompt, temperature=temperature,
            max_output_tokens=max_output_tokens, endpoint=endpoint,
        )
        return po_save_profile(profile)

    elif action == "delete":
        if not name:
            return {"error": "Profile name is required."}
        return po_delete_profile(name)

    elif action == "set_keys":
        config = po_get_provider_config()
        if openai_api_key:
            config["openai_api_key"] = openai_api_key
        if anthropic_api_key:
            config["anthropic_api_key"] = anthropic_api_key
        if ollama_endpoint:
            config["ollama_endpoint"] = ollama_endpoint
        po_save_provider_config(config)
        return {
            "status": "keys_saved",
            "openai_configured": bool(config.get("openai_api_key")),
            "anthropic_configured": bool(config.get("anthropic_api_key")),
            "ollama_endpoint": config.get("ollama_endpoint", "http://localhost:11434"),
        }

    else:
        return {"error": f"Unknown action '{action}'. Use: create, delete, set_keys."}


# -----------------------------------------------------------------------
# Resources (passive context for AI agents)
# -----------------------------------------------------------------------

@mcp.resource("clipboard://current")
def resource_current_clipboard() -> str:
    """The user's current clipboard content."""
    try:
        text = pyperclip.paste()
        return text if text and text.strip() else "(clipboard is empty)"
    except Exception:
        return "(could not read clipboard)"


@mcp.resource("clipboard://history")
def resource_clipboard_history() -> str:
    """Recent clipboard/OCR history entries."""
    if _stack.size() == 0:
        return "(no history)"
    entries = []
    for i in range(_stack.size()):
        e = _stack.get_entry(i)
        if e is None:
            continue
        preview = e.original[:100]
        entries.append(f"[{i}] {preview}")
    return "\n---\n".join(entries)


# -----------------------------------------------------------------------
# Entry point
# -----------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
