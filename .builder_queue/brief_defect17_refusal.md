# Brief — DEFECT-17 option (d): transpiler refusal gate for RV x31 (t6)

Roadmap row: **DEFECT-17** (`.builder_queue/REPAIR_PENDING_defect17_x31_hw_stack.md`,
ruling `.builder_queue/RULING_20260912_defect18_a_defect17_d.md` § Decision 2 — option (d),
loud refusal gate). **Do NOT commit anything.** Do not touch the main checkout.

## Where to work

An isolated worktree is already prepared for you; `REPO` (passed to the wrapper) is:

    /home/jericho/projects/zion/projects/visual_audio_wt_defect17

Do **all** file edits there. Never edit `/home/jericho/projects/zion/projects/visual_audio`
(the main checkout) — a parallel session owns it.

## Read first (in that worktree)

1. `.builder_queue/REPAIR_PENDING_defect17_x31_hw_stack.md` (short, ~80 lines) — the defect.
2. `.builder_queue/bk11_defect17_probe.py` (~60 lines) — the RED witness probe.
3. `tools/rv64i_to_glyph.py` regions: `transpile_rv32i_to_glyph()` at line ~280 (the choke
   point where the instruction stream is decoded via `decode_instruction(word)` →
   `(op, rd, rs1, rs2, imm, aux)`), and `main()` at ~1295 (CLI).
4. `tools/glass_box_demo.py:47` — the existing refusal discipline this must mirror
   (`REFUSAL: GEOS_EMIT_ACK`).

## The defect in one paragraph

The transpiler's register map is the identity map: RV `x0..x30` → glyph `r0..r30`, and
glyph `r31` is the **hardware call stack pointer** (CALL/RET/PUSH/POP all use it). RV `x31`
(`t6`, a caller-saved scratch GCC may use freely) therefore has **no** home. A program's own
`li t6, 90` lowers to `LDI r31 0x5a`, which destroys the call stack, and the next `RET` pops
garbage — silently. Measured RED (`output/bk11_defect17_red.txt`), lowered sequence:

    LDI r31 1087            ; initialize hardware call stack pointer
    JMP :ccpDDTnk.o
    LDI r31 0x5a            ; <-- the program's own li t6, 90
    RET

Ruling (d): do not change the register map. Instead **refuse loudly** — a static scan of the
decoded RV instruction stream refuses an x31 user with a named error, the same discipline as
`INTEGRITY_FAIL` (a detectable failure must never be silent).

## Deliverable (two files, additive only)

**1. `tools/rv64i_to_glyph.py`** — add a static scan + named refusal:

- A module-level scan function (suggested: `scan_rv_x31_references(text_bytes, base_addr=0)`)
  that walks the text section 4 bytes at a time, uses the existing `decode_instruction(word)`,
  and reports every instruction where `rd == 31 or rs1 == 31 or rs2 == 31` — as a list of
  records carrying the pc, the 32-bit word, the mnemonic/op if cheaply available, and which
  role(s) reference x31 (dest / src1 / src2). `decode_instruction` returning `None` (data or
  unknown) must be skipped, never treated as a hit.
- A named exception class, exported: `class RVX31RefusalError(RuntimeError)`. Its message
  **must contain the literal substring** `REFUSAL: RV x31`, and should name the first
  offending `pc`, the hex word, and the role(s), plus a one-line explanation that lower glyph
  `r31` is the hardware call stack so lowering would silently corrupt it.
- Wire the scan in exactly **one** choke point — the top of `transpile_rv32i_to_glyph()` —
  so both entry paths (`raw text` callers and `transpile_elf_to_glyph()`) are covered and no
  caller can bypass it. Raise before any lowering work happens. Document the refusal in that
  function's docstring (Raises:).
- **No change to any lowering/emit semantics, no register-map change.** For a program with no
  x31 reference the generated Glyph assembly must be byte-identical to the pre-change output.
  Additive scan + raise only.

**2. `tests/test_defect17_x31_refusal.py`** — the gate (this is the module the roadmap row
names). Four legs, all non-vacuous (each must fail if the scan is removed or neutered):

- **L1 library refusal:** hand-assembled RV32I words for `li t6, 90` (== `LDI r31 0x5a`
  hazard: `addi x31, x0, 90`) followed by `ret` (== `jalr x0, 0(x1)`, jalr with rd=x0,
  rs1=1) → `transpile_rv32i_to_glyph()` raises `RVX31RefusalError`, the message contains
  `REFUSAL: RV x31`, and it names the offending pc.
- **L2 no false positive / no regression:** the same program *without* the x31 write
  transpiles without raising. Capture goldens **before** you add the scan (run the
  pre-change code on 2–3 real corpus inputs, e.g. the BK-1 C main + rt0 shim used by
  `tests/test_bk1_argv.py`, or any committed `.elf`/fixture the repo transpiles) and compare
  the post-change output byte-for-byte in the gate. Store goldens under `tests/fixtures/`
  or regenerate them in-test from a frozen copy — do not leave them in `/tmp`.
- **L3 CLI refusal leg:** run the tool as a subprocess (`sys.executable`, `-m` or direct
  script path) on the x31 fixture → exit code != 0 and `REFUSAL: RV x31` on **stderr**; and
  on a clean fixture → exit 0 with output on stdout. Use a committed fixture ELF or text
  file under `tests/fixtures/`.
- **L4 corpus stays clean:** assert the scan reports zero x31 references on a real gate
  corpus input (the BK-1 shim / a committed coreutils fixture) — this is the tripwire the
  ruling names, so it must be a measured count, not a comment.
- Also assert the refusal is catchable as a distinct type (e.g. `pytest.raises(RVX31RefusalError)`)
  so callers can distinguish it from a crash.

## Gate command (run it yourself, in the worktree, and paste the output)

    cd /home/jericho/projects/zion/projects/visual_audio_wt_defect17
    /usr/bin/python3 -m pytest tests/test_defect17_x31_refusal.py -q
    /usr/bin/python3 -m pytest tests/test_bk1_argv.py -q      # L4/regression control

`/usr/bin/python3` is the canonical interpreter (py3.12 user site); the worktree has no venv,
so run from the worktree root and let the repo's `conftest.py` handle `sys.path`. If an
import fails for that reason, set `PYTHONPATH=$PWD` — do not install packages.

## Constraints

- **Do not commit.** Leave the changes in the worktree working tree.
- **In scope:** `tools/rv64i_to_glyph.py`, `tests/test_defect17_x31_refusal.py`, plus
  committed fixtures under `tests/fixtures/` if you need them. Nothing else.
- `tests/test_*.py` is hidden by `.gitignore` — that is expected; the orchestrator force-adds
  it. Do not fight the ignore rules.
- Iterate up to 6 attempts on the gate. If still red, stop and report the exact failing
  command and output — a precise RED report is a valid result, a silent half-fix is not.
