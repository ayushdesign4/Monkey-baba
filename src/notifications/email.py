"""Email notification manager for pipeline success and failure alerts."""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
from src.config import (
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USERNAME,
    SMTP_PASSWORD,
    NOTIFICATION_EMAIL,
    GITHUB_RUN_ID,
    GITHUB_REPOSITORY
)
from src.utils.logging import log, log_warn, log_success

# IST is UTC+5:30
IST_TZ = timezone(timedelta(hours=5, minutes=30))

class EmailNotifier:
    def __init__(self):
        self.host = SMTP_HOST
        self.port = SMTP_PORT
        self.user = SMTP_USERNAME
        self.password = SMTP_PASSWORD
        self.recipient = NOTIFICATION_EMAIL

    def is_configured(self) -> bool:
        return bool(self.user and self.password and self.recipient)

    def send_email(self, subject: str, body: str):
        """Send plain text email via SMTP with STARTTLS."""
        if not self.is_configured():
            log_warn("EMAIL", "SMTP credentials or recipient not configured. Notification printed to logs.")
            log("EMAIL", f"Subject: {subject}\n{body}")
            return

        msg = MIMEMultipart()
        msg["From"] = f"Monkey-Baba Bot <{self.user}>"
        msg["To"] = self.recipient
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))

        try:
            with smtplib.SMTP(self.host, self.port, timeout=20) as server:
                server.starttls()
                server.login(self.user, self.password)
                server.send_message(msg)
            log_success("EMAIL", f"Sent alert email to {self.recipient} ('{subject}')")
        except Exception as e:
            log_warn("EMAIL", f"Failed to send email notification: {e}")

    def send_success_email(self, run_record: Dict[str, Any]):
        """Send Short publication success email matching Section 18."""
        now_ist = datetime.now(IST_TZ).strftime("%I:%M %p IST")
        title = run_record.get("title", "Untitled Short")
        url = run_record.get("youtube_url", "https://youtube.com")
        duration = run_record.get("duration_seconds", 45)
        topic = run_record.get("topic", "")
        vid = run_record.get("youtube_video_id", "")
        brain = run_record.get("brain_provider", "Gemini")
        video_p = run_record.get("video_provider", "Agnes")

        subject = "🎬 YouTube Short Uploaded Successfully"
        body = f"""Video Uploaded Successfully

Title: {title}
Status: ✅ Published
YouTube: {url}
Duration: {duration:.0f} sec
Upload Time: {now_ist}
Topic: {topic}
Video ID: {vid}

Pipeline:
{brain.title()} → {video_p.title()} → Editing → YouTube ✅
"""
        self.send_email(subject, body)

    def send_failure_email(self, topic: str, stage: str, error_message: str, run_id: str = None, retries: int = 3):
        """Send pipeline failure notification matching Section 19."""
        run_id = run_id or GITHUB_RUN_ID
        run_url = f"https://github.com/{GITHUB_REPOSITORY}/actions/runs/{run_id}"

        subject = "❌ Monkey-Baba Video Pipeline Failed"
        body = f"""Status: FAILED

Topic: {topic or 'Not Selected'}
Run ID: {run_id}
Failed Stage: {stage}
Error: {error_message[:400]}
Retry Attempts: {retries}

GitHub Actions Run:
{run_url}
"""
        self.send_email(subject, body)
