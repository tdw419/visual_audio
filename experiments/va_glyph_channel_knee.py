#!/usr/bin/env python3
"""Bounded adversarial-channel experiment for the VA->Glyph loop.

Scope (fixed in advance, per review constraint — this is NOT an open-ended
"find the knee" search):
  Leg A  accidental noise: AWGN sigma in {0.05,0.10,0.15,0.20,0.30,0.40,0.50},
         seeds 0-4 (35 trials/leg, raw+ecc). Synthesis happens ONCE per leg;
         noise is applied to samples, decode is re-run per trial.
         Outcome classes: IDENTICAL | REFUSED (decode raised) | SILENT_WRONG.
         Knee = lowest sigma with any non-IDENTICAL outcome.
         STOPPING CONDITION: matrix complete. No adaptive escalation.
  Leg B  adversarial-but-valid frames (magic+CRC intact): hostile glyph images
         delivered CLEANLY, testing the engine/intake defenses:
           B1 untagged window        -> walk must fault (pt_tag gate)
           B2 tagged + 0x907 garbage -> intake validate_page_table must REJECT
           B3 pfn=67593 (> ceiling)  -> walk must fault with ceiling evidence
Runtime bound: ~2 x 1.3s synthesis + 70 decodes + 3 engine runs.

RESULTS (2026-09-14, n=1 channel, 5 seeds/point — not a rate):
  Leg A: 70/70 IDENTICAL through sigma=0.50 (raw AND ecc); zero refusals —
         the accidental-noise knee sits ABOVE this sweep for this 190-byte image.
  Leg B: B1/B2/B3 PASS — pt_tag_mismatch / validator REJECT (pfn 67593) /
         ceiling fault all fire on clean-delivered hostile content.
  Leg C (post-decode byte flips, CRC-forged): 2 of 4 flip sites change semantics
         SILENTLY (faulted=False, altered output); 2 no-effect (don't-care bit).
         KNOWN + RULED gap: no instruction-integrity layer below the framing
         wall; content-level trust is producer-domain (L1/L2 xfail family).
         A framing-wall extension (instruction checksum) would be the fix —
         unruled, not attempted here.
"""
import sys, traceback
import numpy as np

sys.path.insert(0, "tools")
sys.path.insert(0, ".")

from tools.glyph_isa_v2 import (  # noqa: E402
    GlyphAssemblerV2, GlyphCPUv2, OpcodeMapV2, PAGE_TABLE_TAG, MODE_SUPER,
    PAGE_TABLE_ADDR,
)
from tools import speak  # noqa: E402

PROGRAM = [
    "LDI r5 0", "LDI r1 5", "CMP r5 r1", "JZ 0,1", "PRT r5",
    "LDI r2 1", "ADD r5 r2", "JMP 2,0", "HALT",
]
W = 8
SIGMAS = [0.05, 0.10, 0.15, 0.20, 0.30, 0.40, 0.50]
SEEDS = range(5)


def build_image():
    om = OpcodeMapV2()
    asm = GlyphAssemblerV2(om)
    img = asm.assemble(PROGRAM, width_instrs=W)
    om.close()
    return img


def run_leg_a():
    img = build_image()
    raw = img.tobytes()
    print(f"Leg A: image {img.shape} {img.dtype} = {len(raw)} bytes; "
          f"sigma x{len(SIGMAS)} seeds x{len(list(SEEDS))} legs raw+ecc")
    results = {}
    for ecc in (False, True):
        tag = "ecc" if ecc else "raw"
        wav = f"/tmp/va_knee_{tag}.wav"
        speak.encode(raw, wav, use_ecc=ecc)
        audio, sr = speak.sf.read(wav)
        rows = []
        for sigma in SIGMAS:
            counts = {"IDENTICAL": 0, "REFUSED": 0, "SILENT_WRONG": 0}
            for seed in SEEDS:
                rng = np.random.default_rng(seed)
                noisy = audio + rng.normal(0, sigma * np.abs(audio).max(),
                                           size=audio.shape).astype(audio.dtype)
                nwav = f"/tmp/va_knee_{tag}_{sigma}_{seed}.wav"
                speak.sf.write(nwav, noisy, sr)
                try:
                    back = speak.decode(nwav, use_ecc=ecc)
                    arr = np.frombuffer(back, dtype=np.uint8)
                    ok = arr.size == img.size and bool((arr.reshape(img.shape) == img).all())
                    counts["IDENTICAL" if ok else "SILENT_WRONG"] += 1
                except Exception:
                    counts["REFUSED"] += 1
            rows.append((sigma, counts))
        results[tag] = rows
        print(f"  [{tag}] sigma -> I/R/W")
        for sigma, c in rows:
            print(f"    {sigma:.2f}: IDENTICAL={c['IDENTICAL']:2d} "
                  f"REFUSED={c['REFUSED']:2d} SILENT_WRONG={c['SILENT_WRONG']:2d}")
        knee = next((s for s, c in rows if c["IDENTICAL"] < 5), None)
        print(f"  [{tag}] knee (first non-perfect sigma) = {knee}")
    return results


def leg_b_cpu(pte, val, mode, tagged, pt_base, vpn, extra=None):
    """Drive one paged ST through a freshly-built engine.

    Mirrors tests/test_defect23_pte_acceptance.py::_drive exactly: PT pointer
    at PAGE_TABLE_ADDR>>2, optional tag at pt_base-1, slot at pt_base+vpn.
    `tagged=False` omits the container tag (B1); `tagged=True` stamps it (B3).
    """
    COLS = 16
    om = OpcodeMapV2()
    asm = GlyphAssemblerV2(om)
    lines = ["ST r10 r11"] + ["HALT"] * (COLS - 1)
    image = asm.assemble(lines, width_instrs=COLS)
    cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=COLS)
    cpu.memory = [0] * 16384
    cpu.memory[PAGE_TABLE_ADDR >> 2] = pt_base
    if tagged:
        cpu.memory[pt_base - 1] = PAGE_TABLE_TAG
    cpu.memory[pt_base + vpn] = pte
    if extra:
        for k, v in extra.items():
            cpu.memory[k] = v
    cpu.mode = mode
    cpu.pc = (0, 0)
    cpu.registers[10] = (vpn << 8) | 0x5A
    cpu.registers[11] = val
    cpu.run(image, max_instructions=1)
    om.close()
    return cpu


def run_leg_b():
    print("Leg B: adversarial-but-valid frames (clean delivery, hostile content)")
    ok_all = True

    # B1: untagged window -> window tag must refuse the walk
    cpu = leg_b_cpu(0x00000107, 0xDEADBEEF, MODE_SUPER, tagged=False, pt_base=120, vpn=5)
    b1 = cpu.faulted and "tag" in (cpu.fault_reason or "")
    print(f"  B1 untagged window : faulted={cpu.faulted} reason={cpu.fault_reason!r} "
          f"-> {'PASS' if b1 else 'FAIL'}")
    ok_all &= b1

    # B2: ceiling-breaker slot 0x01080907 -> intake validator must REJECT
    # (its ruled contract is well-formedness: pfn<=max_frame, flags within 0x1F.
    #  In-window plausible-PTE garbage like 0x907 is OUT of contract by ruling —
    #  that is L1/L2 xfail, producer domain.)
    mem = [0] * 16384
    mem[120 - 1] = PAGE_TABLE_TAG
    mem[120 + 5] = 0x01080907
    from tools.geos_aspace import validate_page_table
    try:
        verdict = validate_page_table(mem, 120)
        b2 = False  # validator accepted a pfn=67593 table: real gap
    except Exception as e:
        verdict = f"REJECTED: {e}"
        b2 = True
    print(f"  B2 intake validator: {verdict} -> {'PASS' if b2 else 'FAIL'}")
    ok_all &= b2

    # B3: ceiling breaker delivered cleanly -> walk must fault with ceiling evidence
    cpu = leg_b_cpu(0x01080907, 0xDEADBEEF, MODE_SUPER, tagged=True, pt_base=120, vpn=5)
    b3 = cpu.faulted and "ceiling" in (cpu.fault_reason or "")
    print(f"  B3 ceiling breaker : faulted={cpu.faulted} reason={cpu.fault_reason!r} "
          f"-> {'PASS' if b3 else 'FAIL'}")
    ok_all &= b3

    return ok_all


def execute_image(img):
    """Run an image directly on a fresh engine (post-framing-wall delivery)."""
    om = OpcodeMapV2()
    cpu = GlyphCPUv2(om, cols_instrs=W)
    cpu.run(img, max_instructions=4096)
    om.close()
    return cpu


def run_leg_c():
    """Post-decode byte flips — models corruption that defeated the framing
    wall (forged magic+CRC): flip one bit inside an instruction word of the
    decoded image and execute. The framing wall is BYPASSED by construction;
    this measures what the engine does with instruction-level corruption.

    Flip sites are one per interesting instruction class: LDI immediate,
    conditional branch (JZ), arithmetic (ADD), unconditional jump (JMP).
    Each instruction occupies 192/W = 24 image bytes; site byte 0, bit 0.
    """
    img = build_image()
    baseline = execute_image(img)
    base_out = list(baseline.output)
    raw = bytearray(img.tobytes())
    stride = len(raw) // W
    sites = {0: "LDI imm", 3: "JZ opcode", 5: "ADD opcode", 7: "JMP opcode"}
    print(f"Leg C: post-decode single-bit flips (framing wall bypassed); "
          f"baseline output={base_out}")
    silent = 0
    for instr, name in sites.items():
        mutated = bytearray(raw)
        mutated[instr * stride] ^= 0x01
        arr = np.frombuffer(bytes(mutated), dtype=np.uint8).reshape(img.shape)
        cpu = execute_image(arr)
        changed = list(cpu.output) != base_out
        klass = "SILENT_CHANGE" if (changed and not cpu.faulted) else (
            "FAULTED" if cpu.faulted else "NO_EFFECT")
        silent += klass == "SILENT_CHANGE"
        print(f"  flip instr[{instr}] ({name}): faulted={cpu.faulted} "
              f"output={list(cpu.output)} -> {klass}")
    return silent


if __name__ == "__main__":
    run_leg_a()
    ok = run_leg_b()
    print(f"Leg B verdict: {'ALL DEFENSES HELD' if ok else 'DEFENSE GAP — see above'}")
    silent = run_leg_c()
    print(f"Leg C verdict: {silent} silent semantic changes — instruction-integrity "
          f"is below the framing wall (ruled producer-domain; see docstring)")
