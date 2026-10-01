#!/usr/bin/env python3
"""dbg_item20_budget_af3e.py — why does the shell-native grep fault at ~30 lines?

Measures the per-turn step count vs file size and locates the faulting
event. Read-only probe; results to stdout.
"""
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path("/home/jericho/projects/zion/projects/visual_audio")
sys.path[:0] = [str(REPO), str(REPO / "tools"), str(REPO / "experiments")]

from experiments.glyph_l1_shell import (  # noqa: E402
    L1Session, GlyphL1Shell, SHELLNATIVE_RUN_STEPS,
)


def probe(n_lines: int, root: Path) -> None:
    name = f"f{n_lines}.txt"
    (root / name).write_text(
        "".join(f"line{i:03d}xxxxxxxxxxxxxxxx\n" for i in range(n_lines)))
    s = GlyphL1Shell(session=L1Session(root=str(root)))

    from tools.glyph_gpt import runner as rmod
    orig = rmod.GlyphRunner.run
    info = {}

    def spy(self, **kw):
        r = orig(self, **kw)
        info.update({k: v for k, v in r.items() if not isinstance(v, list)})
        return r

    rmod.GlyphRunner.run = spy  # type: ignore[assignment]
    try:
        out = s.turn(f"grep line {name}")
    finally:
        rmod.GlyphRunner.run = orig
    print(f"lines={n_lines:4d} halted={info.get('halted')} "
          f"faulted={info.get('faulted')} steps={info.get('steps')} "
          f"status_word={info.get('status_word_value')} out={out[:40]!r}")


if __name__ == "__main__":
    root = Path(tempfile.mkdtemp(prefix="g20budget_"))
    try:
        for n in (1, 5, 10, 15, 20, 24, 25, 26, 28, 30, 50, 100):
            probe(n, root)
    finally:
        shutil.rmtree(root, ignore_errors=True)
