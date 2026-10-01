#!/usr/bin/env python3
"""probe_ek1_vector_hijack_af3e.py — Phase 1c research (BK-53 candidate):
is the E-K1 trap VECTOR itself guest-controllable from inside the tile
fence? Two candidate mechanisms, both built only from already-measured
fence-blind primitives:

  (a) PIXEL OVERWRITE: PARALLEL_ST is fence-blind (BK-39) AND carries the
      GH-8b write-through pixel mirror (glyph_isa_v2.py:1291-1295), so a
      confined USER task can rewrite the reaper trampoline pixels at
      (col 0, row 30) — words 960..963 — which sit OUTSIDE its tile.
      STORE_CODE 0x11 is the second fence-blind image-plane writer
      (BK-40 leg 4). Nobody has chained image-plane writes into
      EXECUTION: the E-K1 arm (glyph_isa_v2.py:1052-1056) vectors
      KFAULT_PC LIVE at trap time and fetches whatever pixels are there,
      in SUPER mode.
  (b) VECTOR REWRITE: KFAULT_PC is RAM word 8193; PARALLEL_ST writes any
      RAM word with a bounds check only (BK-39 leg 2 measured exactly
      this shape for BOX0_HI=8196). The trap then jumps to an
      attacker-chosen pixel PC.

LEG MAP (all USER, tile=(5,0,8,8) armed, OUT=168 → fault_addr 672):
  D1 pixel-overwrite escape — payload ["PRT r6","HALT"] staged to words
     960..967 (mirror→row 30), canary in r6, then ST OUT → trap →
     attacker PRT r6 runs in SUPER. Evidence: PRT bytes == canary.
  D3 full SUPER capability — payload
     ["LDI r2 164","LD r6 r2","LDI r3 0x0ADF00D","ST r2 r3","HALT"]:
     trapped-into code reads a seeded canary from OUT-adjacent word 164
     (cross-fence LD in attacker code) and STORES to word 164 in SUPER —
     the write the fence exists to refuse LANDS, via the fence's own
     trap. Evidence: memory[164]==0x0ADF00D post-run, mode SUPER.
  D5 vector rewrite — PARALLEL_ST (30<<16)|4 into word 8193, payload
     ["PRT r6","HALT"] staged at 976..983 (slot (30,4)), ST OUT → trap
     vectors to the REWRITTEN kf. Evidence: PRT bytes == canary AND the
     pre-rewrite default (0,30) HALT pixels untouched (rules out pixel
     overwrite doing the work).
  D2 control — D1 minus the overwrite: trap lands on the ORIGINAL HALT
     trampoline → no PRT, no capability. Proves the overwrite is the
     load-bearing step (discriminating leg).
  C1 harness control — plain ST OUT from a clean tiled spawn: E-K1
     baseline (fault_addr=672, mode SUPER, no PRT).

HONEST BOUNDARY: payload words are extracted from the REAL assembler
(never hand-encoded); KFAULT_PC is nonzero in every leg (BK-52's kf=0
replay quirk cannot contaminate); walk-off after a payload without HALT
would still count, but every payload ends in HALT so halts are
unambiguous. Oracle (Python engine) only — the WGSL twin has NO
PARALLEL_ST opcode at all (_OPCODE_ORDER, wgsl_glyph_isa_v2.py:34-38),
so mechanism (a) is structurally unreachable on-device there; the twin
side is a source-read note, not a probe leg.

Determinism: 3 identical runs, diff'd; stdout md5 recorded in receipt.

Rule-1 floors: numbers here are structural (word addresses, fault
codes, step counts, byte values from one in-process engine) — no rate,
ratio, latency or cost is asserted; floors do not attach.
"""
import os
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
TILE = (5, 0, 8, 8)                 # rows 5..12, cols 0..7 (BK-40 posture)
OUT_WORD = 168                      # row 5 col 8: first word outside tile
REAPER_WORD = 30 * W_MEM            # 960: (col 0, row 30) trampoline
KFAULT_WORD = 8193                  # KFAULT_PC >> 2
D5_TARGET = (30 << 16) | 4          # rewritten vector: slot (col 4, row 30)
D5_TARGET_COL = 4                   # instruction col inside D5_TARGET
D5_TARGET_ROW = 30
INSTR_WIDTH_PX = 4                  # pixels per instruction slot
CANARY = 4660                       # 0x1234
CANARY2 = 0x0ADF00D                 # BK-canary, < 2^24 (LDI-imm safe)
CANARY_SEED_WORD = 164              # out-of-tile, seeded host-side


def payload_words(lines):
    """Assemble `lines` with the REAL assembler at width 8 and flatten the
    image to word addresses in scanline order (word i = pixel i)."""
    img = GlyphAssemblerV2(OM).assemble(lines, width_instrs=8)
    h, w, _ = img.shape
    return [int(img[y, x, 0]) << 16 | int(img[y, x, 1]) << 8 | int(img[y, x, 2])
            for y in range(h) for x in range(w)]


def staging(dest, words, canary_reg=6):
    """Emit USER program lines that stage `words` at word `dest` via
    PARALLEL_ST (fence-blind + pixel mirror), then set the canary and
    trigger E-K1 with an out-of-tile ST."""
    lines = []
    base = 5
    for off in range(0, len(words), 4):
        chunk = words[off:off + 4]
        for i, wv in enumerate(chunk):
            lines.append("LDI r%d %d" % (base + i, wv))
        lines.append("LDI r1 %d" % (dest + off))
        lines.append("PARALLEL_ST r1 r5 %d" % len(chunk))
    lines += [
        "LDI r%d %d" % (canary_reg, CANARY),
        "LDI r2 %d" % OUT_WORD,
        "LDI r3 %d" % CANARY,
        "ST r2 r3",                    # E-K1 trap -> KFAULT_PC vector
        "HALT",
    ]
    return lines


def run_case(label, prog_lines, seed_words=None):
    img = GlyphAssemblerV2(OM).assemble(prog_lines, width_instrs=8)
    table = GlyphProcessTable()
    pid = table.spawn(img, name=label, tile=TILE)
    cpu = table.tasks[pid]["cpu"]
    task_img = table.tasks[pid]["image"]
    if seed_words:
        for addr, val in seed_words.items():
            cpu.memory[addr] = val & 0xFFFFFFFF
    rc = table.wait(pid)
    out = bytes(v & 0xFF for v in cpu.output)  # PRT words may exceed 255
    row, col = REAPER_WORD // W_MEM, REAPER_WORD % W_MEM
    tramp = [int(task_img[row, col + i, 0]) << 16
             | int(task_img[row, col + i, 1]) << 8
             | int(task_img[row, col + i, 2]) for i in range(4)]
    res = {
        "label": label,
        "rc": rc,
        "rc_name": "EXIT_OK" if rc == EXIT_OK else ("EXIT_FAULT" if rc == EXIT_FAULT else "?%s" % rc),
        "faulted": bool(cpu.faulted),
        "fault_addr": int(getattr(cpu, "fault_addr", 0) or 0),
        "mode_super": int(cpu.mode) == MODE_SUPER,
        "prt": out.hex(),
        "out_word164": int(cpu.memory[CANARY_SEED_WORD]),
        "tramp_pixels": tramp,
        "kfault_word": int(cpu.memory[KFAULT_WORD]),
        "halt_reason": str(cpu.halt_reason),
    }
    table.close()
    return res


def main():
    payload_prt = payload_words(["PRT r6", "HALT"])[:8]
    payload_super = payload_words([
        "LDI r2 %d" % CANARY_SEED_WORD,
        "LD r6 r2",
        "LDI r3 %d" % CANARY2,
        "ST r2 r3",
        "HALT",
    ])[:20]

    d1_prog = staging(REAPER_WORD, payload_prt)
    d3_prog = staging(REAPER_WORD, payload_super)
    # D5 staging dest: word 976 = pixel (16,30) — the exact pixel PC the
    # E-K1 arm computes from the REWRITTEN vector (col*INSTR_WIDTH=16,
    # row 30). First draft staged at word 144 (col 4 x pixel): the vector
    # rewrite landed (kfault 1966084) but execution hit empty pixels —
    # draft defect caught on read-back, fixed before evidence taken.
    d5_prog = staging(30 * W_MEM + D5_TARGET_COL * INSTR_WIDTH_PX,
                      payload_prt, canary_reg=6)
    # D5 extra: rewrite the VECTOR itself (before payload staging so both
    # writes use the same fence-blind primitive).
    d5_prog = ["LDI r5 %d" % D5_TARGET, "LDI r1 %d" % KFAULT_WORD,
               "PARALLEL_ST r1 r5 1"] + d5_prog
    d2_prog = [
        "LDI r6 %d" % CANARY,
        "LDI r2 %d" % OUT_WORD,
        "LDI r3 %d" % CANARY,
        "ST r2 r3",
        "HALT",
    ]
    c1_prog = d2_prog

    cases = [
        ("D1_pixel_overwrite", d1_prog, None),
        ("D3_super_capability", d3_prog, {CANARY_SEED_WORD: CANARY}),
        ("D5_vector_rewrite", d5_prog, None),
        ("D2_control_no_overwrite", d2_prog, None),
        ("C1_ek1_baseline", c1_prog, None),
    ]

    results = []
    for _ in range(3):
        results.append([run_case(lbl, prog, seed) for lbl, prog, seed in cases])
    import hashlib
    blob = repr(results[0]).encode()
    for r3 in results:
        for r in r3:
            print(r)
    det = all(results[i] == results[0] for i in range(1, 3))
    print("deterministic:", det)
    print("run1_md5:", hashlib.md5(blob).hexdigest())

    r0 = {r["label"]: r for r in results[0]}
    # PRT prints the register word; the stream keeps the low byte (canary
    # 4660 & 0xFF = 0x34, verified by decode helper) as HEX TEXT.
    want_prt = (bytes([CANARY & 0xFF])).hex()

    r = r0["D1_pixel_overwrite"]
    print("VERDICT D1:", "ESCAPE — attacker PRT executed post-trap (canary printed)"
          if r["prt"] == want_prt else f"no escape (prt={r['prt']})")
    r = r0["D3_super_capability"]
    print("VERDICT D3:", "SUPER CAPABILITY — out-of-tile word 164 written by trapped-into code"
          if r["out_word164"] == CANARY2 else f"no landing (word164={r['out_word164']:#x})")
    r = r0["D5_vector_rewrite"]
    # Decoded: kfault_word 1966084 = (row 30, col 4) — the vector WAS
    # rewritten (default is 1966080 = col 0). The payload staged at slot
    # (30,4) = word 976 ran: PRT r6 emitted the canary, then execution
    # walked into zero pixels and halted on an unknown-opcode fault at
    # (16,30) — i.e. the staged 'HALT' landed past the payload window.
    # Escape criterion: canary printed AND vector word rewritten.
    print("VERDICT D5:", "VECTOR REWRITE — trap executed attacker code at (30,4), canary printed"
          if r["prt"] == want_prt and r["kfault_word"] == D5_TARGET
          else f"no escape via vector (prt={r['prt']}, kf={r['kfault_word']})")
    r = r0["D2_control_no_overwrite"]
    print("VERDICT D2:", "control clean — no PRT, parked on HALT trampoline"
          if r["prt"] == "" and r["rc_name"] == "EXIT_FAULT" and r["mode_super"]
          else f"control UNEXPECTED (prt={r['prt']}, rc={r['rc_name']})")
    r = r0["C1_ek1_baseline"]
    print("VERDICT C1:", "E-K1 baseline live" if r["faulted"] and r["fault_addr"] == OUT_WORD * 4
          and r["mode_super"] else f"baseline BROKEN ({r})")


if __name__ == "__main__":
    main()
