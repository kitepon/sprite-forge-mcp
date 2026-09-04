"""Runtime settings for the Mac-side orchestrator; GPU code stays on fox."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = Path(os.environ.get("SPRITEFORGE_CACHE", ROOT / ".cache"))
COMFY_URL = os.environ.get("SPRITEFORGE_COMFY_URL", "http://192.168.1.11:8188").rstrip("/")
BOX_SSH = os.environ.get("SPRITEFORGE_BOX_SSH", "fox")
BOX_TRAIN = os.environ.get("SPRITEFORGE_BOX_TRAIN", r"C:\sf\train.py")
BOX_LORAS = os.environ.get("SPRITEFORGE_BOX_LORAS", r"C:\Users\kite_\ComfyUI\ComfyUI\models\loras")
EVENTS_PATH = CACHE / "events.ndjson"
JOBS_PATH = CACHE / "jobs"
