"""
text_processor.py — Token-optimized text compression for LLMs.

All techniques are designed to reduce actual LLM token count
(measured with tiktoken cl100k_base), not just character count.
Vowel removal and other character-level tricks are intentionally
excluded because they INCREASE token count.

Level 1 (🪶 Light):     Safe for code — whitespace + blank lines + trailing spaces
Level 2 (🦖 Cruncher):  Prose-focused — stop words, filler phrases, markdown, URLs
Level 3 (💀 Annihilator): Aggressive — comments, timestamps, paths, dedup, boilerplate
Level 4 (☢️ Nuke):       Maximum — bullets→CSV, all punct, short words, bag-of-words
"""

import re
from typing import Tuple

from contextcruncher.security_scanner import redact_secrets

# ---------------------------------------------------------------------------
# Stop words (bilingual DE + EN)
# ---------------------------------------------------------------------------
STOP_WORDS = {
    # German
    "der", "die", "das", "ein", "eine", "einer", "einem", "eines", "und",
    "oder", "ist", "sind", "war", "als", "für", "mit", "von", "zu", "auf",
    "in", "an", "bei", "den", "dem", "des", "mich", "dich", "sich", "wir",
    "ihr", "sie", "es", "nicht", "auch", "so", "wie", "aus", "aber", "wenn",
    "dann", "nur", "noch", "schon", "doch", "daß", "dass", "wird", "kann",
    "hat", "haben", "sein", "seine", "seiner", "seinen", "seinem", "ihrer",
    "ihrem", "ihren", "werden", "wurde", "können", "müssen", "soll", "sollte",
    "hier", "dort", "diese", "dieser", "diesem", "diesen", "jeder", "jede",
    "jedes", "jemand", "etwas", "alle", "alles", "mehr", "sehr", "viel",
    "nach", "über", "unter", "zwischen", "durch", "gegen",

    # English
    "the", "a", "an", "and", "or", "is", "are", "was", "were", "to", "for",
    "with", "from", "at", "in", "on", "by", "of", "me", "you", "him", "her",
    "it", "we", "they", "this", "that", "these", "those", "not", "also", "so",
    "as", "but", "if", "then", "only", "just", "yet", "be", "been", "being",
    "has", "have", "had", "do", "does", "did", "will", "would", "should",
    "could", "can", "may", "might", "shall", "its", "my", "your", "his",
    "our", "their", "which", "who", "whom", "what", "there", "here", "very",
    "more", "most", "some", "any", "each", "every", "all", "both", "such",
    "than", "too", "into", "about", "up", "out", "down", "over", "under",
    "between", "through", "during", "before", "after", "above", "below",
}

# ---------------------------------------------------------------------------
# Filler phrases (entire phrases that add zero information)
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

# ---------------------------------------------------------------------------
# Web/UI boilerplate words (Level 3+)
# ---------------------------------------------------------------------------
UI_BOILERPLATE = {
    "skip", "navigation", "repositories", "packages", "sponsoring",
    "avatar", "followers", "following", "organizations", "footer", "terms",
    "privacy", "security", "status", "community", "docs", "contact",
    "manage", "cookies", "share", "personal", "information", "search",
    "menu", "login", "signup", "sign", "loading", "activity",
    "contributions", "learn", "count", "create", "received",
    "inc", "copyright", "github", "issues", "breadcrumb", "sidebar",
    "widget", "advertisement", "subscribe", "newsletter", "popup",
    "modal", "tooltip", "dropdown", "hamburger", "toggle",
}

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
_MARKDOWN_ITALIC = re.compile(r'\*(.+?)\*')
_MARKDOWN_LINK = re.compile(r'\[([^\]]+)\]\([^\)]+\)')
_MARKDOWN_CODE_BLOCK = re.compile(r'```\w*\n')
_CODE_COMMENT_HASH = re.compile(r'#\s.*$', re.MULTILINE)
_CODE_COMMENT_SLASH = re.compile(r'//\s.*$', re.MULTILINE)
_TIMESTAMP_ISO = re.compile(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[\.\d]*Z?\s*')
_TIMESTAMP_LOG = re.compile(r'\[\d{4}[-/]\d{2}[-/]\d{2}[T ]\d{2}:\d{2}:\d{2}[^\]]*\]\s*')
_FILE_PATH_WIN = re.compile(r'[A-Z]:\\(?:[\w\.\-]+\\){2,}')
_FILE_PATH_UNIX = re.compile(r'(?:/[\w\.\-]+){3,}')
_BULLET_BLOCK = re.compile(r'((?:^[ \t]*[-*•]\s+.+\n?){3,})', re.MULTILINE)
_REPEATED_PUNCT = re.compile(r'([!?.])\1{2,}')
_EMAIL_RE = re.compile(r'\b[\w\.\-]+@[\w\.\-]+\.\w+\b')


def _collapse_bullets(match: re.Match) -> str:
    """Convert a block of 3+ bullet lines into a comma-separated list."""
    block = match.group(0)
    items = []
    for line in block.strip().splitlines():
        item = re.sub(r'^[ \t]*[-*•]\s+', '', line).strip()
        if item:
            items.append(item)
    return ", ".join(items)


def _shorten_path(match: re.Match) -> str:
    """Keep only the last 2 segments of a file path."""
    path = match.group(0)
    sep = "\\" if "\\" in path else "/"
    parts = [p for p in path.replace("\\", "/").split("/") if p]
    if len(parts) > 2:
        return ".../" + "/".join(parts[-2:])
    return path


def minify_for_ai(text: str, level: int = 1,
                  xml_wrap: bool = False, xml_tag: str = "context"
                  ) -> Tuple[str, float]:
    """
    Compress text for token-efficient AI consumption.

    All techniques target actual LLM token reduction (cl100k_base),
    not just character count.

    Level 1 (🪶 Light):      Whitespace normalization — safe for code
    Level 2 (🦖 Cruncher):   Stop words + filler phrases + markdown + URLs
    Level 3 (💀 Annihilator): Comments + timestamps + paths + dedup + boilerplate
    Level 4 (☢️ Nuke):        Bullets→CSV + all punct + short words + bag-of-words

    Returns (compressed_text, saved_percent_chars).
    """
    # ===================================================================
    # ZERO-TRUST: Redact secrets before processing
    # ===================================================================
    text = redact_secrets(text)
    original_len = len(text)
    if original_len == 0:
        return text, 0.0

    # ===================================================================
    # LEVEL 1: 🪶 Light — whitespace normalization (code-safe)
    # ===================================================================
    # Tabs → 2 spaces
    text = text.replace('\t', '  ')
    # Collapse blank lines → single newline
    text = _BLANK_LINES.sub('\n', text)
    # Strip trailing whitespace per line
    text = _TRAILING_WS.sub('', text)
    # Collapse multiple spaces (but not at line start — preserve indentation)
    text = re.sub(r'(?<!^)(?<!\n)[ \t]{2,}', ' ', text, flags=re.MULTILINE)
    # Collapse repeated punctuation  (!!!! → !)
    text = _REPEATED_PUNCT.sub(r'\1', text)

    # ===================================================================
    # LEVEL 2: 🦖 Cruncher — safe for prose, not for code
    # ===================================================================
    if level >= 2:
        # Remove filler phrases (high token savings: ~75% per phrase)
        text_lower = text.lower()
        for phrase in FILLER_PHRASES:
            idx = text_lower.find(phrase)
            while idx != -1:
                text = text[:idx] + text[idx + len(phrase):]
                text_lower = text.lower()
                idx = text_lower.find(phrase)

        # Shorten URLs (saves ~53% tokens each)
        text = _URL_RE.sub('[URL]', text)

        # Remove email addresses
        text = _EMAIL_RE.sub('[EMAIL]', text)

        # Strip markdown formatting (saves ~38% tokens)
        text = _MARKDOWN_CODE_BLOCK.sub('', text)
        text = _MARKDOWN_LINK.sub(r'\1', text)  # [text](url) → text
        text = _MARKDOWN_HEADER.sub('', text)     # ## Header → Header
        text = _MARKDOWN_BOLD.sub(r'\1', text)    # **bold** → bold
        text = _MARKDOWN_ITALIC.sub(r'\1', text)  # *italic* → italic

        # Remove stop words (saves ~22% tokens)
        lines = text.split('\n')
        processed_lines = []
        for line in lines:
            words = line.split()
            filtered = []
            for w in words:
                clean_w = _PUNCT_RE.sub('', w).lower()
                if clean_w not in STOP_WORDS:
                    filtered.append(w)
            processed_lines.append(" ".join(filtered))
        text = "\n".join(processed_lines)

    # ===================================================================
    # LEVEL 3: 💀 Annihilator — aggressive, for web scrapes & logs
    # ===================================================================
    if level >= 3:
        # Remove log timestamps (saves ~85% tokens!)
        text = _TIMESTAMP_ISO.sub('', text)
        text = _TIMESTAMP_LOG.sub('', text)

        # Remove code comments (saves ~55% tokens)
        text = _CODE_COMMENT_HASH.sub('', text)
        text = _CODE_COMMENT_SLASH.sub('', text)

        # Shorten file paths (saves ~67% tokens)
        text = _FILE_PATH_WIN.sub(lambda m: _shorten_path(m), text)
        text = _FILE_PATH_UNIX.sub(lambda m: _shorten_path(m), text)

        # Remove UI boilerplate words
        words = text.split()
        words = [w for w in words if w.lower() not in UI_BOILERPLATE]
        text = " ".join(words)

        # Deduplicate lines (saves ~50% tokens)
        lines = text.split('\n')
        seen = set()
        deduped = []
        for line in lines:
            stripped = line.strip()
            if stripped and stripped not in seen:
                seen.add(stripped)
                deduped.append(line)
            elif not stripped:
                deduped.append(line)
        text = "\n".join(deduped)

    # ===================================================================
    # LEVEL 4: ☢️ Nuke — maximum compression, bag-of-words
    # ===================================================================
    if level >= 4:
        # Collapse bullet lists into comma-separated (saves ~27% tokens)
        text = _BULLET_BLOCK.sub(_collapse_bullets, text)

        # Strip non-ASCII (kills emojis, special chars)
        text = text.encode("ascii", "ignore").decode("ascii")
        # Strip all remaining punctuation
        text = re.sub(r'[^a-zA-Z0-9\s]', ' ', text)

        # Bag-of-words: unique words only, skip short ones
        words = text.split()
        seen = set()
        final_words = []
        for w in words:
            lw = w.lower()
            if len(lw) <= 2 and not w.isdigit():
                continue
            if lw not in seen:
                seen.add(lw)
                final_words.append(w)
        text = " ".join(final_words)

    # ===================================================================
    # Finalize
    # ===================================================================
    # Clean up any double-spaces left by removals
    text = _MULTI_SPACE.sub(' ', text)
    text = _BLANK_LINES.sub('\n', text)
    text = text.strip()

    if xml_wrap and xml_tag:
        text = f"<{xml_tag}>\n{text}\n</{xml_tag}>"

    saved_percent = 0.0
    if original_len > 0:
        saved_percent = ((original_len - len(text)) / original_len) * 100.0

    return text, saved_percent
