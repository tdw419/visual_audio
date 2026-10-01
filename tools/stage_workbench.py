#!/usr/bin/env python3
"""tools/stage_workbench.py — the Workbench Session Root staging primitive
(items 22+23 merged, PRODUCT_LANE_STATE.md ROUND 11 ADDENDUM).

ONE mechanism, TWO verification contexts:
  - item 22 (local dev): stage tests + scripts into a SHORT-path session
    root (PATH_CAP=48 at experiments/glyph_l1_shell.py:85) so the L1 shell
    can boot bound to it and run `python -m pytest -q` INSIDE the shell.
  - item 23 (container): the same manifest shape is what a one-file
    container payload carries; unpack_manifest() materializes it into the
    IDENTICAL layout (content entries instead of host-path symlinks).

Layout contract (asserted, not assumed — the gate pins it):
  <root>/w.dat       FS-window arm (seed write path)
  <root>/bin/        glyph dispatch image, atlas/LUTs (empty placeholder)
  <root>/scripts/    builder python scripts
  <root>/tests/      staged pytest fixtures

PATH_CAP is a LAYOUT CONSTRAINT, not a bug (round-11 addendum DECISIONS):
any root whose w.dat seed path exceeds PATH_CAP-1 is REFUSED here, loudly,
at staging time.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
if str(_REPO / "experiments") not in sys.path:
    sys.path.insert(0, str(_REPO / "experiments"))

from experiments.glyph_l1_shell import PATH_CAP  # noqa: E402

WORKBENCH_PREFIX = "glyph_workbench_"


def _check_path_cap(root: Path) -> None:
    seed = str(root / "w.dat")
    if len(seed) > PATH_CAP - 1:
        raise ValueError(
            f"workbench root {root} violates PATH_CAP: seed path "
            f"{seed!r} is {len(seed)} bytes, cap {PATH_CAP - 1} "
            f"(experiments/glyph_l1_shell.py:85; round-10-addendum "
            f"measured constraint). Use a SHORTER base directory.")


def _layout(root: Path) -> None:
    for d in ("bin", "scripts", "tests"):
        (root / d).mkdir(parents=True, exist_ok=True)


def _stage_entries(root: Path, entries: dict) -> None:
    # Staged tests import the shell as `experiments.glyph_l1_shell` — the
    # session root itself must be importable as a package source, so the
    # staging contract plants experiments/__init__-style namespace markers
    # for every top-level package the lane-family tests import. The shell's
    # python shim already puts the session root FIRST on PYTHONPATH
    # (glyph_l1_shell.py:958), so plain package dirs here are enough.
    for pkg in ("experiments", "tools", "src"):
        (root / pkg).mkdir(parents=True, exist_ok=True)
    for rel, src in entries.items():
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if src is None:
            continue                    # content-only entry (see manifest)
        src = Path(src)
        if not src.exists():
            raise FileNotFoundError(f"manifest entry {rel!r}: missing {src}")
        if dest.exists() or dest.is_symlink():
            dest.unlink()
        # symlinks keep a single copy of the fixture; pytest resolves
        # __file__ through realpath back to the repo, which is correct for
        # staged tests (their own REPO anchors stay valid).
        dest.symlink_to(src.resolve())


def _assert_layout(root: Path) -> None:
    assert (root / "w.dat").exists(), f"{root}/w.dat missing"
    for d in ("bin", "scripts", "tests"):
        assert (root / d).is_dir(), f"{root}/{d} missing"


def _short_base() -> Path:
    """A SHORT staging base under /tmp (the round-11 layout's
    /tmp/glyph_workbench_XXXX). pytest's tmp_path is typically >90 chars
    and can NEVER satisfy PATH_CAP — measured at gate authoring time."""
    import tempfile
    return Path(tempfile.mkdtemp(prefix="gwb_"))


def stage_workbench(manifest: dict, base: str | Path | None = None,
                    make_wdat: bool = True) -> Path:
    """Stage a workbench session root under `base` from `manifest`.

    manifest = {
      "root_name": str,                  # dir name under base
      "entries": {rel_path: host_path},  # symlinked into the root
      "content": {rel_path: str},        # OPTIONAL literal files
    }
    base=None (recommended) picks a short /tmp staging dir — the ONLY
    reliably PATH_CAP-safe choice (see _short_base).
    Returns the root Path. Raises ValueError on PATH_CAP violation.
    """
    base = Path(base) if base is not None else _short_base()
    root = base / manifest["root_name"]
    _check_path_cap(root)
    if root.exists():
        shutil.rmtree(root)
    _layout(root)
    if make_wdat:
        (root / "w.dat").write_bytes(b"\0" * 8)
    _stage_entries(root, manifest.get("entries", {}))
    for rel, text in manifest.get("content", {}).items():
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text)
    _assert_layout(root)
    return root


def unpack_manifest(manifest: dict, base: str | Path | None = None) -> Path:
    """Item-23 context: materialize a container payload manifest into the
    IDENTICAL workbench layout (content entries, no host dependencies).
    Any entries that carry host paths are staged as copies (a container
    payload must not depend on the staging machine's tree)."""
    base = Path(base) if base is not None else _short_base()
    root = base / manifest["root_name"]
    _check_path_cap(root)
    if root.exists():
        shutil.rmtree(root)
    _layout(root)
    (root / "w.dat").write_bytes(b"\0" * 8)
    for pkg in ("experiments", "tools", "src"):   # import-root contract
        (root / pkg).mkdir(parents=True, exist_ok=True)
    for rel, src in manifest.get("entries", {}).items():
        if src is None:
            continue
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
    for rel, text in manifest.get("content", {}).items():
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text)
    _assert_layout(root)
    return root


if __name__ == "__main__":
    # smoke: stage an empty workbench and print its path
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        r = stage_workbench({"root_name": WORKBENCH_PREFIX + "smoke",
                             "entries": {}}, d)
        print(r)
