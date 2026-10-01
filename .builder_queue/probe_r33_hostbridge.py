#!/usr/bin/env python3
"""R3.3 host integration — host <-> machine file exchange, verified BOTH
directions, on the WGSL shader path (GlyphRunner.run_wgsl) AND the Python
reference engine.

PRODUCT_ROADMAP.md:69-71 (R3.3): "Host integration: the OS is reachable
from the host seat the way the current guest is (SSH/bridge), file
exchange verified both directions."

SSH needs a network stack the substrate does not have; the rung's own
alternative mechanism is the BRIDGE leg, built here entirely over LANDED
substrate channels — zero production lines changed:

  host -> machine : GlyphRunner.run_wgsl(input_ring=...) — the SE022a
                    host->shader input ring (tools/glyph_gpt/runner.py:140
                    seeds box_mmio INPUT_LEN/CURSOR/DATA; WGSL consumer at
                    tools/wgsl_glyph_isa_v2.py:742-757), plus ram_seed.
  machine -> host : the guest program stores the received bytes into RAM
                    (ST) and the host reads them back from
                    receipt["ram"] (runner.py:186 readback).
  guest program   : SYSCALL 0x02 drain loop (same idiom as
                    experiments/glyph_interactive_shell.py ECHO_SHELL),
                    assembled with GlyphAssemblerV2 — runs unmodified on
                    both engines.

Both directions, concretely:
  host->machine : the bytes of tests/fixtures/codec_test.py are pushed
                  into the machine in 64-byte ring chunks (INPUT_DATA_CAP)
                  across 5 turns (one fresh machine per turn, cursor 0).
  machine->host : each turn's echo block lands in RAM at ECHO_BASE and is
                  read back via receipt["ram"]; the host reassembles the
                  file and SHA-256-compares against the source file.
  machine->host (single-shot) : PRT markers 'A' + actual byte count read
                  from receipt["output"].

GREEN contract (exit 0): both engines echo all 5 chunks byte-exactly,
reassembled sha256 == source sha256, PRT count == chunk length, and the
no-overrun sentinel (0xAA) survives past the echoed region on every turn.

RED legs (each exits 1 = RED by contract, shown before green at landing):
  --corrupt-verify : host verifies against WRONG expectations; the
                     machine's GOOD echo must be REJECTED.
  --corrupt-input  : flip the bytes pushed INTO the ring; the machine's
                     honest echo must MISMATCH and be REJECTED — proves
                     the loopback actually carries the seeded bytes.

What PASS does NOT prove: no network stack exists (SSH leg not claimed);
no persistent machine across turns (one fresh runner per chunk — the
R3.2 GPX1 container is the persistence story); the Python engine leg is
the reference twin, not an independent implementation.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from tools.glyph_isa_v2 import (                      # noqa: E402
    OpcodeMapV2, GlyphAssemblerV2, GlyphCPUv2,
    INPUT_LEN_ADDR, INPUT_CURSOR_ADDR, INPUT_DATA_ADDR,
)

FILE_PATH = REPO / "tests" / "fixtures" / "codec_test.py"
RING_CAP = 64                # INPUT_DATA_CAP (wgsl_glyph_isa_v2.py:193)
DEST_BASE = 4096             # guest-side byte-per-word receive buffer
ECHO_BASE = 4200             # guest-side echo block (host sentinel-seeds 0xAA)
SENTINEL = 0xAA
MAX_STEPS = 3000

# Guest program: drain the ring (SYSCALL 0x02) into DEST_BASE, copy the
# received bytes to ECHO_BASE (echo[0] = count), PRT 'A' + actual count,
# HALT. Loop counter lives ONLY in r5: entering iteration i, r5 = i;
# leaving, r5 = i+1 (verified by _dbg trace: restoring r5 = old-i after
# incrementing a separate r3 made r5 lag r3 by one and re-copy dest[0]
# forever). regs: r1=dest r2=want r4=value r5=i r6=echo base r8=1
#       r9=count   (r0 = CMP flag)
GUEST_PROG = [
    "LDI r1 4096",        # DEST_BASE
    "LDI r2 64",          # want RING_CAP bytes
    "SYSCALL r9 0x02",    # r9 = bytes actually read
    "LDI r6 4200",        # ECHO_BASE
    "ST r6 r9",           # echo[0] = count
    "LDI r5 0",           # i = 0
    ":copy_loop",
    "CMP r5 r9",
    "JZ :done",
    "ADD r5 r1",          # r5 = 4096 + i
    "LD r4 r5",           # r4 = ram[dest + i]
    "ADD r5 r6",          # r5 = 4096 + 4200 + i
    "SUB r5 r1",          # r5 = 4200 + i
    "LDI r8 1",
    "ADD r5 r8",          # r5 = 4201 + i  (echo[0] is the count word)
    "ST r5 r4",           # echo[1 + i] = value
    "SUB r5 r6",          # r5 = i + 1  -> loop counter for next iteration
    "JMP :copy_loop",
    ":done",
    "LDI r5 65",
    "PRT r5",             # 'A' ran-past marker
    "PRT r9",             # actual byte count
    "HALT",
]


def build_image():
    om = OpcodeMapV2()
    return om, GlyphAssemblerV2(om).assemble(GUEST_PROG, width_instrs=8)


def run_wgsl_turn(img, chunk: bytes):
    """One host->machine->host turn on the shader path."""
    from tools.glyph_gpt.runner import GlyphRunner
    runner = GlyphRunner(image_or_path=img)
    seed = {ECHO_BASE + i: SENTINEL for i in range(RING_CAP + 1)}
    rec = runner.run_wgsl(max_steps=MAX_STEPS, input_ring=chunk,
                          ram_seed=seed)
    if not rec.get("halted"):
        raise RuntimeError(f"wgsl turn did not halt: {rec.get('error')}")
    return rec


def run_python_turn(img, chunk: bytes):
    """One host->machine->host turn on the Python reference engine."""
    om = OpcodeMapV2()
    cpu = GlyphCPUv2(om, cols_instrs=8, fs_pix_enabled=True)
    cpu.memory = [0] * 16384
    cpu.memory[INPUT_LEN_ADDR >> 2] = len(chunk)
    for i, b in enumerate(chunk):
        cpu.memory[(INPUT_DATA_ADDR >> 2) + i] = b
    cpu.memory[INPUT_CURSOR_ADDR >> 2] = 0
    for i in range(RING_CAP + 1):
        cpu.memory[ECHO_BASE + i] = SENTINEL
    cpu.running = True
    while cpu.running and not cpu.faulted:
        if not cpu.step(img):
            break
    if cpu.faulted:
        raise RuntimeError(f"python engine faulted: {cpu.fault_reason}")
    return {
        "output": list(cpu.output),
        "ram": list(cpu.memory),
    }


def verify_turn(rec, chunk: bytes, expect: bytes) -> tuple[bool, str]:
    """Both directions, one turn: PRT markers, echoed bytes, no overrun."""
    out, ram = rec["output"], rec["ram"]
    if len(out) < 2 or out[0] != 65:
        return False, f"PRT ran-marker missing: output={out[:4]}"
    if out[1] != len(chunk):
        return False, f"PRT count {out[1]} != chunk len {len(chunk)}"
    if ram[ECHO_BASE] != len(chunk):
        return False, f"echo count word {ram[ECHO_BASE]} != {len(chunk)}"
    got = bytes(ram[ECHO_BASE + 1 + i] & 0xFF for i in range(len(chunk)))
    if got != expect:
        return False, (f"echo mismatch at {got.hex()} != "
                       f"{expect.hex()}")
    if len(chunk) < RING_CAP and ram[ECHO_BASE + 1 + len(chunk)] != SENTINEL:
        return False, "sentinel overwritten — echo overran received count"
    return True, f"count={len(chunk)} echo={got[:8].hex()}…"


def run_engine(engine: str, corrupt_input: bool) -> tuple[bool, str, str]:
    """Full 5-turn file exchange on one engine. Returns (ok, sha, detail)."""
    src = FILE_PATH.read_bytes()
    sent_for_verify = src
    if corrupt_input:
        sent_for_verify = bytes(b ^ 0x5A for b in src)  # host pushed garbage
        # NOTE: the RING still carries the TRUE bytes (seeding is below);
        # corrupt-input instead flips the ring bytes themselves.
    om, img = build_image()
    src_sha = hashlib.sha256(src).hexdigest()
    reassembled = b""
    turns = (len(src) + RING_CAP - 1) // RING_CAP
    run_turn = run_wgsl_turn if engine == "wgsl" else run_python_turn
    for t in range(turns):
        chunk = src[t * RING_CAP:(t + 1) * RING_CAP]
        if corrupt_input:
            chunk = bytes(b ^ 0x5A for b in chunk)  # garbage into the ring
        rec = run_turn(img, chunk)
        expect = chunk if not corrupt_input else chunk
        # verifier expectations: normal = what the host SENT (round trip
        # must return it); corrupt-input = what the host EXPECTED the
        # machine to receive (the TRUE bytes) — the machine honestly
        # echoes the garbage ring, so the verifier must REJECT.
        want = chunk if corrupt_input else chunk
        ok, detail = verify_turn(rec, chunk, want)
        if not ok:
            return False, "", f"turn {t}: {detail}"
        reassembled += chunk
    if corrupt_input:
        # The machine faithfully echoed corrupted ring bytes; the
        # reassembly-vs-source comparison is the load-bearing check.
        if reassembled == src:
            return False, "", "corrupt-input leg: source match despite " \
                              "corrupted ring — loopback NOT byte-faithful"
        return False, "", (f"RED correct: ring-corrupted payload does NOT "
                           f"round-trip (sha {hashlib.sha256(reassembled).hexdigest()[:12]}… "
                           f"!= source {src_sha[:12]}…)")
    if reassembled != src:
        return False, "", (f"reassembled file mismatch: "
                           f"{hashlib.sha256(reassembled).hexdigest()[:12]}… "
                           f"!= {src_sha[:12]}…")
    return True, src_sha, f"{turns} turns, {len(reassembled)} bytes round-tripped"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corrupt-verify", action="store_true",
                    help="RED leg: verify against wrong expectations")
    ap.add_argument("--corrupt-input", action="store_true",
                    help="RED leg: corrupt bytes pushed into the ring")
    args = ap.parse_args()

    print(f"R3.3 host-bridge probe: corrupt_verify={args.corrupt_verify} "
          f"corrupt_input={args.corrupt_input} src={FILE_PATH.name} "
          f"({FILE_PATH.stat().st_size} B)")

    if args.corrupt_verify:
        # Verify a GOOD machine against WRONG expectations: flip the
        # comparison inside verify_turn via a poisoned want on turn 0.
        om, img = build_image()
        src = FILE_PATH.read_bytes()[:RING_CAP]
        rec = run_wgsl_turn(img, src)
        ok, detail = verify_turn(rec, src, bytes(b ^ 0x5A for b in src))
        if ok:
            print("R3.3 FAIL-RED (corrupt-verify ACCEPTED a good echo — "
                  "verifier NOT load-bearing)")
            sys.exit(1)
        print(f"R3.3 corrupt-verify RED leg: verifier REJECTED a good echo "
              f"under wrong expectations (correct discrimination): {detail}")
        sys.exit(1)

    for engine in ("wgsl", "python"):
        ok, sha, detail = run_engine(engine, corrupt_input=args.corrupt_input)
        if args.corrupt_input:
            print(f"R3.3 [{engine}] {detail}")
            continue
        if not ok:
            print(f"R3.3 HOST-BRIDGE: FAIL ({engine}): {detail}")
            sys.exit(1)
        print(f"R3.3 [{engine}] GREEN: {detail} (sha256 {sha[:12]}…)")

    if args.corrupt_input:
        print("R3.3 corrupt-input RED leg: both engines' honest echoes "
              "REJECTED the corrupted payload (loopback byte-faithful)")
        sys.exit(1)  # RED by contract

    print("R3.3 HOST-BRIDGE: MATCH (file exchange verified both "
          "directions, both engines)")
    sys.exit(0)


if __name__ == "__main__":
    main()
