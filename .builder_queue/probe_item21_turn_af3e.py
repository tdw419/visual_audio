#!/usr/bin/env python3
"""probe_item21_turn_af3e.py — reproduce the turn-level NOENT."""
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO), str(REPO / "tools"), str(REPO / "experiments")]

from experiments.glyph_l1_shell import GlyphL1Shell, L1Session  # noqa: E402
from tools.stage_workbench import stage_workbench  # noqa: E402

SCRIPT = "scripts/glyph_build/fixture_synth.py"
STAGED = "scripts/fixture_synth.py"
root = stage_workbench({"root_name": "g21_probe3",
                        "entries": {STAGED: str(REPO / SCRIPT)}})
print("root:", root)
staged = root / STAGED
print("staged exists:", staged.exists(), "symlink:", staged.is_symlink())

sh = GlyphL1Shell(session=L1Session(root=str(root)))
print("session.root:", sh.session.root)
real = sh.session.expand(STAGED)
print("expand ->", real, "isfile:", Path(real).is_file())

out = sh.turn(f"python {STAGED} synth f1 5 seed1")
print("turn status:", sh.last_status, "out:", out[:120])

# try a bare filename too
out2 = sh.turn("python fixture_synth.py synth f1 5 seed1")
print("bare turn status:", sh.last_status, "out2:", out2[:120])
shutil.rmtree(root, ignore_errors=True)
