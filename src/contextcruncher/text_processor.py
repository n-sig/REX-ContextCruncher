"""
text_processor.py — Token-optimized text compression for LLMs.

Single-pass architecture (v3):
  Phase 0: Detect content type + protect code blocks
  Phase 1: Normalize whitespace, quotes, bullets
  Phase 2: Remove filler phrases + stop words
  Phase 3: Synonym replacement + URL/path shortening
  Phase 4: Structural compression (Markdown tables, separators, etc.)
  Phase 5: Window-based dedup + final cleanup

All phases run EVERY time. No more levels — one smart pass.
Code blocks are protected before processing and restored afterward.
"""

import re
from dataclasses import dataclass, field
from typing import Tuple

from contextcruncher.security_scanner import redact_secrets
from contextcruncher.token_counter import count_tokens

# ---------------------------------------------------------------------------
# Stop words — SAFE subset only
#
# ONLY words that carry zero semantic meaning for an LLM.
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
# Matched with word boundaries (\b) to avoid substring matches.
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

# Pre-compile filler phrases with word boundaries
_FILLER_REGEXES = [
    re.compile(r'\b' + re.escape(phrase) + r'\b', re.IGNORECASE)
    for phrase in FILLER_PHRASES
]

# ---------------------------------------------------------------------------
# Synonym table — short technical equivalents
# ---------------------------------------------------------------------------
SYNONYMS = {
    # Long technical terms → standard abbreviations
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
    # More aggressive abbreviations
    "executable": "exe",
    "execution": "exec",
    "management": "mgmt",
    "manager": "mgr",
    "notification": "notif",
    "notifications": "notifs",
    "registration": "reg",
    "connection": "conn",
    "connections": "conns",
    "function": "fn",
    "functions": "fns",
    "variable": "var",
    "variables": "vars",
    "component": "comp",
    "components": "comps",
    "performance": "perf",
    "operation": "op",
    "operations": "ops",
    "package": "pkg",
    "packages": "pkgs",
    "message": "msg",
    "messages": "msgs",
    "response": "resp",
    "request": "req",
    "requests": "reqs",
    "number": "num",
    "numbers": "nums",
    "address": "addr",
    "addresses": "addrs",
    "reference": "ref",
    "references": "refs",
    "argument": "arg",
    "arguments": "args",
    "attribute": "attr",
    "attributes": "attrs",
    "exception": "exc",
    "expression": "expr",
    "description": "desc",
    "permissions": "perms",
    "permission": "perm",
    "certificate": "cert",
    "certificates": "certs",
    "encryption": "enc",
    "middleware": "mw",
    "interface": "iface",
    "interfaces": "ifaces",
    "memory": "mem",
    "object": "obj",
    "objects": "objs",
    "available": "avail",
    "library": "lib",
    "libraries": "libs",
    "following": "below",
    "necessary": "needed",
    "however": "but",
    "therefore": "so",
    "although": "tho",
    "because": "bc",
    "without": "w/o",
    "between": "btwn",
    "through": "thru",
    "different": "diff",
    "including": "incl",
    "contains": "has",
    "containing": "with",
    "provides": "gives",
    "currently": "now",
    "specific": "",
    "individual": "",
    "particular": "",
    "appropriate": "",
    "respective": "",
    "especially": "esp",
    "significant": "major",
    "immediately": "now",
    "completely": "fully",
    "separately": "apart",
    "typically": "usually",
    "whether": "if",
    "multiple": "many",
    "requires": "needs",
    "required": "needed",
    "existing": "current",
    "throughout": "across",
    "consistently": "always",
    "permanently": "forever",
    "recommended": "rec'd",
    "successfully": "ok",
    "originally": "was",
    "within": "in",
    "should be": "→",
    "needs to be": "→",
    "must be": "→",
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

# Code block detection
_FENCED_CODE = re.compile(r'```[\s\S]*?```')
_INLINE_CODE = re.compile(r'`[^`\n]+`')

# ---------------------------------------------------------------------------
# Critical data protection — lines containing these patterns skip stop-word
# removal entirely to prevent accidental destruction of dates, deadlines,
# versions, and numeric data.
# ---------------------------------------------------------------------------
_CRITICAL_LINE_RE = re.compile(
    r'(?:'
    r'\b\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4}\b'             # dates: 15.04.2026
    r'|(?:deadline|frist|bis zum|until|due|fällig)\b'       # deadline keywords
    r'|\b(?:TODO|FIXME|HACK|XXX|WARNING|NOTE)\b'           # dev annotations
    r'|\bv?\d+\.\d+(?:\.\d+)?(?:-\w+)?\b'                 # versions: v1.2.3
    r'|\b\d{1,2}:\d{2}\b'                                  # times: 14:30
    r'|\b(?:Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Sonntag'
    r'|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b'
    r')',
    re.IGNORECASE,
)

# Repeated punctuation
_REPEATED_PUNCT = re.compile(r'([!?.])\1{2,}')

# Markdown structural patterns
_MD_HORIZONTAL_RULE = re.compile(r'^[ \t]*[-*_]{3,}[ \t]*$', re.MULTILINE)
_MD_TABLE_SEP_ROW = re.compile(r'^\|?[ \t]*[-:]+[-| :]*$', re.MULTILINE)
_MD_TABLE_ROW = re.compile(r'^\|(.+)\|[ \t]*$', re.MULTILINE)
_MD_HEADER = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)


# =========================================================================
# DETECT & PROTECT
# =========================================================================

@dataclass
class ContentFrame:
    """Analyzed text with protected regions and metadata."""
    content_type: str
    text: str
    protected: dict = field(default_factory=dict)
    techniques: list = field(default_factory=list)
    removed: list = field(default_factory=list)


def _detect_content_type(text: str) -> str:
    """Heuristic content-type detection."""
    lines = text.strip().splitlines()[:30]
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

    # BUG-13 FIX: Raw source code without ``` fences.
    # Must run AFTER markdown/log/email detection so markdown files containing
    # code snippets are still routed to markdown compression.
    raw_code_type = _detect_raw_code_language(text)
    if raw_code_type:
        return raw_code_type

    return "prose"


# ---------------------------------------------------------------------------
# Raw code detection (BUG-13)
# ---------------------------------------------------------------------------

_PY_SIGNALS = re.compile(
    r'^(?:def |class |import |from \S+ import |@\w|if __name__|async def )',
    re.MULTILINE,
)
_JS_SIGNALS = re.compile(
    r'^(?:(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+\w|'
    r'(?:export\s+)?(?:const|let|var)\s+\w+\s*=|'
    r'import\s+.+\s+from\s+[\'"]|'
    r'require\([\'"])',
    re.MULTILINE,
)
_GENERIC_CODE_SIGNALS = re.compile(
    r'(?:^\s*(?:if|for|while|switch|try|catch|return|throw)\s*\(|'
    r'[;{}]\s*$|'
    r'^\s*(?://|/\*))',
    re.MULTILINE,
)


def _detect_raw_code_language(text: str) -> str:
    """Detect whether *text* is raw (unfenced) source code.

    Returns a content-type label from {"code_python", "code_js", "code_generic"}
    or ``""`` if the text does not look like source code.

    Strong Python signals (def/class/import/@decorator/from X import) and
    strong JS/TS signals (function/const/let/import from/require) count double.
    Generic brace/semicolon/control-flow signals require at least 3 hits plus
    noticeable indentation to avoid false positives on prose that happens to
    contain the odd `if (` or `{` character.
    """
    # Count strong language-specific hits.
    py_hits = len(_PY_SIGNALS.findall(text))
    js_hits = len(_JS_SIGNALS.findall(text))

    # At least one strong Python or JS signal on its own line is almost always
    # source code — e.g. a one-liner like `def foo(): return 1` or a short
    # two-line snippet.  Two or more is essentially conclusive.
    if py_hits >= 1 and py_hits >= js_hits:
        # Require a second corroborating signal: indentation, colon-ended line,
        # or another py_hit.  This blocks prose that mentions "def" once.
        if py_hits >= 2:
            return "code_python"
        if re.search(r'^[ \t]{2,}\S', text, re.MULTILINE):
            return "code_python"
        if re.search(r':\s*$', text, re.MULTILINE):
            return "code_python"

    if js_hits >= 1:
        if js_hits >= 2:
            return "code_js"
        if re.search(r'[;{}]\s*$', text, re.MULTILINE):
            return "code_js"

    # Generic code heuristic — needs several signals AND indentation.
    gen_hits = len(_GENERIC_CODE_SIGNALS.findall(text))
    has_indent = bool(re.search(r'^[ \t]{2,}\S', text, re.MULTILINE))
    if gen_hits >= 3 and has_indent:
        return "code_generic"

    return ""


def _is_real_code(block_content: str) -> bool:
    """Heuristic: does a fenced code block contain actual source code?

    Returns True for programming language code (Python, JS, etc.)
    Returns False for directory trees, simple command lists, config snippets,
    or plain text that just happens to be in a fenced block.
    """
    lines = [l for l in block_content.strip().splitlines() if l.strip()]
    if not lines:
        return False

    # Check for language hint on the opening fence
    first_line = lines[0].strip().lower()

    # Tree structure indicators
    tree_chars = sum(1 for l in lines if any(c in l for c in '├└│└─'))
    if tree_chars >= 2:
        return False

    # Very short blocks (≤ 3 non-empty lines) — likely command examples
    if len(lines) <= 3:
        return False

    # Code indicators: assignments, function defs, imports, braces, semicolons
    code_indicators = sum(1 for l in lines if (
        re.search(r'(def |class |import |from .+ import |function |const |let |var |return )', l)
        or re.search(r'[{};]$', l.strip())
        or re.search(r'^\s*(if|for|while|try|except|catch)\b', l)
    ))
    if code_indicators >= 2:
        return True

    # If it looks like a plain list of commands (lines starting with #, $, or simple words)
    command_lines = sum(1 for l in lines if re.match(r'^\s*(#|[$>]|\w+\s)', l))
    if command_lines >= len(lines) * 0.7:
        return False

    # Default: protect if we're unsure and it's long enough
    return len(lines) > 5


def _compress_tree_block(content: str) -> str:
    """Compress a directory-tree code block: strip tree chars and inline comments."""
    lines = content.splitlines()
    result = []
    for line in lines:
        # Strip tree-drawing characters
        compressed = re.sub(r'[├└│]', '', line)
        compressed = re.sub(r'──\s*', ' ', compressed)
        # Strip inline comments (# ... at end of line)
        compressed = re.sub(r'\s{2,}#\s+.*$', '', compressed)
        # Collapse padding
        compressed = re.sub(r'^[ \t]+', ' ', compressed)
        compressed = compressed.rstrip()
        if compressed.strip():
            result.append(compressed)
    return '\n'.join(result)


def _compress_command_block(content: str) -> str:
    """Compress a shell command block: remove comment-only lines, strip excess whitespace."""
    lines = content.splitlines()
    result = []
    for line in lines:
        stripped = line.strip()
        # Skip pure comment lines
        if stripped.startswith('#') and not stripped.startswith('#!'):
            continue
        # Skip empty lines
        if not stripped:
            continue
        result.append(stripped)
    return '\n'.join(result)


def _protect_code_blocks(text: str) -> tuple:
    """Process fenced code blocks intelligently.

    Real source code (Python, JS, etc.) is protected from compression.
    Non-code blocks (directory trees, command lists) are compressed
    in-place and NOT protected, so they benefit from token savings.
    """
    protected = {}
    counter = [0]

    def _process_block(match):
        full = match.group(0)
        # Extract content between ``` fences
        inner = full.strip()
        if inner.startswith('```'):
            # Get the language hint (if any) and content
            first_newline = inner.find('\n')
            if first_newline == -1:
                return full  # empty block
            lang_hint = inner[3:first_newline].strip().lower()
            content = inner[first_newline + 1:]
            if content.endswith('```'):
                content = content[:-3].rstrip()

            # If language hint says it's a programming language, always protect
            code_langs = {'python', 'py', 'javascript', 'js', 'typescript', 'ts',
                          'java', 'c', 'cpp', 'c++', 'csharp', 'cs', 'go', 'rust',
                          'ruby', 'rb', 'php', 'swift', 'kotlin', 'scala', 'r',
                          'sql', 'lua', 'perl', 'haskell', 'html', 'css', 'jsx',
                          'tsx', 'vue', 'svelte'}
            if lang_hint in code_langs:
                key = f"__PROTECTED_{counter[0]}__"
                protected[key] = full
                counter[0] += 1
                return key

            # Check for tree structure
            tree_chars = sum(1 for l in content.splitlines() if any(c in l for c in '├└│'))
            if tree_chars >= 2:
                compressed = _compress_tree_block(content)
                return f"```\n{compressed}\n```"

            # Check for shell/command blocks
            if lang_hint in ('bash', 'sh', 'shell', 'cmd', 'powershell', 'ps1', 'zsh'):
                compressed = _compress_command_block(content)
                return f"```\n{compressed}\n```"

            # For blocks with no language hint, use heuristic
            if _is_real_code(content):
                key = f"__PROTECTED_{counter[0]}__"
                protected[key] = full
                counter[0] += 1
                return key

            # Non-code block: compress command-style content
            compressed = _compress_command_block(content)
            if compressed != content:
                return f"```\n{compressed}\n```"

        # Default: protect
        key = f"__PROTECTED_{counter[0]}__"
        protected[key] = full
        counter[0] += 1
        return key

    text = _FENCED_CODE.sub(_process_block, text)

    return text, protected


def _restore_protected(text: str, protected: dict) -> str:
    """Restore protected code blocks from placeholders."""
    for key, original in protected.items():
        text = text.replace(key, original)
    return text


# =========================================================================
# PHASE 1 — Normalize
# =========================================================================

def _phase_normalize(text: str, frame: ContentFrame) -> str:
    """Whitespace normalization + character cleanup."""
    is_code = frame.content_type.startswith("code_")

    # Smart quotes → ASCII (skip for code — source strings should stay verbatim)
    if not is_code:
        for fancy, plain in _SMART_QUOTES:
            text = text.replace(fancy, plain)

    # Fancy bullets → ASCII dash (prose only — unlikely in code)
    if not is_code:
        text = _FANCY_BULLETS.sub('- ', text)

    # Tabs → 2 spaces (applies to both — tabs are rarely meaningful for AI)
    text = text.replace('\t', '  ')
    # Strip trailing whitespace per line
    text = _TRAILING_WS.sub('', text)
    # Collapse multiple spaces.  For code, only collapse AFTER non-whitespace
    # so leading indentation survives intact.  For prose, the old behavior
    # (line-start-aware lookbehind) is preserved for backward compatibility.
    if is_code:
        text = re.sub(r'(?<=\S)[ \t]{2,}', ' ', text)
    else:
        text = re.sub(r'(?<!^)(?<!\n)[ \t]{2,}', ' ', text, flags=re.MULTILINE)
    # Collapse repeated punctuation (!!!! → !) — skip for code
    if not is_code:
        text = _REPEATED_PUNCT.sub(r'\1', text)

    frame.techniques.append("normalize")
    return text


# =========================================================================
# PHASE 2 — Remove filler + stop words
# =========================================================================

def _phase_trim(text: str, frame: ContentFrame) -> str:
    """Remove filler phrases and stop words from prose lines."""
    removed_samples = []

    # Remove filler phrases
    for regex in _FILLER_REGEXES:
        match = regex.search(text)
        if match and len(removed_samples) < 5:
            removed_samples.append(f"Filler: '{match.group(0)}'")
        text = regex.sub('', text)

    # Remove stop words line-by-line (skip code/config-looking lines)
    lines = text.split('\n')
    processed_lines = []
    for line in lines:
        stripped = line.strip()
        # Skip protected placeholders, shebangs, comments, table rows, headers
        if (stripped.startswith(('__PROTECTED_', '#!', '//', '/*', '*', '|'))
                or stripped.startswith('#')):
            processed_lines.append(line)
            continue
        # Skip lines containing critical data (dates, deadlines, TODOs, versions)
        if _CRITICAL_LINE_RE.search(stripped):
            processed_lines.append(line)
            continue
        words = line.split()
        filtered = [w for w in words if _PUNCT_RE.sub('', w).lower() not in STOP_WORDS]
        processed_lines.append(" ".join(filtered))
    text = "\n".join(processed_lines)

    if removed_samples:
        frame.removed.extend(removed_samples)
    frame.techniques.append("filler_trim")
    return text


# =========================================================================
# PHASE 3 — Synonym replacement + URL/path cleanup
# =========================================================================

def _phase_optimize(text: str, frame: ContentFrame) -> str:
    """Synonym replacement, URL shortening, path compression."""
    # Synonym replacement
    synonym_count = 0
    for regex, repl in _SYNONYM_REGEXES:
        text, n = regex.subn(repl, text)
        synonym_count += n
    for regex in _SYNONYM_DROP:
        text, n = regex.subn('', text)
        synonym_count += n
    if synonym_count:
        frame.techniques.append(f"synonyms:{synonym_count}")

    # Shorten URLs
    url_count = len(_URL_RE.findall(text))
    if url_count:
        text = _URL_RE.sub('[URL]', text)
        frame.techniques.append(f"urls:{url_count}")

    # URL tracking parameter cleanup
    text = _URL_TRACKING.sub('', text)

    # Replace email addresses
    email_count = len(_EMAIL_RE.findall(text))
    if email_count:
        text = _EMAIL_RE.sub('[EMAIL]', text)

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
        frame.techniques.append(f"paths:{path_count}")

    return text


# =========================================================================
# PHASE 4 — Telegraphic rewriting (verbose phrases → compact forms)
# =========================================================================

# Multi-word patterns that can be safely compressed.
# Sorted longest-first so greedy matching works.
# Format: (pattern_regex, replacement)
_VERBOSE_PATTERNS: list[tuple[re.Pattern, str]] = []

_VERBOSE_RAW = [
    # Fluff verbs / hedging
    (r"\bis able to\b", "can"),
    (r"\bare able to\b", "can"),
    (r"\bin order to\b", "to"),
    (r"\bfor the purpose of\b", "to"),
    (r"\bwith the aim of\b", "to"),
    (r"\bso as to\b", "to"),
    (r"\bmake sure\b", "ensure"),
    (r"\bmake certain\b", "ensure"),
    (r"\btake advantage of\b", "use"),
    (r"\btake into account\b", "consider"),
    (r"\btakes into account\b", "considers"),
    (r"\bgive rise to\b", "cause"),
    (r"\bcome up with\b", "create"),
    (r"\bcarry out\b", "run"),
    (r"\bcarried out\b", "ran"),
    (r"\bset up\b", "setup"),
    (r"\bput together\b", "assemble"),
    (r"\bget rid of\b", "remove"),
    (r"\bend up\b", "become"),

    # Verbose descriptions → compact
    (r"\ba large number of\b", "many"),
    (r"\ba small number of\b", "few"),
    (r"\ba wide range of\b", "many"),
    (r"\ba variety of\b", "various"),
    (r"\bon a regular basis\b", "regularly"),
    (r"\bat the same time\b", "simultaneously"),
    (r"\bat a later time\b", "later"),
    (r"\bat a later date\b", "later"),
    (r"\bin the majority of cases\b", "usually"),
    (r"\bin most cases\b", "usually"),
    (r"\bin some cases\b", "sometimes"),
    (r"\bin many cases\b", "often"),
    (r"\bin the case of\b", "for"),
    (r"\bin the context of\b", "in"),
    (r"\bin the absence of\b", "without"),
    (r"\bin the presence of\b", "with"),
    (r"\bin conjunction with\b", "with"),
    (r"\bin accordance with\b", "per"),
    (r"\bin relation to\b", "about"),
    (r"\bin close proximity to\b", "near"),
    (r"\bprior to\b", "before"),
    (r"\bsubsequent to\b", "after"),
    (r"\bwith the exception of\b", "except"),
    (r"\bfor the sake of\b", "for"),
    (r"\bby means of\b", "via"),
    (r"\bby way of\b", "via"),
    (r"\bas a consequence of\b", "bc"),
    (r"\bon the basis of\b", "based on"),
    (r"\bon behalf of\b", "for"),
    (r"\bup to this point\b", "so far"),
    (r"\bat the present time\b", "now"),
    (r"\bat the current time\b", "now"),
    (r"\bas of right now\b", "now"),
    (r"\bfor the time being\b", "now"),
    (r"\buntil such time as\b", "until"),
    (r"\bregardless of whether\b", "whether"),
    (r"\birrespective of\b", "regardless"),

    # Tech-doc verbose → compact
    (r"\bthe ability to\b", "can"),
    (r"\bhas the ability to\b", "can"),
    (r"\bprovides the ability to\b", "enables"),
    (r"\bthe fact that\b", "that"),
    (r"\bdue to the fact that\b", "bc"),
    (r"\bin spite of the fact that\b", "despite"),
    (r"\bregardless of the fact that\b", "even tho"),
    (r"\bit is possible to\b", "can"),
    (r"\bit is necessary to\b", "must"),
    (r"\bit is recommended to\b", "should"),
    (r"\bit is important to\b", "should"),
    (r"\bit is essential to\b", "must"),
    (r"\bthere is a need to\b", "must"),
    (r"\bthere is no need to\b", "needn't"),
    (r"\bwhen it comes to\b", "for"),
    (r"\bas far as .{1,20} (?:is|are) concerned\b", "about"),
    (r"\bthe purpose of .{1,30} is to\b", ""),
    (r"\bin such a way that\b", "so"),
    (r"\bto a large extent\b", "mostly"),
    (r"\bto a certain extent\b", "partly"),
    (r"\bto some extent\b", "partly"),
    (r"\bon the other hand\b", "but"),
    (r"\bas opposed to\b", "vs"),
    (r"\bas compared to\b", "vs"),
    (r"\bin comparison to\b", "vs"),
    (r"\bas long as\b", "if"),
    (r"\bprovided that\b", "if"),
    (r"\bin the event that\b", "if"),
    (r"\bin the event of\b", "if"),
    (r"\bgiven that\b", "since"),

    # Sentence starters that add nothing
    (r"^(?:Please )?(?:note|be aware|keep in mind) that ", ""),
    (r"^It (?:should|must|is important to) be (?:noted|mentioned|emphasized) that ", ""),
    (r"^It is worth (?:noting|mentioning|pointing out) that ", ""),
    (r"^(?:As|Like) (?:we )?(?:mentioned|discussed|noted|described|stated) (?:above|earlier|before|previously),? ?", ""),

    # Passive voice → active (common patterns)
    (r"\bcan be used to\b", "can"),
    (r"\bis used to\b", "does"),
    (r"\bare used to\b", "do"),
    (r"\bcan be found in\b", "is in"),
    (r"\bcan be seen in\b", "is in"),
    (r"\bshould be configured\b", "configure"),
    (r"\bmust be configured\b", "configure"),
    (r"\bneeds to be configured\b", "configure"),
    (r"\bshould be installed\b", "install"),
    (r"\bmust be installed\b", "install"),
    (r"\bneeds to be installed\b", "install"),
    (r"\bshould be updated\b", "update"),
    (r"\bmust be updated\b", "update"),
    (r"\bshould be set to\b", "set to"),
    (r"\bmust be set to\b", "set to"),

    # German verbose patterns
    (r"\bes handelt sich um\b", "="),
    (r"\bim Rahmen von\b", "bei"),
    (r"\bim Zusammenhang mit\b", "bei"),
    (r"\bauf der Grundlage von\b", "basierend auf"),
    (r"\bunter Berücksichtigung von\b", "mit"),
    (r"\bmit dem Ziel\b", "um"),
    (r"\bzu dem Zweck\b", "um"),
    (r"\bin Bezug auf\b", "bzgl"),
    (r"\bim Hinblick auf\b", "bzgl"),
    (r"\bsowohl .{1,20} als auch\b", "und"),
    (r"\bnicht nur .{1,20} sondern auch\b", "und"),
    (r"\bauf Grund von\b", "wegen"),
    (r"\baufgrund von\b", "wegen"),
    (r"\baus diesem Grund\b", "daher"),
    (r"\bauf diese Weise\b", "so"),
]

# Sort longest first, compile all
_VERBOSE_RAW.sort(key=lambda x: len(x[0]), reverse=True)
_VERBOSE_PATTERNS = [
    (re.compile(pat, re.IGNORECASE | re.MULTILINE), repl)
    for pat, repl in _VERBOSE_RAW
]

# Additional stop words for telegraphic mode — ONLY applied to long lines (>8 words).
# Removes prepositions and conjunctions that an LLM can infer from context.
_EXTRA_STOP_WORDS = {
    "then", "there", "here", "where", "while",
    "each", "every", "both", "some",
    "such", "same", "other", "own",
    "shall",
    "only", "even", "still",
    "yet",
    # Keep: of, to, and, for, with, from, not, if, but, or, no, by, on, at, can, will
}


def _phase_telegraphic(text: str, frame: ContentFrame) -> str:
    """Rewrite verbose phrases into telegraphic form.

    This is the most aggressive compression phase — it rewrites multi-word
    patterns into compact equivalents while preserving semantic meaning.
    """
    count = 0
    for regex, repl in _VERBOSE_PATTERNS:
        text, n = regex.subn(repl, text)
        count += n

    if count:
        frame.techniques.append(f"telegraphic:{count}")

    # Second-pass stop word removal (more aggressive now that phrases are compacted)
    lines = text.split('\n')
    processed = []
    for line in lines:
        stripped = line.strip()
        # Skip protected, table rows, code-looking lines
        if (stripped.startswith(('__PROTECTED_', '|', '```'))
                or not stripped):
            processed.append(line)
            continue
        # Skip lines with critical data (dates, deadlines, TODOs, versions)
        if _CRITICAL_LINE_RE.search(stripped):
            processed.append(line)
            continue
        words = line.split()
        # Only apply to LONG lines (short lines need every word)
        if len(words) > 8:
            filtered = [w for w in words
                        if _PUNCT_RE.sub('', w).lower() not in _EXTRA_STOP_WORDS
                        or len(w) <= 1]  # keep single chars like "=" "+"
            processed.append(" ".join(filtered))
        else:
            processed.append(line)
    text = "\n".join(processed)

    # Remove leftover double spaces and leading/trailing spaces on lines
    text = re.sub(r' {2,}', ' ', text)
    text = re.sub(r'^ +| +$', '', text, flags=re.MULTILINE)

    frame.techniques.append("extra_stop")
    return text


# =========================================================================
# PHASE 5 — Structural compression (tables, separators, formatting)
# =========================================================================

def _compact_table(lines: list[str]) -> list[str]:
    """Compact a Markdown table: strip padding, remove separator row,
    and collapse cells into minimal form.

    Input lines should all belong to one contiguous table block.
    Returns compacted lines.
    """
    out = []
    for line in lines:
        # Skip separator rows (|---|---|)
        if re.match(r'^\|?[ \t]*[-:]+[-| :]*$', line):
            continue
        # Compact cell padding: | foo | bar | → |foo|bar|
        if '|' in line:
            cells = line.split('|')
            # Strip each cell, filter empty leading/trailing from split
            compacted = '|'.join(c.strip() for c in cells)
            # Ensure it starts and ends with |
            if not compacted.startswith('|'):
                compacted = '|' + compacted
            if not compacted.endswith('|'):
                compacted = compacted + '|'
            # Remove double || from empty cells at edges
            while '||' in compacted and compacted != '||':
                compacted = compacted.replace('||', '|')
            out.append(compacted)
        else:
            out.append(line)
    return out


def _phase_structural(text: str, frame: ContentFrame) -> str:
    """Compress structural elements: tables, separators, markdown formatting."""

    # --- Horizontal rules → remove entirely ---
    hr_count = len(_MD_HORIZONTAL_RULE.findall(text))
    if hr_count:
        text = _MD_HORIZONTAL_RULE.sub('', text)
        frame.techniques.append(f"hr_removal:{hr_count}")

    # --- Strip inline code backticks: `word` → word ---
    inline_count = len(_INLINE_CODE.findall(text))
    if inline_count:
        text = _INLINE_CODE.sub(lambda m: m.group(0)[1:-1], text)
        frame.techniques.append(f"inline_code_strip:{inline_count}")

    # --- Markdown formatting: strip bold/italic/link syntax ---
    text = _MARKDOWN_LINK.sub(r'\1', text)       # [text](url) → text
    text = _MARKDOWN_BOLD.sub(r'\1', text)        # **bold** → bold
    text = _MARKDOWN_ITALIC.sub(r'\1', text)      # *italic* → italic

    # --- Compress Markdown headers: "## Title" → "Title:" ---
    def _header_to_label(m: re.Match) -> str:
        return m.group(2).rstrip() + ":"
    header_count = len(_MD_HEADER.findall(text))
    if header_count:
        text = _MD_HEADER.sub(_header_to_label, text)
        frame.techniques.append(f"header_compact:{header_count}")

    # --- Compress Markdown list items: "- **Label:** text" → "Label: text" ---
    # Strips leading "- " from simple bullet lists
    text = re.sub(r'^[ \t]*[-*+][ \t]+', '', text, flags=re.MULTILINE)
    frame.techniques.append("list_compact")

    # --- Compact Markdown tables ---
    lines = text.split('\n')
    result_lines = []
    table_buffer: list[str] = []
    in_table = False
    tables_compacted = 0

    for line in lines:
        stripped = line.strip()
        is_table_line = stripped.startswith('|') and stripped.endswith('|')
        is_sep_line = bool(re.match(r'^\|?[ \t]*[-:]+[-| :]*$', stripped))

        if is_table_line or is_sep_line:
            if not in_table:
                in_table = True
                table_buffer = []
            table_buffer.append(line)
        else:
            if in_table:
                # Flush table
                compacted = _compact_table(table_buffer)
                result_lines.extend(compacted)
                tables_compacted += 1
                in_table = False
                table_buffer = []
            result_lines.append(line)

    # Flush trailing table
    if in_table and table_buffer:
        compacted = _compact_table(table_buffer)
        result_lines.extend(compacted)
        tables_compacted += 1

    if tables_compacted:
        frame.techniques.append(f"table_compact:{tables_compacted}")

    text = "\n".join(result_lines)
    return text


# =========================================================================
# PHASE 6 — Dedup + final cleanup
# =========================================================================

def _phase_dedup(text: str, frame: ContentFrame) -> str:
    """Window-based consecutive line dedup + blank line collapse."""
    lines = text.split('\n')
    if len(lines) > 5:
        deduped = []
        window: list[str] = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                # Keep one blank line max (will be cleaned later)
                if deduped and deduped[-1].strip() == '':
                    continue
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
        frame.techniques.append("dedup")

    return text


# =========================================================================
# PUBLIC API
# =========================================================================

def minify_for_ai(text: str, level: int = 1,
                  xml_wrap: bool = False, xml_tag: str = "context"
                  ) -> Tuple[str, dict]:
    """Compress text for token-efficient AI consumption.

    Single-pass architecture — all techniques run every time for maximum
    compression while preserving semantic content.

    The `level` parameter is accepted for backward compatibility but
    is ignored — all phases always run.

    Args:
        text: The text to compress.
        level: Ignored (kept for backward compat). All phases always run.
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
    # === DETECT & PROTECT ===
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

    # === PHASES ===
    # BUG-13 FIX: raw code detected from _detect_content_type short-circuits
    # the destructive prose-only phases (trim / optimize / telegraphic).  These
    # phases use line.split() + " ".join() which obliterates leading
    # indentation, and the stop-word filter drops identifiers like `a` or `b`
    # that are real variable names.  For code we only run whitespace
    # normalization and dedup — everything else would break syntax.
    is_code = content_type.startswith("code_")

    text = _phase_normalize(text, frame)
    if not is_code:
        text = _phase_trim(text, frame)
        text = _phase_optimize(text, frame)
        text = _phase_telegraphic(text, frame)
        text = _phase_structural(text, frame)
    else:
        frame.techniques.append("code_safe_mode")
    text = _phase_dedup(text, frame)

    # === FINALIZE ===
    # BUG-13 FIX: For code content, _MULTI_SPACE would collapse leading
    # indentation.  Use a variant that preserves leading whitespace per line.
    if is_code:
        # Collapse runs of 2+ spaces to 1, but only AFTER non-whitespace on the
        # same line — leaves `    def foo():` indentation intact.
        text = re.sub(r'(?<=\S) {2,}', ' ', text)
    else:
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
