#!/usr/bin/env python3
"""probe_run_arg_af3e.py — Phase 1c research (BK-43 candidate): the 0x07/0x12
RUN arm of the fence-bypass family, left explicitly UNPROBED ("source-read
inference only") by RESEARCH_fw_exfil_path_read.md (its NOT-verified list and
blast-radius note) and RESEARCH_syscall_fence_bypass.md:124.

Difference from BK-42's 0x03 arm: RUN handlers DO check the realpath of the
TARGET against GLYPH_RUN_ALLOW (glyph_isa_v2.py:1576-1579 for 0x07,
:1723-1726 for 0x12) — deny-by-default. But _read_path (:1393-1408) is the
SAME fence-blind decoder proven to walk out-of-tile in BK-42 leg fw_path_read,
and 0x12 RUN2's argv args (:1716-1719) are documented "data, not targets" —
no containment consult of any kind. Questions measured here:
  (a) can out-of-tile RAM bytes a confined task cannot lawfully address
      decide WHICH allowed host binary executes (path decoder smuggle)?
  (b) can out-of-tile RAM bytes travel through execve() as ARGV to a host
      process (RUN2 argv channel)?
  (c) controls: allowlist live path, deny-by-default, E-K1 ST trap.

TILE/INSTRUCTION GEOMETRY (the trap this probe's drafts hit — same class as
the BK-40/BK-42 probe disclosures, caught BEFORE any finding was recorded):
tile (5,0,8,8) => in-tile words rows 5..11 x cols 0..7 = 160..167, 192..199,
... Out-of-tile canaries live at 168+ (row 5, cols 8+). The PARALLEL_ST
write-through pixel mirror (glyph_isa_v2.py:1291-1295) maps word w to pixel
(w//32, w%32): words 160..191 = pixel row 5 = INSTRUCTION SLOTS 40..47 (8
instructions/row, 4 px/instr). Therefore: (i) staged paths are <= 8 in-tile
bytes with the NUL INSIDE the tile, and (ii) every program stays < 40
instructions so staging cannot clobber live code. Draft-1 (32-byte paths,
103 instructions) self-overwrote its tail and staged only 13 bytes —
detected because the CONTROL leg failed; no finding was recorded off it.

Host fixtures (created + cleaned by the probe itself):
  /tmp/r5            7-char /bin/sh runner: writes ARG1=[<argv1>] to
                     /tmp/b5_marker2     (control + deny + argv legs)
  /tmp/runr5r5      12-char identical runner (path-smuggle target: the
                     in-tile 8 bytes only spell '/tmp/run')
  /tmp/b5_marker, /tmp/b5_marker2 — run evidence, unlinked + asserted
                     absent before every leg.

Cases:
  run_ctl_allow     — in-tile path '/tmp/r5', GLYPH_RUN_ALLOW set: the
                      allowlist path is live (marker2 must appear).
  run_denied        — same program, env UNSET: deny-by-default (no marker).
  run_path_smuggle  — in-tile words 160..167 = '/tmp/run' (8 bytes, NO NUL
                      in tile); out-of-tile 168..172 seeded 'r','5','r','5',
                      0. _read_path must decode '/tmp/runr5r5' — an allowed
                      target whose TAIL exists only OUTSIDE the tile — and
                      execute it. Env SET (worst-case posture).
  run2_argv_leak    — 0x12 RUN2, allowed target '/tmp/r5', arg1_addr=168
                      (OUT-of-tile) seeded 'SRC5' + NUL: argv is "data, not
                      targets" — the marker must contain ARG1=[SRC5],
                      proving out-of-tile bytes crossed execve() host-side.
  ctl_st_out        — plain ST to out-of-tile 168 must TRAP (E-K1 baseline,
                      fault_addr = 168*4 = 672).

Verdicts from HOST FILE CONTENTS (marker bytes), never exit codes; every
fixture unlinked + asserted absent pre-leg. Determinism: 3 runs,
byte-identical results blob, md5 printed.
Run: python3 .builder_queue/probe_run_arg_af3e.py
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
STAGE_WORD = 160
TERM_WORD = 168          # first OUT-of-tile word (row 5 col 8)
TILE_H_WORD = TILE_H_ADDR >> 2
BYTE_F = 0x46

RUNNER_SHORT = "/tmp/r5"
RUNNER_LONG = "/tmp/runr5r5"
MARKER = "/tmp/b5_marker"
MARKER2 = "/tmp/b5_marker2"

with open(os.path.join(REPO, ".builder_queue",
                       "probe_run_arg_af3e_runner_sh.template")) as f:
    RUNNER_BODY = f.read()


def stage_bytes(byte_vals, word=STAGE_WORD):
    """PARALLEL_ST each byte to its own word. Caller guarantees the program
    stays < 40 instructions (mirror row-5 clobber window)."""
    lines = []
    for i, b in enumerate(byte_vals):
        lines += ["LDI r5 %d" % (word + i), "LDI r6 %d" % b,
                  "PARALLEL_ST r5 r6 1"]
    return lines


def prog_run_07(path_bytes):
    """0x07 RUN: r1=path_addr. Path MUST be <=8 bytes incl. NUL (all in-tile)."""
    assert len(path_bytes) <= 8 and path_bytes.endswith(b"\x00")
    return stage_bytes(path_bytes) + [
        "LDI r1 %d" % STAGE_WORD,
        "LDI r17 7",
        "SYSCALL r10 7",
        "HALT",
    ]


def prog_run2_argv(path_bytes, arg1_addr):
    """0x12 RUN2: r1=path (in-tile, NUL in-tile), r2=arg1_addr (out-of-tile)."""
    assert len(path_bytes) <= 8 and path_bytes.endswith(b"\x00")
    return stage_bytes(path_bytes) + [
        "LDI r1 %d" % STAGE_WORD,
        "LDI r2 %d" % arg1_addr,
        "LDI r3 0",
        "LDI r17 18",
        "SYSCALL r10 18",
        "HALT",
    ]


def run_case(label, prog_lines, targets, env, seed):
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
    old = os.environ.get("GLYPH_RUN_ALLOW")
    try:
        if env is None:
            os.environ.pop("GLYPH_RUN_ALLOW", None)
        else:
            os.environ["GLYPH_RUN_ALLOW"] = env
        rc = table.wait(pid)
    finally:
        if old is None:
            os.environ.pop("GLYPH_RUN_ALLOW", None)
        else:
            os.environ["GLYPH_RUN_ALLOW"] = old
    got = {p: open(p, "rb").read() if os.path.exists(p) else None
           for p in targets}
    return {
        "label": label,
        "rc": rc,
        "rc_name": "EXIT_OK" if rc == EXIT_OK else
                   ("EXIT_FAULT" if rc == EXIT_FAULT else f"?{rc}"),
        "faulted": bool(cpu.faulted),
        "fault_addr": int(getattr(cpu, "fault_addr", 0) or 0),
        "files": {p: (c.hex() if c is not None else None) for p, c in got.items()},
        "tile_h_word": int(cpu.memory[TILE_H_WORD]),
        "mode_super": int(cpu.mode) == MODE_SUPER,
    }


def main():
    os.makedirs("/tmp", exist_ok=True)  # trivially true; keep fixture logic explicit
    for runner in (RUNNER_SHORT, RUNNER_LONG):
        with open(runner, "w") as f:
            f.write(RUNNER_BODY)
        os.chmod(runner, 0o755)
    allow_short = os.path.realpath(RUNNER_SHORT)
    allow_long = os.path.realpath(RUNNER_LONG)
    try:
        smuggle_prog = (
            stage_bytes(b"/tmp/run")               # 8 bytes, NO NUL in tile
            + ["LDI r1 %d" % STAGE_WORD, "LDI r17 7", "SYSCALL r10 7", "HALT"])
        cases = [
            ("run_ctl_allow",
             prog_run_07(RUNNER_SHORT.encode() + b"\x00"),
             [MARKER2], allow_short, {}),
            ("run_denied",
             prog_run_07(RUNNER_SHORT.encode() + b"\x00"),
             [MARKER2], None, {}),
            ("run_path_smuggle",
             smuggle_prog,
             [MARKER2], allow_long,
             {TERM_WORD + 0: 0x72,   # r
              TERM_WORD + 1: 0x35,   # 5
              TERM_WORD + 2: 0x72,   # r
              TERM_WORD + 3: 0x35,   # 5
              TERM_WORD + 4: 0x00}),  # NUL out-of-tile
            ("run2_argv_leak",
             prog_run2_argv(RUNNER_SHORT.encode() + b"\x00", TERM_WORD),
             [MARKER2], allow_short,
             {TERM_WORD + 0: 0x53,   # S
              TERM_WORD + 1: 0x52,   # R
              TERM_WORD + 2: 0x43,   # C
              TERM_WORD + 3: 0x35,   # 5
              TERM_WORD + 4: 0x00}),
            ("ctl_st_out",
             ["LDI r2 %d" % TERM_WORD, "LDI r3 %d" % BYTE_F, "ST r2 r3",
              "HALT"],
             [MARKER], None, {}),
        ]
        results = []
        for _ in range(3):
            results.append([run_case(l, p, t, e, s)
                            for l, p, t, e, s in cases])
        for r5 in results:
            for r in r5:
                print(r)
        print("deterministic:",
              all(results[i] == results[0] for i in range(1, 3)))

        r0 = {r["label"]: r for r in results[0]}
        c = r0["run_ctl_allow"]
        print("VERDICT run_ctl_allow:",
              "allowlist path live (marker written)"
              if c["files"][MARKER2] is not None else
              f"CONTROL FAILED (rc={c['rc_name']}, files={c['files']})")
        d = r0["run_denied"]
        print("VERDICT run_denied:",
              "deny-by-default holds (no marker)"
              if d["files"][MARKER2] is None else
              "DENY-BY-DEFAULT BROKEN (marker present!)")
        s = r0["run_path_smuggle"]
        print("VERDICT run_path_smuggle:",
              "OUT-OF-TILE BYTES SELECTED THE EXECUTED BINARY: the allowed "
              "path's tail exists only outside the tile"
              if s["files"][MARKER2] is not None else
              f"not confirmed (rc={s['rc_name']}, files={s['files']})")
        m2 = r0["run2_argv_leak"]["files"].get(MARKER2)
        leak = m2 is not None and bytes.fromhex(m2) == b"ARG1=[SRC5]"
        a = r0["run2_argv_leak"]
        print("VERDICT run2_argv_leak:",
              "OUT-OF-TILE BYTES CROSSED execve() AS ARGV (args are data, "
              "no consult)"
              if leak else
              f"not confirmed (rc={a['rc_name']}, files={a['files']})")
        st = r0["ctl_st_out"]
        print("VERDICT ctl_st_out:",
              "trapped as required"
              if st["faulted"] and st["fault_addr"] == TERM_WORD * 4 else
              f"NOT TRAPPED (rc={st['rc_name']}, fault_addr={st['fault_addr']})")

        blob = repr(results[0]).encode()
        print("results_md5:", hashlib.md5(blob).hexdigest())
    finally:
        for p in (RUNNER_SHORT, RUNNER_LONG, MARKER, MARKER2):
            try:
                os.unlink(p)
            except OSError:
                pass


if __name__ == "__main__":
    main()
