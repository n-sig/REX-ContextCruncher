"""
security_scanner.py - Zero-Trust Paranoia Mode for ContextCruncher.

Scans for high-entropy secrets (AWS keys, JWTs, API tokens, SSH keys, UUIDs, private IPs)
and redacts them before compression or MCP transmission.

Two-pass strategy:
  Pass 1 — Known-pattern redaction (deterministic, zero false-positives)
  Pass 2 — Shannon-entropy catch-all (catches unknown/prefixless API keys)
"""

import re
import math
import logging
from collections import Counter

logger = logging.getLogger(__name__)

import os
import sys
import json
from pathlib import Path

if sys.platform == "win32":
    _APP_DIR = Path(os.getenv("APPDATA", os.path.expanduser("~"))) / "ContextCruncher"
else:
    _APP_DIR = Path("~/.config/ContextCruncher").expanduser()

# ---------------------------------------------------------------------------
# Pass 1 — Known patterns (compiled once at import time)
# ---------------------------------------------------------------------------

_DEFAULT_SECRETS_PATTERNS: dict[str, re.Pattern] = {
    # AWS Access Key ID  (AKIA + 16 uppercase alphanum)
    "[AWS_KEY_REDACTED]": re.compile(r'\bAKIA[0-9A-Z]{16}\b'),

    # AWS Secret Access Key  (context-aware: must follow the known env/config key name)
    "[AWS_SECRET_REDACTED]": re.compile(
        r'(?i)aws_secret_access_key\s*[=:]\s*["\']?[A-Za-z0-9/+]{40}["\']?'
    ),

    # Stripe API keys  (live and test variants, 24+ chars after prefix)
    # Supports both underscore (sk_live_xxx) and hyphen (sk-live-xxx) formats
    "[STRIPE_KEY_REDACTED]": re.compile(r'\bsk[_-](?:live|test)[_-][a-zA-Z0-9]{20,}\b'),

    # OpenAI / Anthropic / other sk-* API keys
    # Covers: sk-<20+>, sk-proj-<43>, sk-ant-api03-<long>, sk-live-<hex>
    # BUG-09 FIX: Lowered minimum from {32,} to {20,} to catch shorter keys
    "[AI_API_KEY_REDACTED]": re.compile(r'\bsk-(?:proj-|ant-[a-zA-Z0-9]+-|live-|test-)?[a-zA-Z0-9_\-]{20,}\b'),

    # GitHub Personal Access Tokens  (classic ghp_ format)
    "[GH_TOKEN_REDACTED]": re.compile(r'\bghp_[a-zA-Z0-9]{36}\b'),

    # JWT tokens  (header.payload.signature — all three segments required)
    "[JWT_REDACTED]": re.compile(
        r'\beyJ[a-zA-Z0-9_-]+\.eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\b'
    ),

    # Standard UUIDs  (database IDs, correlation IDs, etc.)
    "[UUID_REDACTED]": re.compile(
        r'\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b'
    ),

    # PEM private key blocks  (RSA, OPENSSH, EC, PKCS8, etc.)
    "[PRIVATE_KEY_REDACTED]": re.compile(
        r'-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----.*?-----END (?:[A-Z]+ )?PRIVATE KEY-----',
        re.DOTALL,
    ),

    # IPv4 addresses  (NOTE: may fire on version strings like 1.0.0.1 — acceptable trade-off)
    "[IP_REDACTED]": re.compile(r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'),
}

SECRETS_PATTERNS: dict[str, re.Pattern] = dict(_DEFAULT_SECRETS_PATTERNS)

def _load_custom_patterns():
    try:
        path = _APP_DIR / "custom_patterns.json"
        if path.is_file():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    for tag, pattern_str in data.items():
                        try:
                            SECRETS_PATTERNS[tag] = re.compile(pattern_str)
                        except Exception as e:
                            logger.warning(f"Failed to compile custom pattern {tag}: {e}")
    except Exception:
        pass

_load_custom_patterns()


# ---------------------------------------------------------------------------
# Pass 2 — Shannon-entropy catch-all
# ---------------------------------------------------------------------------

# Bits-per-character threshold above which a token is treated as a secret.
# Real secrets (base64/hex) typically score 4.5–5.5; natural-language tokens
# rarely exceed 4.0.
_ENTROPY_THRESHOLD: float = 4.5

# Minimum token length to bother checking entropy.
_MIN_SECRET_LEN: int = 20

# Character set considered "secret-like" (alphanumeric + base64 extras).
_SECRET_CHARS: frozenset[str] = frozenset(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789"
    "+/=_-"
)

# Minimum fraction of _SECRET_CHARS in a token before we compute entropy.
_SECRET_CHAR_RATIO: float = 0.85

# Tokeniser: splits on whitespace and common punctuation/delimiters.
# Deliberately excludes quotes so that quoted strings are split at the quote.
_TOKEN_RE: re.Pattern = re.compile(r'[^\s"\'`(){}\[\],;:]+')


def _shannon_entropy(s: str) -> float:
    """Return the Shannon entropy (bits per character) of *s*."""
    if not s:
        return 0.0
    counts = Counter(s)
    length = len(s)
    return -sum((c / length) * math.log2(c / length) for c in counts.values())


def _looks_like_secret(token: str) -> bool:
    """
    Heuristic: return True when *token* is long enough, composed mostly of
    alphanumeric/base64 characters, and has high Shannon entropy.

    Additional guards to reduce false positives:
    - Tokens with dots are skipped (version strings, file paths, FQDNs).
    - Purely lowercase tokens are skipped: real secrets almost always contain
      at least one uppercase letter, digit, or special character.  A 35-char
      all-lowercase word (e.g. a pangram or concatenated identifier) can have
      suspiciously high entropy while clearly being natural language.
    """
    if len(token) < _MIN_SECRET_LEN:
        return False
    if "." in token:
        return False  # version strings, file paths, domain names
    # Require character-type diversity — real secrets mix cases, digits, specials
    has_upper = any(c.isupper() for c in token)
    has_digit = any(c.isdigit() for c in token)
    has_special = any(c in "+/=_-" for c in token)
    if not (has_upper or has_digit or has_special):
        return False  # purely lowercase → likely natural language, not a secret
    ratio = sum(1 for c in token if c in _SECRET_CHARS) / len(token)
    if ratio < _SECRET_CHAR_RATIO:
        return False
    return _shannon_entropy(token) >= _ENTROPY_THRESHOLD


def _redact_high_entropy(text: str) -> str:
    """Replace high-entropy tokens in *text* with ``[SECRET_REDACTED]``."""
    def _replace(m: re.Match) -> str:
        return "[SECRET_REDACTED]" if _looks_like_secret(m.group(0)) else m.group(0)

    return _TOKEN_RE.sub(_replace, text)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def redact_secrets(text: str) -> str:
    """
    Scan *text* for secrets and replace them with ``[..._REDACTED]`` tags.

    Safe to call on any string — returns the original value unchanged if
    *text* is falsy.

    Two passes are applied in order:
      1. Known-pattern redaction (Stripe, OpenAI, AWS, JWT, GitHub, …)
      2. High-entropy catch-all for secrets without a recognisable prefix
    """
    if not text:
        return text

    # Pass 1 — deterministic pattern matching
    redacted = text
    for tag, pattern in SECRETS_PATTERNS.items():
        redacted = pattern.sub(tag, redacted)

    # Pass 2 — entropy-based detection (runs on already-cleaned text so
    #           known-pattern placeholders are never double-processed)
    redacted = _redact_high_entropy(redacted)

    return redacted
