#!/usr/bin/env python3
"""probe_bk44_red_af3e.py — BK-44 RED-first probe: the GLYPH_FS_ALLOW
attack-surface asymmetry, measured on the CURRENT tree (07eefcc2) with the
landed BK-39..BK-43 fence consults in it.

The research probe (probe_fs_allow_asym_af3e.py, HEAD d61dc186) predates
the landed fences: it stages the path at word 168 (OUT of the GO-2 tile
under the CURRENT geometry — see probe_bk42_geom_af3e), so every leg now
traps in the STAGING PARALLEL_ST (fault_addr=672=168*4, write_arm_fence)
before any syscall verdict. Re-measured here with the BK-42/43 fixture
geometry: in-tile staging at the 192..199 run, out-of-tile canary at 168.

Legs (all USER, tile (5,0,8,8), verdicts from HOST FILE CONTENTS + in-RAM
syscall rc, never handler stdout):
  A list_denied   — GLYPH_FS_ALLOW unset: 0x13 FILE_LIST '/tmp/b8d' ->
                    rc -1, dest zero (BK-15 containment live).
  B fw_no_env     — GLYPH_FS_ALLOW unset: 0x03 FILE_WRITE '/tmp/b8w',
                    in-tile data 'W','X' -> rc 0, host file b'WX'
                    (arbitrary host write, zero containment).
  C fr_no_env     — GLYPH_FS_ALLOW unset: 0x04 FILE_READ '/tmp/b8r'
                    (host fixture b'AUTUMN') -> rc 6, 'AU' lands in-tile
                    (arbitrary host read, zero containment).
  D list_allowed  — GLYPH_FS_ALLOW=/tmp/b8d: same program as A -> rc 1,
                    dest b'k1\0' (leg A's refusal is the containment,
                    not a dead harness).
  E ctl_st_out    — plain ST to out-of-tile 168 traps (E-K1 intact).

Run: python3 .builder_queue/probe_bk44_red_af3e.py
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
    W_MEM,
)
from tools.glyph_process import EXIT_FAULT, EXIT_OK, GlyphProcessTable  # noqa: E402

OM = OpcodeMapV2()
TILE_ROW, TILE_COL, TILE_H, TILE_W = 5, 0, 8, 8
OUT_TILE_WORD = TILE_ROW * W_MEM + TILE_COL + TILE_W   # 168: first OUT word
STAGE_WORD = 192                                        # in-tile run (path, 8B)
DATA_WORD = 224                                         # in-tile run 224..231
LIST_DEST = 224                                         # in-tile (same run, other legs)
RC_WORD = 231                                           # in-tile, past all dest blobs

DIR_PATH = "/tmp/b8"
DIR_ENTRY = "k1"
WRITE_PATH = "/tmp/b9"
READ_PATH = "/tmp/ba"
READ_FIXTURE = b"AUTUMN"
ENV_VAR = "GLYPH_FS_ALLOW"


def stage(word, data: bytes, term=True):
    out = []
    for i, b in enumerate(data):
        out += ["LDI r5 %d" % (word + i), "LDI r6 %d" % b,
                "PARALLEL_ST r5 r6 1"]
    if term:
        out += ["LDI r5 %d" % (word + len(data)), "LDI r6 0",
                "PARALLEL_ST r5 r6 1"]
    return out


def prog_sys(sysnum, r2, r3, path):
    lines = stage(STAGE_WORD, path)
    lines += ["LDI r1 %d" % STAGE_WORD,
              "LDI r2 %d" % r2,
              "LDI r3 %d" % r3,
              "SYSCALL r10 %d" % sysnum,
              "LDI r2 %d" % RC_WORD,
              "ST r2 r10",
              "HALT"]
    return lines


def run_case(label, prog, env, seed):
    img = GlyphAssemblerV2(OM).assemble(prog, width_instrs=8)
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
        "reason": (getattr(cpu, "fault_reason", None) or ""),
        "syscall_rc": "%08x" % (int(cpu.memory[RC_WORD]) & 0xFFFFFFFF),
        "list_dest": bytes(cpu.memory[LIST_DEST + i] & 0xFF
                           for i in range(4)).hex(),
        "data_word": int(cpu.memory[DATA_WORD]) & 0xFF,
        "host_write_file": (open(WRITE_PATH, "rb").read().hex()
                            if os.path.exists(WRITE_PATH) else None),
        "mode_super": int(cpu.mode) == MODE_SUPER,
    }


def main():
    os.makedirs(DIR_PATH, exist_ok=True)
    with open(os.path.join(DIR_PATH, DIR_ENTRY), "wb") as f:
        f.write(b"x")
    if os.path.exists(WRITE_PATH):
        os.unlink(WRITE_PATH)
    assert not os.path.exists(WRITE_PATH)
    with open(READ_PATH, "wb") as f:
        f.write(READ_FIXTURE)

    cases = [
        ("list_denied", prog_sys(19, LIST_DEST, 7, DIR_PATH.encode()), None,
         {LIST_DEST: 0, LIST_DEST + 1: 0, RC_WORD: 0}),
        ("fw_no_env", prog_sys(3, DATA_WORD, 2, WRITE_PATH.encode()), None,
         {DATA_WORD: 0x57, DATA_WORD + 1: 0x58, RC_WORD: 0}),
        ("fr_no_env", prog_sys(4, DATA_WORD, 7, READ_PATH.encode()), None,
         {DATA_WORD: 0, RC_WORD: 0}),
        ("list_allowed", prog_sys(19, LIST_DEST, 7, DIR_PATH.encode()),
         DIR_PATH, {LIST_DEST: 0, LIST_DEST + 1: 0, RC_WORD: 0}),
        ("ctl_st_out", ["LDI r2 %d" % OUT_TILE_WORD, "LDI r3 4660",
                        "ST r2 r3", "HALT"], None, {}),
    ]

    try:
        results = []
        for _ in range(3):
            if os.path.exists(WRITE_PATH):
                os.unlink(WRITE_PATH)
            results.append([run_case(l, p, e, s) for l, p, e, s in cases])
        for row in results[0]:
            print(row)
        print("deterministic:",
              all(results[i] == results[0] for i in range(1, 3)))

        r0 = {r["label"]: r for r in results[0]}
        a = r0["list_denied"]
        a_ok = (a["rc"] == EXIT_OK and a["syscall_rc"] == "ffffffff"
                and a["list_dest"] == "00000000")
        print("VERDICT list_denied:",
              "0x13 REFUSED with env unset (containment live)"
              if a_ok else f"CONTROL FAILED ({a})")
        b = r0["fw_no_env"]
        b_ok = (b["rc"] == EXIT_OK and b["syscall_rc"] == "00000000"
                and b["host_write_file"] == "5758")
        print("VERDICT fw_no_env:",
              "0x03 WROTE A HOST FILE with NO allow env (no root check)"
              if b_ok else f"not confirmed ({b})")
        c = r0["fr_no_env"]
        c_ok = (c["rc"] == EXIT_OK
                and c["syscall_rc"] == "%08x" % len(READ_FIXTURE)
                and c["data_word"] == ord("A"))
        print("VERDICT fr_no_env:",
              "0x04 READ A HOST FILE with NO allow env (no root check)"
              if c_ok else f"not confirmed ({c})")
        d = r0["list_allowed"]
        d_ok = (d["rc"] == EXIT_OK and d["syscall_rc"] == "00000001"
                and d["list_dest"].startswith(b"k1\0".hex()))
        print("VERDICT list_allowed:",
              "control green: same listing ALLOWED under its root"
              if d_ok else f"CONTROL FAILED ({d})")
        e = r0["ctl_st_out"]
        e_ok = e["faulted"] and e["fault_addr"] == OUT_TILE_WORD * 4
        print("VERDICT ctl_st_out:",
              "trapped as required (E-K1 intact)"
              if e_ok else f"NOT TRAPPED ({e})")

        if a_ok and b_ok and c_ok and d_ok and e_ok:
            print("ASYMMETRY MEASURED: under the identical empty env the "
                  "engine REFUSES listing /tmp/b8d (0x13, BK-15) while the "
                  "SAME task WRITES /tmp/b8w (0x03) and READS /tmp/b8r "
                  "(0x04) — the containment posture is inverted relative "
                  "to its stated rationale (glyph_isa_v2.py:576-579).")
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
