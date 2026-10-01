#!/usr/bin/env python3
"""probe_fs_allow_asym_af3e.py — Phase 1c research (BK-44 candidate): the
GLYPH_FS_ALLOW attack-surface ASYMMETRY, left explicitly unmeasured by
RESEARCH_fw_exfil_path_read.md:115-117: "no GLYPH_FS_ALLOW-style allow-root
check exists for 0x03 (unlike 0x13 FILE_LIST, :1779-1786) — this is a
source-read observation, not a measured attack-surface diff."

BK-15's landing comment states the containment RATIONALE
(glyph_isa_v2.py:576-579): "enumeration is the more invasive primitive, it
must not be cheaper to reach than RUN". If 0x03 FILE_WRITE and 0x04
FILE_READ have NO root check at all (source-read: no _get_fs_allow_roots
consult in either handler, :1462-1506 / :1508-1551), then the posture is
INVERTED: the two primitives that destroy host files and exfiltrate host
file CONTENT are strictly cheaper to reach than the one that only names
them. BK-42 measured write-to-arbitrary-path but never in A/B contrast
with 0x13 under the SAME env in one process; BK-40's 0x04 leg was
documented under GLYPH_FS_ALLOW=/tmp (env relevance never isolated).
This probe measures the diff directly:

Cases (all USER, tile (5,0,8,8), harness = the landed item-29 containment
path GlyphProcessTable.spawn; verdicts from HOST FILE CONTENTS + in-RAM
syscall return codes, never handler stdout):
  A list_denied    — GLYPH_FS_ALLOW unset: 0x13 FILE_LIST '/tmp/b7d' ->
                     rc -1 (refused), dest bytes stay zero. Containment
                     live; the gate this lane itself landed.
  B fw_no_env      — GLYPH_FS_ALLOW unset: 0x03 FILE_WRITE '/tmp/b7w',
                     in-tile data 'W','X' -> rc 0, host file contains
                     b'WX'. Arbitrary host-file WRITE, zero containment.
  C fr_no_env      — GLYPH_FS_ALLOW unset: 0x04 FILE_READ '/tmp/b7r'
                     (host fixture b'AUTUMN'), dest = OUT-of-tile word
                     168 -> rc = 6, 'A','U' land at 168/169. Arbitrary
                     host-file READ with zero containment, AND it is a
                     fence-blind out-of-tile RAM write arm (BK-40's L2
                     shape re-measured with the env isolation this time).
  D list_allowed   — GLYPH_FS_ALLOW=/tmp/b7d: same program as A ->
                     rc = 1 (entry count), dest = b'k1\\0'. Control: leg
                     A's refusal is the containment, not a broken harness.
  E ctl_st_out     — plain ST to out-of-tile 168 must TRAP (E-K1
                     baseline, fault_addr = 168*4 = 672).

Expected (if the source-read is right): A refused while B and C succeed
under the identical (empty) env, D green — the measured asymmetry.

GEOMETRY (the documented trap class): tile rows 5..11 x cols 0..7; staged
paths are 9 bytes (8-char path + NUL) at words 160..168-prefix -> 27
staging instructions + 7 tail = 34 < 40, clear of the PARALLEL_ST
write-through mirror row 5 = instruction slots 40..47. Listing dest
words 192..194 (in-tile row 6), rc word 198 (in-tile), read dest 168
(out-of-tile row 5 col 8), data words 196/197 (in-tile).

Fixture hygiene: private dir /tmp/b7d with exactly one file 'k1' (deterministic
listing); /tmp/b7w unlinked + asserted absent before every leg; /tmp/b7r
rewritten each leg; rc and dest words zero-seeded. GLYPH_FS_ALLOW is
popped/set explicitly around every wait() and restored after.

Determinism: 3 internal runs, byte-identical results blob, md5 printed.
Run: python3 .builder_queue/probe_fs_allow_asym_af3e.py
"""
import hashlib
import os
import shutil
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from tools.glyph_isa_v2 import (  # noqa: E402
    GlyphAssemblerV2,
    MODE_SUPER,
    OpcodeMapV2,
    TILE_H_ADDR,
)
from tools.glyph_process import EXIT_FAULT, EXIT_OK, GlyphProcessTable  # noqa: E402

OM = OpcodeMapV2()
TILE_ROW, TILE_COL, TILE_H, TILE_W = 5, 0, 8, 8
STAGE_WORD = 160
LIST_DEST = 192                      # in-tile (row 6 col 0)
RC_WORD = 198                        # in-tile (row 6 col 6)
DATA_WORD = 196                      # in-tile (row 6 col 4)
READ_DEST = 168                      # OUT-of-tile (row 5 col 8)
TILE_H_WORD = TILE_H_ADDR >> 2

DIR_PATH = "/tmp/b7d"
DIR_ENTRY = "k1"
WRITE_PATH = "/tmp/b7w"
READ_PATH = "/tmp/b7r"
READ_FIXTURE = b"AUTUMN"
ALLOW_ROOT = DIR_PATH

ENV_VAR = "GLYPH_FS_ALLOW"


def stage_bytes(byte_vals, word=STAGE_WORD):
    lines = []
    for i, b in enumerate(byte_vals):
        lines += ["LDI r5 %d" % (word + i), "LDI r6 %d" % b,
                  "PARALLEL_ST r5 r6 1"]
    return lines


def prog_path_tail(path_bytes, sysnum, *tail_regs):
    """Stage path (each byte one word), issue SYSCALL sysnum with
    r1=path_addr and r2/r3 from tail_regs (addr, len-or-max), park the
    syscall return code in RC_WORD, HALT."""
    assert path_bytes.endswith(b"\x00") and len(path_bytes) <= 9
    lines = stage_bytes(path_bytes)
    regs = ["r1 %d" % STAGE_WORD]
    reg_names = ["r2", "r3"]
    for i, val in enumerate(tail_regs):
        regs.append("%s %d" % (reg_names[i], val))
    for spec in regs:
        lines.append("LDI %s" % spec)
    lines += ["LDI r17 %d" % sysnum,
              "SYSCALL r10 %d" % sysnum,
              "LDI r2 %d" % RC_WORD,
              "ST r2 r10",
              "HALT"]
    return lines


def run_case(label, prog_lines, env, seed):
    img = GlyphAssemblerV2(OM).assemble(prog_lines, width_instrs=8)
    table = GlyphProcessTable()
    pid = table.spawn(img, name=label, tile=(TILE_ROW, TILE_COL, TILE_H, TILE_W))
    cpu = table.tasks[pid]["cpu"]
    for addr, val in seed.items():
        cpu.memory[addr] = val & 0xFFFFFFFF
    old = os.environ.get(ENV_VAR)
    try:
        if env is None:
            os.environ.pop(ENV_VAR, None)
        else:
            os.environ[ENV_VAR] = env
        rc = table.wait(pid)
    finally:
        if old is None:
            os.environ.pop(ENV_VAR, None)
        else:
            os.environ[ENV_VAR] = old
    return {
        "label": label,
        "rc": rc,
        "rc_name": "EXIT_OK" if rc == EXIT_OK else
                   ("EXIT_FAULT" if rc == EXIT_FAULT else f"?{rc}"),
        "faulted": bool(cpu.faulted),
        "fault_addr": int(getattr(cpu, "fault_addr", 0) or 0),
        "syscall_rc": "%08x" % (int(cpu.memory[RC_WORD]) & 0xFFFFFFFF),
        "list_dest": bytes(cpu.memory[LIST_DEST + i] & 0xFF
                           for i in range(4)).hex(),
        "read_dest_ab": bytes(cpu.memory[READ_DEST + i] & 0xFF
                              for i in range(2)).hex(),
        "host_write_file": (open(WRITE_PATH, "rb").read().hex()
                            if os.path.exists(WRITE_PATH) else None),
        "tile_h_word": int(cpu.memory[TILE_H_WORD]),
        "mode_super": int(cpu.mode) == MODE_SUPER,
    }


def main():
    # fixtures: private deterministic listing dir + read fixture
    os.makedirs(DIR_PATH, exist_ok=True)
    with open(os.path.join(DIR_PATH, DIR_ENTRY), "wb") as f:
        f.write(b"x")
    if os.path.exists(WRITE_PATH):
        os.unlink(WRITE_PATH)
    assert not os.path.exists(WRITE_PATH)
    with open(READ_PATH, "wb") as f:
        f.write(READ_FIXTURE)

    p_dir = DIR_PATH.encode() + b"\x00"
    p_write = WRITE_PATH.encode() + b"\x00"
    p_read = READ_PATH.encode() + b"\x00"

    cases = [
        ("list_denied",
         prog_path_tail(p_dir, 19, LIST_DEST, 64),
         None,
         {LIST_DEST: 0, LIST_DEST + 1: 0, LIST_DEST + 2: 0, RC_WORD: 0}),
        ("fw_no_env",
         prog_path_tail(p_write, 3, DATA_WORD, 2),
         None,
         {DATA_WORD: 0x57, DATA_WORD + 1: 0x58, RC_WORD: 0}),
        ("fr_no_env",
         prog_path_tail(p_read, 4, READ_DEST, 64),
         None,
         {READ_DEST: 0, READ_DEST + 1: 0, RC_WORD: 0}),
        ("list_allowed",
         prog_path_tail(p_dir, 19, LIST_DEST, 64),
         ALLOW_ROOT,
         {LIST_DEST: 0, LIST_DEST + 1: 0, LIST_DEST + 2: 0, RC_WORD: 0}),
        ("ctl_st_out",
         ["LDI r2 %d" % READ_DEST, "LDI r3 4660", "ST r2 r3", "HALT"],
         None,
         {}),
    ]

    try:
        results = []
        for _ in range(3):
            for path in (WRITE_PATH,):
                if os.path.exists(path):
                    os.unlink(path)
            results.append([run_case(l, p, e, s) for l, p, e, s in cases])
        for r5 in results:
            for r in r5:
                print(r)
        print("deterministic:",
              all(results[i] == results[0] for i in range(1, 3)))

        r0 = {r["label"]: r for r in results[0]}
        a = r0["list_denied"]
        a_ok = a["syscall_rc"] == "ffffffff" and a["list_dest"] == "00000000"
        print("VERDICT list_denied:",
              "0x13 REFUSED with env unset (containment live)"
              if a_ok else f"CONTROL FAILED ({a})")
        b = r0["fw_no_env"]
        b_ok = (b["syscall_rc"] == "00000000"
                and b["host_write_file"] == bytes([0x57, 0x58]).hex())
        print("VERDICT fw_no_env:",
              "0x03 WROTE A HOST FILE with NO allow env (no root check)"
              if b_ok else f"not confirmed ({b})")
        c = r0["fr_no_env"]
        c_ok = (c["syscall_rc"] == "%08x" % len(READ_FIXTURE)
                and c["read_dest_ab"] == b"AU".hex())
        print("VERDICT fr_no_env:",
              "0x04 READ A HOST FILE with NO allow env INTO OUT-OF-TILE RAM"
              if c_ok else f"not confirmed ({c})")
        d = r0["list_allowed"]
        d_ok = (d["syscall_rc"] == "00000001"
                and d["list_dest"].startswith(b"k1\0".hex()))
        print("VERDICT list_allowed:",
              "control green: same listing ALLOWED under its root"
              if d_ok else f"CONTROL FAILED ({d})")
        e = r0["ctl_st_out"]
        e_ok = e["faulted"] and e["fault_addr"] == READ_DEST * 4
        print("VERDICT ctl_st_out:",
              "trapped as required (E-K1 intact)"
              if e_ok else f"NOT TRAPPED ({e})")

        if a_ok and b_ok and c_ok and d_ok and e_ok:
            print("ASYMMETRY MEASURED: under the identical empty env the "
                  "engine REFUSES listing /tmp/b7d (0x13) while the SAME "
                  "task WRITES /tmp/b7w (0x03) and READS /tmp/b7r into "
                  "out-of-tile RAM (0x04) — the containment posture is "
                  "inverted relative to its stated rationale "
                  "(glyph_isa_v2.py:576-579).")
        else:
            print("ASYMMETRY NOT FULLY CONFIRMED (see per-leg verdicts)")

        blob = repr(results[0]).encode()
        print("results_md5:", hashlib.md5(blob).hexdigest())
    finally:
        for p in (WRITE_PATH, READ_PATH, os.path.join(DIR_PATH, DIR_ENTRY)):
            try:
                os.unlink(p)
            except OSError:
                pass
        try:
            os.rmdir(DIR_PATH)
        except OSError:
            shutil.rmtree(DIR_PATH, ignore_errors=True)


if __name__ == "__main__":
    main()
