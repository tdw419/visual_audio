#!/usr/bin/env python3
"""L2-FILES gate — SUPPLY_ROUND8 layer 2 (ledger NEXT line, one sub-step
per tick). This tick's sub-step: `ls -l` columns (size/mtime), the first
item in the BK-15 receipt's L2 order:

    ls -l columns (FSTAB size/mtime) -> `files`/`ls` verb migration over
    0x13 -> mkdir/rmdir under allow-scoped root -> `>>` append (BK-7).

Legs (this tick's sub-step only — later sub-steps are separate commits):
  F1  `ls -l` shows NAME + SIZE + MTIME for 3 created files, sorted by
      name; sizes are byte-exact vs the written payloads; mtimes are
      parseable epoch-adjacent timestamps (not placeholders).
  F2  plain `ls` output is UNCHANGED (bare names) — the column format is
      opt-in via -l, L1's W3 leg contract holds.
  F3  non-vacuity: the -l formatter is not a passthrough — a mutated
      formatter that returns the bare listing fails F1's column legs.
      (Enforced by asserting on DISTINCT substrings: size digits and the
      iso mtime prefix must appear on the same line as each name; the
      bare listing contains neither.)
  F4  `ls -l` on an empty root returns "" (no header line invented).

RED-first: measured at HEAD 5d2f1265 pre-implementation — `ls -l` ignored
its argument entirely (turn() routed every `ls` to the bare listing), so
F1's column legs went RED (no size/mtime on any line). Tail recorded in
the landing commit and RECEIPT_L2_files.md.

SUB-STEP 2 legs (added when the verbs migrated over SYSCALL_FILE_LIST
0x13 — the BK-15 receipt's L2 order line):
  M1  the `files` verb exists and returns the SAME listing as `ls`
      (0x13 is the served arm for both spellings).
  M2  engine-served, no host fallback: with os.listdir poisoned to raise,
      `ls` STILL lists — the names came from the engine's 0x13 arm, not
      a host shim. (On the pre-landing tree this leg REDs: the host
      os.listdir shim is the only listing path.)
  M3  refusal propagates: `ls no_such_dir` returns ERR text — never a
      silent empty listing, never a host fallback to the cwd.

SUB-STEP 3 legs (mkdir/rmdir under allow-scoped root — this commit):
  D1  `mkdir d` creates a real directory under the session root; `ls d`
      is a silent empty listing (0x13 counts 0 entries — the directory
      is real and EMPTY, not a failed listing); `mkdir d` again refuses
      ERR:EEXIST. POSIX no-intermediate: `mkdir a/b` with `a` absent
      refuses (ERR:NOENT), then after `mkdir a` succeeds.
  D2  `rmdir d` removes the empty directory; a subsequent `ls d` returns
      ERR (the 0x13 arm's not-a-directory refusal, propagating through
      the shell's no-host-fallback contract). `rmdir missing` refuses
      ERR:NOENT — never silence.
  D3  `rmdir` on a NON-EMPTY directory refuses with ERR text (POSIX
      rmdir is the safe remover; ENOTEMPTY must not silently delete
      content). Non-vacuity for D2/D3: the same call on the pre-landing
      tree returns ERR:UNKNOWN_CMD (grammar ERR, not the structured
      refusal), so the legs cannot pass on an unimplemented surface.
  D4  escape containment: `mkdir ../escape` refuses (ERR text) and the
      host parent of the session root is unchanged after the attempt.
SUB-STEP 4 legs (append-mode write `>>` + rm -f quiet semantics):
  A1  `write >> file payload` (and `write file >> payload`) appends
      byte-exact vs whole-file read; `cat` reflects concatenated payloads.
  A2  `>>` on a nonexistent file creates it (POSIX append create).
  A3  `echo payload >> file` redirection appends output to the file;
      subsequent `cat` reads whole file back byte-exact.
  A4  `rm -f` quiet semantics: nonexistent file returns "", while bare
      `rm` returns ERR:NOENT:...
  A5  escape containment: `write >> ../escape payload` and `echo >>`
      refuse with ERR text; parent directory unchanged.
  A6  navigation & cwd: `cd sub` followed by bare `ls` lists cwd contents
      without prefix doubling; `pwd` returns exact directory without trailing `/.`;
      `cd ..` returns cleanly to root.

What the PASS does NOT prove: mkdir/rmdir are host-shim verbs under the
0x13 containment model (GLYPH_FS_ALLOW armed append-only with the
session root) — no engine mkdir/rmdir syscall arm exists yet (0x14/0x15
migration is later sub-step work, with spec/rot-guard/twin sync per the
TICKET_ITEM8 precedent); D-legs exercise the CPU engine's 0x13 arm for
listing, not the shader path; GLYPH_FS_ALLOW is process-environment
state shared with the engine's deny-by-default check — the armed root
persists for the process lifetime by design (append-only policy).
"""
from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
for _p in (str(REPO), str(REPO / "tools"), str(REPO / "experiments")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from experiments.glyph_l1_shell import GlyphL1Shell  # noqa: E402


_MTIME_RE = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}")


def _three_files(sh: GlyphL1Shell) -> None:
    # NOTE the dispatch payload convention: the shell forwards "e <text>"
    # (echo body), so the written file is " <text>" — one leading space,
    # byte-exact with L1's read-back contract (" hello l1"). Sizes:
    # " a"=2, " bbbbbbbb"=9, " cc"=3.
    sh.turn("write charlie.txt cc")
    sh.turn("write alpha.txt a")
    sh.turn("write beta.txt bbbbbbbb")  # sorts between the others


# ── F1: ls -l columns ─────────────────────────────────────────────────────

def test_f1_ls_l_columns_sorted_with_size_and_mtime():
    sh = GlyphL1Shell()
    _three_files(sh)
    out = sh.turn("ls -l")
    lines = out.splitlines()
    assert len(lines) == 3, out
    # sorted by name
    names = [ln.split()[-1] for ln in lines]
    assert names == ["alpha.txt", "beta.txt", "charlie.txt"], names
    by_name = {ln.split()[-1]: ln for ln in lines}
    # byte-exact sizes vs the payloads written through the shell
    assert by_name["alpha.txt"].split()[0] == "2"
    assert by_name["beta.txt"].split()[0] == "9"
    assert by_name["charlie.txt"].split()[0] == "3"
    # parseable mtime on every line, not a placeholder
    for ln in lines:
        m = _MTIME_RE.search(ln)
        assert m, f"no iso mtime in line: {ln!r}"
        parsed = time.mktime(time.strptime(m.group(0), "%Y-%m-%d %H:%M"))
        assert abs(parsed - time.time()) < 300, m.group(0)


# ── F2: plain ls is unchanged ─────────────────────────────────────────────

def test_f2_plain_ls_stays_bare_names():
    sh = GlyphL1Shell()
    _three_files(sh)
    out = sh.turn("ls")
    assert out.splitlines() == ["alpha.txt", "beta.txt", "charlie.txt"], out


# ── F3: the -l path is not a passthrough (non-vacuity) ────────────────────

def test_f3_long_form_differs_from_bare_listing():
    sh = GlyphL1Shell()
    _three_files(sh)
    long_out = sh.turn("ls -l")
    bare_out = sh.turn("ls")
    assert long_out != bare_out
    # every long line carries a size digit AND an mtime; no bare line does
    for ln in long_out.splitlines():
        assert re.search(r"\d+", ln.split()[0])
        assert _MTIME_RE.search(ln)


# ── F4: empty root ────────────────────────────────────────────────────────

def test_f4_ls_l_empty_root_is_silent():
    sh = GlyphL1Shell()
    assert sh.turn("ls -l") == ""


# ── M1: `files` verb = `ls` (sub-step 2, 0x13-served) ─────────────────────

def test_m1_files_verb_matches_ls():
    sh = GlyphL1Shell()
    _three_files(sh)
    assert sh.turn("files").splitlines() == ["alpha.txt", "beta.txt", "charlie.txt"]
    assert sh.turn("files") == sh.turn("ls")


# ── M2: engine-served listing, no host os.listdir fallback ────────────────

def test_m2_listing_survives_poisoned_shell_listdir(monkeypatch):
    sh = GlyphL1Shell()
    _three_files(sh)
    # Poison os.listdir ONLY when the caller frame is the shell module:
    # the shell must never enumerate host-side (the engine's 0x13 arm in
    # tools/glyph_isa_v2.py is the sanctioned os.listdir caller). On the
    # pre-landing tree the shell's host-shim listing called os.listdir
    # itself, so this leg REDs there.
    import inspect
    import os as _os
    shell_file = inspect.getsourcefile(GlyphL1Shell)
    real_listdir = _os.listdir

    def _poison(*a, **k):
        caller = inspect.stack()[1]
        if caller.filename == shell_file:
            raise AssertionError("shell-side host listdir fallback")
        return real_listdir(*a, **k)

    monkeypatch.setattr(_os, "listdir", _poison)
    out = sh.turn("ls")  # must come from the engine 0x13 arm
    assert out.splitlines() == ["alpha.txt", "beta.txt", "charlie.txt"], out


# ── M3: refusal propagates as ERR text, never a silent host fallback ──────

def test_m3_bad_dir_returns_err_text():
    sh = GlyphL1Shell()
    out = sh.turn("ls no_such_dir_anywhere")
    assert out.startswith("ERR:"), out


# ── D1: mkdir creates a real, empty, re-mkdir-refused directory (sub-step 3)

def test_d1_mkdir_creates_real_empty_dir_posix_semantics():
    sh = GlyphL1Shell()
    assert sh.turn("mkdir d1") == ""
    # the directory is REAL under the session root (host-visible fact)
    assert (Path(sh.session.root) / "d1").is_dir()
    # and EMPTY per the engine's own 0x13 listing (0 entries, silent)
    assert sh.turn("ls d1") == ""
    # POSIX EEXIST on the second mkdir
    assert sh.turn("mkdir d1") == "ERR:EEXIST:d1"
    # POSIX no-intermediate: a/b with a absent refuses, then works after
    # the parent exists (the engine's FILE_WRITE cannot create parents
    # either — mkdir holds to the same honest-refusal contract)
    assert sh.turn("mkdir a/b") == "ERR:NOENT:a/b"
    assert not (Path(sh.session.root) / "a").exists()
    assert sh.turn("mkdir a") == ""
    assert sh.turn("mkdir a/b") == ""
    assert (Path(sh.session.root) / "a" / "b").is_dir()


# ── D2: rmdir removes an empty dir; missing dir refuses; ls reflects both ─

def test_d2_rmdir_removes_empty_dir_missing_refused():
    sh = GlyphL1Shell()
    sh.turn("mkdir d1")
    assert sh.turn("rmdir d1") == ""
    assert not (Path(sh.session.root) / "d1").exists()
    # the listing arm's own refusal propagates: ls on the removed dir is
    # ERR text, never a silent empty listing (no host fallback)
    assert sh.turn("ls d1").startswith("ERR:")
    # missing dir refuses with the structured NOENT, never silence
    assert sh.turn("rmdir d1") == "ERR:NOENT:d1"


# ── D3: rmdir on a non-empty directory refuses and deletes NOTHING ────────

def test_d3_rmdir_nonempty_refuses_content_survives():
    sh = GlyphL1Shell()
    sh.turn("mkdir d1")
    sh.turn("write d1/f.txt keep")
    # POSIX rmdir is the SAFE remover: ENOTEMPTY refuses, content intact
    out = sh.turn("rmdir d1")
    assert out.startswith("ERR:"), out
    assert (Path(sh.session.root) / "d1" / "f.txt").is_file()
    assert sh.turn("cat d1/f.txt") == " keep"
    # the general remover still works for the cleanup path (rm semantics
    # unchanged from L1's W4 round-trip)
    assert sh.turn("rm d1/f.txt") == ""
    assert sh.turn("rmdir d1") == ""


# ── D4: escape containment — mkdir cannot reach outside the session root ──

def test_d4_mkdir_escape_refused_parent_unchanged():
    sh = GlyphL1Shell()
    parent = Path(sh.session.root).parent
    before = sorted(p.name for p in parent.iterdir())
    out = sh.turn("mkdir ../escape_probe_should_not_exist")
    assert out.startswith("ERR:"), out
    after = sorted(p.name for p in parent.iterdir())
    assert before == after, "host parent mutated by an escaped mkdir"
    assert not (parent / "escape_probe_should_not_exist").exists()


# ── D5: keep-leg — the 0x03/0x04 write/read surface did not drift ─────────

def test_d5_write_read_roundtrip_unchanged():
    sh = GlyphL1Shell()
    assert sh.turn("write keep.txt payload") == ""
    assert sh.turn("cat keep.txt") == " payload"
    assert sh.turn("ls").splitlines() == ["keep.txt"]


# ── A1: write >> append accumulates byte-exact payloads ──────────────────

def test_a1_write_append_accumulates_byte_exact():
    sh = GlyphL1Shell()
    assert sh.turn("write app.txt first") == ""
    assert sh.turn("cat app.txt") == " first"
    assert sh.turn("write >> app.txt second") == ""
    assert sh.turn("cat app.txt") == " first second"
    # Infix syntax support: write <file> >> <text>
    assert sh.turn("write app.txt >> third") == ""
    assert sh.turn("cat app.txt") == " first second third"


# ── A2: >> on nonexistent file creates it (POSIX append create) ──────────

def test_a2_append_creates_nonexistent_file():
    sh = GlyphL1Shell()
    assert sh.turn("write >> brand_new.txt init") == ""
    assert sh.turn("cat brand_new.txt") == " init"
    assert "brand_new.txt" in sh.turn("ls").splitlines()


# ── A3: echo >> redirection appends output to file ───────────────────────

def test_a3_echo_append_redirection():
    sh = GlyphL1Shell()
    assert sh.turn("echo hello >> streamed.txt") == ""
    assert sh.turn("cat streamed.txt") == " hello"
    assert sh.turn("echo world >> streamed.txt") == ""
    assert sh.turn("cat streamed.txt") == " hello world"


# ── A4: rm -f quiet semantics vs bare rm refusal ──────────────────────────

def test_a4_rm_f_quiet_semantics_vs_bare_rm_refusal():
    sh = GlyphL1Shell()
    # bare rm refuses missing file
    assert sh.turn("rm missing_file") == "ERR:NOENT:missing_file"
    # rm -f is quiet on missing file
    assert sh.turn("rm -f missing_file") == ""
    # rm -f removes existing file cleanly
    sh.turn("write temp.txt delme")
    assert (Path(sh.session.root) / "temp.txt").is_file()
    assert sh.turn("rm -f temp.txt") == ""
    assert not (Path(sh.session.root) / "temp.txt").exists()


# ── A5: escape containment — append cannot escape session root ────────────

def test_a5_append_escape_refused_parent_unchanged():
    sh = GlyphL1Shell()
    parent = Path(sh.session.root).parent
    before = sorted(p.name for p in parent.iterdir())
    out1 = sh.turn("write >> ../escape_probe payload")
    assert out1.startswith("ERR:"), out1
    out2 = sh.turn("echo payload >> ../escape_probe")
    assert out2.startswith("ERR:"), out2
    after = sorted(p.name for p in parent.iterdir())
    assert before == after, "host parent mutated by an escaped append"
    assert not (parent / "escape_probe").exists()
 
 
# ── A6: navigation & cwd — cd sub then bare ls without prefix doubling ────

def test_a6_cd_subdirectory_relative_ls_and_pwd_normalization():
    sh = GlyphL1Shell()
    assert sh.turn("mkdir nav_dir") == ""
    assert sh.turn("mkdir nav_dir/sub") == ""
    assert sh.turn("write nav_dir/sub/file.txt payload") == ""

    assert sh.turn("pwd") == sh.session.root
    assert sh.turn("cd nav_dir") == ""
    assert sh.turn("pwd") == os.path.join(sh.session.root, "nav_dir")

    # Bare ls in nav_dir must list "sub" via 0x13 without doubling prefix to nav_dir/nav_dir
    ls_out = sh.turn("ls")
    assert "sub" in ls_out.splitlines(), f"ls failed in subdirectory: {ls_out!r}"

    # cd further into child
    assert sh.turn("cd sub") == ""
    assert sh.turn("pwd") == os.path.join(sh.session.root, "nav_dir", "sub")
    assert "file.txt" in sh.turn("ls").splitlines()

    # cd .. back to nav_dir
    assert sh.turn("cd ..") == ""
    assert sh.turn("pwd") == os.path.join(sh.session.root, "nav_dir")

    # cd .. back to session root
    assert sh.turn("cd ..") == ""
    assert sh.turn("pwd") == sh.session.root

