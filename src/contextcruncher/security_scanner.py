"""
security_scanner.py - Zero-Trust Paranoia Mode for ContextCruncher.

Scans for high-entropy secrets (AWS keys, JWTs, API tokens, SSH keys, UUIDs, private IPs)
and redacts them before compression or MCP transmission.
"""

import re
import logging

logger = logging.getLogger(__name__)

# Compile regexes for performance
SECRETS_PATTERNS = {
    # Match standard AWS AKIA keys
    "[AWS_KEY_REDACTED]": re.compile(r'\bAKIA[0-9A-Z]{16}\b'),
    
    # Match standard JWT tokens (header.payload.signature)
    "[JWT_REDACTED]": re.compile(r'\beyJ[a-zA-Z0-9_-]+\.eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\b'),
    
    # Match Github Classic Tokens
    "[GH_TOKEN_REDACTED]": re.compile(r'\bghp_[a-zA-Z0-9]{36}\b'),
    
    # Match standard UUIDs (like database IDs or API keys)
    "[UUID_REDACTED]": re.compile(r'\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b'),
    
    # Match typical private RSA/Ed25519 blocks
    "[PRIVATE_KEY_REDACTED]": re.compile(r'-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----.*?-----END (?:RSA |OPENSSH )?PRIVATE KEY-----', re.DOTALL),
    
    # Match IPv4 addresses
    "[IP_REDACTED]": re.compile(r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'),
}


def redact_secrets(text: str) -> str:
    """
    Scans the input text for well-known secrets and PII and replaces them
    with [REDACTED] tags. Safe to run on any string.
    """
    if not text:
        return text
        
    redacted_text = text
    for tag, pattern in SECRETS_PATTERNS.items():
        redacted_text = pattern.sub(tag, redacted_text)
        
    return redacted_text
