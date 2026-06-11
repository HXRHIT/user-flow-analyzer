"""Application configuration via environment variables."""
import os
from pathlib import Path

DATA_DIR = Path(os.getenv("UFA_DATA_DIR", "./data")).resolve()
UPLOAD_DIR = DATA_DIR / "uploads"
JOBS_DIR = DATA_DIR / "jobs"

MAX_UPLOAD_MB = int(os.getenv("UFA_MAX_UPLOAD_MB", "500"))
MAX_DURATION_SEC = int(os.getenv("UFA_MAX_DURATION_SEC", "600"))
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".webm"}

# Frame extraction
SCENE_THRESHOLD = float(os.getenv("UFA_SCENE_THRESHOLD", "0.18"))
SAMPLE_INTERVAL_SEC = float(os.getenv("UFA_SAMPLE_INTERVAL", "2.0"))
FRAME_WIDTH = int(os.getenv("UFA_FRAME_WIDTH", "720"))

# Dedup
PHASH_DISTANCE = int(os.getenv("UFA_PHASH_DISTANCE", "8"))

# LLM
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
VISION_MODEL = os.getenv("UFA_VISION_MODEL", "claude-sonnet-4-6")
MAX_KEYFRAMES_TO_LLM = int(os.getenv("UFA_MAX_KEYFRAMES_TO_LLM", "60"))

# Privacy: blur detected sensitive regions in stored keyframes (account numbers, balances)
MASK_SENSITIVE = os.getenv("UFA_MASK_SENSITIVE", "true").lower() == "true"

for d in (UPLOAD_DIR, JOBS_DIR):
    d.mkdir(parents=True, exist_ok=True)
