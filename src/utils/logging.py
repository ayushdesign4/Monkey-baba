"""Structured logger with stage tags and secret masking."""

import sys
import re
from datetime import datetime

# Regex pattern to sanitize potential keys/tokens from logs
_SECRET_PATTERNS = [
    re.compile(r"(AIzaSy[A-Za-z0-9_-]{33})"),
    re.compile(r"(gsk_[A-Za-z0-9]{48,})"),
    re.compile(r"(github_pat_[A-Za-z0-9_]{50,})"),
    re.compile(r"(1//0[A-Za-z0-9_-]{40,})"),
    re.compile(r"([A-Za-z0-9+/]{40,}={0,2})"),
]

def mask_secrets(text: str) -> str:
    """Mask potential secrets in string output."""
    if not isinstance(text, str):
        text = str(text)
    sanitized = text
    for pattern in _SECRET_PATTERNS:
        sanitized = pattern.sub("[REDACTED_SECRET]", sanitized)
    return sanitized

def log(stage: str, message: str, level: str = "INFO"):
    """Format and print structured log with stage tag."""
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    clean_msg = mask_secrets(message)
    formatted = f"[{now}] [{level}] [{stage.upper()}] {clean_msg}"
    try:
        print(formatted, flush=True)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "ascii"
        print(formatted.encode(encoding, errors="replace").decode(encoding), flush=True)

def log_error(stage: str, message: str):
    """Log an error."""
    log(stage, message, level="ERROR")

def log_warn(stage: str, message: str):
    """Log a warning."""
    log(stage, message, level="WARN")

def log_success(stage: str, message: str):
    """Log success."""
    log(stage, message, level="SUCCESS")
