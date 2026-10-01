#!/usr/bin/env python3
"""tests/test_syscall_corpus_capture.py — parser gates for tools/syscall_corpus/.

These tests consume the REAL archived raw traces under corpus/raw/, not
synthetic strings, so dialect drift in qemu-user -strace or guest strace is
caught against actual captured evidence. The two dialect traps pinned here
have already bitten once each (2026-09-16):
  - QEMU: payload-printed-after-args spans TWO lines ("write(...)OK\n" / " = 3")
  - guest strace: PID prefix + column-aligned returns ("2391  brk(NULL)   = ...")
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from tools.syscall_corpus.capture import parse_linux_strace, parse_qemu_strace  # noqa: E402

CORPUS = _REPO / "tools" / "syscall_corpus" / "corpus"


def _corpus_records(name: str) -> list[dict]:
    p = CORPUS / name
    if not p.exists():
        pytest.skip(f"corpus {name} not yet captured")
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


# ---------------------------------------------------------------------------
# QEMU user-mode dialect (rv64 leg)
# ---------------------------------------------------------------------------

def test_qemu_parse_file_lifecycle_matches_corpus():
    raw = (CORPUS / "raw" / "file_lifecycle.qemu-strace.txt").read_text()
    recs = parse_qemu_strace(raw)
    names = [r["name"] for r in recs]
    assert names == ["openat", "write", "fsync", "close", "openat", "read",
                     "close", "unlinkat", "brk", "write", "exit_group"]
    # flag decoding present on the create openat
    assert "O_CREAT" in recs[0]["args_raw"] and "O_TRUNC" in recs[0]["args_raw"]
    assert recs[0]["ret"] == 3          # fd
    assert recs[1]["ret"] == 23         # payload bytes
    assert recs[9]["ret"] == 3          # the OK\n write


def test_qemu_payload_continuation_is_one_record():
    """The two-line payload record must yield ONE syscall with the right ret."""
    raw = '999 write(1,0xdeadbeef,3)OK\n = 3\n999 exit_group(0)\n'
    recs = parse_qemu_strace(raw)
    assert len(recs) == 2
    assert recs[0]["name"] == "write"
    assert recs[0]["ret"] == 3
    assert recs[0]["payload"] == "OK"
    assert "ret" not in recs[1]         # exit_group has no return line


def test_qemu_corpus_records_agree_with_raw_parse():
    for rec in _corpus_records("rv64_syscalls.jsonl"):
        raw = (CORPUS / "raw" / f"{rec['fixture']}.qemu-strace.txt").read_text()
        assert len(rec["syscalls"]) == len(parse_qemu_strace(raw))
    # hello_write_exit measured by hand: rc 7, write then exit
    hello = next(r for r in _corpus_records("rv64_syscalls.jsonl")
                 if r["fixture"] == "hello_write_exit")
    assert hello["rc"] == 7
    assert [s["name"] for s in hello["syscalls"]] == ["write", "exit"]


# ---------------------------------------------------------------------------
# Linux strace dialect (guest leg)
# ---------------------------------------------------------------------------

def test_guest_pid_prefix_and_aligned_returns():
    """The regex must tolerate 'PID  name(args)  = ret' column alignment."""
    raw = ('2391  execve("/usr/bin/sh", ["sh", "-c", "x"], 0x7ffc /* 17 vars */) = 0\n'
           '2391  brk(NULL)                         = 0x55918b272000\n'
           '2391  access("/etc/ld.so.preload", R_OK) = -1 ENOENT (No such file or directory)\n'
           '2391  exit_group(0)                     = ?\n'
           '+++ exited with 0 +++\n')
    recs, rc = parse_linux_strace(raw)
    assert rc is None  # rc comes from the runner echo, not the trace
    assert [r["name"] for r in recs] == ["execve", "brk", "access", "exit_group"]
    assert recs[2]["ret"] == -1 and recs[2]["errno"] == "ENOENT"
    assert "ret" not in recs[3]


def test_guest_corpus_ls_tmp_parse_is_stable():
    ls = [r for r in _corpus_records("guest_syscalls.jsonl")
          if r["fixture"] == "ls_tmp"]
    if not ls:
        pytest.skip("ls_tmp record not yet captured")
    raw = (CORPUS / "raw" / "ls_tmp.linux-strace.txt").read_text()
    fresh, _ = parse_linux_strace(raw)
    # 261 = pre-hex-fix (lossy); 306 = +hex rets; 309 = +resumed-line pairs
    assert len(ls[0]["syscalls"]) == len(fresh) == 309
    assert fresh[-1]["name"] == "exit_group"


def test_guest_persist_probe_semantic_lifecycle():
    """The persistence probe must show the full create->write->read->unlink."""
    probe = [r for r in _corpus_records("guest_syscalls.jsonl")
             if r["fixture"] == "persist_probe"]
    if not probe:
        pytest.skip("persist_probe record not yet captured")
    names = [s["name"] for s in probe[0]["syscalls"]]
    assert "openat" in names and "write" in names and "unlinkat" in names
    # the marker string itself must appear in the archived raw trace
    raw = (CORPUS / "raw" / "persist_probe.linux-strace.txt").read_text()
    assert "persist-probe" in raw


# ---------------------------------------------------------------------------
# Hex-return dialect (regression: 2026-09-16 — brk(NULL) = 0x11000 was either
# dropped entirely (guest) or parsed as ret=0 off the leading digit (QEMU))
# ---------------------------------------------------------------------------

def test_qemu_hex_ret_is_ret_hex_not_decimal():
    raw = '999 brk(NULL) = 0x0000000000011000\n999 exit_group(0)\n'
    recs = parse_qemu_strace(raw)
    assert recs[0]["ret_hex"] == "0x0000000000011000"
    assert "ret" not in recs[0]


def test_guest_hex_ret_is_ret_hex_not_dropped():
    raw = '2391  brk(NULL)                         = 0x55918b272000\n'
    recs, _ = parse_linux_strace(raw)
    assert len(recs) == 1
    assert recs[0]["ret_hex"] == "0x55918b272000"
    assert "ret" not in recs[0]


def test_guest_resumed_pairs_are_records():
    """strace -f splits long syscalls: '<... vfork resumed>) = 2867' must count."""
    raw = ('2866  vfork( <unfinished ...>\n'
           '2867  execve("/bin/true", ["true"], 0x0 /* 2 vars */ <unfinished ...>\n'
           '2867  <... execve resumed>)             = 0\n'
           '2866  <... vfork resumed>)              = 2867\n'
           '2866  exit_group(0)                     = ?\n')
    recs, _ = parse_linux_strace(raw)
    names = [r["name"] for r in recs]
    assert names.count("vfork") == 1
    assert names.count("execve") == 1
    assert recs[names.index("vfork")]["ret"] == 2867
