"""Analyze which compression techniques actually save LLM tokens."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from contextcruncher.token_counter import count_tokens

# Force UTF-8 on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

tests = {
    "Stop words": (
        "The quick brown fox jumps over the lazy dog",
        "quick brown fox jumps over lazy dog",
    ),
    "URL removal": (
        "Check out https://github.com/user/repo/blob/main/file.py for details",
        "Check out [URL] for details",
    ),
    "Duplicate lines": (
        "Error occurred\nError occurred\nError occurred\nFailed to connect",
        "Error occurred\nFailed to connect",
    ),
    "Markdown strip": (
        "## Section Title\n\n**Bold text** and *italic text*",
        "Section Title\nBold text and italic text",
    ),
    "Filler phrases": (
        "In order to understand the basic fundamentals of this, it is important to note that",
        "To understand fundamentals,",
    ),
    "Empty lines": (
        "Line 1\n\n\n\n\nLine 2\n\n\nLine 3",
        "Line 1\nLine 2\nLine 3",
    ),
    "Code comments": (
        "x = 5  # Set x to 5\ny = 10  # Set y to 10\nresult = x + y  # Calculate result",
        "x = 5\ny = 10\nresult = x + y",
    ),
    "Repeated punct": (
        "Hello!!! How are you??? I am fine...",
        "Hello! How are you? I am fine.",
    ),
    "Bullets to CSV": (
        "- Item one\n- Item two\n- Item three\n- Item four",
        "Item one, Item two, Item three, Item four",
    ),
    "Vowel removal": (
        "The quick brown fox jumps",
        "Th qck brwn fx jmps",
    ),
    "Abbreviations": (
        "function application configuration documentation implementation",
        "func app config docs impl",
    ),
    "Sentence merge": (
        "This is line one.\nThis is line two.\nThis is line three.",
        "This is line one. This is line two. This is line three.",
    ),
    "Log timestamps": (
        "2024-01-15T14:23:45.123Z INFO Starting\n2024-01-15T14:23:46.456Z INFO Running\n2024-01-15T14:23:47.789Z INFO Done",
        "INFO Starting\nINFO Running\nINFO Done",
    ),
    "Path shortening": (
        "File at C:\\Users\\JohnDoe\\Documents\\Projects\\MyApp\\src\\main.py",
        "File at .../src/main.py",
    ),
}

print(f"{'Technique':<20} {'Before':>8} {'After':>8} {'Saved':>8} {'% Saved':>8}")
print("-" * 58)
for name, (before, after) in tests.items():
    tb = count_tokens(before)
    ta = count_tokens(after)
    saved = tb - ta
    pct = (saved / tb * 100) if tb > 0 else 0
    marker = " ***" if pct > 25 else ""
    print(f"{name:<20} {tb:>8} {ta:>8} {saved:>8} {pct:>7.1f}%{marker}")
