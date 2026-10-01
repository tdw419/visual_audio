# Glyph ISA Improvement Roadmap

**Authored 2026-09-16** (agent, at Jericho's request). Provenance note: every
item below traces to a measured failure or a verified gap from this session's
work; nothing is aspirational filler. Items marked **[J-DECISION]** reserve
the call to Jericho explicitly — this document proposes sequencing, it does
not self-ratify.

Ground rule inherited from the session: a gate that cannot fail is not a
verification. Every phase lands with a red-proven test (the SE021 standard:
measured failure → fix → measured green → blast-radius sweep).

---

## Measured ground truth (2026-09-16, HEAD d009e0c)

| Fact | Measurement |
|------|-------------|
| Python ISA surface | 31 opcodes (GlyphCPUv2 dispatch) |
| WGSL twin opcode table | auto-generated from Python map → table parity is automatic |
| WGSL twin syscall layer | NONE (0x04/0x09/0x12 absent from exec path) |
| gpu_frame_exec.py (SE016) | 0 syscalls — arithmetic/control-flow only |
| Program height limit | 62 rows (FS window aliases image rows 64..80 by definition) |
| Named faults | fault_reason exists but undecodable pixel = silent unnamed halt |
| JZ semantics trap | fired twice in two days incl. the session that documented it |
| Memory model | dual-space (RAM array vs image) with one alias window — root cause of SE021's 3-day stack |

---

## Pillar 1 — Feedback & Safety (ships alone, no design decisions needed)

The ISA's worst failure mode is *silent wrongness*: unnamed halts, empty
outputs, inverted-jump loops that only tests catch. This pillar makes wrong
programs loud.

### 1.1 SE024 — JNZ/JNE alias opcodes (additive)
- **LANDED 2026-09-16** (0d02f4a on se024-jnz-jne, receipt e64f725): JNZ and
  JNE alias opcodes added to OpcodeMapV2 + Python dispatch + WGSL twin
  (table regen), JZ untouched, twin byte-exact. 16 tests across
  test_se024_jnz_jne.py (incl. the non-vacuity leg: the exact
  inverted-jump loop shape that trapped the SE023 porting session,
  load-bearing on JNZ semantics) and test_se024_wgsl_parity.py (live GPU
  leg, wgpu/mesa). Pre-commit 38-test differential green at HEAD.
- Kills the trap for all NEW code without touching the 51-file JZ surface.
- Remaining rung: none for the opcode itself; the (b) ladder's second
  item (CMP tri-state, JLT/JGT) is 1.3 below.
- Concurrent-session gate record (builder cron af3e62239ce2): all 5
  ticket gates green — RED 8F/4P at pre-patch `971261f` (KeyError
  'JNZ'/'JNE'), GREEN 12/12 (`tests/test_se024_jnz_jne.py`), arc
  SEED=202609161 rc=0 323P/1S, pre-commit differential 38/38, WGSL twin
  parity 4/4 live + non-vacuity probe (JZ-in-JNZ-slot → 0x1 vs correct
  0xAA, gate discriminating). Receipt
  `systems/RECEIPT_SE024_JNZ_JNE.md`; WGSL leg ran mesa/i915, not the
  5090 — vendor-driver run not performed.

### 1.2 Named faults — no more unnamed halts
- Undecodable pixel → fault with pc, pixel RGB, and "opcode-None at (x,y)"
  instead of running=False silence. `fault_reason` plumbing already exists.
- This session's leg-2 bug would have been a 5-minute diagnosis instead of
  an 87-tick gate if (4,68) had said "opcode-None, pixel (0,0,67), this is
  inside the FS window's image footprint."
- **Landed 2026-09-16 as `halt_reason` (dfc6126)** — the cheap version
  first: halt_reason names opcode-None pixels and walk-offs (pc + RGB in
  the string), stays None on normal HALT, 4/4 tests incl. a non-vacuity
  leg.
- **5-site follow-up RULED + LANDED 2026-09-16 (Jericho, in-channel,
  delegated via "you lead" for this fork).** All 5 sites are under the
  spatial page walker's kf==0 (no kernel-fault-handler-armed) branch and
  ALREADY set `faulted=True` — the honest classification is "these are
  faults," not a named-halt-vs-stay-as-is ambiguity. Inspection found 3 of
  5 already set `fault_reason` (tag-mismatch, via `check_pt_tag`'s
  `tag_reason`); the other 2 (LD's and ST's PTE-invalid/permission-denied
  branches) left `fault_reason=None` despite `faulted=True` - an
  inconsistency, not a design question. Fixed both to match their
  siblings' style (`pte_invalid pte=... vaddr=... mode=... op=LD|ST
  site=glyph_isa_v2`); gated by tests/test_glyph_pte_invalid_fault_reason.py
  (3 tests incl. non-vacuity), full differential + parity sweep (65
  tests) clean, twin synced byte-identical.
- Gate: fault-injection test proving RED before / GREEN after (shipped:
  tests/test_glyph_halt_reason.py, tests/test_glyph_pte_invalid_fault_reason.py).

### 1.3 Comparison flags — CMP writes tri-state, JLT/JGT opcodes
- Second rung of the (b) mitigation ladder (provenance-corrected ruling,
  ROADMAP.md 2026-09-16): cmp result becomes a real eq/lt/gt encoding.
- Enables sign-aware loops; JZ keeps legacy meaning forever.
- Gate: same additive discipline as 1.1. **[J-DECISION: file as SE025 or
  fold into SE024's ticket]**

**Pillar 1 exit criteria:** every way a program can stop has a name; new
code has no reason to touch JZ; transpiler can emit jump-only-on-condition
idiomatically.

---

## Pillar 2 — Engine Convergence (make "not just Python" true)

Today the syscall layer — the OS-shaped half of the machine — exists only
in the Python interpreter. The WGSL twin executes the arithmetic ISA out of
container frames but has no I/O, no filesystem, no process spawn. The gap
is not incidental: RUN2's allowlist, `_read_path`, and the errno contract
are host-Python semantics invisible to the pixel format.

### 2.1 Define the syscall ABI as a spec, not a Python function
- One page per syscall: register contract, argument addressing (which
  memory view!), return codes, errno set, containment rules.
- Written against the ISA, implementable by any engine. The errno
  discussion (#5 this session) already produced the right frame: the
  contract is the interface, engines are implementations.
- Gate: the doc's register/addr claims are extracted from code by a test
  (doc-rot guard), not transcribed.

### 2.2 WGSL twin: FILE_READ/FILE_WRITE over a virtual FS binding
- No subprocess on GPU — instead a memory-mapped FS region the host fills
  before dispatch (same pattern as the existing FS window, formalized).
- Unlocks: GPU-executed programs that do I/O → parity tests become
  cross-engine golden runs (same PNG, same observable output, both engines).
- Gate: golden test corpus runs byte-identical observable output on
  GlyphCPUv2 and the WGSL twin. **[J-DECISION: scope — which syscalls are
  "core ISA" (twin-required) vs host-only (Python spec impl)]**

### 2.2a SYSCALL_READ divergence — Python/WGSL split introduced 2026-09-16
- **Fresh, measured, not hypothetical**: 7f47606 gave the Python engine a
  real input ring (drains INPUT_LEN/CURSOR/DATA, returns bytes ACTUALLY
  read so "no more input" is distinguishable from "zero bytes"). The WGSL
  twin's syscall 2u is still the old stub — `mem_write(addr+i, 0u)`,
  always returns 0. Everything built on real READ semantics (SE020's
  interactive shell line) currently works ONLY on the Python engine,
  silently. Found by Claude's roadmap review, same day.
- This is Pillar 2's thesis in miniature: the twin's syscall layer
  implements *stubs*, not semantics, and stubs drift the moment the
  reference engine evolves. Fix order: (i) WGSL READ drains a
  host-filled input ring with the same return-actual-count contract;
  (ii) the 2.3 parity gate gets a READ-semantics leg (ring exhaustion vs
  zero-byte read, both engines) so this class of divergence is RED in CI,
  not discovered by review.
- Gate: cross-engine READ test where the two engines currently disagree;
  RED at HEAD proves the divergence, GREEN after the twin fix.

### 2.3 Parity gate as a standing CI leg
- Currently parity is checked ad hoc. Make the golden corpus a named
  pytest leg that pre-commit runs when either engine changes.
- Gate: provable RED when a dispatch is edited in one engine only.

**Pillar 2 exit criteria:** an independent-engine implementer could build
a conforming Glyph VM from the spec + golden corpus without reading Python.

---

## Pillar 3 — Memory Model Unification (backlog (d), RULED 2026-09-16)

The scoping pass landed 2026-09-16 (commit e747ebe, receipt pointer in
ROADMAP.md). Two designs were on the table:

- **(A) Unify**: RAM is THE data space; image is ROM; FS window stays as
  the sanctioned persistence alias. Deeper fix; touches every syscall
  handler + WGSL twin + PNG round-trip story.
- **(B) Split syntax**: LD/LDIMG, ST/STIMG — mismatches statically
  checkable, additive, keeps dual-space forever.

**RULING (Jericho, in-channel 2026-09-16, delegated via explicit "you
lead" for this specific fork): (A) scoped to handlers only** — the
scoping receipt's own §7 structural recommendation, not a new argument.
Mechanism: syscall data args (0x01 WRITE, 0x03 FILE_WRITE's data, 0x04
FILE_READ's dest, 0x08 AUDIO_OUT, 0x09 AUDIO_IN's dest — 5 handlers, not
8; §2's other space-taking entries are 0x02 already-RAM and 0x03/0x04/
0x07's path args already view-merged) go RAM per the existing 0x02
precedent. **Correction 2026-09-16 (caught before implementation
started): `0x11 STORE_CODE` stays pixel-space for BOTH its src and dest
per DEFECT-27's ruling (image is ROM for CODE, not for data) and its own
docstring ("Copy code/payload words in pixel space") — the ruling text
above originally and wrongly listed "0x11's src" as migrating; it does
not, 0x11 is fully excluded from this migration.** `0x10 BOOT_LINUX`'s
container-header read is also excluded (not in
`IMAGE_SPACE_WRITE_SYSCALLS`, not part of the scoping receipt's
per-syscall pain inventory — a boot mechanism, not general data I/O; out
of scope for this ruling either way). The `_read_path` view-merge
retires once paths are RAM-first everywhere;
`IMAGE_SPACE_WRITE_SYSCALLS` + the FS-window exemption in the static
check become obsolete and get deleted, not just narrowed. (B) alone was
rejected: it makes the dual-space split statically nameable but leaves
the actual pain (SE021-class syscall-arg-space divergence) in place. Full
(A) (stack migration, PUSH/POP/CALL/RET off image space) is NOT ruled
here — orthogonal, may follow or never.

Corroborating data point (not the deciding one): SE022a/2.2a (commit
b55be74, 2026-09-16) hit exactly this asymmetry live — the WGSL twin's
new SYSCALL_READ has no RAM view to write into, so its destination write
goes through `mem_write` (image space) while Python's goes to
`self.memory` (RAM); the two engines already diverge on READ's dest view
today, papered over only because the parity test checks r9/PRT output,
not the dest address space. (A)-scoped-to-handlers is exactly what
retires this class of divergence for good, rather than accumulating one
more per-syscall exception.

Implementation is its own gated task (11 handler arms + WGSL twin's
bounded E-K2-path delta + ~16 test files per the receipt's blast-radius
census) — NOT done as part of this ruling. Whichever handler lands first
inherits Pillar 1's named-fault infrastructure (a view mismatch becomes a
loud fault, matching the retired static check's original intent) and
Pillar 2's ABI spec (argument addressing gets ONE rule instead of
per-syscall lore).

---

## Pillar 4 — Throughput & Ergonomics (after 1–3)

- **Layout budget**: 62-row program ceiling is real (measured: absolute
  paths blew it; bare filenames leave 11 rows margin). Candidates: banked
  program regions above row 80, or window relocation. Needs its own
  outcome-shaping pass — file only after (d) resolves, since (d)-A may
  dissolve the window entirely.
- **Data directives** (.asciz/.word): kill the per-byte ST-stamp loops
  (~450 instrs of stamp code in real builds). Explicitly subordinated to
  (d) per the 2026-09-16 ruling.
- **Live pixel-view editor** (backlog (c)): unchanged, next ergonomics
  rung after (d).
- Performance baselines stay as AGENTS.md defines them; no new numbers
  invented here.

---

## Pillar 5 — LLVM IR → Glyph (filed 2026-09-16, NOT STARTED)

Filed as its own pillar rather than a Pillar 2 backlog row: this is a
second, independent frontend (LLVM IR, not RV64I asm) into the same
Glyph target — genuinely multi-week scope (a real IR-lowering pass with
its own instruction-selection and register-allocation concerns), not a
small addition to the existing RV64I-to-Glyph transpiler's backlog.

- **Scope, provisional:** lower a subset of LLVM IR (starting from
  whatever `clang -emit-llvm` produces for the existing RV64I transpiler's
  own C test fixtures, so day-one has a working differential oracle) to
  Glyph assembly, reusing `rv64i_to_glyph.py`'s label-resolution and
  differential-verification machinery rather than rebuilding it.
- **Explicitly NOT scoped yet:** which LLVM IR subset, SSA-to-register
  strategy, whether it replaces or sits alongside the RV64I path, GPU-twin
  parity story. All of that is the first real design pass this pillar
  needs — filing does not imply any of it is decided.
- **Dependency:** independent of Pillars 1–4; can start whenever, but
  benefits from Pillar 2's ABI spec landing first (one syscall-arg-space
  rule to target instead of the current per-syscall lore) and from (d)'s
  implementation (one memory model to lower into instead of two).
- **Exit criteria (provisional):** an independent-engine implementer
  could take one non-trivial LLVM IR test program, lower it through this
  pillar's pass, and get byte-identical output to the same program
  compiled via the existing RV64I-to-Glyph path, on both engines.

---

## Sequencing (dependency-ordered)

```
1.1 SE024 (additive, zero-risk) ──┐
1.2 Named faults ─────────────────┼──► 3. (d) implementation ──► 4. ergonomics
1.3 Flags (J-DECISION) ───────────┘         ▲
2.1 ABI spec (independent, do anytime)      │
2.2 WGSL FS binding ────────────────────────┘ (2 needs the ABI spec first)
2.2a READ-divergence RED test (do FIRST in pillar 2 — proves the gap)
2.3 Parity CI (after 2.2; its READ leg depends on 2.2a's fix)
```

Pillar 1 items are independent one-session chunks — the proven
one-opcode-plus-tests size that ships. Pillar 2.1 can start immediately in
parallel (it's documentation-with-a-rot-guard, not code). Pillar 3's A/B
call is RULED 2026-09-16 ((A) scoped to handlers) — its implementation is
its own gated task, not blocked on a decision anymore. Pillar 5 (LLVM
IR→Glyph) is independent of 1–4; filed 2026-09-16, not started, no
particular urgency implied by the filing itself.

## What this roadmap deliberately does NOT do

- No JZ rename (do-not-rename ruling stands; blast radius unchanged).
- No 20ms symbol constraint changes (constitution: VCC validation required).
- No WGSL syscall parity claims until the golden corpus proves them.
- No performance targets beyond the existing AGENTS.md baselines.
