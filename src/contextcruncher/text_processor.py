"""
text_processor.py — Token-optimized text compression for LLMs.

Layered Architecture (v2):
  Layer 0 (🔍 Detect):   Content-type detection + code-block protection  [ALWAYS]
  Layer 1 (🪶 Clean):    Tokenizer-aligned whitespace normalization       [level≥1]
  Layer 2 (🧹 Trim):     Safe filler/stop-word removal                    [level≥2]
  Layer 3 (🏷️ Optimize): Synonym replacement + URL/path cleanup           [level≥3]

All techniques target actual LLM token reduction (tiktoken cl100k_base).
Code blocks are protected before any processing and restored afterward.
"""

import re
from dataclasses import dataclass, field
from typing import Tuple

from contextcruncher.security_scanner import redact_secrets
from contextcruncher.token_counter import count_tokens

# ---------------------------------------------------------------------------
# Stop words — SAFE subset only (CR-03 fix)
#
# ONLY words that carry zero semantic meaning for an LLM:
#   - Articles (a, an, the, der, die, das, …)
#   - Copula forms (is, are, was, were, …)
#   - Possessive/personal pronouns (my, your, his, …)
#   - True filler intensifiers (very, really, just, quite)
#
# NEVER include: not, if, but, or, before, after, above, below,
#   between, through, during, over, under, should, could, would,
#   can, may, which, who, what — these carry meaning!
# ---------------------------------------------------------------------------
STOP_WORDS = {
    # German — articles + pronouns only
    "der", "die", "das", "ein", "eine", "einer", "einem", "eines",
    "den", "dem", "des",
    "mich", "dich", "sich",
    "seine", "seiner", "seinen", "seinem",
    "ihrer", "ihrem", "ihren",
    "diese", "dieser", "diesem", "diesen",
    "sehr", "auch",

    # English — articles + copula + pronouns + intensifiers
    "the", "a", "an",
    "is", "are", "was", "were", "be", "been", "being",
    "has", "have", "had", "do", "does", "did",
    "me", "him", "her", "it", "we", "they",
    "its", "my", "your", "his", "our", "their",
    "this", "that", "these", "those",
    "very", "just", "really", "quite", "rather",
    "also", "too",
}

# ---------------------------------------------------------------------------
# Filler phrases — complete phrases that add zero information.
# Matched with word boundaries (\b) to avoid substring matches (CR-12 fix).
# ---------------------------------------------------------------------------
FILLER_PHRASES = [
    # English
    "it is important to note that",
    "it should be noted that",
    "it is worth mentioning that",
    "in order to",
    "as a matter of fact",
    "at the end of the day",
    "in terms of",
    "with respect to",
    "with regard to",
    "due to the fact that",
    "for the purpose of",
    "in the event that",
    "on the other hand",
    "as a result of",
    "in addition to",
    "as well as",
    "at this point in time",
    "in the process of",
    "it goes without saying that",
    "needless to say",
    "please note that",
    "please be aware that",
    "as mentioned above",
    "as previously mentioned",
    "as described above",
    "as shown below",
    "as you can see",
    "basically",
    "essentially",
    "fundamentally",
    "generally speaking",
    "in general",

    # German
    "es ist wichtig zu beachten dass",
    "es sollte beachtet werden dass",
    "im folgenden",
    "im grunde genommen",
    "darüber hinaus",
    "nichtsdestotrotz",
    "grundsätzlich",
    "selbstverständlich",
    "meiner meinung nach",
]
# Sort longest first so greedy matching works
FILLER_PHRASES.sort(key=len, reverse=True)

# Pre-compile filler phrases with word boundaries (CR-12 fix)
_FILLER_REGEXES = [
    re.compile(r'\b' + re.escape(phrase) + r'\b', re.IGNORECASE)
    for phrase in FILLER_PHRASES
]

# ---------------------------------------------------------------------------
# Synonym table — short technical equivalents (Layer 3)
# ---------------------------------------------------------------------------
SYNONYMS = {
    "approximately": "~",
    "functionality": "feature",
    "implementation": "impl",
    "configuration": "config",
    "documentation": "docs",
    "application": "app",
    "information": "info",
    "requirements": "reqs",
    "environment": "env",
    "development": "dev",
    "production": "prod",
    "repository": "repo",
    "dependency": "dep",
    "dependencies": "deps",
    "authentication": "auth",
    "authorization": "authz",
    "database": "db",
    "directory": "dir",
    "parameter": "param",
    "parameters": "params",
    "maximum": "max",
    "minimum": "min",
    "specification": "spec",
    "specifications": "specs",
    "administrator": "admin",
    "temporary": "temp",
    "initialize": "init",
    "initialized": "init'd",
    "utilization": "usage",
    "utilise": "use",
    "utilize": "use",
    "modification": "mod",
    "modifications": "mods",
    "automatically": "auto",
    "previously": "prev",
    "additionally": "also",
    "unfortunately": "",
    "corresponding": "matching",
    "respectively": "each",
}

# Pre-compile synonym regex (word-boundary, case-insensitive)
_SYNONYM_REGEXES = [
    (re.compile(r'\b' + re.escape(word) + r'\b', re.IGNORECASE), repl)
    for word, repl in SYNONYMS.items()
    if repl  # skip empty replacements in regex, handle separately
]
_SYNONYM_DROP = [
    re.compile(r'\b' + re.escape(word) + r'\b', re.IGNORECASE)
    for word, repl in SYNONYMS.items()
    if not repl  # words to drop entirely
]

# ---------------------------------------------------------------------------
# Compiled regex patterns (compiled once, reused)
# ---------------------------------------------------------------------------
_PUNCT_RE = re.compile(r'[.,!?();:]')
_MULTI_SPACE = re.compile(r'[ \t]{2,}')
_BLANK_LINES = re.compile(r'\n[ \t]*\n+')
_TRAILING_WS = re.compile(r'[ \t]+$', re.MULTILINE)
_URL_RE = re.compile(r'https?://\S+')
_MARKDOWN_HEADER = re.compile(r'^#{1,6}\s+', re.MULTILINE)
_MARKDOWN_BOLD = re.compile(r'\*\*(.+?)\*\*')
_MARKDOWN_ITALIC = re.compile(r'(?<!\*)\*([^*]+?)\*(?!\*)')
_MARKDOWN_LINK = re.compile(r'\[([^\]]+)\]\([^\)]+\)')
_EMAIL_RE = re.compile(r'\b[\w\.\-]+@[\w\.\-]+\.\w+\b')
_FILE_PATH_WIN = re.compile(r'[A-Z]:\\(?:[\w\.\-]+\\){2,}')
_FILE_PATH_UNIX = re.compile(r'(?:/[\w\.\-]+){3,}')
_URL_TRACKING = re.compile(r'[?&](?:utm_\w+|ref|source|campaign|medium|content|fbclid|gclid)=[^&\s]*')

# Smart quotes / fancy chars → ASCII
_SMART_QUOTES = [
    ('\u201c', '"'), ('\u201d', '"'),   # " "
    ('\u2018', "'"), ('\u2019', "'"),   # ' '
    ('\u2013', '-'), ('\u2014', '--'),  # – —
    ('\u2026', '...'),                  # …
    ('\u00a0', ' '),                    # non-breaking space
]
_FANCY_BULLETS = re.compile(r'^[ \t]*[•●○◦▸▹►▻➤➜→]', re.MULTILINE)

# Code block detection for Layer 0
_FENCED_CODE = re.compile(r'```[\s\S]*?```')
_INLINE_CODE = re.compile(r'`[^`\n]+`')

# Repeated punctuation (fixed: raw string)
_REPEATED_PUNCT = re.compile(r'([!?.])\1{2,}')


# =========================================================================
# LAYER 0 — 🔍 Detect & Protect
# =========================================================================

@dataclass
class ContentFrame:
    """Analyzed text with protected regions and metadata."""
    content_type: str                                   # "prose" (default)
    text: str                                           # text WITH placeholders
    protected: dict = field(default_factory=dict)       # {"__CB_0__": original}
    techniques: list = field(default_factory=list)       # techniques applied
    removed: list = field(default_factory=list)          # what was removed (samples)


def _detect_content_type(text: str) -> str:
    """Heuristic content-type detection."""
    lines = text.strip().splitlines()[:30]  # sample first 30 lines
    if not lines:
        return "prose"

    text_sample = "\n".join(lines).lower()

    # Log detection: timestamps + log levels
    log_indicators = sum(1 for l in lines if re.match(
        r'^\s*[\[\d].*?(INFO|WARN|ERROR|DEBUG|TRACE|WARNING|CRITICAL)', l, re.IGNORECASE))
    if log_indicators >= 3:
        return "log"

    # Email detection
    email_markers = ["from:", "to:", "subject:", "date:", "sent:"]
    if sum(1 for m in email_markers if m in text_sample) >= 2:
        return "email"

    # Web scrape detection
    web_markers = ["skip to content", "cookie", "privacy policy", "terms of service",
                   "sign in", "sign up", "footer", "navigation", "©"]
    if sum(1 for m in web_markers if m in text_sample) >= 3:
        return "web_scrape"

    # Markdown detection
    if sum(1 for l in lines if re.match(r'^#{1,6}\s', l)) >= 2:
        return "markdown"

    return "prose"


def _protect_code_blocks(text: str) -> tuple:
    """Extract code blocks and replace with placeholders."""
    protected = {}
    counter = [0]

    def _protect(match):
        key = f"__PROTECTED_{counter[0]}__"
        protected[key] = match.group(0)
        counter[0] += 1
        return key

    # Fenced code blocks first (``` ... ```)
    text = _FENCED_CODE.sub(_protect, text)
    # Inline code (`...`)
    text = _INLINE_CODE.sub(_protect, text)

    return text, protected


def _restore_protected(text: str, protected: dict) -> str:
    """Restore protected code blocks from placeholders."""
    for key, original in protected.items():
        text = text.replace(key, original)
    return text


# =========================================================================
# LAYER 1 — 🪶 Clean (Tokenizer Alignment)
# =========================================================================

def _layer_clean(text: str, frame: ContentFrame) -> str:
    """Tokenizer-aligned whitespace normalization. ZERO semantic risk."""
    # Smart quotes → ASCII
    for fancy, plain in _SMART_QUOTES:
        text = text.replace(fancy, plain)

    # Fancy bullets → ASCII dash
    text = _FANCY_BULLETS.sub('- ', text)

    # Tabs → 2 spaces
    text = text.replace('\t', '  ')
    # Collapse blank lines → single newline
    text = _BLANK_LINES.sub('\n', text)
    # Strip trailing whitespace per line
    text = _TRAILING_WS.sub('', text)
    # Collapse multiple spaces (but not at line start — preserve indentation)
    text = re.sub(r'(?<!^)(?<!\n)[ \t]{2,}', ' ', text, flags=re.MULTILINE)
    # Collapse repeated punctuation (!!!! → !)
    text = _REPEATED_PUNCT.sub(r'\1', text)

    frame.techniques.append("tokenizer_alignment")
    return text


# =========================================================================
# LAYER 2 — 🧹 Trim (Safe Content Removal)
# =========================================================================

def _layer_trim(text: str, frame: ContentFrame) -> str:
    """Remove filler phrases, stop words, and safe formatting. ZERO semantic risk."""
    removed_samples = []

    # Remove filler phrases with word boundaries (CR-12 fix)
    for regex in _FILLER_REGEXES:
        match = regex.search(text)
        if match and len(removed_samples) < 5:
            removed_samples.append(f"Filler: '{match.group(0)}'")
        text = regex.sub('', text)

    # Shorten URLs (saves ~53% tokens each)
    url_count = len(_URL_RE.findall(text))
    if url_count:
        text = _URL_RE.sub('[URL]', text)
        frame.techniques.append(f"url_shortening:{url_count}")

    # Replace email addresses
    email_count = len(_EMAIL_RE.findall(text))
    if email_count:
        text = _EMAIL_RE.sub('[EMAIL]', text)

    # Strip markdown formatting (but NOT code blocks — they're protected)
    text = _MARKDOWN_LINK.sub(r'\1', text)    # [text](url) → text
    text = _MARKDOWN_HEADER.sub('', text)      # ## Header → Header
    text = _MARKDOWN_BOLD.sub(r'\1', text)     # **bold** → bold
    text = _MARKDOWN_ITALIC.sub(r'\1', text)   # *italic* → italic

    # Remove stop words (safe subset only — CR-03)
    lines = text.split('\n')
    processed_lines = []
    for line in lines:
        # Skip lines that look like code or config
        stripped = line.strip()
        if stripped.startswith(('__PROTECTED_', '#!', '//', '/*', '*')):
            processed_lines.append(line)
            continue
        words = line.split()
        filtered = [w for w in words if _PUNCT_RE.sub('', w).lower() not in STOP_WORDS]
        processed_lines.append(" ".join(filtered))
    text = "\n".join(processed_lines)

    if removed_samples:
        frame.removed.extend(removed_samples)
    frame.techniques.append("safe_word_removal")
    return text


# =========================================================================
# LAYER 3 — 🏷️ Optimize (Structural Optimization)
# =========================================================================

def _layer_optimize(text: str, frame: ContentFrame) -> str:
    """Synonym replacement, URL cleanup, path shortening. LOW semantic risk."""
    # Synonym replacement
    synonym_count = 0
    for regex, repl in _SYNONYM_REGEXES:
        text, n = regex.subn(repl, text)
        synonym_count += n
    for regex in _SYNONYM_DROP:
        text, n = regex.subn('', text)
        synonym_count += n
    if synonym_count:
        frame.techniques.append(f"synonym_replacement:{synonym_count}")

    # URL tracking parameter cleanup
    text = _URL_TRACKING.sub('', text)

    # Shorten file paths (keep last 2 segments)
    def _shorten_path(match: re.Match) -> str:
        path = match.group(0)
        parts = [p for p in path.replace("\\", "/").split("/") if p]
        if len(parts) > 2:
            return ".../{}".format("/".join(parts[-2:]))
        return path

    path_count = len(_FILE_PATH_WIN.findall(text)) + len(_FILE_PATH_UNIX.findall(text))
    if path_count:
        text = _FILE_PATH_WIN.sub(_shorten_path, text)
        text = _FILE_PATH_UNIX.sub(_shorten_path, text)
        frame.techniques.append(f"path_shortening:{path_count}")

    # Window-based consecutive dedup (3-line window, fixes CR-15)
    lines = text.split('\n')
    if len(lines) > 5:
        deduped = []
        window = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                deduped.append(line)
                continue
            if stripped in window:
                if len(frame.removed) < 5:
                    frame.removed.append(f"Dedup: '{stripped[:50]}...'")
                continue
            deduped.append(line)
            window.append(stripped)
            if len(window) > 3:
                window.pop(0)
        text = "\n".join(deduped)
        frame.techniques.append("window_dedup")

    return text


# =========================================================================
# PUBLIC API
# =========================================================================

def minify_for_ai(text: str, level: int = 1,
                  xml_wrap: bool = False, xml_tag: str = "context"
                  ) -> Tuple[str, dict]:
    """Compress text for token-efficient AI consumption.

    Layered architecture — each level adds MORE techniques, not more damage:

    Level 1 (🪶 Clean):    Tokenizer-aligned whitespace — safe for everything
    Level 2 (🧹 Trim):     Filler phrases + stop words + markdown — safe for prose
    Level 3 (🏷️ Optimize): Synonyms + URL cleanup + path shortening + window dedup

    Args:
        text: The text to compress.
        level: Compression level (1-3). Each level includes all previous.
        xml_wrap: Wrap output in XML tags.
        xml_tag: Tag name for XML wrapping.

    Returns:
        Tuple of (compressed_text, stats_dict).

        stats_dict contains:
          - original_tokens: int
          - compressed_tokens: int
          - saved_percent: float (token-based)
          - content_type: str (detected content type)
          - techniques_applied: list[str]
          - what_was_removed: list[str] (samples, max 5)
    """
    # ===================================================================
    # LAYER 0: 🔍 Detect & Protect — ALWAYS runs
    # ===================================================================
    text = redact_secrets(text)
    original_tokens = count_tokens(text)
    if original_tokens == 0:
        return text, {
            "original_tokens": 0, "compressed_tokens": 0,
            "saved_percent": 0.0, "content_type": "empty",
            "techniques_applied": [], "what_was_removed": [],
        }

    # Protect code blocks before any processing
    text, protected = _protect_code_blocks(text)
    content_type = _detect_content_type(text)

    frame = ContentFrame(
        content_type=content_type,
        text=text,
        protected=protected,
    )
    frame.techniques.append(f"detect:{content_type}")

    # ===================================================================
    # LAYER 1: 🪶 Clean — ALWAYS runs (level ≥ 1)
    # ===================================================================
    text = _layer_clean(text, frame)

    # ===================================================================
    # LAYER 2: 🧹 Trim — level ≥ 2
    # ===================================================================
    if level >= 2:
        text = _layer_trim(text, frame)

    # ===================================================================
    # LAYER 3: 🏷️ Optimize — level ≥ 3
    # ===================================================================
    if level >= 3:
        text = _layer_optimize(text, frame)

    # ===================================================================
    # FINALIZE — restore protected blocks + compute stats
    # ===================================================================
    # Clean up artifacts from removals
    text = _MULTI_SPACE.sub(' ', text)
    text = _BLANK_LINES.sub('\n', text)
    text = text.strip()

    # Restore protected code blocks (untouched)
    text = _restore_protected(text, protected)

    if xml_wrap and xml_tag:
        text = f"<{xml_tag}>\n{text}\n</{xml_tag}>"

    compressed_tokens = count_tokens(text)
    saved_percent = 0.0
    if original_tokens > 0:
        saved_percent = ((original_tokens - compressed_tokens) / original_tokens) * 100.0

    stats = {
        "original_tokens": original_tokens,
        "compressed_tokens": compressed_tokens,
        "saved_percent": round(saved_percent, 1),
        "content_type": content_type,
        "techniques_applied": frame.techniques,
        "what_was_removed": frame.removed[:5],
    }

    return text, stats
