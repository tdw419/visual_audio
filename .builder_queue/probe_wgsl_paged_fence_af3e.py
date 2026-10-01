"""BK-60 research probe (af3e, 2026-09-27): the paged branch of the WGSL
twin's walker — probed on-device for the first time.

Every prior WGSL probe ran UNPAGED (PT words zero): RESEARCH_ek1_vector_
hijack_wgsl_af3e.md:112-113 disclosed "the paged branch of walk_st (:412-441)
was not probed ... Its unmapped-store `return false` is a disclosed divergent
shape"; RESEARCH_bk51_twin_tile_ld_af3e.md:104-105 scoped tile probes to the
unpaged posture. BK-59 (landed 2dbe69da) makes Stage 3+ desktop work hard-
gated on the BK-38..57 sequenced fence commit landing clean on BOTH engines,
and GH-25's swap/fault legs already run paged workloads on the twin — the
unprobed branch is load-bearing.

Harness (v3, the GH-25 gate's exact image-stamping discipline): the PT arm
word (8211), tag (1535) and PTE (1548) are stamped into the IMAGE pixels
post-bake (_write_pte/_arm_pt of tests/test_gh25_hilbert_paging.py:229-247).
The CPU's RAM-first PTE fetch finds memory[1548]==0 (ram_words=16384 arms a
zero RAM) and falls back to the image PTE — the GH-25 designed path; the
twin's walk_ld/walk_st do the identical RAM-then-image fallback (:375-377,
:414-416). Bake-time data_words seed only NON-reserved words (the canary at
3072, box words at 8195/8196 — 8192+ is NOT in _BAKER_RESERVED_RANGES).
The canary sits in RAM on the twin via run_wgsl's ram_seed; on the CPU via
cpu.memory — the runner's `memory` receipt is the CPU's RAM array, so
mem_3072 is the CPU-side readback; ram_3072 is the twin's.
Both engines run the IDENTICAL baked image. USER mode via the kernel's own
MODE_LATCH + KJMP prologue (CPU one-shot glyph_isa_v2.py:1270-1274; twin
KJMP arm wgsl:618-633 — parity by construction).

Source-read facts under test (RTX 5090, wgpu 0.32.0):
  S1: twin walk_ld's paged branch checks ONLY PTE_V — zero PTE_U/PTE_W refs
      (PTE_U defined at wgsl_glyph_isa_v2.py:172, never consulted). Oracle
      checks PTE_U on paged USER LD (glyph_isa_v2.py:872-876) and PTE_W +
      PTE_U on paged ST (:997), faulting pte_invalid through E-K1.
  S2: twin walk_ld's paged branch has NO fence consults — 0 tile refs, 0
      addr_in_box refs, no MMIO read posture: a mapped VA whose PTE targets
      the config block is readable in USER through translation (BK-56's
      posture only guards the UNPAGED branch at :361-363).
  S3: twin walk_st's paged branch drops unmapped stores SILENTLY ("return
      false" :441), validates only PTE_V — the oracle faults pte_invalid
      (op=ST) through E-K1 and vectors KFAULT_PC.

Verdicts from READBACK BYTES (receipt memory/ram/registers/fault fields),
never stdout. Run: python3 .builder_queue/probe_wgsl_paged_fence_af3e.py
"""
import hashlib
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
for p in (str(REPO), str(REPO / "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np  # noqa: E402

CANARY = 0x0ADF00D
BOX_LO, BOX_HI = 1200, 1300        # byte addresses of the armed box
PT_TAG_WORD = 1535
PT_BASE_WORD = 1536
PT_ARM_WORD = 8211                  # PAGE_TABLE_WORD
VPN12_PTE_WORD = PT_BASE_WORD + 12  # 1548
MODE_LATCH_WORD = 8192              # BOX_MMIO_BASE >> 2
PTE_V, PTE_W, PTE_U = 1, 2, 4
VA_CANARY = 3072                    # vpn 12 offset 0
VA_MMIO = 12 * 256 + 4              # 3076: plain PTE pfn 32, offset 4 -> word 8196
RECEIPT_WORD = 720                  # task writes its verdict word here
FAULT_ADDR_WORD = 8199


def source_legs():
    src = (REPO / "tools" / "wgsl_glyph_isa_v2.py").read_text()
    wld = src[src.index("fn walk_ld"):src.index("fn walk_st")]
    wst = src[src.index("fn walk_st"):src.index("// E-K1: is byte_addr")]
    return {
        "S1_walkld_PTE_U_refs": wld.count("PTE_U"),
        "S1_walkld_PTE_W_refs": wld.count("PTE_W"),
        "S1_walkld_PTE_V_refs": wld.count("PTE_V"),
        "S1_walkst_PTE_U_refs": wst.count("PTE_U"),
        "S1_walkst_PTE_W_refs": wst.count("PTE_W"),
        "S2_walkld_tile_refs": wld.count("TILE"),
        "S2_walkld_addr_in_box_refs": wld.count("addr_in_box"),
        "S3_walkst_unmapped_silent": (
            "return false; // unmapped store: dropped" in wst),
    }


def kernel_prologue(arm=True, box=True, latch=True):
    lines = [":__entry", "JMP :__kmain", ":__kmain",
             "LDI r15 %d" % RECEIPT_WORD, "LDI r14 0", "ST r15 r14"]
    if box:
        lines += ["LDI r15 8195", "LDI r14 %d" % BOX_LO, "ST r15 r14",
                  "LDI r15 8196", "LDI r14 %d" % BOX_HI, "ST r15 r14"]
    if arm:
        lines += ["LDI r15 %d" % PT_ARM_WORD, "LDI r14 %d" % PT_BASE_WORD,
                  "ST r15 r14"]
    if latch:
        lines += ["LDI r15 %d" % MODE_LATCH_WORD, "LDI r14 1", "ST r15 r14",
                  "LDI r30 0", "KJMP r30"]
    return "\n".join(lines) + "\n"


def kernel_epilogue():
    return (":__kdone\nLDI r3 4660\nLDI r15 %d\nST r15 r3\nHALT\n"
            % RECEIPT_WORD)


def leg_programs():
    """(program_text, image_stamps, ram_seeds_or_None).
    image_stamps: word->value stamped into image pixels post-bake (PT words).
    ram_seeds: twin-side ram buffer seeds (canary); CPU gets the same value
    via data_words bake seed (word 3072 is non-reserved, allowed)."""
    pte_vwu_12 = PTE_V | PTE_W | PTE_U | (12 << 8)
    pte_vw_12 = PTE_V | PTE_W | (12 << 8)
    pte_vwu_32 = PTE_V | PTE_W | PTE_U | (32 << 8)
    pte_vw_32 = PTE_V | PTE_W | (32 << 8)
    tags = {PT_TAG_WORD: 0x505447}
    arm = {PT_ARM_WORD: PT_BASE_WORD}
    prog_ld = (":__task\nLDI r15 %d\nLD r10 r15\n")
    prog_st = (":__task\nLDI r5 %d\nLDI r15 %d\nST r15 r5\n")
    return {
        # D1: identity map vpn 12 (V|W|U pfn 12); USER LD of the canary word.
        "D1_paged_control": (
            kernel_prologue() + prog_ld % VA_CANARY + kernel_epilogue(),
            {**tags, **arm, VPN12_PTE_WORD: pte_vwu_12},
            {VA_CANARY: CANARY}),
        # D2: U CLEAR (V|W). Oracle must pte_invalid-fault (glyph :872-876);
        # twin per S1: canary arrives, no fault channel exists.
        "D2_pte_u_bypass": (
            kernel_prologue() + prog_ld % VA_CANARY + kernel_epilogue(),
            {**tags, **arm, VPN12_PTE_WORD: pte_vw_12},
            {VA_CANARY: CANARY}),
        # D3: plain PTE pfn 32 offset 4 -> word 8196 (BOX0_HI). USER reads
        # the config block THROUGH the translation path (S2). Twin's paged
        # plain-frame path reads ram[8196]; seeded = BOX_HI.
        "D3_mmio_read_through_pte": (
            kernel_prologue() + prog_ld % VA_MMIO + kernel_epilogue(),
            {**tags, **arm, VPN12_PTE_WORD: pte_vwu_32},
            {8196: BOX_HI}),
        # D4: vpn 12 UNMAPPED (PTE 0). USER ST canary -> 3072. Oracle must
        # pte_invalid(op=ST)-fault (:997-1006); twin per S3: silent drop.
        "D4_unmapped_store_silent": (
            kernel_prologue() + prog_st % (CANARY, VA_CANARY) + kernel_epilogue(),
            {**tags, **arm, VPN12_PTE_WORD: 0},
            None),
        # C1: PT NOT armed (no arm ST, no tag) — plain USER ST out-of-box
        # word 100. Both engines must E-K1 (box words still armed in-prog).
        # Isolates the armed-walker delta between C1 and D4.
        "C1_unpaged_ek1_control": (
            kernel_prologue(arm=False, box=True)
            + prog_st % (4660, 100) + kernel_epilogue(),
            {},
            None),
        # C2: D3's table, SUPER mode (no latch/KJMP): kernel-mode LD of the
        # same VA. Both engines return the word (translation sane for SUPER;
        # pins D3 as the USER-posture gap, not a broken walker).
        "C2_super_paged_mmio_read": (
            kernel_prologue(arm=False, box=False, latch=False)
            + prog_ld % VA_MMIO + "HALT\n",
            {**tags, VPN12_PTE_WORD: pte_vw_32},
            {8196: BOX_HI}),
    }


def bake_two_pass(text, cols_instrs=8, min_rows=16):
    """Two-pass bake (GH-17 paged_kernel_image discipline, gh25_hilbert_
    paging.py:268-284 shape): pass 1 assembles the text WITH the placeholder
    'LDI r30 0' already present (identical instruction count in both passes —
    inserting the LDI between passes would shift :__task and mis-target the
    jump by one), reads :__task's coords, pass 2 re-assembles with the real
    packed pixel PC. packed = (col)|(row<<16). Legs without a latch have no
    KJMP and no :__task — they bake in one pass."""
    from tools.rv64i_to_glyph import assemble_glyph_to_pixels
    from tools.glyph_gpt.baker import bake_image
    if "KJMP r30" not in text:
        return bake_image(text, cols_instrs=cols_instrs, min_rows=min_rows,
                          out_path=None)
    assert "LDI r30 0\nKJMP r30" in text, (
        "leg text must carry the placeholder 'LDI r30 0' before KJMP so both "
        "passes have identical instruction counts")
    _, coords = assemble_glyph_to_pixels(text, cols_instrs=cols_instrs,
                                         min_rows=min_rows)
    col, row = coords[":__task"]
    packed = (col & 0xFFFF) | ((row & 0xFFFF) << 16)
    final = text.replace("LDI r30 0\nKJMP r30",
                         f"LDI r30 {packed}\nKJMP r30")
    return bake_image(final, cols_instrs=cols_instrs, min_rows=min_rows,
                      out_path=None)


def stamp_image(img, stamps):
    """_write_pte/_arm_pt discipline (GH-25 gate :229-247): 24-bit value at
    a linear word, scanline."""
    h, w, _ = img.shape
    for word, val in stamps.items():
        img[word % (h * w) // w, word % (h * w) % w] = (
            (val >> 16) & 0xFF, (val >> 8) & 0xFF, val & 0xFF)
    return img


def run_legs():
    from tools.glyph_gpt.baker import bake_image
    from tools.glyph_gpt.runner import GlyphRunner

    results = {}
    for name, (text, stamps, ram_seeds) in leg_programs().items():
        with tempfile.TemporaryDirectory() as td:
            png = Path(td) / f"{name}.png"
            # canary seed for the CPU: data_words at word 3072 is allowed
            # (non-reserved); twin gets it via ram_seed below. Two-pass bake
            # resolves :__task's pixel PC for the KJMP latch.
            seeds = {}
            if name in ("D1_paged_control", "D2_pte_u_bypass"):
                seeds[VA_CANARY] = CANARY
            img = bake_two_pass(text, cols_instrs=8)
            for a, v in seeds.items():
                stamp_image(img, {a: v})
            stamp_image(img, stamps)
            from PIL import Image
            Image.fromarray(img.astype(np.uint8)).save(png)
            runner = GlyphRunner(png, ram_words=16384)
        rec_cpu = runner.run(max_instructions=4000)
        rec_wgsl = runner.run_wgsl(max_steps=4000,
                                   ram_seed=dict(ram_seeds or {}))
        results[name] = {"cpu": cpu_view(rec_cpu), "wgsl": wgsl_view(rec_wgsl)}
    return results


def cpu_view(rec):
    mem = rec.get("memory") or []
    return {
        "halted": rec.get("halted"),
        "faulted": rec.get("faulted"),
        "fault_addr": rec.get("fault_addr"),
        "r10": (rec.get("registers_full") or [0] * 11)[10],
        "receipt_720": mem[720] if len(mem) > 720 else None,
        "mem_3072": mem[3072] if len(mem) > 3072 else None,
        "mem_100": mem[100] if len(mem) > 100 else None,
        "steps": rec.get("steps"),
        "error": rec.get("error"),
    }


def wgsl_view(rec):
    ram = rec.get("ram") or []
    return {
        "halted": rec.get("halted"),
        "r10": (rec.get("registers_full") or [0] * 11)[10],
        "receipt_720_ram": ram[720] if len(ram) > 720 else None,
        "ram_3072": ram[3072] if len(ram) > 3072 else None,
        "ram_100": ram[100] if len(ram) > 100 else None,
        "steps": rec.get("steps"),
        "error": rec.get("error"),
    }


if __name__ == "__main__":
    print("== S legs (source reads) ==")
    for k, v in sorted(source_legs().items()):
        print(f"{k} = {v}")
    print("== D/C legs (CPU oracle + WGSL twin, RTX 5090) ==")
    try:
        d = run_legs()
        blob = json.dumps(d, indent=1, sort_keys=True)
        print(blob)
        print(f"results_md5={hashlib.md5(blob.encode()).hexdigest()}")
    except Exception as e:  # noqa: BLE001
        print(f"LEG-ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
