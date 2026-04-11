import re

STOP_WORDS = {
    # Deutsch
    "der", "die", "das", "ein", "eine", "einer", "einem", "eines", "und", "oder", "ist", "sind", "war", "als", "für",
    "mit", "von", "zu", "auf", "in", "an", "bei", "den", "dem", "des", "mich", "dich", "sich", "wir", "ihr", "sie",
    "es", "nicht", "auch", "so", "wie", "aus", "aber", "wenn", "dann", "nur", "noch", "schon", "doch", "daß", "dass",
    
    # English
    "the", "a", "an", "and", "or", "is", "are", "was", "were", "to", "for", "with", "from", "at", "in", "on", "by",
    "of", "me", "you", "him", "her", "it", "we", "they", "this", "that", "these", "those", "not", "also", "so", "as",
    "but", "if", "then", "only", "just", "yet"
}

# Pre-compiled regex for punctuation stripping in Level 2 (avoids recompilation per word)
_PUNCT_RE = re.compile(r'[.,!?();:]')

# Web/UI boilerplate words to filter out in Level 3+
UI_BOILERPLATE = {
    "skip", "content", "user", "navigation", "overview", "repositories", "projects", 
    "packages", "stars", "sponsoring", "view", "full", "sized", "avatar", "followers", 
    "following", "organizations", "footer", "terms", "privacy", "security", "status", 
    "community", "docs", "contact", "manage", "cookies", "share", "personal", "information",
    "search", "menu", "login", "signup", "sign", "out", "home", "about", "us", "loading",
    "more", "activity", "public", "private", "contributions", "learn", "how", "count", 
    "less", "high", "low", "medium", "create", "pull", "request", "received", "comments",
    "inc", "copyright", "github", "issues"
}


def minify_for_ai(text: str, level: int = 1, xml_wrap: bool = False, xml_tag: str = "context") -> tuple[str, float]:
    """
    Compress text for token-efficient AI consumption.
    
    level 1: Light (whitespace normalization only — safe for code)
    level 2: Token-Cruncher (Light + stop word removal)
    level 3: Annihilator (Level 2 + boilerplate removal + Bag-of-Words deduplication)
    level 4: Experimentell (Level 3 + Vokal-Entfernung — NICHT AI-kompatibel!)
    """
    original_len = len(text)
    if original_len == 0:
        return text, 0.0

    # 1. Basics (Immer Level 1+)
    text = text.replace('\t', '  ')
    text = re.sub(r'\n[ \t]*\n+', '\n', text)
    text = re.sub(r'[ \t]+$', '', text, flags=re.MULTILINE)
    text = re.sub(r'(?<!^)(?<!\n)[ \t]{2,}', ' ', text, flags=re.MULTILINE)
    
    # 2. Token-Cruncher (Level 2+)
    if level >= 2:
        words = text.split()
        filtered = []
        for w in words:
            clean_w = _PUNCT_RE.sub('', w).lower()
            if clean_w not in STOP_WORDS:
                filtered.append(w)
        # Reconstruct as single line. For Level 2+ this is acceptable
        # since it's aggressive text minification where paragraph structure matters less.
        text = " ".join(filtered)
        
    # 3. Extreme Web & Boilerplate Annihilator (Level 3+)
    if level >= 3:
        # Strip non-ASCII (kills emojis, special chars, encoding artifacts)
        text = text.encode("ascii", "ignore").decode("ascii")
        # Keep only letters, digits and whitespace
        text = re.sub(r'[^a-zA-Z0-9\s]', ' ', text)
        
        words = text.split()
        seen = set()
        final_words = []
        for w in words:
            lw = w.lower()
            if lw in UI_BOILERPLATE:
                continue
            # Remove words <= 2 chars (unless they are numbers)
            if len(lw) <= 2 and not w.isdigit():
                continue
            # Unique Words Filter (Bag of Words approach)
            if lw not in seen:
                seen.add(lw)
                final_words.append(w)
                
        text = " ".join(final_words)

    # 4. Extreme Vowel & Space Annihilator (Level 4 - Experimentell)
    if level >= 4:
        # Removes ALL vowels — makes text practically unreadable for AIs
        # (This was the old Level 3 in its most extreme form)
        text = re.sub(r'[aeiouAEIOUäöüÄÖÜ]', '', text)

    text = text.strip()
    
    # Statistics
    new_len = len(text)
    
    if xml_wrap and xml_tag:
        text = f"<{xml_tag}>\n{text}\n</{xml_tag}>"

    saved_percent = 0.0
    if original_len > 0:
        saved_percent = ((original_len - new_len) / original_len) * 100.0
        
    return text, saved_percent
