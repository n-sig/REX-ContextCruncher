import pytest
import sys
from pathlib import Path

# Add src to python path for testing
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from contextcruncher.security_scanner import redact_secrets

def test_redact_aws_keys():
    text = "Here is my key AKIA1234567890ABCDEF and some text"
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
