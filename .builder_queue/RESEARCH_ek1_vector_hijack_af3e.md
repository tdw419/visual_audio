# RESEARCH — E-K1 trap-vector hijack: the fence's own trap is a USER→SUPER escape primitive

**Builder:** af3e62239ce2 · **Date:** 2026-09-27 · **Lane:** Phase 1c research tick (claim queue empty, monitor CLEAN queue=0 stall_tier=0, mailbox clean)
**Tree:** HEAD 5d05c530, tracked clean at claim. Probe `.builder_queue/probe_ek1_vector_hijack_af3e.py` (untracked, landed modules only). No engine/shader code touched.

## Question

BK-39 leg 4 and BK-40 leg 4 measured fence-blind **image-plane writes** from a confined USER task, but both left the same blast radius explicitly unproven: does an out-of-tile image pixel ever get **executed**? This probe closes that question and finds something stronger: the E-K1 store-fence trap **itself** is the escalation primitive. The trap arm (glyph_isa_v2.py:1052-1056) reads KFAULT_PC **live at trap time** and jumps there in SUPER mode — so anything the confined task can plant at the vector target executes with the fence **disabled** (SUPER stores skip `_addr_in_box`, :1041).

## Method

- Harness = the landed item-29 posture itself: `GlyphProcessTable.spawn(img, tile=(5,0,8,8))`, reaper trampoline `HALT` at (col 0, row 30) = word 960 (glyph_containment.py:104-119), KFAULT_PC=1966080 armed at spawn (glyph_process.py:168-169). OUT word 168 → E-K1 fault_addr 672.
- Payload words extracted from the **real assembler** (`GlyphAssemblerV2.assemble`, never hand-encoded), staged via `PARALLEL_ST` (fence-blind RAM write + GH-8b pixel mirror, glyph_isa_v2.py:1291-1295 — the two mechanisms BK-39/40 measured), then the task issues one out-of-tile `ST` to trigger E-K1.
- Helper decode legs: `.builder_queue/dbg_ek1_decode_af3e.py` (payload word dump), `.builder_queue/dbg_ek1_d5b_af3e.py` (kf→pixel-PC arithmetic: col×4 + row×32).
- Determinism: 3 full runs byte-identical, stdout md5 **5e107adaa9495bb7e1d4804d30444fc3**.

## Findings (measured, all USER, tile armed)

| Leg | Program shape | Result | Verdict |
|---|---|---|---|
| **D1 pixel overwrite** | stage `PRT r6; HALT` words to 960..963, canary r6=4660, ST→168 | trampoline pixels now `f75350 ffff06` (PRT r6); trap vectors there; PRT emits `0x34` (=4660&0xFF); mode SUPER | **ESCAPE** — attacker code executes from the trap |
| **D3 SUPER capability** | stage `LDI r2 164; LD r6 r2; LDI r3 0x0ADF00D; ST r2 r3; HALT` to 960.., ST→168 | post-run `memory[164]==11399181` (0x0ADF00D) — the exact out-of-tile store E-K1 refuses **lands**, written by trapped-into code after an out-of-tile LD | **FULL FENCE ESCAPE** — read+write outside tile, delivered by the fence's own trap |
| **D5 vector rewrite** | `PARALLEL_ST` (30<<16)\|4 → word 8193 (KFAULT_PC), payload staged at word 976 = pixel (16,30), ST→168 | kfault_word=1966084 (rewritten); original trampoline pixels **untouched** (`ff6347` HALT still at 960); PRT emits `0x34` from the NEW target | **VECTOR REWRITE** — trap executes attacker-chosen PC |
| D2 control | canary + ST→168, no overwrite | no PRT, faulted, parked on HALT trampoline | overwrite is the load-bearing step |
| C1 control | plain ST→168 clean spawn | fault_addr=672, mode SUPER, no PRT | E-K1 baseline live |

**Root cause chain (source, measured at each link):**
1. `PARALLEL_ST` writes any RAM word + mirrors to image pixels, no `_addr_in_box` consult (glyph_isa_v2.py:1271-1295) — BK-39's primitive, re-confirmed.
2. The reaper trampoline and any (row,col) pixel are **image-plane** targets the tile fence never guards (fence = RAM word predicate, `_addr_in_box` :720-747).
3. The E-K1 arm vectors KFAULT_PC **unconditionally** at trap time (:1052-1056, no kf-provenance check) and the mode is already **SUPER** (:1051) — the trap is a privileged jump to guest-controlled pixels.
4. SUPER-mode stores skip the box check (:1041), so code reached via the trap can store anywhere.

**Consequence:** the item-29 tile fence is not merely bypassable at its edges (BK-38/39/40/42/43) — its **failure handler** is a privilege-escalation gadget. A confined task that can execute ≥3 instructions (one PARALLEL_ST + one ST) converts any fence violation into arbitrary SUPER execution. Every BK-38..52 "posture decided at landing" rows must treat the **trap vector** as a guest-writable surface in the same sequenced fence commit.

**WGSL twin (source-read, not probed on-device):** `walk_st`'s E-K1 returns a rejected flag and the caller vectors `box_mmio[KFAULT_PC_WORD]` (wgsl_glyph_isa_v2.py:446-450, :218-220) — structurally similar vectoring. BUT mechanism (a) (pixel overwrite via the PARALLEL_ST mirror) is **structurally unreachable on-device**: `_OPCODE_ORDER` (wgsl_glyph_isa_v2.py:34-38) omits all PARALLEL opcodes, and the twin has no image-plane store the payload staging needs. Mechanism (b) (KFAULT_PC word rewrite) reduces to BK-50's unmode-gated box_mmio door — already measured. Twin side therefore inherits the vector-trust problem only through BK-50, disclosed here, not re-measured.

## Probe-defect disclosures (both caught on read-back, before any verdict line was accepted)

1. Draft D5 staged the payload at word 144 (instruction-col × 4 misread as a word address). The vector rewrite landed (kfault 1966084) but execution hit empty pixels at (16,30) — `halt_reason: opcode-None`. Fixed: staging dest = word 976 (pixel (16,30), the exact PC the arm computes: `tx*INSTR_WIDTH=16, ty=30`). Draft artifacts: `.builder_queue/dbg_ek1_d5_af3e.py`.
2. `want_prt` initially asserted a 2-byte packing; PRT emits the register word low-byte as hex text (`34`). Fixed after decode-helper verification (`dbg_ek1_decode_af3e.py`).
3. Harness note: `bytes(cpu.output)` raises on PRT words >255 — masked with `& 0xFF` (PRT contract is the low byte; canary legs unaffected).

## Rule-1 floors statement

All numbers are structural (word addresses, fault codes, register values, byte hex, step-free state reads from a single in-process engine). No rate, ratio, latency, cost, or throughput is asserted. Floors do not attach; no floors_authoritative.json citation required.

## What this PASS does NOT prove

- WGSL twin behavior is source-read only — no on-device probe ran this tick (harness for PARALLEL ops does not exist; structurally absent).
- BK-52's kf=0 replay quirk cannot contaminate these legs (KFAULT_PC nonzero in every leg, verified in each result dict), but the BK-52 **repair** and this item's **fix** interact — both touch :1052-1056 / :1075-1085.
- No fix posture is decided here (kernel-write-only config block vs kf-provenance check vs trampoline-page protection) — that belongs to the sequenced fence commit's landing gate, alongside BK-41's posture decision.
- The RAM-grid write side of the instruction stream (can a payload corrupt a **neighbor task's** image?) remains unprobed: engines own private images (glyph_process.py:160-175), so the cross-task path would have to route through shared VFS or the compositor — noted, not measured.

## Filed

- **BK-53** appended to `systems/GLYPH_BACKLOG.md`: gate `tests/test_bk53_ek1_vector_hijack.py`, lands IN the BK-38..45 sequenced fence commit, blast radius `tools/glyph_isa_v2.py` (E-K1 vector arms) + `tools/glyph_containment.py` (trampoline planting) — engine files, worktree isolation per AGENTS.md.
