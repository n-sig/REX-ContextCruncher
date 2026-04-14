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

Exposed tools (14):
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
  • search_stack         — Search through clipboard/OCR history.
  • ocr_get_stack        — Return the entire history stack as a list.
  • ocr_get_current      — Return the currently selected stack entry.
  • ocr_push_text        — Push arbitrary text into the stack.
  • ocr_clear_stack      — Clear the history stack.
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
from contextcruncher.token_counter import count_tokens, token_stats, cost_estimate, format_cost
from contextcruncher.security_scanner import redact_secrets
from contextcruncher.skeletonizer import crunch_skeleton

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
        "7) Provide real token counts (tiktoken cl100k_base) for any text."
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
        level: Compression level (1-4):
            1: Light (whitespace only) — safe for code
            2: Token-Cruncher (removes stop words) — great for prose
            3: Annihilator (deduplication + boilerplate removal) — best for web scrapes
            4: Experimental (vowel removal) — NOT AI-readable, use with caution!

    Returns:
        A dict with compressed_text, original_chars, compressed_chars, saved_percent.
    """
    if not text:
        return {"error": "Cannot compress empty text."}

    level = max(1, min(4, level))
    compressed, saved = minify_for_ai(text, level=level)
    stats = token_stats(text, compressed)
    return {
        "compressed_text": compressed,
        "original_chars": len(text),
        "compressed_chars": len(compressed),
        "char_saved_percent": round(saved, 1),
        "level_used": level,
        **stats,
    }


@mcp.tool()
def search_stack(query: str) -> list[dict]:
    """Search through clipboard/OCR history for entries matching a query.

    Use this when the user asks "did I copy something about X?",
    "find that thing I scanned earlier", or wants to recall
    previous clipboard content.

    Args:
        query: The search term to look for (case-insensitive).

    Returns:
        A list of matching entries with their index and text preview.
    """
    if not query:
        return [{"error": "Please provide a search query."}]

    results = []
    for i, entry in enumerate(_stack._items):
        if query.lower() in entry.original.lower():
            results.append({
                "index": i,
                "text": entry.original[:200],
                "has_compact": entry.compact is not None,
            })

    if not results:
        return [{"message": f"No entries matching '{query}' found in {_stack.size()} stack entries."}]
    return results


@mcp.tool()
def ocr_get_stack() -> list[dict[str, str | None]]:
    """Return the entire OCR/clipboard history stack.

    Returns:
        A list of entries, newest first. Each entry is a dict with keys:
          - 'text': the currently active variant (original or compact)
          - 'original': the original OCR text
          - 'compact': the compact variant (spaces stripped), or null
    """
    entries = []
    for entry in _stack._items:
        entries.append({
            "text": entry.text,
            "original": entry.original,
            "compact": entry.compact,
        })
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
        level: Compression level (1-4):
            1: 🪶 Light (whitespace only) — safe for code
            2: 🦖 Token-Cruncher (removes stop words) — great for prose
            3: 💀 Annihilator (deduplication + boilerplate) — best for web/docs
            4: ☢️ Experimental (vowel removal) — NOT AI-readable!

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

    level = max(1, min(4, level))
    compressed, char_pct = minify_for_ai(text, level=level)
    stats = token_stats(text, compressed)

    return {
        "file": p.name,
        "compressed_text": compressed,
        "original_chars": len(text),
        "compressed_chars": len(compressed),
        "level_used": level,
        **stats,
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
    level = max(1, min(4, level))

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
        stats = token_stats(text, compressed)

        rel_path = str(f.relative_to(p))
        combined_original.append(f"--- {rel_path} ---\n{text}")
        combined_compressed.append(f"--- {rel_path} ---\n{compressed}")
        total_orig_tokens += stats["original_tokens"]
        total_comp_tokens += stats["compressed_tokens"]

        files_processed.append({
            "file": rel_path,
            "original_tokens": stats["original_tokens"],
            "compressed_tokens": stats["compressed_tokens"],
            "saved_percent": stats["saved_percent"],
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

    # FR-02 — per-model input cost in US cents
    costs = cost_estimate(tokens)
    cost_summary = "  |  ".join(
        f"{model}: {format_cost(c)}" for model, c in costs.items()
    )

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
    for i, e in enumerate(_stack._items):
        preview = e.original[:100]
        entries.append(f"[{i}] {preview}")
    return "\n---\n".join(entries)


# -----------------------------------------------------------------------
# Entry point
# -----------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
