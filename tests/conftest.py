"""Test harness path setup."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for entry in (ROOT, ROOT / "src"):
    text = str(entry)
    if text not in sys.path:
        sys.path.insert(0, text)
