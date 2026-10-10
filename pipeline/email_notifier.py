"""SMTP email notification helper for upload success and pipeline failure alerts.

Reuses existing repository secrets:
  SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, NOTIFICATION_EMAIL
"""
from __future__ import annotations

import html
import os
import smtplib
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

# IST timezone: UTC + 5 hours 30 minutes
IST = timezone(timedelta(hours=5, minutes=30))


def _get_smtp_config() -> dict[str, Any] | None:
    host = os.environ.get("SMTP_HOST", "").strip()
    port_str = os.environ.get("SMTP_PORT", "").strip()
    user = os.environ.get("SMTP_USERNAME", "").strip()
    pw = os.environ.get("SMTP_PASSWORD", "").strip()
    recipient = os.environ.get("NOTIFICATION_EMAIL", "").strip()

    if not (host and user and pw and recipient):
        return None

    try:
        port = int(port_str) if port_str else 587
    except ValueError:
        port = 587

    return {
        "host": host,
        "port": port,
        "user": user,
        "password": pw,
        "recipient": recipient,
    }


def _send_smtp(subject: str, text_body: str, html_body: str) -> tuple[bool, str]:
    config = _get_smtp_config()
    if not config:
        return False, "SMTP secrets not configured; skipping email notification"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config["user"]
    msg["To"] = config["recipient"]

    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        # Use SSL for port 465, STARTTLS for port 587 / others
        if config["port"] == 465:
            with smtplib.SMTP_SSL(config["host"], config["port"], timeout=30.0) as server:
                server.login(config["user"], config["password"])
                server.send_message(msg)
        else:
            with smtplib.SMTP(config["host"], config["port"], timeout=30.0) as server:
                server.starttls()
                server.login(config["user"], config["password"])
                server.send_message(msg)
        return True, "Email sent successfully"
    except Exception as exc:
        # Sanitize exception message to ensure no credentials or tokens are logged
        sanitized = str(exc).replace(config["password"], "[REDACTED]")
        return False, f"SMTP send failed: {sanitized}"


def send_upload_success_email(
    *,
    title: str,
    video_id: str,
    summary: str,
    duration_seconds: float,
    run_id: str = "manual",
    run_url: str = "",
    niche: str = "Horror Storytelling",
    stages_passed: list[str] | None = None,
) -> tuple[bool, str]:
    """Send rich upload confirmation email with clickable canonical URL and IST time."""
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    shorts_url = f"https://www.youtube.com/shorts/{video_id}"
    ist_time_str = datetime.now(IST).strftime("%d %b %Y, %I:%M %p IST")

    if not stages_passed:
        stages_passed = ["Script", "Visuals", "Voiceover", "Subtitles", "Render", "Quality Gate", "YouTube Upload"]

    subject = f"🎬 Your YouTube Horror Short Is Uploaded — {title}"

    text_body = f"""🎬 YOUTUBE SHORT UPLOADED SUCCESSFULLY

Title: {title}
Status: Published / Active
Canonical YouTube URL: {video_url}
YouTube Shorts URL: {shorts_url}

Story Summary:
{summary}

Niche: {niche}
Duration: {duration_seconds:.1f} seconds
Upload Time: {ist_time_str}
Video ID: {video_id}
GitHub Actions Run: {run_url or run_id}

Pipeline Stages:
{" | ".join(f"{s} ✓" for s in stages_passed)}
"""

    safe_title = html.escape(title)
    safe_summary = html.escape(summary)
    safe_niche = html.escape(niche)

    html_body = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #121214; color: #e4e4e7; margin: 0; padding: 24px; }}
  .card {{ max-width: 600px; margin: 0 auto; background-color: #1c1c20; border: 1px solid #2e2e34; border-radius: 12px; padding: 28px; box-shadow: 0 8px 24px rgba(0,0,0,0.4); }}
  .header {{ border-bottom: 1px solid #2e2e34; padding-bottom: 16px; margin-bottom: 20px; }}
  .badge {{ background-color: #166534; color: #bbf7d0; font-size: 12px; font-weight: 700; padding: 4px 10px; border-radius: 20px; text-transform: uppercase; letter-spacing: 0.5px; }}
  h1 {{ color: #ffffff; font-size: 20px; margin: 12px 0 6px 0; }}
  .btn {{ display: inline-block; background-color: #dc2626; color: #ffffff !important; text-decoration: none; padding: 12px 24px; border-radius: 8px; font-weight: 600; margin: 16px 0; text-align: center; }}
  .summary-box {{ background-color: #24242a; border-left: 4px solid #dc2626; padding: 14px 16px; border-radius: 4px; margin: 16px 0; color: #d4d4d8; font-style: italic; }}
  .details-table {{ width: 100%; border-collapse: collapse; margin-top: 16px; }}
  .details-table td {{ padding: 8px 4px; border-bottom: 1px solid #27272a; font-size: 14px; }}
  .label {{ color: #a1a1aa; width: 35%; }}
  .value {{ color: #fafafa; font-weight: 500; }}
  .pipeline {{ margin-top: 20px; padding: 12px; background-color: #24242a; border-radius: 6px; font-size: 13px; color: #4ade80; text-align: center; }}
</style>
</head>
<body>
<div class="card">
  <div class="header">
    <span class="badge">Upload Confirmed</span>
    <h1>{safe_title}</h1>
    <div style="color: #a1a1aa; font-size: 13px;">Uploaded at {ist_time_str}</div>
  </div>

  <div style="text-align: center;">
    <a href="{video_url}" class="btn" target="_blank">▶ Watch on YouTube</a>
  </div>

  <div class="summary-box">
    &ldquo;{safe_summary}&rdquo;
  </div>

  <table class="details-table">
    <tr><td class="label">Niche:</td><td class="value">{safe_niche}</td></tr>
    <tr><td class="label">Duration:</td><td class="value">{duration_seconds:.1f}s</td></tr>
    <tr><td class="label">Video ID:</td><td class="value"><code>{video_id}</code></td></tr>
    <tr><td class="label">Canonical Link:</td><td class="value"><a href="{video_url}" style="color: #60a5fa;">{video_url}</a></td></tr>
    <tr><td class="label">Shorts Link:</td><td class="value"><a href="{shorts_url}" style="color: #60a5fa;">{shorts_url}</a></td></tr>
    {f'<tr><td class="label">Actions Run:</td><td class="value"><a href="{run_url}" style="color: #60a5fa;">View Run Log</a></td></tr>' if run_url else ''}
  </table>

  <div class="pipeline">
    ✓ {' ✓ '.join(stages_passed)}
  </div>
</div>
</body>
</html>"""

    return _send_smtp(subject, text_body, html_body)


def send_pipeline_failure_email(
    *,
    failed_stage: str,
    error_summary: str,
    topic_title: str = "",
    run_id: str = "manual",
    run_url: str = "",
    upload_attempted: bool = False,
) -> tuple[bool, str]:
    """Send alert email on pipeline failure."""
    subject = "❌ Monkey-Baba Horror Shorts Pipeline Failed"
    ist_time_str = datetime.now(IST).strftime("%d %b %Y, %I:%M %p IST")

    sanitized_error = error_summary[:400]
    ambiguity_note = "Upload status needs reconciliation" if upload_attempted else "No video upload was performed"

    text_body = f"""❌ MONKEY-BABA PIPELINE FAILED

Failed Stage: {failed_stage}
Timestamp: {ist_time_str}
Topic: {topic_title or 'N/A'}
Upload State: {ambiguity_note}
GitHub Actions Run: {run_url or run_id}

Error Details:
{sanitized_error}
"""

    safe_stage = html.escape(failed_stage)
    safe_topic = html.escape(topic_title or "N/A")
    safe_error = html.escape(sanitized_error)

    html_body = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #121214; color: #e4e4e7; margin: 0; padding: 24px; }}
  .card {{ max-width: 600px; margin: 0 auto; background-color: #1c1c20; border: 1px solid #7f1d1d; border-radius: 12px; padding: 28px; }}
  .badge {{ background-color: #991b1b; color: #fecaca; font-size: 12px; font-weight: 700; padding: 4px 10px; border-radius: 20px; }}
  h1 {{ color: #ffffff; font-size: 20px; margin: 12px 0 6px 0; }}
  .error-box {{ background-color: #261818; border-left: 4px solid #ef4444; padding: 14px; border-radius: 4px; font-family: monospace; font-size: 13px; color: #fca5a5; }}
</style>
</head>
<body>
<div class="card">
  <span class="badge">Pipeline Failed</span>
  <h1>Failure at Stage: {safe_stage}</h1>
  <p style="color: #a1a1aa; font-size: 13px;">Triggered at {ist_time_str}</p>
  <p><strong>Topic:</strong> {safe_topic}</p>
  <p><strong>Upload Status:</strong> {ambiguity_note}</p>
  <div class="error-box">{safe_error}</div>
  {f'<p style="margin-top: 16px;"><a href="{run_url}" style="color: #60a5fa;">View GitHub Actions Workflow Log</a></p>' if run_url else ''}
</div>
</body>
</html>"""

    return _send_smtp(subject, text_body, html_body)
