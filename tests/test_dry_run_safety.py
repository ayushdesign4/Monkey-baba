import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from scripts.run_short import run_pipeline


def test_dry_run_strictly_prohibits_upload_and_live_email(tmp_path, monkeypatch):
    """Verify that when dry_run=True, upload_short and send_upload_success_email
    are NEVER called, even if upload_enabled=True is passed.
    """
    monkeypatch.setattr("pipeline.story_history.DATA_DIR", tmp_path)
    monkeypatch.setattr("pipeline.story_history.TOPIC_HISTORY_PATH", tmp_path / "topic_history.json")
    monkeypatch.setattr("pipeline.story_history.UPLOAD_HISTORY_PATH", tmp_path / "upload_history.json")
    monkeypatch.setattr("pipeline.story_history.RUN_STATE_PATH", tmp_path / "run_state.json")

    mock_upload = MagicMock()
    mock_email = MagicMock()

    with patch("pipeline.youtube_upload.upload_short", mock_upload), \
         patch("scripts.run_short.send_upload_success_email", mock_email), \
         patch("scripts.run_short.synthesize_full", return_value=(45.0, [{"start": 0, "end": 45, "text": "sentence"}])), \
         patch("scripts.run_short.build_srt"), \
         patch("scripts.run_short.render_vertical_short"), \
         patch("scripts.run_short.validate_short_quality") as mock_qg, \
         patch("scripts.run_short.save_scene_image", return_value=("ok", "huggingface (FLUX)")):

        mock_qg.return_value = MagicMock(passed=True, duration=45.0, width=1080, height=1920, errors=[])

        # Execute pipeline with dry_run=True AND upload_enabled=True
        result = run_pipeline(
            channel_id="horror",
            topic_override="a lake where the water remains unnaturally still even during thunderstorms",
            upload_enabled=True,   # Even with upload_enabled=True
            dry_run=True,          # dry_run MUST strictly override
            run_id="test_dry_run",
            allow_procedural_fallback=True,
        )

        assert result["status"] == "success"
        assert result["dry_run"] is True
        assert result["video_id"].startswith("sim_")

        # Crucial assertions: neither upload nor live success email was ever called!
        assert mock_upload.call_count == 0, "YouTube upload MUST NOT be called in dry-run mode!"
        assert mock_email.call_count == 0, "Live success email MUST NOT be called in dry-run mode!"
