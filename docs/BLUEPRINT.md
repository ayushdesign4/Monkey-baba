# Monkey-Baba × ZeroCost-Shorts — Master Implementation Blueprint
## Antigravity execution specification

**Target repository:** https://github.com/ayushdesign4/Monkey-baba  
**Upstream project:** https://github.com/igennova/ZeroCost-Shorts  
**Implementation environment:** Antigravity IDE + GitHub Actions  
**Channel niche:** Horror storytelling Shorts  
**Schedule:** Every day at **4:00 AM India Standard Time (IST)**  
**Output:** English, vertical YouTube Shorts, 30–60 seconds  
**Operating mode:** Fully unattended generation, duplicate protection, YouTube upload, persistent history, email notification  
**Repository rule:** Keep the existing `Monkey-baba` GitHub repository and its GitHub Settings intact. Replace the repository's tracked project files with the ZeroCost-Shorts project as the new codebase, then add the requirements in this document. **Do not delete, reset, or recreate the GitHub repository itself.**

---

# 0. Antigravity's mission and execution rules

Antigravity must implement this blueprint directly in the existing local checkout of `ayushdesign4/Monkey-baba`, test it, and push the completed changes to that same repository.

Do not ask the user to manually write code. Do not create a different GitHub repository. Do not delete or modify GitHub Actions repository secrets. Do not print secret values in logs, terminal output, reports, commits, screenshots, or this file.

Before editing anything:

1. Inspect the current `Monkey-baba` working tree, branch, uncommitted changes, current workflow files, history/state files, and project structure.
2. Inspect the actual current upstream repository at `https://github.com/igennova/ZeroCost-Shorts`, including its README, dependency files, workflow files, configuration, authentication flow, uploader, media-generation stages, and current secret/environment-variable names.
3. Determine whether the local checkout is clean. If there are valuable uncommitted changes, preserve them in a safe patch/branch before proceeding.
4. Read the upstream code before assuming that any documented function, model, secret, or path exists. Adapt to the real code rather than inventing APIs or filenames.
5. Make a backup branch or commit before replacing project files.
6. Import the upstream project into the existing `Monkey-baba` repository **without replacing `.git/` and without recreating the GitHub repository**. Preserve `.github/` only where appropriate: inspect upstream workflows and merge/adapt them deliberately rather than blindly retaining conflicting workflows.
7. Preserve the repository's GitHub Settings and all existing Actions secrets. GitHub Actions secrets live in repository Settings, not in the project files. Deleting tracked files does not require deleting those secrets.
8. Implement, test, document, commit, and push changes to `ayushdesign4/Monkey-baba`.
9. Never claim a test, upload, email, or deployment succeeded unless the corresponding result is observed.
10. If a required upstream service has changed, is unavailable, or needs a missing credential, explain the exact blocker. Do not silently substitute an incompatible API or claim the system is fully operational.

**Important:** “Viral-worthy” means optimize for strong, honest hooks and metadata; no implementation can guarantee viral views.

---

# 1. Desired final behavior

Every day, GitHub Actions should run at **04:00 IST**, without the user's computer being on, and attempt exactly one new horror Short.

The pipeline should:

1. Load configuration and secrets safely.
2. Acquire a concurrency lock so two scheduled/manual runs do not produce or upload the same item simultaneously.
3. Read the persistent topic and upload history.
4. Generate several fresh horror story ideas.
5. Reject ideas that are duplicates or too similar to previous stories.
6. Select one topic deterministically for the current run and reserve it in persistent state.
7. Generate an English horror script of at least 100 words.
8. Split the story into 6–8 scenes.
9. Generate detailed, consistent scene prompts in vertical 9:16 format using the actual media-generation capabilities in ZeroCost-Shorts.
10. Generate the visual assets/clips using the upstream project's supported provider(s).
11. Remove/mute any audio embedded in generated clips if narration is added separately.
12. Concatenate/assemble clips in the correct order.
13. Generate English voiceover using the upstream project's existing TTS integration; do not add a paid provider unless the existing project explicitly requires it and the user has configured it.
14. Mix the narration with the final visuals, ensuring intelligible audio and correct timing.
15. Generate a thumbnail or thumbnail frame using the existing supported capability. Do not make the pipeline fail solely because a non-essential thumbnail enhancement fails, unless the upstream uploader requires that asset.
16. Generate a strong but accurate title, description, hashtags, and relevant tags/keywords.
17. Validate the final video and metadata.
18. Check duplicate fingerprints again immediately before upload.
19. Upload to the authorized YouTube channel automatically.
20. Verify that the upload response contains a valid video ID and construct the URL `https://www.youtube.com/watch?v=<VIDEO_ID>`.
21. Write the successful upload record and history to durable repository state.
22. Send a success email with title, URL, topic, duration, upload time, video ID, and a concise story summary.
23. If the pipeline fails, preserve diagnostic logs and send a concise failure email where SMTP configuration is available.
24. Commit/push only the small history/state files needed for deduplication. Do not commit generated MP4 files, tokens, credentials, or large temporary artifacts.
25. Retain workflow logs and optionally upload generated media as short-lived GitHub Actions artifacts for debugging.

A run must never report “success” merely because the Python process ended. Success means the YouTube upload was confirmed, the record was saved, and the success notification was attempted.

---

# 2. Existing GitHub Actions secrets — reuse and map them

The user has already configured these repository secrets in `ayushdesign4/Monkey-baba`:

| Existing secret | Intended use | Required action |
|---|---|---|
| `GROQ_API_KEY` | Groq-based script/metadata generation if the imported project uses Groq | Reuse; inspect the upstream client and map its expected environment variable |
| `HF_TOKEN` | Hugging Face Inference/image generation if supported by the upstream code | Reuse; verify the selected inference task/model and permissions actually work |
| `YOUTUBE_CLIENT_ID` | YouTube OAuth client ID | Reuse |
| `YOUTUBE_CLIENT_SECRET` | YouTube OAuth client secret | Reuse |
| `YOUTUBE_REFRESH_TOKEN` | OAuth refresh token for the authorized YouTube account | Reuse and validate without printing it |
| `NOTIFICATION_EMAIL` | Email recipient | Reuse |
| `SMTP_HOST` | SMTP server hostname | Reuse |
| `SMTP_PORT` | SMTP port | Reuse |
| `SMTP_USERNAME` | SMTP login username | Reuse |
| `SMTP_PASSWORD` | SMTP login/app password | Reuse |

The repository also contains `GEMINI_API_KEY` and `AGNES_API_KEY`; the user explicitly says to **ignore both** for this ZeroCost-Shorts implementation. Do not call Gemini or Agnes, do not make them mandatory, and do not remove their secrets.

## 2.1 Secret-handling requirements

- Do not add a secret value to source code, a `.env` file committed to Git, README, workflow YAML, issue, or log.
- Do not print environment values to debug whether they exist.
- It is acceptable to print only a boolean such as “`GROQ_API_KEY` configured: yes/no”.
- Pass secrets to steps using GitHub Actions `${{ secrets.SECRET_NAME }}` environment mappings.
- Do not expose all secrets to every step. Give each step only the credentials it needs.
- Ensure exceptions and HTTP errors are sanitized before logging.
- Never output OAuth refresh tokens in authentication errors.
- Do not create new secrets unless inspection proves one is required. If the upstream project expects a different variable name, map the existing secret to that expected variable in the workflow instead of asking the user to create a duplicate secret.
- Do not assume `HF_TOKEN` is sufficient for every Hugging Face model. Verify the current provider/model access and handle unavailable models gracefully.
- Do not assume YouTube OAuth credentials work until a safe authentication check or real upload confirms them.
- Never run `env`, `printenv`, `set`, or equivalent commands that expose secrets in CI logs.

## 2.2 Map the current secrets to the upstream project's real variable names

Inspect the upstream code and identify its exact expected variable names. Create a clear mapping table in the final report.

For example, if the imported code expects `YT_CLIENT_ID`, map it to the existing `YOUTUBE_CLIENT_ID` secret in the workflow:

```yaml
env:
  YT_CLIENT_ID: ${{ secrets.YOUTUBE_CLIENT_ID }}
```

This is an example only. Use the actual variable names discovered in the imported source. Do not change the existing GitHub secret names just to match upstream naming.

If the upstream project requires a secret that does not exist in the list above, first determine whether the feature can use an already-configured credential or a keyless provider. If not, report the missing requirement precisely and do not claim that the pipeline is ready.

---

# 3. Repository replacement strategy

The existing repository is the user's primary/source-of-truth repository. It must remain the same repository.

## 3.1 What may be replaced

Replace the old project's tracked application files with the upstream ZeroCost-Shorts codebase, then add this specification's changes. This includes old Python modules, scripts, documentation, dependencies, and obsolete workflows when they conflict with the new implementation.

## 3.2 What must not be deleted

- The GitHub repository itself.
- Git history or the `.git/` directory.
- GitHub repository Settings.
- GitHub Actions secrets listed in Section 2.
- Existing notification secrets.
- The new implementation blueprint and useful setup documentation.
- Any useful upstream license and attribution notices.

Do not run destructive commands against the GitHub repository or use a force-push as a shortcut. Avoid broad shell commands such as `rm -rf .git`, deleting the repository, or deleting every `.github` file without inspection.

## 3.3 Import procedure

1. Make a backup branch or commit from the current state.
2. Fetch/clone the upstream project to a separate temporary directory or worktree.
3. Inspect the upstream license and preserve its attribution/license files.
4. Copy the upstream project's application files into the existing repository checkout while preserving `.git/`.
5. Review all old workflows and keep only the intended active workflow(s); remove or disable conflicting scheduled workflows so the old and new pipelines cannot both upload.
6. Add history/state files, email notification, duplicate protection, niche configuration, tests, and documentation.
7. Inspect `git status` and `git diff --stat` before committing.
8. Commit and push to the existing repository.

Do not copy any upstream `.env`, local credentials, caches, generated videos, or tokens.

---

# 4. Niche and content configuration

The channel niche is **English horror storytelling**. The primary niche configuration should live in:

`pipeline/channel_presets.py`

Use the actual upstream path if it differs; if it does, either adapt that file or create a compatibility layer and document the final path. Do not create two competing sources of truth.

The horror preset should define:

- `niche`: horror storytelling
- `language`: English
- `format`: YouTube Shorts
- `aspect_ratio`: `9:16`
- `target_duration_seconds`: configurable within 30–60 seconds
- `min_script_words`: `100`
- `scene_count_min`: `6`
- `scene_count_max`: `8`
- `tone`: suspenseful, cinematic, eerie, emotionally engaging
- `story_types`: supernatural encounters, urban legends, unexplained mysteries, psychological horror, haunted places, unsettling fictional events
- `audience`: broad English-speaking horror audience
- `narration`: clear English voiceover
- `visual_style`: consistent cinematic horror visuals, strong subject readability on mobile, no accidental text/watermarks
- `metadata_language`: English

Content must be original and varied. Do not copy popular creators' scripts, reuse entire stories, or create misleading “true story” claims for fiction. If the story is fictional, do not falsely present it as verified fact.

Use a strong opening hook within the first 1–3 seconds, steadily escalating tension, a clear payoff or twist, and a satisfying ending. Avoid generic filler, repeated stock phrases, excessive screaming, or misleading engagement bait.

## 4.1 Character and scene consistency

The script/story data should include a compact continuity bible:

- Main character appearance and clothing
- Character age range when story-relevant, without unnecessary detail
- Setting and time period
- Important props
- Lighting/color palette
- Recurring visual motifs
- Camera/style rules

Each of the 6–8 scenes must include its scene number, narration text, visual prompt, duration target, and continuity references. Use a shared character/environment description in each prompt when the generation model cannot preserve state across requests.

Do not claim that the model guarantees perfect visual consistency; implement explicit prompt continuity and validate outputs where possible.

---

# 5. Duplicate-topic and duplicate-video protection

This is a release-blocking requirement. The system must prevent repeated topics/stories and repeated uploads across scheduled runs, manual runs, and reruns.

## 5.1 Persistent state location

Use a small, version-controlled state directory, preferably:

```text
data/
  topic_history.json
  upload_history.json
  run_state.json
```

If the upstream project already has a durable database/state mechanism, inspect and reuse it instead of adding a competing one. Document the chosen single source of truth.

Do not store media files in the JSON history. Store compact records and fingerprints only.

## 5.2 Topic history record

For each reserved or completed story, store at least:

- `topic_id`
- `normalized_topic`
- `topic_title`
- `topic_summary`
- `story_fingerprint`
- `key_entities`
- `story_type`
- `created_at_utc`
- `run_id`
- `status` (`reserved`, `generated`, `uploaded`, `failed`, or `abandoned`)
- `youtube_video_id` if uploaded
- `youtube_url` if uploaded

Normalize case, whitespace, punctuation, and common title variations before comparison.

## 5.3 Duplicate checks

Implement layered deduplication:

1. **Exact topic match:** normalized topic/title.
2. **Exact story fingerprint:** stable hash of normalized script/story content.
3. **Near-duplicate script detection:** token/character similarity or an appropriate lightweight similarity method.
4. **Semantic topic check:** compare the new topic/summary to recent historical topics using the LLM already configured, if available. Do not add a new paid embedding API.
5. **Final-video fingerprint:** SHA-256 of the rendered video file, for exact file duplicates.
6. **Upload record check:** do not upload a video whose video ID or content fingerprint already exists in upload history.
7. **Pre-upload recheck:** check history immediately before calling YouTube upload.

Use configurable similarity thresholds and explain them in the documentation. Similarity thresholds should be conservative enough to reject a lightly reworded version of an old story while allowing genuinely different stories in the same horror subgenre.

A repeated genre is allowed; a repeated story or near-identical script is not. Example: “haunted elevator” may be used again only if the plot, characters, events, reveal, and script are meaningfully different and the duplicate check passes.

## 5.4 Reserve before expensive generation

Once a topic passes the checks, write a `reserved` record before expensive media generation. On a recoverable failure, mark the record as failed/abandoned with the error stage; do not silently erase the history. A failed topic may be retried only under an explicit resume policy and must not cause duplicate uploads.

## 5.5 Idempotent upload behavior

Before upload:

- Confirm the current run's topic/story is not already uploaded.
- Confirm the final file fingerprint is not already uploaded.
- Confirm no previous run has already recorded the same story as uploaded.
- Use a unique `run_id` and stable `topic_id`.
- Do not blindly retry an upload request if the request may have succeeded but the response was lost. First reconcile the ambiguous outcome with the YouTube channel/API where possible; otherwise stop and flag it for safe recovery.

After a confirmed upload, immediately save the video ID and URL to state.

## 5.6 Persisting history between GitHub Actions runs

GitHub-hosted runners are ephemeral. Local JSON changes disappear unless committed, uploaded as an artifact (not sufficient as the only long-term state), or stored externally. Since this project should not need another database service, use Git-tracked JSON state.

Configure the workflow with minimum necessary permissions:

```yaml
permissions:
  contents: write
```

At the start of a run, check out the latest branch state and pull/rebase safely if necessary. At the end, commit and push only the state files (and intentional code changes are committed separately). Do not commit generated MP4 files.

Use a GitHub Actions concurrency group to prevent simultaneous production runs. If a push conflict occurs, fetch/rebase and retry a bounded number of times. Never overwrite another run's newer history. If state cannot be persisted, do not silently report full success; notify the user because future duplicate protection would be degraded.

Keep state compact. Add a retention/archive strategy for old records without discarding fingerprints needed to prevent repeats. Do not remove history just to keep the JSON small unless an explicit safe archival mechanism preserves it.

---

# 6. Daily GitHub Actions schedule — 4:00 AM IST

GitHub Actions scheduled cron uses **UTC**, not India local time.

India Standard Time is UTC+05:30, so 04:00 IST = 22:30 UTC on the previous UTC date.

Use:

```yaml
on:
  schedule:
    - cron: "30 22 * * *"
  workflow_dispatch:
```

This is the intended daily schedule. Do not use `0 4 * * *`, because that would run at 09:30 IST.

GitHub scheduled workflows may start a little later than the exact minute due to platform load. Explain that 04:00 IST is the scheduled trigger, not a hard real-time guarantee.

Requirements:

- Exactly one active daily production workflow.
- Manual `workflow_dispatch` for controlled testing.
- Concurrency group to stop overlapping uploads.
- Set `permissions: contents: write` only if required for persistent state.
- Use a supported Python version and pin/install dependencies from the upstream project.
- Install FFmpeg in the GitHub runner if the workflow needs it.
- Use explicit timeouts.
- Upload useful short-lived logs/artifacts on failure without exposing secrets.
- No requirement for the user's laptop to remain on.

## 6.1 Safe first-run mode

Add a configuration flag such as `DRY_RUN` or `UPLOAD_ENABLED` if the upstream project can support it cleanly. Default the first validation run to dry-run or upload-disabled. Do not change the intended final production behavior: once the user enables production mode, it should automatically upload without manual approval on each daily run.

Before the first real public upload, validate OAuth, model access, FFmpeg, media duration, vertical format, metadata, history persistence, and email configuration. Use private/unlisted upload only if supported by the actual uploader and user settings; do not invent unsupported upload options.

---

# 7. Workflow architecture

Use one clear orchestrator and one active workflow. Adapt names to the imported source but keep responsibilities separate.

```text
GitHub Actions cron (22:30 UTC = 04:00 IST)
                  |
                  v
        Checkout latest repository
                  |
                  v
       Acquire concurrency / state lock
                  |
                  v
         Validate required secrets
                  |
                  v
           Load horror preset
                  |
                  v
          Read topic/upload history
                  |
                  v
     Generate candidate horror topics
                  |
                  v
      Reject duplicate / near-duplicate
                  |
                  v
          Reserve unique topic ID
                  |
                  v
        Generate >=100-word script
                  |
                  v
          Validate story structure
                  |
                  v
            Split into 6–8 scenes
                  |
                  v
       Generate consistent scene prompts
                  |
                  v
         Generate images/video assets
                  |
                  v
        Mute generated clip audio if needed
                  |
                  v
             Assemble visual clips
                  |
                  v
          Generate narration with TTS
                  |
                  v
        Mix voiceover and final visuals
                  |
                  v
       Generate thumbnail/frame if supported
                  |
                  v
       Generate title/description/hashtags/tags
                  |
                  v
       Validate duration, format, audio, content
                  |
                  v
       Re-check duplicate history before upload
                  |
                  v
             Upload to YouTube
                  |
                  v
       Confirm video ID and build canonical URL
                  |
                  v
       Persist topic + upload history to Git
                  |
                  v
          Send SMTP success email
                  |
                  v
       Retain sanitized logs/artifacts and finish
```

If any essential stage fails, stop before upload. Mark the run failed, persist the failure state when possible, and send a failure notification. A failure email must never contain API keys, OAuth tokens, passwords, or raw secret-bearing environment output.

---

# 8. Video and audio requirements

Follow the actual ZeroCost-Shorts capabilities and do not invent an unsupported text-to-video service. If the upstream project uses images plus motion/stock footage rather than true AI-generated video, document that accurately.

Final video requirements:

- English horror storytelling.
- Vertical 9:16.
- Duration: 30–60 seconds.
- At least 100 words in the original script; narration speed may need adjustment to fit the duration. If the word count and target duration conflict, adapt pacing/script length while keeping the minimum requirement and validate the result. Do not speed the voice to an unintelligible rate.
- 6–8 scenes.
- Clips in intended story order.
- Embedded scene audio removed when a separate TTS narration is used.
- No clipped first/last words.
- No silent or black gaps unless intentional.
- Correct audio/video duration.
- FFmpeg exit codes checked.
- Final file exists, has non-zero size, decodes successfully, and passes `ffprobe` validation.
- Reject corrupt, zero-byte, or wrongly oriented media.
- Avoid unlicensed/restricted footage and respect each asset provider's terms.
- Do not claim every generated visual is copyright-free without checking the actual provider license and terms.

Use a short thumbnail-style opening frame only if it does not break story flow or push the final duration over 60 seconds. YouTube Shorts thumbnail selection and API support can vary; do not assume a separate custom thumbnail can be set for every Short through the same API path. Preserve any thumbnail/frame support already in the upstream project and document platform limitations.

---

# 9. Viral-oriented metadata generation

Generate metadata after the story is finalized and before upload. Metadata must accurately represent the actual story.

## 9.1 Title

Produce a small set of candidate titles and choose one based on clarity, curiosity, natural English, and story relevance. Prefer a concise hook that creates curiosity without giving away the ending.

Rules:

- No false claims such as “real footage” or “true story” unless verified.
- No unrelated trending names/keywords.
- No keyword stuffing.
- No repetitive all-caps titles or excessive emoji.
- No misleading promise that the video fails to deliver.
- Keep the title suitable for a mobile Shorts feed.
- Do not use the same title repeatedly.

## 9.2 Description

Generate a short, unique description containing:

- A one- or two-sentence story hook/summary.
- A natural call to action only when it fits.
- A small set of relevant hashtags.
- A fiction disclaimer if needed to avoid presenting fiction as fact.

Do not fill descriptions with irrelevant hashtags, repeated keywords, or copied boilerplate that makes every upload look identical.

## 9.3 Hashtags

Choose a small, relevant set, for example some combination of `#HorrorShorts`, `#ScaryStories`, `#HorrorStory`, plus story-specific tags. These are examples, not mandatory fixed tags for every upload. Select based on the actual story.

Do not stuff dozens of hashtags into every description. Avoid unrelated trending hashtags.

## 9.4 Tags / keywords

Generate relevant YouTube tags where the API/uploader supports them. Focus on the actual subgenre, central premise, and audience intent. Do not confuse video tags with hashtags in the description.

## 9.5 Metadata quality validation

Before upload, verify:

- Title, description, and tags exist.
- Metadata matches the actual story.
- No placeholders such as `[TITLE]`, `TODO`, or `undefined`.
- No unsupported “guaranteed viral” wording.
- No sensitive tokens or internal prompt text are included.
- Metadata is valid for the actual YouTube Data API request schema.
- Record the selected title and metadata in upload history.

**Important:** This system can optimize metadata; it cannot guarantee views, recommendations, CTR, or virality.

---

# 10. YouTube OAuth and upload

Reuse the existing GitHub secrets:

- `YOUTUBE_CLIENT_ID`
- `YOUTUBE_CLIENT_SECRET`
- `YOUTUBE_REFRESH_TOKEN`

Inspect the upstream OAuth implementation and map these existing secret names to its expected environment variable names. Do not require the user to add duplicate secrets if the existing values are compatible.

Requirements:

1. Use the YouTube Data API upload mechanism already present in the upstream project.
2. Refresh access tokens securely using the refresh token; never print tokens.
3. Fail with a sanitized and actionable message if OAuth is invalid or revoked.
4. Upload only after media and metadata validation.
5. Store the returned video ID and canonical URL.
6. Ensure upload status/privacy is configured explicitly in the existing configuration. Do not unexpectedly change the user's channel privacy policy.
7. Do not retry blindly after an ambiguous upload timeout. Reconcile before trying again to prevent duplicate videos.
8. Do not upload a second video if the same run is resumed after upload success.
9. Handle quota/rate-limit errors without endlessly retrying.
10. Respect YouTube API terms and channel/account restrictions.

A successful upload record should include:

```json
{
  "video_id": "REAL_VIDEO_ID",
  "video_url": "https://www.youtube.com/watch?v=REAL_VIDEO_ID",
  "title": "Selected video title",
  "topic_id": "stable-topic-id",
  "story_fingerprint": "sha256-or-stable-fingerprint",
  "video_sha256": "sha256-of-final-video",
  "duration_seconds": 45,
  "language": "en",
  "niche": "horror",
  "uploaded_at_utc": "ISO-8601 timestamp",
  "run_id": "github-actions-run-id",
  "status": "uploaded"
}
```

The values above are a schema example, not real upload data. Use actual runtime values.

---

# 11. SMTP upload-success email — mandatory feature

Implement an email notification that is sent **only after the YouTube upload has been confirmed** and the upload record has been saved or is safely recoverable.

Use existing secrets:

- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `NOTIFICATION_EMAIL`

No new email provider API key should be required if these SMTP credentials are valid.

## 11.1 Success email content

**Subject:** `🎬 Your YouTube Horror Short Is Uploaded — <Video Title>`

Email body should include:

- Success status.
- Exact uploaded title.
- Clickable canonical YouTube URL.
- Short story summary (2–3 sentences).
- Horror subgenre/topic.
- Duration in seconds.
- Upload time in IST.
- YouTube video ID.
- Run ID or a link to the GitHub Actions run.
- A brief list of important pipeline stages that succeeded.

Example template:

```text
🎬 YOUTUBE SHORT UPLOADED SUCCESSFULLY

Title: <actual title>
Status: Published (or actual configured visibility)
YouTube URL: https://www.youtube.com/watch?v=<actual-video-id>

Story:
<2–3 sentence accurate summary>

Niche: Horror
Duration: <actual seconds>
Upload time: <actual time in IST>
Video ID: <actual ID>
Run: <GitHub Actions run URL>

Pipeline: Script ✓ | Visuals ✓ | Voiceover ✓ | Metadata ✓ | Upload ✓
```

Use MIME multipart email with a plain-text body and an HTML body containing a clickable video link, if the existing SMTP helper supports it. Escape dynamic HTML fields to avoid malformed HTML. Do not put a generic/guessed video URL in the message; use the confirmed video ID returned by the upload API.

## 11.2 Email failure behavior

- A failed email must not cause the system to upload the video a second time.
- If upload succeeds but SMTP fails, keep the upload record as uploaded and mark notification status as pending/failed.
- Log a sanitized SMTP error and provide a bounded retry for the notification only.
- Support a later notification-only retry without regenerating or re-uploading the video.
- Do not say “email sent” unless SMTP send returns success.
- Never put credentials or raw tokens in email content.

## 11.3 Failure notification

If a critical stage fails, send a failure email where SMTP is available:

**Subject:** `❌ Monkey-Baba Horror Shorts Pipeline Failed`

Include:

- Failed stage.
- Short sanitized error.
- Topic ID/title if reserved.
- GitHub Actions run URL.
- Whether an upload may already have occurred.
- Whether a success email is pending.

If the upload outcome is ambiguous, the email must clearly say “upload status needs reconciliation” instead of claiming failure or success.

## 11.4 Avoid duplicate emails

Store notification state with the upload record, such as:

```json
{
  "notification_status": "sent",
  "notification_sent_at_utc": "ISO-8601 timestamp"
}
```

If an email fails, use `pending` or `failed`. A notification-only retry must not re-upload the video. Exactly-once email delivery cannot be guaranteed by SMTP in every failure mode, so implement idempotency using the video ID and notification status, and document the remaining edge case.

---

# 12. Persistent records and run logs

Use compact JSON records and a stable schema. Example:

```text
data/
  topic_history.json
  upload_history.json
  run_state.json
```

Suggested `run_state.json` fields:

- `run_id`
- `started_at_utc`
- `finished_at_utc`
- `stage`
- `status`
- `topic_id`
- `video_id`
- `upload_status`
- `notification_status`
- `last_error_stage`
- `last_error_summary`

Never write secrets into state files. Keep error summaries sanitized. Add tests for empty/corrupt history files; recover safely rather than treating an unreadable history as empty and uploading without deduplication.

If the state file is corrupt or missing unexpectedly, fail closed for production upload until the history is safely recovered. An empty initial history on the first-ever run is valid; an unexpected parse error in an existing history file is not the same thing.

---

# 13. Retry, resume, and error handling

Use bounded retries with exponential backoff for transient errors only, such as timeouts, temporary 5xx responses, and rate limits where retry is appropriate.

Do not retry forever.

Do not treat invalid credentials, permission errors, unsupported model errors, malformed local media, or exhausted quotas as transient indefinitely.

Track pipeline stage transitions so a rerun can understand whether:

- topic was reserved,
- script was generated,
- media was generated,
- final video was rendered,
- upload was attempted,
- upload was confirmed,
- notification was sent.

A rerun must not blindly start over and upload a duplicate. Reuse valid local artifacts within the same job when possible, but remember GitHub-hosted runners are ephemeral. Cross-run resume must be implemented explicitly if needed; do not assume a prior runner's files still exist.

If a video was uploaded but saving state failed, attempt to reconcile with YouTube using the known video ID before doing anything else. If the video ID was never received due to an ambiguous request, stop and alert rather than making a blind second upload.

---

# 14. GitHub Actions security and resource use

- Set `permissions` to the minimum required.
- Do not use `pull_request_target` or execute untrusted pull-request code with secrets.
- Do not print secrets or use shell tracing (`set -x`) in secret-bearing steps.
- Pin third-party GitHub Actions to a reviewed version or commit SHA when practical.
- Use dependency versions supported by the upstream project; pin important dependencies where compatible.
- Add job timeout limits.
- Avoid committing generated videos or large artifacts.
- Add appropriate `.gitignore` entries for `.env`, tokens, caches, temporary files, local output directories, and generated MP4s.
- Do not accidentally ignore the persistent JSON history.
- Upload debugging artifacts only when useful and ensure they contain no credentials.
- Limit retry loops to protect API quotas and runner time.
- Make workflow failures visible in GitHub Actions logs and via the configured email.
- Use a concurrency group such as `monkey-baba-daily-short` with `cancel-in-progress: false` or an equivalent safe queueing policy. Do not cancel a run in the middle of a potentially successful upload and then immediately start a duplicate upload.

---

# 15. Tests required before production

Implement tests appropriate to the real upstream code. At minimum:

## Configuration and secrets
- Missing required secret fails early with a clear, sanitized message.
- Optional/ignored Gemini and Agnes secrets are not required or called.
- Existing secret-name mappings are correct.
- No secret value appears in logs.

## Niche/content
- Horror preset loads.
- Script language is English.
- Script word-count validation enforces at least 100 words.
- Scene count is between 6 and 8.
- Metadata validation rejects placeholders and unrelated tags.

## Deduplication
- Exact same topic is rejected.
- Same script with whitespace/punctuation changes is rejected.
- Near-duplicate story is rejected at the configured threshold.
- Different story in the same horror genre is allowed.
- Same video file hash is rejected.
- Uploaded topic cannot be uploaded again.
- Corrupt history does not silently become an empty history.
- Concurrent runs do not race into duplicate uploads.

## Media
- Corrupt/zero-byte video is rejected.
- Wrong aspect ratio is rejected or explicitly normalized.
- Final duration must be 30–60 seconds.
- Audio/video streams are present as intended.
- Embedded scene audio is removed when separate narration is used.
- FFmpeg errors are caught.

## Upload
- Upload failure does not create a false success record.
- Successful upload ID and URL are recorded.
- Ambiguous upload response does not cause a blind duplicate retry.
- Rerun after upload success does not upload again.

## Email
- Success email contains title, real URL, summary, duration, timestamp, video ID, and run URL.
- Failure email is sanitized.
- SMTP failure does not re-upload the video.
- Notification-only retry does not regenerate or upload.
- Notification status is recorded.

## Workflow
- Cron is `30 22 * * *`.
- Manual dispatch works.
- State commit/push is safe and does not include media.
- Only one production workflow schedules the daily upload.

Run focused tests and the project's existing test suite. Avoid an endless cycle of tests or unrelated refactoring. Do not claim external services are tested unless the workflow actually reached them.

---

# 16. Recommended repository deliverables

Adapt to the upstream structure, but provide these logical modules:

- Horror niche preset/configuration.
- One orchestrator that owns stage order.
- Topic generator/selector and duplicate detector.
- Script/scene validator.
- Media assembler and final media validator.
- Metadata generator/validator.
- YouTube uploader with safe idempotency behavior.
- SMTP notification helper.
- Persistent state/history manager.
- One active GitHub Actions workflow.
- Tests for state, duplicate protection, metadata, notifications, and upload handling.
- README with setup, secret mapping, cron explanation, manual run, debugging, and known provider limits.
- This implementation blueprint retained in the repository, preferably under `docs/`.

Do not force these exact filenames if the upstream project already has clean equivalents. Reuse and adapt existing modules rather than creating duplicate parallel implementations.

---

# 17. Acceptance criteria — definition of done

The implementation is complete only when all applicable items are true:

- [ ] `Monkey-baba` remains the same GitHub repository.
- [ ] Existing Git history is preserved.
- [ ] Existing GitHub Actions secrets remain unchanged.
- [ ] Gemini and Agnes are ignored by this pipeline.
- [ ] ZeroCost-Shorts source and license/attribution are imported correctly.
- [ ] Existing conflicting scheduled workflows are removed or disabled.
- [ ] Horror niche is configured in `pipeline/channel_presets.py` or a documented equivalent.
- [ ] English scripts are at least 100 words.
- [ ] Stories are split into 6–8 scenes.
- [ ] Final video is vertical 9:16 and 30–60 seconds.
- [ ] Scene audio is muted/removed when separate narration is used.
- [ ] Title, description, hashtags, and tags/keywords are generated and validated.
- [ ] Daily cron is `30 22 * * *` UTC, equivalent to 04:00 IST.
- [ ] Manual workflow dispatch exists.
- [ ] Only one active daily production workflow remains.
- [ ] Exact and near-duplicate topic/story checks are implemented.
- [ ] Video fingerprint and upload history are checked before upload.
- [ ] History survives across GitHub Actions runs.
- [ ] Upload handling is safe against ambiguous outcomes and reruns.
- [ ] Upload success record includes actual video ID and URL.
- [ ] SMTP success email contains title, clickable URL, story summary, duration, upload time, video ID, and workflow URL.
- [ ] SMTP failure does not trigger a duplicate upload.
- [ ] Failure email is implemented where possible.
- [ ] No secrets are hard-coded, committed, or printed.
- [ ] Tests pass or any failure is clearly reported.
- [ ] Workflow YAML and cron are validated.
- [ ] First real upload is not attempted until the safe validation path has passed.
- [ ] Changes are committed and pushed to `https://github.com/ayushdesign4/Monkey-baba`.
- [ ] Final report lists files changed, tests run, exact secret mapping, cron conversion, remaining setup, and the latest commit hash.

---

# 18. Required Antigravity final report

After implementation, provide a concise but complete report containing:

1. **Repository status:** confirm the target repository URL and branch.
2. **Replacement status:** which old tracked project files were removed/replaced and confirmation that `.git/` and GitHub Settings/secrets were preserved.
3. **Upstream import:** commit/version or upstream revision used.
4. **Workflow:** exact workflow filename and cron expression; explain `22:30 UTC = 04:00 IST`.
5. **Secret mapping:** names only, never values; identify any genuinely missing secrets.
6. **Niche:** final configuration location and active horror preset.
7. **Duplicate protection:** history paths, fingerprint methods, concurrency behavior, and ambiguous-upload handling.
8. **Email:** SMTP variables used and the success/failure email fields.
9. **Tests:** commands run and real pass/fail counts.
10. **Deployment:** commit hash and whether push succeeded.
11. **First run:** exact steps for running a dry-run/validation workflow and then enabling normal unattended publishing.
12. **Known limitations:** provider free-tier limits, model availability, API quota, YouTube API restrictions, and anything not verified.

Do not say “fully working” until an actual controlled workflow run has confirmed the relevant stages. Do not claim an upload or email was successful based solely on unit tests.

---

# Final instruction

Implement this specification in the existing `ayushdesign4/Monkey-baba` repository using the actual ZeroCost-Shorts source as the base. Preserve all existing GitHub Actions secrets and ignore the Gemini/Agnes secrets. Configure English horror Shorts, daily 04:00 IST scheduling, robust persistent duplicate prevention, automatic YouTube upload, and SMTP email notification with the real title, URL, and concise story details. Validate carefully, then commit and push to the same repository.
