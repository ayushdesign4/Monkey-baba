"""Central configuration for Monkey-Baba."""

import os
from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"
TOPICS_FILE = DATA_DIR / "topics.json"
UPLOADS_FILE = DATA_DIR / "uploads.json"

# Pipeline Constraints
MIN_SCRIPT_WORDS = 100
TARGET_MIN_DURATION_SEC = 30
TARGET_MAX_DURATION_SEC = 60
MIN_SCENES = 6
MAX_SCENES = 8
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
ASPECT_RATIO = "9:16"

# Provider Settings
PRIMARY_BRAIN_PROVIDER = "gemini"
FALLBACK_BRAIN_PROVIDERS = ["groq", "local"]

PRIMARY_VIDEO_PROVIDER = "agnes"
FALLBACK_VIDEO_PROVIDERS = ["fallback"]

PRIMARY_THUMBNAIL_PROVIDER = "agnes"
FALLBACK_THUMBNAIL_PROVIDERS = ["fallback"]

PRIMARY_TTS_PROVIDER = "edge"
FALLBACK_TTS_PROVIDERS = ["gtts", "offline"]

# API Keys & Credentials
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
AGNES_API_KEY = os.getenv("AGNES_API_KEY", "")

# YouTube OAuth
YOUTUBE_CLIENT_ID = os.getenv("YOUTUBE_CLIENT_ID", "")
YOUTUBE_CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET", "")
YOUTUBE_REFRESH_TOKEN = os.getenv("YOUTUBE_REFRESH_TOKEN", "")

# Email Notifications
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
NOTIFICATION_EMAIL = os.getenv("NOTIFICATION_EMAIL", os.getenv("SMTP_USERNAME", ""))

# GitHub Actions context
GITHUB_RUN_ID = os.getenv("GITHUB_RUN_ID", "local")
GITHUB_REPOSITORY = os.getenv("GITHUB_REPOSITORY", "ayushdesign4/Monkey-baba")
