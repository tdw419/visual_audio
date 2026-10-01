#!/usr/bin/env python3
"""probe_item21_staging_af3e.py — why does ERR:NOENT appear for the staged script?"""
import os
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO), str(REPO / "tools"), str(REPO / "experiments")]

from tools.stage_workbench import stage_workbench  # noqa: E402

SCRIPT = "scripts/glyph_build/fixture_synth.py"
STAGED = "scripts/fixture_synth.py"
root = stage_workbench({"root_name": "g21_probe2",
                        "entries": {STAGED: str(REPO / SCRIPT)}})
print("root:", root)
print("staged exists:", (root / STAGED).exists())
print("is symlink:", (root / STAGED).is_symlink())
if (root / STAGED).is_symlink():
    print("symlink target:", os.readlink(root / STAGED))
print("target exists:", (REPO / SCRIPT).exists())
shutil.rmtree(root, ignore_errors=True)
