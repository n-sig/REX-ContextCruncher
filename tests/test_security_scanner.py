import pytest
import sys
from pathlib import Path

# Add src to python path for testing
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from contextcruncher.security_scanner import redact_secrets, _shannon_entropy, _looks_like_secret


# ---------------------------------------------------------------------------
# Pass 1 — Known patterns (pre-existing tests, kept unchanged)
# ---------------------------------------------------------------------------

def test_redact_aws_keys():
    text = "Here is my key " + "AKIA" + "1234567890ABCDEF and some text"
    assert redact_secrets(text) == "Here is my key [AWS_KEY_REDACTED] and some text"

def test_redact_jwt():
    text = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    assert "[JWT_REDACTED]" in redact_secrets(text)
    assert "eyJ" not in redact_secrets(text)

def test_redact_github_tokens():
    text = "Deploy with ghp_1234567890ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    assert redact_secrets(text) == "Deploy with [GH_TOKEN_REDACTED]"

def test_redact_ips_and_uuids():
    text = "Server ping 192.168.1.1 ID 123e4567-e89b-12d3-a456-426614174000"
    assert redact_secrets(text) == "Server ping [IP_REDACTED] ID [UUID_REDACTED]"

def test_no_secrets():
    text = "Just normal text 1234 hello"
    assert redact_secrets(text) == text


# ---------------------------------------------------------------------------
# Pass 1 — New patterns
# ---------------------------------------------------------------------------

def test_redact_stripe_live_key():
    text = "Payment config: " + "sk_live_" + "51Mabc1234567890abcdefghijklmnopqrstuvwxyz0123456789ABC"
    result = redact_secrets(text)
    assert "[STRIPE_KEY_REDACTED]" in result
    assert "sk_live_" not in result

def test_redact_stripe_test_key():
    text = "Test mode key: " + "sk_test_" + "51Mabc1234567890abcdefghijklmnopqrstuvwxyz0123456789ABC"
    result = redact_secrets(text)
    assert "[STRIPE_KEY_REDACTED]" in result
    assert "sk_test_" not in result

def test_redact_openai_key_classic():
    # Classic OpenAI key format: sk- + 48 alphanumeric chars
    text = "OPENAI_API_KEY=" + "sk-" + "abc123abc123abc123abc123abc123abc123abc123abc1"
    result = redact_secrets(text)
    assert "[AI_API_KEY_REDACTED]" in result
    assert "sk-abcd" not in result

def test_redact_openai_key_proj():
    text = "key = " + "sk-proj-" + "abc123abc123abc123abc123abc123abc123abc123abc123abc123ab"
    result = redact_secrets(text)
    assert "[AI_API_KEY_REDACTED]" in result

def test_redact_anthropic_key():
    text = "ANTHROPIC_KEY=" + "sk-ant-api03-" + "abc123abc123abc123abc123abc123abc123abc123abc123abc123ab"
    result = redact_secrets(text)
    assert "[AI_API_KEY_REDACTED]" in result
    assert "sk-ant-" not in result

def test_redact_aws_secret_key_context():
    text = "aws_secret_access_key = " + "wJalrXUtn" + "FEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    result = redact_secrets(text)
    assert "[AWS_SECRET_REDACTED]" in result
    assert "wJalrXUtn" not in result

def test_redact_aws_secret_key_env_format():
    text = "AWS_SECRET_ACCESS_KEY=" + "wJalrXUtn" + "FEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    result = redact_secrets(text)
    assert "[AWS_SECRET_REDACTED]" in result

def test_redact_pem_private_key_ec():
    text = "-----BEGIN EC PRIVATE KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA\n-----END EC PRIVATE KEY-----"
    result = redact_secrets(text)
    assert "[PRIVATE_KEY_REDACTED]" in result
    assert "MIIBIjAN" not in result


# ---------------------------------------------------------------------------
# Pass 2 — Shannon-entropy catch-all
# ---------------------------------------------------------------------------

def test_entropy_helper_low_entropy():
    # "aaaa" has entropy 0
    assert _shannon_entropy("aaaa") == 0.0
    # Short natural word
    assert _shannon_entropy("hello") < 3.0

def test_entropy_helper_high_entropy():
    # 40-char random-looking string (like a real secret)
    secret = "wJalrXUtn" + "FEMI7K7MDENGbPxRfiCYEXAMPLEKEY"
    assert _shannon_entropy(secret) > 4.0

def test_looks_like_secret_true():
    # Real-looking 40-char high-entropy token
    assert _looks_like_secret("wJalrXUtn" + "FEMI7K7MDENGbPxRfiCYEXAMPLEKEY") is True

def test_looks_like_secret_false_short():
    assert _looks_like_secret("abc123") is False

def test_looks_like_secret_false_version_string():
    # Version strings contain dots — must NOT be flagged
    assert _looks_like_secret("10.2.3.456789abcdefABCDEF") is False

def test_looks_like_secret_false_natural_language():
    # Normal English sentence fragment — low entropy
    assert _looks_like_secret("thequickbrownfoxjumpsoverthelazydog") is False

def test_entropy_catch_unknown_token():
    # A high-entropy bearer token without a known prefix should be caught by Pass 2
    unknown_token = "Bearer xK9mP2qR7nL4vT8wZ3sA6dF1hJ5cU0eB"
    result = redact_secrets(unknown_token)
    assert "[SECRET_REDACTED]" in result

def test_entropy_does_not_redact_normal_text():
    text = "The configuration file was loaded successfully from disk."
    assert redact_secrets(text) == text

def test_entropy_does_not_redact_code_identifiers():
    # Long but low-entropy class name
    text = "class AbstractUserAuthenticationManagerFactory:"
    result = redact_secrets(text)
    # Should remain unchanged (class name has low char-diversity / entropy)
    assert "[SECRET_REDACTED]" not in result


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_empty_string():
    assert redact_secrets("") == ""

def test_none_like_falsy():
    # redact_secrets returns input unchanged for falsy values
    assert redact_secrets(None) is None  # type: ignore[arg-type]

def test_already_redacted_text_not_double_processed():
    # Text that was already redacted should come through without modification
    text = "Token: [AWS_KEY_REDACTED] was found."
    result = redact_secrets(text)
    assert result == text
    assert result.count("[AWS_KEY_REDACTED]") == 1

def test_multiple_secrets_in_one_string():
    text = (
        "key=" + "AKIA" + "1234567890ABCDEF "
        "stripe=" + "sk_live_" + "51Mabc1234567890abcdefghijklmnopqrstuvwxyz0123456789ABC "
        "uuid=123e4567-e89b-12d3-a456-426614174000"
    )
    result = redact_secrets(text)
    assert "[AWS_KEY_REDACTED]" in result
    assert "[STRIPE_KEY_REDACTED]" in result
    assert "[UUID_REDACTED]" in result
    assert "AKIA" not in result
    assert "sk_live_" not in result
