import pytest
from pipeline.email_notifier import send_upload_success_email, send_pipeline_failure_email


def test_send_email_when_smtp_unconfigured(monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SMTP_USERNAME", raising=False)
    
    ok, msg = send_upload_success_email(
        title="Midnight Whisper",
        video_id="dQw4w9WgXcQ",
        summary="A radio turns on by itself.",
        duration_seconds=45.0,
    )
    assert ok is False
    assert "SMTP secrets not configured" in msg


def test_send_failure_email_when_smtp_unconfigured(monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    
    ok, msg = send_pipeline_failure_email(
        failed_stage="Quality Gate",
        error_summary="Duration 12s is below 25s",
    )
    assert ok is False
    assert "SMTP secrets not configured" in msg
