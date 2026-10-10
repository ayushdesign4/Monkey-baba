# Monkey-Baba 🐵🎬 × ZeroCost-Shorts
### Autonomous AI Horror YouTube Shorts Production Pipeline

[![Daily YouTube Horror Short](https://github.com/ayushdesign4/Monkey-baba/actions/workflows/daily_short.yml/badge.svg)](https://github.com/ayushdesign4/Monkey-baba/actions/workflows/daily_short.yml)
[![Python](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/)

**Monkey-Baba** is an autonomous, unattended cloud production pipeline for English horror storytelling YouTube Shorts (9:16 vertical, 30–60 seconds). Running on GitHub Actions, it produces and publishes high-retention content daily at **04:00 AM India Standard Time (IST)** without requiring a personal computer to be powered on.

Based on the [ZeroCost-Shorts](https://github.com/igennova/ZeroCost-Shorts) upstream architecture, Monkey-Baba has been specialized with zero-cost AI pipelines, deterministic local emergency fallbacks, robust multi-layer duplicate prevention, a pre-upload visual quality gate, and rich SMTP email alerts.

---

## 🕒 Daily Schedule: 04:00 AM IST

- **Schedule Trigger:** Every day at **04:00 AM IST** (India Standard Time).
- **Cron Definition in GitHub Actions:** `30 22 * * *` (UTC).
  - *Conversion:* India Standard Time is UTC + 5:30. 
  - `04:00 IST - 5 hours 30 minutes = 22:30 UTC` on the preceding calendar day.
- **Workflow:** `.github/workflows/daily_short.yml` (the single active production workflow).
- **Concurrency Protection:** Uses `concurrency: group: monkey-baba-daily-short` (`cancel-in-progress: false`) to ensure overlapping runs never compete or trigger duplicate uploads.

---

## 🏗 Pipeline Architecture & Fallback Hierarchy

```text
               GitHub Actions Cron (22:30 UTC = 04:00 IST)
                                    │
                                    ▼
                     Load Preset & Persistent History
                                    │
                                    ▼
                         Candidate Horror Topic
                         (Layered Deduplication)
                                    │
                                    ▼
                            Reserve Topic ID
                                    │
                                    ▼
                          Script Generation
               Groq (Llama 3.3) ──[fallback]──► Deterministic Local Fallback
               (Script >= 100 words, English, 6–8 scene beats)
                                    │
                                    ▼
                         Visual Scene Generation
           DeAPI ──► HuggingFace (HF_TOKEN) ──► Pollinations ──► Local PIL
           (Vertical 9:16, dark atmospheric cinematic horror style)
                                    │
                                    ▼
                          Edge TTS Voiceover
                       (en-US-ChristopherNeural)
                                    │
                                    ▼
                           Word-Level Captions
                         (Creepster horror font)
                                    │
                                    ▼
                             FFmpeg Render
               (Ken Burns zoompan + fadeblack transitions + audio mix)
                                    │
                                    ▼
                         Visual Quality Gate
               (Check 30–60s duration, 9:16 aspect, non-blank frames)
                                    │
                                    ▼
                        Pre-Upload Duplicate Check
                                    │
                                    ▼
                           YouTube Data API v3
                     (OAuth token refresh & upload)
                                    │
                                    ▼
                        Git-Tracked State Persist
                     (data/*.json commit & push)
                                    │
                                    ▼
                          SMTP Email Notification
           (Title, clickable URL, summary, duration, IST time, video ID)
```

---

## 🔑 GitHub Actions Secrets Mapping

All existing repository secrets are preserved and mapped without requiring new secret creations:

| Existing Repository Secret | Mapped Variable in Workflow | Purpose |
|----------------------------|-----------------------------|---------|
| `GROQ_API_KEY` | `GROQ_API_KEY` | Script and metadata generation via Groq |
| `HF_TOKEN` | `HF_TOKEN` | Hugging Face Inference / Router image generation |
| `YOUTUBE_CLIENT_ID` | `YT_CLIENT_ID` | YouTube OAuth client ID |
| `YOUTUBE_CLIENT_SECRET` | `YT_CLIENT_SECRET_VALUE` | YouTube OAuth client secret |
| `YOUTUBE_REFRESH_TOKEN` | `YT_REFRESH_TOKEN` | Authorized YouTube account OAuth refresh token |
| `SMTP_HOST` | `SMTP_HOST` | SMTP server host (e.g. `smtp.gmail.com`) |
| `SMTP_PORT` | `SMTP_PORT` | SMTP port (e.g. `587` or `465`) |
| `SMTP_USERNAME` | `SMTP_USERNAME` | SMTP account / sender username |
| `SMTP_PASSWORD` | `SMTP_PASSWORD` | SMTP app password |
| `NOTIFICATION_EMAIL` | `NOTIFICATION_EMAIL` | Recipient email for success and failure alerts |

> [!NOTE]
> `GEMINI_API_KEY` and `AGNES_API_KEY` are safely ignored by this pipeline. They remain in repository secrets without being called or removed.

---

## 🛡 Layered Duplicate Protection

Persistent state is stored in Git-tracked JSON records under `data/`:
- `data/topic_history.json`: Tracks reserved, generated, and uploaded story topics with summaries and fingerprints.
- `data/upload_history.json`: Tracks confirmed YouTube uploads, video IDs, duration, file SHA-256 hashes, and notification states.
- `data/run_state.json`: Real-time run state, timestamps, and error diagnostics.

Deduplication layers include:
1. **Exact Topic Match:** Normalized case, punctuation, and whitespace comparison against past topics.
2. **Exact Script Fingerprint:** SHA-256 hash of normalized narration content.
3. **Near-Duplicate Script Detection:** Word-level Jaccard similarity rejection at threshold $\ge 0.65$.
4. **Final Video Fingerprint:** SHA-256 hash of the rendered MP4 file before upload.
5. **Reserve Pattern:** Topics are reserved in durable state before media generation begins.
6. **Fail-Closed on Corruption:** If any state file contains corrupt JSON, the pipeline immediately aborts rather than risking duplicate uploads.

---

## 🚦 Pre-Upload Visual Quality Gate

Before calling the YouTube Upload API, `pipeline/quality_gate.py` validates:
- **File Integrity:** Video file exists and size $> 50\text{ KB}$.
- **Duration:** Strictly between $25.0$ and $60.0$ seconds.
- **Orientation & Aspect Ratio:** Enforces vertical $9:16$ format ($1080 \times 1920$ or $720 \times 1280$).
- **Streams:** Verified active H.264 video and AAC audio streams.
- **Frame Luminance Analysis:** Samples multiple frames across the video to reject solid black or blank visual outputs.

---

## 📧 Email Notifications

After confirmed upload, `pipeline/email_notifier.py` delivers a multipart MIME notification with:
- Canonical YouTube URL: `https://www.youtube.com/watch?v=<VIDEO_ID>`
- YouTube Shorts URL: `https://www.youtube.com/shorts/<VIDEO_ID>`
- Story hook summary (2–3 sentences)
- Exact upload timestamp in India Standard Time (IST)
- Video ID and run diagnostics
- Pipeline stages confirmation

---

## 🚀 Manual Execution & Testing

### Running Tests Locally
```bash
python -m pytest tests/ -v
```

### Running a Dry-Run (Local or CI)
Generate script, visuals, audio, and video without uploading to YouTube:
```bash
python scripts/run_short.py --channel horror --dry-run
```

### Triggering via GitHub Actions
1. Navigate to **Actions** → **Daily YouTube Horror Short**.
2. Click **Run workflow**.
3. Select parameters:
   - `channel`: `horror`
   - `topic`: (optional custom premise)
   - `dry_run`: `true` for validation, `false` for live upload
   - `privacy`: `public`, `unlisted`, or `private`
4. Click **Run workflow**.

---

## 📜 Upstream Attribution
- Base project: [ZeroCost-Shorts](https://github.com/igennova/ZeroCost-Shorts) by igennova.
- Adaptations for Monkey-Baba: English horror preset, deterministic local fallbacks, quality gate, Git state persistence, and SMTP notification suite.
- Blueprint retained in [`docs/BLUEPRINT.md`](docs/BLUEPRINT.md).
