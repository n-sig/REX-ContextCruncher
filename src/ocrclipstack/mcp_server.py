"""
mcp_server.py — Model Context Protocol server for ContextCruncher.

Exposes ContextCruncher functionality to AI agents (Claude, Gemini, etc.)
via the MCP standard.  Run this as a standalone process:

    python -m ocrclipstack.mcp_server

AI clients (e.g. Claude Desktop) can register it in their config:

    {
      "mcpServers": {
        "contextcruncher": {
          "command": ["python", "-m", "ocrclipstack.mcp_server"]
        }
      }
    }

Exposed tools:
  • ocr_scan_region   — Prompt user to select a screen region, return OCR text.
  • screenshot_full   — OCR the entire visible screen without user interaction.
  • read_clipboard    — Read the current system clipboard content.
  • crunch_text       — Compress text for token-efficient AI consumption.
  • search_stack      — Search through clipboard/OCR history.
  • ocr_get_stack     — Return the entire history stack as a list.
  • ocr_get_current   — Return the currently selected stack entry.
  • ocr_push_text     — Push arbitrary text into the stack.
  • ocr_clear_stack   — Clear the history stack.
"""

from __future__ import annotations

import os
import sys
import threading

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

from ocrclipstack.stack import TextStack
from ocrclipstack.ocr import recognise, is_ocr_available
from ocrclipstack.overlay import select_region
from ocrclipstack.clipboard import set_clipboard
from ocrclipstack.normalize import compact_variant
from ocrclipstack.text_processor import minify_for_ai

import pyperclip

# -----------------------------------------------------------------------
# Shared state (independent of the GUI app — this is a standalone process)
# -----------------------------------------------------------------------
_stack = TextStack()

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
        "5) Push prepared text directly to the user's clipboard for pasting."
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
    return {
        "compressed_text": compressed,
        "original_chars": len(text),
        "compressed_chars": len(compressed),
        "saved_percent": round(saved, 1),
        "level_used": level,
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
