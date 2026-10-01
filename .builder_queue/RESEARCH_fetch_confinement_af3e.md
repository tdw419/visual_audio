# RESEARCH — PC/fetch confinement: a tile-confined task's own program text lives
# entirely outside its tile, and fence-blind writes compose with JMPR into
# direct out-of-tile execution (no trap needed)

**Builder:** af3e62239ce2 (Hermes cron, Glyph OS event chain)
**Date:** 2026-09-28 ~04:5x CDT
**Claim HEAD:** 2626466d (ledger HEAD at claim re-verified: 2626466d5ad1e6a15b1196380b9bbac1212f729c)
**Probe:** `.builder_queue/probe_fetch_confinement_af3e.py`
**3 runs byte-identical, stdout md5 `0f1ef65668f0a51e906139b45cd970cf`, results md5 `01c45108a20f2d6725b8117cddfa71b0`**
**Numbers structural (word values, addresses, exit codes) — rule-1 floors do not attach.**

## The question

Every fence row (BK-38..45, 52/53, 60..66) governs **data** arms: LD/ST,
PARALLEL, stack ops, syscall dests, frame paths, the trap vectors. The
**fetch** side was never probed: `step()` reads instruction pixels
directly from the image (`glyph_isa_v2.py:753-764`) with zero
`_addr_in_box` consults, and every jump arm (`JMP` :1208, `JZ/JNZ/JLT/
JGT`, `JMPR` :1245, `CALL`, `RET`, `CALLR`, `KJMP`) sets `next_pc` with
no fence consult — only `_check_alignment` (col%4) guards the target.

Two sub-questions:
1. **Census:** where does a tile-confined task's fetch actually run?
2. **Composition:** can the task reach *its own choice* of out-of-tile
   code, by direct jump (no trap, no BK-53 vector involvement)?

Sub-question 2 is distinct from BK-53 (whose escape runs through the
E-K1 trap and lands in SUPER): here the jump is an ordinary USER-mode
instruction and the injected code executes **in USER**, with the fence
still nominally armed.

## Method (what was read, what was run)

Source read first (paths precise, HEAD 2626466d):

- `tools/glyph_isa_v2.py:751-770`: fetch = `image[y, x]` at `self.pc`,
  bounds check is image-shape walk-off only; no mode/box/tile term.
- `:1208-1212` (`JMP`), `:1245-1252` (`JMPR`): `next_pc = (tx*4, ty)`
  from imm/register; alignment check only.
- `:1041` (the single `_addr_in_box` consult) is on the ST arm — fetch
  never passes through it.
- `tools/glyph_containment.py:74-99` (`arm_tile`): tile words + USER
  drop happen host-side pre-instruction; nothing pins PC to the tile.

Probe harness (delta-minimal vs tick 8's):

- `GlyphProcessTable(memory_words=16384).spawn(image=img,
  tile=(256,19,1,2), max_instructions=500)` — the REAL item-29 posture,
  identical tile to tick 8 (covers RAM words 8211/8212). NO paging this
  tick: fetch never translates on the oracle BY SOURCE READ (`:753`
  reads the image directly; the paged-fetch sibling is a source-read
  note, not probed).
- `min_rows=64` image (32×64), so the whole program text occupies image
  rows 0..63 — ALL outside tile rows 256..257.
- Injected payload = the 4 pixels of `LDI r10 <imm>` — opcode color
  resolved at runtime from `OpcodeMapV2().opcode_to_rgb("LDI")` =
  (236,80,80), never hand-encoded.
- Verdicts from `exit_status`, `cpu.faulted/fault_addr/fault_reason`,
  `cpu.mode`, `cpu.registers[10]`, and post-run image readback — never
  stdout (F0's PRT output is a control artifact only).

## Findings (3 runs byte-identical, md5s above)

| Leg | Program | Result | Meaning |
|---|---|---|---|
| **F0** | in-program `JMP 2,0` over a PRT | exit 0, clean, USER | jump machinery live in this harness |
| **F1** | PC census: manual step-loop over `LDI r10 0x0ADF00D; LDI r5 1; HALT`, trace `cpu.pc` per step | rows visited = **[0]** — PCs (0,0),(4,0),(8,0); exit 0, r10=0x0ADF00D | the ENTIRE fetch runs at image row 0, physically outside tile rows 256..257; the program never executes one instruction inside its own tile — and runs clean |
| **F2** | `LDI r15 (40<<16); JMPR r15` with `LDI r10 0x0ADF00D` pixels pre-stamped at (0,40) | exit 0, **r10=0x0ADF00D**, faulted=False, mode USER; then `opcode-None pixel at (4,40)` | USER-mode execution of code OUTSIDE the tile via a direct jump: the injected LDI executed (canary landed in r10), ran off the 4-pixel payload into black pixels (loud halt, no fault) |
| **F3** | full injection: four `PUSH`es (r31=1601..1604, pre-decrement writes image pixels 1600..1603 = row 50 cols 0..3) then `JMPR` to (0,50) | exit 0, **r10=0x0ADF00D**, faulted=False, mode USER; injected word0 readback 15487056 = 0xEC5050 = the LDI opcode color | the task WRITES instruction pixels outside its tile through BK-39 leg-4's fence-blind image-plane PUSH, then EXECUTES them — arbitrary code injection + execution in USER, no trap, no KFAULT_PC, composed entirely from fence-permitted-looking ops (PUSH has no box consult, :1122-1124) |
| **C1** | unpaged out-of-tile ST word 164 | exit 1, fault_addr 656, SUPER | the data fence is LIVE in the exact posture where F2/F3 execute out-of-tile — the probe discriminates |

Interpretation: the item-29 containment statement ("the fence the task
cannot cross is its own tile") is a DATA-plane statement. The tile is
not an execute-confinement boundary at all:
- the spawn posture NEVER places program text inside the tile (fetch
  census F1), so every landed tile-confined leg to date ran its whole
  text out-of-tile;
- the code plane (image pixels) and the data plane (RAM words) are
  disjoint fences, and the code plane has NO fence;
- BK-39 leg 4's "instruction-stream corruption class, RAM-grid blast
  radius unproven" closes: the blast radius is EXECUTION (F3), reachable
  by PUSH + JMPR alone, in USER, without touching the trap machinery
  BK-52/53 guard.

## Consequence (candidate filing)

The fetch/jump arms are a fence-blind surface family of their own:
`step()`'s fetch (:753-764) plus jump arms :1208/:1245/:1130/:1145/
:1275/:1259. Any fix posture (execute-confine PC to the tile when
tile-armed; or a code-plane box) is a design-judgment item — research
files the measurement, not the posture.

**Candidate BK-67 filed** to `systems/GLYPH_BACKLOG.md`:
PC/fetch confinement — fetch + jump arms must consult the confinement
predicate (or the spawn posture must pin executable rows). Gate
`tests/test_bk67_fetch_confinement.py`: RED-first legs = F2/F3's
measured shapes (out-of-tile fetch/jump must trap or refuse), L3
in-tile/marked-rows control, L4 rot-guard pinning C1's live data fence,
L5 non-vacuity, L6 family green. Lands in the BK-38..57 sequenced fence
commit family. Posture decision flagged for the landing gate / Jericho
per the header's design-judgment rule; row filed as a candidate,
promotion-gated.

## What this receipt does NOT prove

- No engine code changed — research proposes, never lands.
- WGSL twin NOT probed: the twin has no spawn(tile=) harness at all
  (BK-51) and no separate Python step() — a twin fetch-confinement leg
  cannot exist until a tile term lands there.
- Paged fetch (GH-17 instruction translation, if any) unprobed — source
  read says fetch never translates on the oracle (:753); the paged×tile
  composition of tick 8 concerned data arms only.
- JZ/JNZ/JLT/JGT/CALL/RET/CALLR/KJMP arms not individually probed (same
  next_pc shape by source read; JMPR carried the measurement as the
  data-sourced representative).
- F2/F3's post-payload halt is `opcode-None` (a silent-halt-class stop
  with a loud halt_reason string, :767-770) — the receipt claims
  execution of the injected instruction (r10 readback + exit path), NOT
  a clean program landing; the payload was 1 instruction by design.
- steps field reads -1 (the engine's run() return value is not stored
  on the CPU object; step counts not pinned).

## Probe defects (disclosed, per discipline)

1. F1's first harness version never set `cpu.running = True` — the
   step-loop exited immediately, `pc_rows_visited: []` (a vacuous
   census). Caught by refusing to accept an empty trace as a finding
   (an empty execution is a dead harness, not "no fetches"); fixed by
   setting `running=True` before the loop. The census datum (row 0
   only) comes from the fixed version.
2. First encoding draft split the canary 0x0ADF00D into pixel bytes
   (0x0A,0xDF,0x0D) — a 6-hex-digit slip. Caught by cross-checking the
   pre-stamp word readback (15487056 = the opcode pixel) against the
   runtime-resolved LDI color; fixed to (0xAD,0xF0,0x0D) BEFORE the 3
   pinned runs. The 3 pinned runs use the corrected encoding
   (r10 = 11399181 = 0x0ADF00D in F2/F3).
3. F0's first jump target (`JMP 1,1`) tripped the assembler's
   bounds-check (index 9 in a 4-instruction program) — rewritten
   `JMP 2,0` with padding NOPs. Mechanism unchanged.

## Self-assessed priority signal (name the command)

`grep -c "tile" .builder_queue/RESEARCH_*.md | sort -t: -k2 -rn | head -3`
→ the fence-research lane keeps rediscovering image-plane write arms;
this is the first receipt that measures the EXECUTE side those
"instruction-stream corruption class" labels point at (BK-39 :66, BK-40
:67, BK-42 :69, tick-8 T2). Blast radius: F3 is the first measured
chain from a confined USER task to executing attacker-chosen pixels
with the fence armed and no trap involved — stronger than BK-53's
trap-mediated escape in that it needs no fence violation to trigger.
