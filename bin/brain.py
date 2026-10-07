#!/usr/bin/env python3
"""Run from any working directory; use --root for a separate private workspace."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from workbrain.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
