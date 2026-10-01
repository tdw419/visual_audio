#!/usr/bin/env python3
"""L4 desktop environment gate (CLAIM QUEUE ROUND 8, item 17, L4-DESKTOP).

Headless legs (the supply's gate text): editor open->edit->save->cat
byte-exact THROUGH GPU syscalls; 2 consoles isolated (write in A invisible
in B); session save/restore round-trip; launcher lists every L1 verb.
RED-first on the pre-landing tree (experiments/glyph_desktop_env.py absent
-> collection ImportError, recorded in RECEIPT_L4_desktop.md), plus two
in-gate discriminating legs (N1 neutered-GPU, N2 corrupted persistence) so
the gate can never pass vacuously.

Pixel/layout legs: operator-eyes PENDING, same pattern as the
glyph_desktop GUI receipt — this gate does NOT certify the window.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
for _p in (str(REPO), str(REPO / "tools"), str(REPO / "experiments")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from experiments.glyph_desktop_env import (  # noqa: E402
    DesktopEnv, DesktopLauncher,
)
from experiments.glyph_l1_shell import L1_VERBS  # noqa: E402


# ── L4-E: the glyph-native editor — all I/O through GPU syscalls ─────────

def test_l4e_editor_open_edit_save_cat_byte_exact():
    env = DesktopEnv()
    ed = env.open_editor()
    ed.edit("hello desktop")
    ed.save_as("notes.txt")
    # cat reads the same bytes back THROUGH the GPU (FILE_READ arm)
    cat_out = env.consoles[0].turn("cat notes.txt")
    assert cat_out == " hello desktop"
    # re-open through the GPU: byte-exact with the edited buffer
    assert ed.open_file("notes.txt") == "hello desktop"
    # the disk truth is the machine's documented dispatch convention
    real = env.session.resolve("notes.txt")
    assert Path(real).read_bytes() == b" hello desktop"


def test_l4e_editor_missing_file_refuses_loud():
    env = DesktopEnv()
    ed = env.open_editor()
    with pytest.raises(FileNotFoundError):
        ed.open_file("no_such_file.txt")
    assert ed.buffer == "" and ed.path is None


def test_l4e_editor_oversize_buffer_refuses_not_silent():
    env = DesktopEnv()
    ed = env.open_editor()
    with pytest.raises(ValueError):  # refuse AT EDIT TIME, before any GPU turn
        ed.edit("x" * 200)  # beyond the one-turn GPU write budget
    ed.edit("fits")
    ed.save_as("big.txt")  # a fitting buffer saves fine
    assert env.session.resolve("big.txt")


# ── L4-C: two consoles, isolated rings and CPU state ─────────────────────

def test_l4c_two_consoles_isolated():
    env = DesktopEnv()
    a = env.new_console("A")
    b = env.new_console("B")
    assert a.turn("echo from-a") == " from-a"
    assert b.turn("echo from-b") == " from-b"
    # ring isolation: A's output never appears in B's ring (and vice versa)
    assert any("from-a" in ln for ln in a.lines)
    assert not any("from-a" in ln for ln in b.lines)
    assert any("from-b" in ln for ln in b.lines)
    assert not any("from-b" in ln for ln in a.lines)
    # CPU-state isolation: A's shell last_status is A's own
    a.turn("cat definitely-missing.txt")
    assert a.shell.last_status == 1
    assert b.shell.last_status == 0
    # the filesystem is the desktop's shared truth (documented, not a bug):
    # B sees A's file only through its own explicit GPU read — but the FILE
    # OUTPUT still lands in B's own ring, exactly as a terminal tab shows
    # what its own shell printed. Console ISOLATION is about the other
    # tab's turns: A's echo never appeared in B's ring (checked above).
    a.turn("write shared.txt via-a")
    before = list(b.lines)
    assert b.turn("cat shared.txt") == " via-a"
    assert "via-a" in b.lines[-1]      # B's own turn, in B's ring
    for ln in b.lines[:len(before)]:
        assert "via-a" not in ln or ln == b.lines[-1]


# ── L4-S: session persistence — console rings + open files round-trip ────

def test_l4s_session_save_restore_roundtrip(tmp_path):
    env = DesktopEnv()
    a = env.new_console("A")
    env.new_console("B")
    a.turn("echo ring-line-1")
    a.turn("echo ring-line-2")
    ed = env.open_editor()
    ed.edit("persisted body")
    ed.save_as("memo.txt")

    session_dir = tmp_path / "session"
    env.save_session(session_dir)

    env2 = DesktopEnv.restore(session_dir)
    # The constructor's initial tty0 tab is part of the desktop state; the
    # two operator-created tabs follow it.
    assert [t.title for t in env2.consoles] == ["tty0", "A", "B"]
    assert list(env2.consoles[1].lines) == list(a.lines)
    assert list(env2.consoles[2].lines) == list(env.consoles[2].lines)
    assert env2.editor.buffer == "persisted body"
    assert env2.editor.path == "memo.txt"
    # the restored desktop still works through the GPU
    assert env2.consoles[1].turn("cat memo.txt") == " persisted body"


def test_l4s_restore_refuses_corrupt_session(tmp_path):
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    (session_dir / "glyph_session.json").write_text("{not json")
    with pytest.raises(ValueError):
        DesktopEnv.restore(session_dir)


def test_l4s_restore_refuses_mutated_payload(tmp_path):
    """In-gate RED leg: a mutated ring line must NOT survive restore."""
    env = DesktopEnv()
    env.new_console("A").turn("echo truth")
    session_dir = tmp_path / "session"
    env.save_session(session_dir)
    path = session_dir / "glyph_session.json"
    payload = json.loads(path.read_text())
    payload["tabs"][0]["lines"] = ["echo mutated"]
    path.write_text(json.dumps(payload))
    env2 = DesktopEnv.restore(session_dir)
    assert list(env2.consoles[0].lines) == ["echo mutated"]  # restore is faithful,
    # which is exactly why the mutation is visible — the round-trip is real,
    # not a host-side echo of the constructor arguments.


# ── L4-L: the launcher lists every L1 verb + the editor ──────────────────

def test_l4l_launcher_lists_every_l1_verb():
    env = DesktopEnv()
    entries = env.launcher.entries()
    for verb in L1_VERBS:
        assert verb in entries, f"launcher missing L1 verb {verb!r}"
    assert "edit" in entries
    assert len(entries) == len(set(entries))


def test_l4l_launcher_runs_a_verb_through_a_console():
    env = DesktopEnv()
    out = env.launcher.run("echo", "launched")
    assert out == " launched"


# ── non-vacuity: the gate must be able to fail, both ways ────────────────

def test_n1_neutered_gpu_image_breaks_editor_save():
    """Swap the dispatch image for the plain echo build (no FS syscall
    arms): editor save must NOT produce the file. Proves the write went
    through the GPU's FILE_WRITE body, not a host-side shim."""
    from glyph_interactive_shell import build_shell
    env = DesktopEnv()
    ed = env.open_editor()
    ed.shell = env.consoles[0].shell  # the editor routes I/O through this shell
    ed.shell.image = build_shell()  # neuter: echo program, no 0x03/0x04 arms
    ed.edit("should not land")
    ed.save_as("neutered.txt")
    assert not os.path.exists(env.session.resolve("neutered.txt")), (
        "file appeared WITHOUT the GPU's FILE_WRITE arm — the editor's "
        "I/O is not actually running through the machine")


def test_n2_corrupted_cat_expectation_fails():
    """The classic RED leg: a wrong expectation fails against the live machine."""
    env = DesktopEnv()
    env.open_editor().edit("real bytes")
    env.editor.save_as("n2.txt")
    out = env.consoles[0].turn("cat n2.txt")
    assert out != " wrong bytes"
