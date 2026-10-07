#!/usr/bin/env python3
"""Local development API; uses a separate loopback Mongo database, never production data."""
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
for line in (root / ".env").read_text().splitlines():
    if line and not line.startswith("#"):
        key, value = line.split("=", 1)
        os.environ.setdefault(key, value)
os.environ.setdefault("MONGO_URI", "mongodb://127.0.0.1:27018/singularity_dev")
os.environ.setdefault("STATE_DIR", str(root / ".local-state"))
os.execv(sys.executable, [sys.executable, "-m", "uvicorn", "singularity.api:app", "--host", "127.0.0.1", "--port", "8000", "--no-access-log"])
