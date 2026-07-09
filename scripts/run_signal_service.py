#!/usr/bin/env python3
"""Run the 24/7 Telegram signal service."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.signal_service import main


if __name__ == "__main__":
    main()
