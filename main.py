"""Monkey-Baba CLI entry point."""

import sys
import argparse
from src.orchestrator import MonkeyBabaOrchestrator
from src.utils.logging import log, log_success
from src.utils.files import read_json
from src.config import TOPICS_FILE, UPLOADS_FILE

def main():
    parser = argparse.ArgumentParser(description="Monkey-Baba Autonomous AI YouTube Shorts Pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Run full pipeline in simulation mode (no charges, simulated upload)")
    parser.add_argument("--topic", type=str, default=None, help="Force a specific topic instead of autonomous ideation")
    parser.add_argument("--test-brain", action="store_true", help="Test Brain providers (Gemini -> Groq -> Local Python)")
    parser.add_argument("--status", action="store_true", help="Print recent pipeline history")

    args = parser.parse_args()

    if args.status:
        topics = read_json(TOPICS_FILE, default=[])
        uploads = read_json(UPLOADS_FILE, default=[])
        print(f"\n--- Monkey-Baba Pipeline Status ---")
        print(f"Total topics recorded: {len(topics)}")
        print(f"Total uploads recorded: {len(uploads)}")
        if uploads:
            print("\nLatest Upload:")
            print(f"  Title: {uploads[-1].get('title')}")
            print(f"  URL:   {uploads[-1].get('youtube_url')}")
        return

    orchestrator = MonkeyBabaOrchestrator()

    if args.test_brain:
        log("CLI", "Testing Brain Provider Manager...")
        text, provider, fallback = orchestrator.brain.generate_text("Provide one sentence about space exploration.")
        log_success("CLI", f"Response from [{provider}] (fallback={fallback}): {text}")
        return

    # Normal execution
    orchestrator.run_pipeline(forced_topic=args.topic, dry_run=args.dry_run)

if __name__ == "__main__":
    main()
