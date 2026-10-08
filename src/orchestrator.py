"""Central Orchestrator for Monkey-Baba autonomous pipeline."""

import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from src.config import OUTPUT_DIR
from src.utils.logging import log, log_warn, log_error, log_success
from src.utils.files import write_json, ensure_dir
from src.brain.manager import BrainManager
from src.topic.generator import TopicGenerator
from src.script.generator import ScriptGenerator
from src.scenes.director import SceneDirector
from src.video.manager import VideoManager
from src.editing.concat import concatenate_clips
from src.tts.manager import TTSManager
from src.editing.finalizer import VideoFinalizer
from src.editing.audio import get_media_duration
from src.thumbnail.manager import ThumbnailManager
from src.metadata.generator import MetadataGenerator
from src.youtube.uploader import YouTubeUploader
from src.notifications.email import EmailNotifier

class MonkeyBabaOrchestrator:
    def __init__(self):
        self.brain = BrainManager()
        self.topic_gen = TopicGenerator(self.brain)
        self.script_gen = ScriptGenerator(self.brain)
        self.director = SceneDirector(self.brain)
        self.video_mgr = VideoManager()
        self.tts_mgr = TTSManager()
        self.thumb_mgr = ThumbnailManager(self.brain)
        self.meta_gen = MetadataGenerator(self.brain)
        self.uploader = YouTubeUploader()
        self.notifier = EmailNotifier()

    def run_pipeline(self, forced_topic: Optional[str] = None, dry_run: bool = False) -> Dict[str, Any]:
        """Execute the end-to-end autonomous video generation and publication pipeline."""
        start_time = time.time()
        run_id = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        run_dir = ensure_dir(OUTPUT_DIR / f"{datetime.utcnow().strftime('%Y-%m-%d')}_{run_id}")

        log("ORCHESTRATOR", f"Starting Monkey-Baba Autonomous Pipeline (Run ID: {run_id})...")
        log("ORCHESTRATOR", f"Artifacts Directory: {run_dir.resolve()}")

        current_stage = "INITIALIZATION"
        selected_topic = None

        try:
            # 1. TOPIC GENERATION & DUPLICATE PREVENTION
            current_stage = "TOPIC"
            topic_record, topic_fallback = self.topic_gen.generate_and_select_topic(forced_topic)
            selected_topic = topic_record["topic"]
            write_json(run_dir / "topic.json", topic_record)

            # 2. SCRIPT GENERATION (>=100 words, English, 6-8 scenes)
            current_stage = "SCRIPT"
            script_data, script_fallback = self.script_gen.generate_script(topic_record)
            write_json(run_dir / "script.json", script_data)
            with open(run_dir / "script.txt", "w", encoding="utf-8") as f:
                f.write(script_data.get("full_narration", ""))

            # 3. SCENES DIRECTION & CHARACTER/ENV CONSISTENCY
            current_stage = "SCENES"
            direction_data, scenes_fallback = self.director.direct_scenes(script_data, topic_record)
            write_json(run_dir / "direction.json", direction_data)
            scenes = direction_data.get("scenes", [])
            write_json(run_dir / "scenes.json", scenes)

            # 4. VIDEO GENERATION (Agnes primary, video fallback)
            current_stage = "VIDEO"
            clip_paths, video_provider, video_fallback = self.video_mgr.generate_scene_clips(scenes, run_dir)

            # 5. MERGE CLIPS (All silent)
            current_stage = "CONCAT"
            reel_path = run_dir / "reel.mp4"
            concatenate_clips(clip_paths, reel_path)

            # 6. TTS GENERATION (Generated after visual clip merging)
            current_stage = "TTS"
            narration_path = run_dir / "narration.mp3"
            self.tts_mgr.generate_speech(script_data["full_narration"], narration_path)

            # 7. THUMBNAIL GENERATION (Agnes primary, fallback)
            current_stage = "THUMBNAIL"
            thumb_path, thumb_provider, thumb_fallback = self.thumb_mgr.generate_thumbnail(topic_record, run_dir)

            # 8. AUDIO/VIDEO COMBINATION & DURATION ENFORCEMENT (30-60 sec)
            current_stage = "FINALIZATION"
            final_video_path = run_dir / "final.mp4"
            VideoFinalizer.finalize_video(
                reel_path=reel_path,
                narration_path=narration_path,
                thumbnail_path=thumb_path,
                output_path=final_video_path,
                include_thumbnail_intro=True
            )
            final_duration = get_media_duration(final_video_path)

            # 9. METADATA GENERATION
            current_stage = "METADATA"
            metadata, meta_fallback = self.meta_gen.generate_metadata(topic_record, script_data)
            write_json(run_dir / "metadata.json", metadata)

            # 10. YOUTUBE UPLOAD
            current_stage = "UPLOAD"
            upload_record = self.uploader.upload_short(
                video_path=final_video_path,
                metadata=metadata,
                thumbnail_path=thumb_path,
                dry_run=dry_run
            )
            write_json(run_dir / "upload.json", upload_record)

            # Update topic record status
            self.topic_gen.history.update_status(
                topic_id=topic_record["topic_id"],
                status="uploaded" if not dry_run else "simulated",
                video_id=upload_record.get("video_id")
            )

            # 11. RECORD RUN STATS
            run_record = {
                "run_id": run_id,
                "status": "uploaded" if not dry_run else "simulated",
                "topic_id": topic_record["topic_id"],
                "topic": selected_topic,
                "title": metadata.get("title"),
                "brain_provider": self.brain.last_provider_used or "gemini",
                "brain_fallback_used": self.brain.fallback_used,
                "video_provider": video_provider,
                "video_fallback_used": video_fallback,
                "thumbnail_provider": thumb_provider,
                "thumbnail_fallback_used": thumb_fallback,
                "duration_seconds": final_duration,
                "youtube_video_id": upload_record.get("video_id"),
                "youtube_url": upload_record.get("youtube_url"),
                "uploaded_at": datetime.utcnow().isoformat(),
                "execution_seconds": time.time() - start_time
            }
            write_json(run_dir / "run.json", run_record)

            # 12. NOTIFICATION EMAIL (SUCCESS)
            current_stage = "EMAIL"
            self.notifier.send_success_email(run_record)

            log_success("ORCHESTRATOR", f"Run {run_id} completed successfully in {time.time() - start_time:.1f}s!")
            return run_record

        except Exception as e:
            log_error("ORCHESTRATOR", f"Pipeline failed at stage [{current_stage}]: {e}")
            error_record = {
                "run_id": run_id,
                "status": "failed",
                "failed_stage": current_stage,
                "topic": selected_topic,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
            write_json(run_dir / "error.json", error_record)

            # Send failure alert email
            try:
                self.notifier.send_failure_email(
                    topic=selected_topic or "Unknown",
                    stage=current_stage,
                    error_message=str(e),
                    run_id=run_id
                )
            except Exception as notify_err:
                log_warn("EMAIL", f"Could not send failure alert: {notify_err}")

            raise e
