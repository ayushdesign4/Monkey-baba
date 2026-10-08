# Monkey-Baba 🐵🎬
### Autonomous AI YouTube Shorts Production System

[![Daily Autonomous YouTube Short](https://github.com/ayushdesign4/Monkey-baba/actions/workflows/daily_youtube.yml/badge.svg)](https://github.com/ayushdesign4/Monkey-baba/actions/workflows/daily_youtube.yml)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10-blue.svg)](https://www.python.org/)

**Monkey-Baba** is a production-grade, unattended system designed to generate, direct, edit, voice, thumbnail, and publish high-retention vertical YouTube Shorts (9:16) automatically every day at **3:00 AM IST** without requiring human intervention or keeping a personal laptop running.

---

## 🏗 Architecture & Provider Hierarchy

```text
                         ┌───────────────────────────┐
                         │       GITHUB ACTIONS      │
                         │    03:00 AM IST (Daily)   │
                         └─────────────┬─────────────┘
                                       │
                                       ▼
                         ┌───────────────────────────┐
                         │   CENTRAL ORCHESTRATOR    │
                         └─────────────┬─────────────┘
                                       │
              ┌────────────────────────┼────────────────────────┐
              │                        │                        │
              ▼                        ▼                        ▼
        ┌───────────┐            ┌───────────┐            ┌───────────┐
        │   BRAIN   │            │   VIDEO   │            │ THUMBNAIL │
        └─────┬─────┘            └─────┬─────┘            └─────┬─────┘
              │                        │                        │
        Gemini 3.8 Flash           Agnes Video              Agnes Image
              │                        │                        │
           fallback                 fallback                 fallback
              │                        │                        │
         Groq (Llama)              Procedural               Cinematic
              │                   Video Engine            Poster Engine
         Backup LLM
              │
              └──────────────┬───────────────┐
                             ▼               │
                      Script (>100w)         │
                      6–8 Scenes             │
                             │               │
                             ▼               │
                       Mute Clip Audio       │
                             │               │
                             ▼               │
                         Merge Clips         │
                             │               │
                             ▼               │
                        TTS Narration        │
                             │               │
                             ▼               │
                      30–60s Final MP4       │
                             │               │
                             └───────┬───────┘
                                     ▼
                              YouTube Upload
                                     │
                         ┌───────────┴───────────┐
                         │                       │
                       SUCCESS                 FAILURE
                         │                       │
                         ▼                       ▼
                   Success Email            Failure Email
```

---

## 📋 Required GitHub Repository Secrets

Configure the following secrets in your repository settings (**Settings** $\rightarrow$ **Secrets and variables** $\rightarrow$ **Actions**):

| Secret Name | Description | Required? |
|-------------|-------------|-----------|
| `GEMINI_API_KEY` | Google Gemini API Key | Primary Brain |
| `GROQ_API_KEY` | Groq Cloud API Key | Fallback #1 Brain |
| `AGNES_API_KEY` | Agnes AI Video & Image Key | Primary Video & Thumbnails |
| `BACKUP_LLM_API_KEY` | Optional OpenAI or compatible key | Fallback #2 Brain |
| `YOUTUBE_CLIENT_ID` | Google Cloud OAuth Client ID | YouTube Upload |
| `YOUTUBE_CLIENT_SECRET`| Google Cloud OAuth Client Secret | YouTube Upload |
| `YOUTUBE_REFRESH_TOKEN`| OAuth2 Refresh Token with YouTube scope | YouTube Upload |
| `SMTP_HOST` | SMTP Host (e.g., `smtp.gmail.com`) | Email Notifications |
| `SMTP_PORT` | SMTP Port (default: `587`) | Email Notifications |
| `SMTP_USERNAME` | SMTP Account Email | Email Notifications |
| `SMTP_PASSWORD` | SMTP App Password | Email Notifications |
| `NOTIFICATION_EMAIL` | Destination email for publication alerts | Email Notifications |

---

## ⚡ Local Usage & Testing

### 1. Dry Run (Full Simulation)
Runs topic ideation, script generation, scene direction, silent video creation, TTS synchronization, thumbnail building, metadata generation, and simulated upload without spending API credits:
```bash
python3 main.py --dry-run
```

### 2. Manual Topic Override
```bash
python3 main.py --topic "The Lost Pyramid Under the Antarctic Ice Sheet"
```

### 3. Check Channel & Run Status
```bash
python3 main.py --status
```

### 4. Run Unit Tests
```bash
python3 -m unittest discover tests
```

---

## 📂 Run Artifacts Directory

Each run creates an isolated directory under `output/YYYY-MM-DD_<run_id>/`:
```text
output/2026-10-08_20261008-030000/
├── topic.json          # Selected topic with duplicate clearance
├── script.json         # Spoken narration (>100 words) & scene cuts
├── script.txt          # Plaintext narration
├── direction.json      # Character & Environment bibles
├── scenes.json         # 6–8 directed visual scene prompts
├── clips/              # Individual generated MP4 clips (audio muted)
│   ├── scene_001.mp4
│   └── ...
├── reel.mp4            # Merged silent video
├── narration.mp3       # Synced studio TTS voiceover
├── thumb.jpg           # 9:16 high-CTR thumbnail
├── final.mp4           # 30–60s finalized vertical YouTube Short
├── metadata.json       # Title (#Shorts), Description, Tags
├── upload.json         # YouTube upload response & URL
└── run.json            # Telemetry & provider execution metrics
```

---

## 🛡️ Autonomous Fail-Safe & Quality Guarantees

1. **Word Count & Duration Guarantee:** Script is validated to have $\ge$ 100 spoken words. Final video is guaranteed between 30 and 60 seconds in vertical 9:16 format.
2. **Audio Separation:** Generated clips are strictly muted via FFmpeg before merging; studio TTS narration is added after visual rendering.
3. **Duplicate Protection:** Topic history (`data/topics.json`) screens out semantically repetitive titles and storylines.
4. **Resilient Fallback Hierarchy:** If Gemini is unavailable, Groq immediately takes over. If external video APIs encounter limits, high-fidelity procedural generation prevents pipeline failure.
5. **Instant Email Alerts:** Clean IST-formatted notifications sent on both successful upload and any unrecoverable errors.
