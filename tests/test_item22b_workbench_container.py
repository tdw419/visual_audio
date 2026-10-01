#!/usr/bin/env python3
"""tests/test_item22b_workbench_container.py — CLAIM QUEUE item 22b:
standalone one-file workbench container (round-11 addendum, items 22+23
merged: ONE staging mechanism, TWO verification contexts).

Item 22 (local dev) landed as BK-25 (tools/stage_workbench.py). Item 22b
is the STANDALONE CONTEXT: a single self-extracting .py file, stdlib-only
bootstrap, that unpacks its payload into the IDENTICAL session-root
layout (w.dat + bin/ + scripts/ + tests/, PATH_CAP-respected) and verifies
every payload file against its sha256 — loud refusal on corruption, never
silent. Doctrine (round-11): "everything in one file" = programs + data,
never the interpreter.

  G1  the container is a single stdlib-only file: every import in its AST
      is in the stdlib allowlist (no repo imports in the bootstrap).
  G2  running the container as a SUBPROCESS unpacks a layout-conforming
      root under a short base: WORKBENCH_ROOT=<path> on stdout, w.dat +
      bin/ + scripts/ + tests/ present, len(root + '/w.dat') <= the REAL
      PATH_CAP imported from experiments.glyph_l1_shell (the embedded
      cap must never drift from the engine's).
  G3  in-shell pytest from the CONTAINER-unpacked root passes (same
      hermetic fixtures as BK-25's G3) — the standalone context satisfies
      the Stage-2 gate, not just the dev context.
  G4  context equivalence: for the same manifest, the container-unpacked
      root carries the same files with byte-identical content as the
      BK-25 staged root (one staging contract, two contexts).
  N1  the gate discriminates:
      (a) a corrupted payload checksum -> container refuses loudly
          (nonzero exit, ERR:CHECKSUM on stderr), never unpacks silently;
      (b) an over-PATH_CAP base -> loud refusal (ERR:PATHCAP), the
          round-10/11 layout constraint preserved in the standalone
          context;
      (c) a truncated container file -> loud failure (nonzero exit), a
          partial payload can never half-unpack.

What the GREEN does NOT prove: the container runs the interpreter inside
the GPU image (Phase-2 doctrine: host CPython executes; the file carries
programs + data only), no WGSL twin exists, and PNG-carrier packing
(item 23's deferred format alternative) is untested here — the .py
self-extractor is the format decision this landing makes, per round-11
"Final call at landing, both formats satisfy the gate".
"""
from __future__ import annotations

import ast
import tempfile
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
for _p in (str(REPO), str(REPO / "tools"), str(REPO / "experiments")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from experiments.glyph_l1_shell import PATH_CAP, L1Session, GlyphL1Shell  # noqa: E402
from tools.build_workbench_container import build_container  # noqa: E402
from tools.stage_workbench import stage_workbench  # noqa: E402

STAGED_TESTS = ["tests/test_bk22_multifile_coreutils.py",
                "tests/test_item11_dispatch_grammar.py"]

# The container bootstrap may import ONLY these (all stdlib, present on
# any CPython >= 3.9 the container targets). Anything else in the AST is
# a contract breach: the standalone file must not lean on the repo.
STDLIB_ALLOWLIST = {
    "base64", "binascii", "hashlib", "json", "os", "sys", "shutil",
    "tempfile", "pathlib", "argparse",
}


def _manifest() -> dict:
    return {
        "root_name": "gwb_c22b",   # SHORT: FS-window path budget (see builder
                                   # --root-name help; 'glyph_workbench_c22b'
                                   # measured ERR:PATH at 49-char file paths)
        "entries": {rel: str(REPO / rel) for rel in STAGED_TESTS},
        "content": {"bin/README": "workbench container c22b\n"},
    }


def _container(tmp_path: Path, manifest: dict | None = None) -> Path:
    src = build_container(manifest or _manifest())
    p = tmp_path / "workbench_container.py"
    p.write_text(src)
    return p


def _run_container(container: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(container), *args],
        capture_output=True, text=True, timeout=120,
    )


def _short_base() -> str:
    """A PATH_CAP-safe base. pytest tmp_path is >90 chars by construction
    and can NEVER satisfy PATH_CAP=48 — the same measured constraint the
    BK-25 gate documented (_short_base in tools/stage_workbench.py)."""
    return tempfile.mkdtemp(prefix="c22b_")


@pytest.fixture(autouse=True)
def _no_leaked_root_env(monkeypatch):
    # item-21 finding 2: a leaked GLYPH_L1_ROOT silently re-roots every
    # shell in the process (glyph_l1_shell.py:175). Gates run without it.
    monkeypatch.delenv("GLYPH_L1_ROOT", raising=False)


# ── G1: single file, stdlib-only bootstrap ───────────────────────────────

def test_g1_container_is_stdlib_only(tmp_path):
    container = _container(tmp_path)
    tree = ast.parse(container.read_text())
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    offenders = roots - STDLIB_ALLOWLIST
    assert not offenders, f"container imports non-allowlist modules: {offenders}"


# ── G2: subprocess unpack builds a conforming, PATH_CAP-safe root ────────

def test_g2_subprocess_unpack_layout(tmp_path):
    container = _container(tmp_path)
    base = _short_base()           # short base; the container enforces the cap
    try:
        res = _run_container(container, "--base", base)
        assert res.returncode == 0, res.stderr
        lines = [ln for ln in res.stdout.splitlines() if ln.startswith("WORKBENCH_ROOT=")]
        assert len(lines) == 1, res.stdout
        root = Path(lines[0].split("=", 1)[1])
        assert root.is_dir() and root.parent == Path(base).resolve()
        assert len(str(root / "w.dat")) <= PATH_CAP, (
            len(str(root / "w.dat")), PATH_CAP)      # embedded cap matches engine
        assert (root / "w.dat").exists()
        for d in ("bin", "scripts", "tests"):
            assert (root / d).is_dir(), d
        for rel in STAGED_TESTS:
            assert (root / rel).is_file(), rel       # content copies, not symlinks
            assert not (root / rel).is_symlink()
        assert (root / "bin" / "README").read_text() == "workbench container c22b\n"
    finally:
        shutil.rmtree(base, ignore_errors=True)


# ── G3: in-shell pytest passes from the CONTAINER-unpacked root ──────────

def test_g3_inshell_pytest_from_container_root(tmp_path):
    container = _container(tmp_path)
    base = _short_base()
    try:
        res = _run_container(container, "--base", base)
        assert res.returncode == 0, res.stderr
        root = Path([ln for ln in res.stdout.splitlines()
                     if ln.startswith("WORKBENCH_ROOT=")][0].split("=", 1)[1])
        sh = GlyphL1Shell(session=L1Session(str(root)))
        out = sh.turn("python -m pytest -q "
                      "tests/test_bk22_multifile_coreutils.py "
                      "tests/test_item11_dispatch_grammar.py")
        assert "passed" in out, out
        assert " failed" not in out and " error" not in out, out
    finally:
        shutil.rmtree(base, ignore_errors=True)


# ── G4: context equivalence — same manifest, same files, same bytes ──────

def test_g4_context_equivalence_with_bk25(tmp_path):
    m = _manifest()
    container = _container(tmp_path, m)
    cbase, dbase = _short_base(), _short_base()
    res = _run_container(container, "--base", cbase)
    assert res.returncode == 0, res.stderr
    croot = Path([ln for ln in res.stdout.splitlines()
                  if ln.startswith("WORKBENCH_ROOT=")][0].split("=", 1)[1])
    droot = stage_workbench(m, base=dbase)              # dev context (BK-25)
    try:
        rels = STAGED_TESTS + ["bin/README", "w.dat"]
        for rel in rels:
            assert (croot / rel).exists() and (droot / rel).exists(), rel
            assert (croot / rel).read_bytes() == (droot / rel).read_bytes(), rel
    finally:
        shutil.rmtree(cbase, ignore_errors=True)
        shutil.rmtree(dbase, ignore_errors=True)


# ── N1: the gate discriminates ───────────────────────────────────────────

def test_n1a_corrupted_checksum_refused(tmp_path):
    container = _container(tmp_path)
    base = _short_base()   # short base so the checksum leg is what trips
    try:
        src = container.read_text()
        # Corrupt one sha256 hex digit inside the embedded payload literal.
        marker = '"sha256": "'
        i = src.index(marker) + len(marker)
        bad = "0" if src[i] != "0" else "1"
        container.write_text(src[:i] + bad + src[i + 1:])
        res = _run_container(container, "--base", base)
        assert res.returncode != 0, res.stdout
        assert "ERR:CHECKSUM" in res.stderr, res.stderr
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_n1b_long_base_refused(tmp_path):
    container = _container(tmp_path)
    long_base = tmp_path / ("L" * 80)              # > PATH_CAP by construction
    long_base.mkdir()
    res = _run_container(container, "--base", str(long_base))
    assert res.returncode != 0, res.stdout
    assert "ERR:PATHCAP" in res.stderr, res.stderr


def test_n1c_truncated_container_fails_loud(tmp_path):
    container = _container(tmp_path)
    src = container.read_text()
    # Cut INSIDE the payload literal: the closing ''' is dropped too, so
    # json.loads('r''' stays unterminated — the container is syntactically
    # broken and must die loudly (a cut at PAYLOAD-END alone would keep
    # the triple-quote terminator... actually the -4 removes it; a naive
    # cut would otherwise leave a valid-but-inert file that exits 0).
    cut = src.index("# PAYLOAD-END") - 4           # drop closing ''' as well
    container.write_text(src[:cut])
    res = _run_container(container, "--base", str(tmp_path / "b6"))
    assert res.returncode != 0, res.stdout
