#!/usr/bin/env python3
"""probe_fw_exfil_af3e.py — Phase 1c research (BK-42 candidate): the 0x03
FILE_WRITE EXFILTRATION side, left explicitly unprobed by the BK-40 tick
(RESEARCH_syscall_fence_bypass.md:124: "No claim about 0x03 FILE_WRITE's
EXFILTRATION side (guest RAM -> host ...)") and still open in
RESEARCH_ksys_pc_self_arm.md:102.

BK-40 measured the syscall WRITE arms (0x02/0x04/0x13/0x11) landing bytes
into out-of-tile GUEST RAM. This probe measures the other direction: can
a USER task confined to tile (5,0,8,8) move guest RAM bytes into a HOST
file it names itself? The handler (glyph_isa_v2.py:1462-1506) reads data
from self.memory[data_addr..] with NO _addr_in_box consult and writes via
open(path, "wb") — the sink is the HOST filesystem, outside the substrate
entirely. The handler catches all exceptions and returns -1 into r10, so
every verdict is taken from HOST FILE CONTENTS, never from exit codes.

Tile geometry (the trap BK-40's probe documents): tile rows 5..11 x cols
0..7 => in-tile words are 160..167, 192..199, 224..231, ... (row-major,
W_MEM=32). Word 168 = row 5 col 8 = FIRST WORD OUTSIDE the tile.

PROBE-DESIGN DISCLOSURE (drafts caught before any finding recorded):
  Draft 1: (a) 14-byte paths -> 48 instructions; the PARALLEL_ST write-
  through pixel mirror (glyph_isa_v2.py:1291-1295) hit pixel 160 = row 5
  = instructions 40-47, i.e. staging overwrote the program's own tail
  mid-run — the exact trap BK-40 documents; (b) a 2-byte canary packed
  into ONE word while the handler reads ONE BYTE PER WORD.
  Draft 2: (a) paths staged WITHOUT a NUL terminator — _read_path
  (glyph_isa_v2.py:1393-1408) decoded past word 167 INTO the out-of-tile
  canary words and built the filename '/tmp/b4aFK' (open-spy proven);
  the exfil fired but landed at an unexpected host path. This accident
  is itself a FINDING and was promoted to leg fw_path_read; (b) the
  path terminator staged at word 168 clobbered a canary seeded at 168 —
  canary moved to 172; (c) the LD-stage leg stored to word 176 = row 5
  col 16 — OUTSIDE the 8-wide tile — and trapped (E-K1 correctly fired);
  in-tile stage word moved to 192 (row 6 col 0).

Cases (all USER, tile armed, path staged at in-tile 160..167, terminator
0 at word 168, mirror pixel 160 = instruction 40, past all programs):
  fw_ram_out   — canary bytes seeded HOST-side at OUT-of-tile words
                 172/173 ('F','K'); FILE_WRITE data_addr=172 len 2
                 path /tmp/b4a. Full exfil chain: fence-blind handler
                 read + host-file sink.
  fw_ld_stage  — LD the out-of-tile canary word 172 (BK-38 primitive),
                 ST it in-tile to 192, FILE_WRITE from 192 len 1 path
                 /tmp/b4b. Composite: exfil fed by the LD read arm (in
                 case the handler's data view were fenced later).
  fw_path_read — path staged '/tmp/b4d' with NO terminator; canary
                 bytes 'X','Y' seeded at out-of-tile 168/169; FILE_WRITE
                 from in-tile 196 (byte 'Z') -> the host file must be
                 created at '/tmp/b4dXY' containing b'Z': _read_path
                 itself walks out of the tile while decoding the
                 filename (cross-fence read via the syscall PATH
                 argument, not via LD).
  fw_ctl_in    — non-vacuity: data in-tile at 196/197, path /tmp/b4c ->
                 b'FK'. If the handler were neutered this fails first.
  ctl_st_out   — plain ST to out-of-tile 172 must TRAP (E-K1 baseline,
                 fault_addr = 172*4 = 688).

Fixture hygiene: every case's expected host file(s) are unlinked BEFORE
the run and asserted absent — stale content cannot false-positive.

Determinism: 3 internal runs, byte-identical results blob, md5 printed.
Run: python3 .builder_queue/probe_fw_exfil_af3e.py
"""
import hashlib
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from tools.glyph_isa_v2 import (  # noqa: E402
    GlyphAssemblerV2,
    MODE_SUPER,
    OpcodeMapV2,
    TILE_H_ADDR,
    W_MEM,
)
from tools.glyph_process import EXIT_FAULT, EXIT_OK, GlyphProcessTable  # noqa: E402

OM = OpcodeMapV2()
TILE_ROW, TILE_COL, TILE_H, TILE_W = 5, 0, 8, 8
STAGE_WORD = 160                    # in-tile row 5 col 0: path staging
TERM_WORD = 168                     # first OUT-of-tile word (row 5 col 8)
CANARY_WORD = 172                   # out-of-tile (row 5 col 12)
LD_STAGE_WORD = 192                 # in-tile (row 6 col 0)
CTL_WORD = 196                      # in-tile (row 6 col 4)
TILE_H_WORD = TILE_H_ADDR >> 2
BYTE_F, BYTE_K, BYTE_X, BYTE_Y, BYTE_Z = 0x46, 0x4B, 0x58, 0x59, 0x5A

PATH_OUT = b"/tmp/b4a"
PATH_LD = b"/tmp/b4b"
PATH_CTL = b"/tmp/b4c"
PATH_XREAD = b"/tmp/b4d"
PATH_XREAD_EXPECT = PATH_XREAD + bytes([BYTE_X, BYTE_Y])   # '/tmp/b4dXY'


def stage_path(path_bytes, terminate=True):
    lines = []
    for i, b in enumerate(path_bytes):
        lines.append("LDI r5 %d" % (STAGE_WORD + i))
        lines.append("LDI r6 %d" % b)
        lines.append("PARALLEL_ST r5 r6 1")
    if terminate:
        lines.append("LDI r5 %d" % (STAGE_WORD + len(path_bytes)))
        lines.append("LDI r6 0")
        lines.append("PARALLEL_ST r5 r6 1")
    return lines


def tail_fw(data_addr, length):
    return [
        "LDI r1 %d" % STAGE_WORD,
        "LDI r2 %d" % data_addr,
        "LDI r3 %d" % length,
        "LDI r17 3",
        "SYSCALL r10 3",
        "HALT",
    ]


def prog_fw(path_bytes, data_addr, length):
    return stage_path(path_bytes) + tail_fw(data_addr, length)


def prog_ld_stage(path_bytes, out_word, stage_word):
    return stage_path(path_bytes) + [
        "LDI r2 %d" % out_word,
        "LD r3 r2",                    # BK-38 primitive: fence-blind read
        "LDI r2 %d" % stage_word,
        "ST r2 r3",                    # in-tile store (allowed)
    ] + tail_fw(stage_word, 1)


def read_file(path):
    return open(path, "rb").read() if os.path.exists(path) else None


def run_case(label, prog_lines, targets, seed):
    """targets: {path: expected_bytes_or_None}. All unlinked pre-run."""
    for path in targets:
        if os.path.exists(path):
            os.unlink(path)
        assert not os.path.exists(path), f"{path} not cleaned"
    img = GlyphAssemblerV2(OM).assemble(prog_lines, width_instrs=8)
    table = GlyphProcessTable()
    pid = table.spawn(img, name=label, tile=(TILE_ROW, TILE_COL, TILE_H, TILE_W))
    cpu = table.tasks[pid]["cpu"]
    for addr, val in seed.items():
        cpu.memory[addr] = val & 0xFFFFFFFF
    rc = table.wait(pid)
    got = {p: read_file(p) for p in targets}
    return {
        "label": label,
        "rc": rc,
        "rc_name": "EXIT_OK" if rc == EXIT_OK else ("EXIT_FAULT" if rc == EXIT_FAULT else f"?{rc}"),
        "faulted": bool(cpu.faulted),
        "fault_addr": int(getattr(cpu, "fault_addr", 0) or 0),
        "files": {p: (c.hex() if c is not None else None) for p, c in got.items()},
        "matches": all(c == e for p, e in targets.items() for c in [got[p]]),
        "tile_h_word": int(cpu.memory[TILE_H_WORD]),
        "mode_super": int(cpu.mode) == MODE_SUPER,
    }


def main():
    cases = [
        ("fw_ram_out",
         prog_fw(PATH_OUT, CANARY_WORD, 2),
         {PATH_OUT: b"FK"},
         {CANARY_WORD: BYTE_F, CANARY_WORD + 1: BYTE_K}),
        ("fw_ld_stage",
         prog_ld_stage(PATH_LD, CANARY_WORD, LD_STAGE_WORD),
         {PATH_LD: b"F"},
         {CANARY_WORD: BYTE_F}),
        ("fw_path_read",
         stage_path(PATH_XREAD, terminate=False) + tail_fw(CTL_WORD, 1),
         {PATH_XREAD_EXPECT: b"Z"},
         {TERM_WORD: BYTE_X, TERM_WORD + 1: BYTE_Y, CTL_WORD: BYTE_Z}),
        ("fw_ctl_in",
         prog_fw(PATH_CTL, CTL_WORD, 2),
         {PATH_CTL: b"FK"},
         {CTL_WORD: BYTE_F, CTL_WORD + 1: BYTE_K}),
        ("ctl_st_out",
         ["LDI r2 %d" % CANARY_WORD,
          "LDI r3 %d" % BYTE_F,
          "ST r2 r3",
          "HALT"],
         {"/tmp/b4z_st_no_fixture": None},
         {}),
    ]
    results = []
    for _ in range(3):
        results.append([run_case(lbl, prog, tgt, seed) for lbl, prog, tgt, seed in cases])
    for r5 in results:
        for r in r5:
            print(r)
    print("deterministic:", all(results[i] == results[0] for i in range(1, 3)))

    r0 = {r["label"]: r for r in results[0]}
    for lbl, want in (("fw_ram_out", b"FK"), ("fw_ld_stage", b"F"),
                      ("fw_path_read", b"Z"), ("fw_ctl_in", b"FK")):
        r = r0[lbl]
        ok = (r["rc_name"] == "EXIT_OK" and not r["faulted"] and r["matches"])
        print(f"VERDICT {lbl}:",
              f"HOST EXFIL CONFIRMED (clean exit; {want!r} landed in the expected host file)"
              if ok else f"not confirmed (rc={r['rc_name']}, files={r['files']})")
    st = r0["ctl_st_out"]
    print("VERDICT ctl_st_out:", "trapped as required"
          if st["faulted"] and st["fault_addr"] == CANARY_WORD * 4
          else f"NOT TRAPPED (rc={st['rc_name']}, fault_addr={st['fault_addr']})")

    blob = repr(results[0]).encode()
    print("results_md5:", hashlib.md5(blob).hexdigest())


if __name__ == "__main__":
    main()
