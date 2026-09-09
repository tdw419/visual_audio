#!/usr/bin/env python3
"""tests/test_gh8c_canonical_replay.py — GH-8c oracle test: the determinism /
canonical-replay leg GH-8b deferred as "a separate item" (roadmap GH-8 row).

Roadmap item GH-8c (systems/GLYPH_SELF_HOSTING_ROADMAP.md, GH-8 row
companion item):

  Canonical replay determinism: the SAME program text bakes to BYTE-IDENTICAL
  images (md5), a run of the same image is REPRODUCIBLE (byte-identical
  post-run image + identical receipt digest), and re-running an already-run
  (post-run, saved) image is IDEMPOTENT (byte-identical post-replay image).
  This is what makes an md5 a valid receipt: "image hash X ⇒ run result Y".

Falsifiable gate:

1. test_gh8c_bake_is_deterministic
   fs_kernel_image(...) twice, independent tempdirs → both images' md5 equal.

2. test_gh8c_online_run_is_reproducible
   Two independent bake+run cycles from the same program text → post-run
   image md5s equal AND the two receipts agree on halted/faulted/steps/
   status_word_value/exit words. (steps is the instruction-count oracle: any
   nondeterministic state would shift it.)

3. test_gh8c_offline_replay_is_idempotent
   Run 1 on a fresh bake → save post-run image P1. Replays 2 and 3: fresh
   GlyphRunner on P1 → post images P2, P3. Assert md5(P1) == md5(P2) ==
   md5(P3) and the FSTAB/payload pix-words are unchanged by replay: the
   resident kernel + idempotent SYS 6 must converge to a FIXPOINT, so the
   image's md5 stays a canonical receipt across replays.

4. test_gh8c_zero_dev_imports — house property: runner.py stays clean.

RED proven: with a nondeterministic engine (mutated _fs_pix_write XORing a
random bit into persisted FS-window pixel writes) gates 2 and 3 fail while
gate 1 correctly still passes (bake does not execute the engine).
"""
from __future__ import annotations

import ast
import hashlib
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_gpt.atlas import build_default_atlas            # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner                   # noqa: E402
from tools.glyph_gpt.baker import fs_kernel_image                # noqa: E402

# ── GH-8/8b image ABI (mirrored from tests/test_gh8_fs.py — do not renumber) ──
GH8_FSTAB_WORD = 1024
GH8_DATA_WORD = 1044
GH8_READOUT_WORD = 752
GH8_EXIT_A = 703
GH8_EXIT_B = 723
EXIT_OK_A = 0xFEED0006
EXIT_OK_B = 0xFEED0007
KERNEL_OK = 0xCAFE0008
GH8_PAYLOAD0 = 0x11223344
GH8_PAYLOAD1 = 0x55667788


def _md5(arr: np.ndarray) -> str:
    return hashlib.md5(np.ascontiguousarray(arr).tobytes()).hexdigest()


def _bake_to(tmp: Path, name: str) -> Path:
    out = tmp / name
    fs_kernel_image(build_default_atlas(), min_rows=80, out_path=out)
    return out


def _receipt_digest(r: dict) -> tuple:
    return (r["halted"], r["faulted"], r["steps"],
            r["status_word_value"], r["memory"][GH8_EXIT_A],
            r["memory"][GH8_EXIT_B], r["memory"][GH8_READOUT_WORD],
            r["memory"][GH8_READOUT_WORD + 1])


def test_gh8c_bake_is_deterministic():
    """Same program text → byte-identical images (md5 receipt is stable)."""
    with tempfile.TemporaryDirectory() as da, tempfile.TemporaryDirectory() as db:
        pa = _bake_to(Path(da), "a.glyph.npy")
        pb = _bake_to(Path(db), "b.glyph.npy")
        ia = np.load(pa)
        ib = np.load(pb)
        assert ia.shape == ib.shape
        assert _md5(ia) == _md5(ib), (
            f"bake md5 {_md5(ia)} != {_md5(ib)} — baker is not deterministic")


def test_gh8c_online_run_is_reproducible():
    """Two independent bake+run cycles → identical post-run images and
    receipt digests (halted/faulted/steps/status/exits/readout)."""
    with tempfile.TemporaryDirectory() as da, tempfile.TemporaryDirectory() as db:
        posts, digests = [], []
        for d in (Path(da), Path(db)):
            runner = GlyphRunner(_bake_to(d, "img.glyph.npy"), ram_words=16384)
            r = runner.run(max_instructions=60000)
            assert r["halted"] is True and r["faulted"] is False, r
            posts.append(runner.image.copy())
            digests.append(_receipt_digest(r))
        assert _md5(posts[0]) == _md5(posts[1]), (
            "post-run images diverge — run is not reproducible")
        assert digests[0] == digests[1], f"receipts diverge: {digests[0]} vs {digests[1]}"
        # sanity: the run did the FS work (not vacuously identical zeros)
        assert digests[0] == (True, False, digests[0][2], KERNEL_OK,
                              EXIT_OK_A, EXIT_OK_B, GH8_PAYLOAD0, GH8_PAYLOAD1), digests[0]


def test_gh8c_offline_replay_is_idempotent():
    """THE canonical-replay gate: replaying an already-run image converges
    to a byte-identical fixpoint. Run 1 → P1; replay 2 on P1 → P2; replay 3
    on P2 → P3. md5(P1)==md5(P2)==md5(P3) proves replays neither drift nor
    rewrite state — the saved image's md5 stays a valid receipt."""
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        runner = GlyphRunner(_bake_to(d, "seed.glyph.npy"), ram_words=16384)
        r1 = runner.run(max_instructions=60000)
        assert r1["halted"] is True and r1["faulted"] is False, r1
        p1 = d / "p1.png"
        Image.fromarray(runner.image, "RGB").save(p1)
        img1 = np.array(Image.open(p1).convert("RGB"))

        def _replay(src: Path) -> np.ndarray:
            rp = GlyphRunner(src, ram_words=16384)
            r = rp.run(max_instructions=60000)
            assert r["halted"] is True, r.get("error", r)
            assert r["faulted"] is False, r
            return rp.image.copy()

        img2 = _replay(p1)
        p2 = d / "p2.png"
        Image.fromarray(img2, "RGB").save(p2)
        img3 = _replay(p2)
        assert _md5(img1) == _md5(img2) == _md5(img3), (
            f"replay drift: {_md5(img1)} vs {_md5(img2)} vs {_md5(img3)} — "
            "replay is not idempotent; image md5 is not a canonical receipt")


def test_gh8c_zero_dev_imports():
    src = (_REPO / "tools" / "glyph_gpt" / "runner.py").read_text()
    tree = ast.parse(src)
    forbidden = {"atlas", "spatial_builder", "synth", "generate",
                 "model", "tokenizer", "corpus", "train", "pack_dataset",
                 "baker"}
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        for n in names:
            for f in forbidden:
                assert f not in n, f"runner.py must not import '{n}'"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-s"]))
