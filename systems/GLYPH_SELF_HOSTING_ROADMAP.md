# Glyph Self-Hosting Roadmap

Minimal launcher + everything-else-in-the-image. The Phase-12 pattern
(`geometry-os-self-hosting` skill) applied to the glyph stratum: today the
Python side (spatial_builder, atlas, FSM, oracle driver) is the "OS" and the
glyph image is a disposable artifact. Goal: invert it — one static glyph image
IS the machine; the launcher shrinks to load-image / run / service-MMIO.

House rules inherited from `glyph_dispatch/ROADMAP.md`: human-owned checklist,
NOT a cron job. Oracle before feature; every item ships a loudly-failing test
first; receipts are command output.

## Why this is closer than it looks

Already spatial (pixels, in-image):
- Program code: `GlyphCPUv2.step(image)` — the image IS the machine state
- Library bodies: RoutineAtlas tiles are pre-assembled pixel regions
- Compiled C: SB-2 ingests real C functions as tiles (`register_from_c`)

Still host-side (what must move or shrink):
| Host component | Size | Self-hosting fate |
|---|---|---|
| spatial_builder caller typesetting | ~300 loc | → in-image kernel (GH-2) |
| atlas.link() label resolution | ~40 loc | → in-image loader (GH-3) |
| FSM grammar masking | ~150 loc | stays host — it is the *toolchain* (build-time), like a cross-compiler |
| GlyphCPUv2 oracle | ~600 loc | stays host — it is the *verifier*, not the machine |
| GlyphGPT coordination | 828K params | stays host — emits intent, never runs in-image |
| launcher glue (load/run/receipt) | ~100 loc | → the whole launcher (GH-1) |

Principle: **self-hosting is about the RUNTIME, not the toolchain.** The
FSM/oracle/model are dev-time; a booted image must need none of them.

## Status

| # | Item | Oracle | State |
|---|------|--------|-------|
| GH-1 | Standalone image container: `bake_image()` emits ONE .glyph/.png (program + .data + atlas payload); generic 100-line runner reproduces `run_linked` receipts from the image alone | `tests/test_gh1_standalone_image.py` | ✅ done — 8/8, runner 98 lines, zero-dev-import AST-gated; commits 8e6f2cd + 9c09c23 (relic removed) |
| GH-2 | Kernel-in-image: dispatch table + caller trampolines + contract checks become a resident kernel tile; launcher services only HALT/fault/print MMIO | `tests/test_gh2_image_kernel.py` — spatial_builder `all` contract passes via kernel syscalls, host imports only the runner | ✅ done — 3/3; kernel :__kmain runs+verifies all 4 contracts in-image, status word 950 = 0xCAFE0004, commit 6c9b9e4 |
| GH-3 | In-image tile loader: kernel accepts new tile bytes over MMIO, patches them into its own code region (patch-and-copy), fixes its dispatch table, CALLs them — capability added with zero host code change | `tests/test_gh3_self_extension.py` — post-boot tile addition, receipt byte-exact | ✅ done — 2/2; mailbox PARALLEL_ST patch loop, offline re-run 0xCAFE0003, patch isolation verified |
| GH-4 | Same image, WGSL leg: identical image runs on `wgsl_glyph_isa_v2` (MMIO yield path); three-way byte-exact native C ≡ GlyphCPUv2 ≡ WGSL | `tests/test_gh4_wgsl_parity.py` | ✅ done — 3/3; run_wgsl() backend on GlyphRunner, Native C ≡ GlyphCPUv2 ≡ WGSL (mix=205, call/ret=43), 32-reg parity |
| GH-5 | Launcher final form: single Python file ≤200 lines (wgpu/wgsl init, one load, run loop, MMIO service, exit) — the `spatial_runtime.rs` analog | line count assert + GH-2/3/4 suites green through it | ✅ done — 7/7; runner.py 173 lines, zero dev imports, launcher_info + CLI --backend, drives GH-2/3/4 |

Ordering: GH-1 → GH-2 → GH-3 strictly (each builds on the prior). GH-4 can
start once GH-1 exists. GH-5 is bookkeeping last.

## Linux-like feature track (GH-6+)

Goal: glyph spatial OS with Linux-analogous user-facing features, all
in-image, all test-gated. Each item = one falsifiable test + one commit.

| # | Item | Oracle | State |
|---|------|--------|-------|
| GH-6 | Syscall interface: user-mode task (USER box) issues SWI; kernel handler writes to a UART-like output buffer + exit status; E-K2 KSYS_PC vector path | `tests/test_gh6_syscalls.py` — user prog "prints" HELLO via syscall; receipt memory shows bytes at uart region; box violation still traps (Lever #2) | ✅ done — 4/4 (GH-1..GH-5 regression 27/27 green); KJMP-only MODE_LATCH one-shot is the entry/exit privilege boundary; runner ram_words opt-in (default 1024 keeps GH-1 parity) |
| GH-7 | Multiprocessing: kernel spawns 2 user tasks in BOX0/BOX1, round-robins via MODE_LATCH/JMPR; contexts saved to box stack pages | `tests/test_gh7_processes.py` — both tasks' outputs present in their buffers, interleaved order proves switching, zero box violations | ✅ done — 5/5 (GH-1..GH-7 regression 32/32 green); single resident `:__ksys` selector dispatches SYS_N 6→A / 7→B slices (a one-number KSYS vector strands the other task); runner opt-in `trace=True` emits row-major (pc,mode) step_trace; `status_word_value` added to receipt; runner stays ≤200 lines (199) with zero dev imports |
| GH-8 | In-image filesystem: flat file table region (name, start, len) + data region; syscalls create/write/read/delete | `tests/test_gh8_fs.py` — create+write file, HALT; re-run SAME image offline, file readable → persistence is in-image, not host | ✅ done — GH-8b fix landed (39/39 GH-1..8b regression from clean, exit 0). Mechanism: FS window words [1024,1280) alias image pixels (2 px per 32-bit word: lo24+hi8) in GlyphCPUv2; runner executes on the LIVE image (no .copy()); kernel boot no longer zeroes FSTAB/data; SYS 6 create is idempotent (skips when slot0.in_use=1) so offline reruns READ the stored pixels. Persistence gate: `test_gh8b_tampered_pixel_survives_offline_rerun` — RED proven on pre-fix engine (readout 0x11223344 canonical, tamper 0xDEADBE00 not read), GREEN after fix. Increment adopted from qwen14b stash (stash@{0}), clean-room verified in throwaway worktree before apply; roadmap trimmed per 59e4b44. Determinism/canonical-replay leg → closed by GH-8c (below). |
| GH-8c | Canonical replay determinism: same text bakes to byte-identical images; runs of the same image are reproducible; replaying an already-run image is idempotent (md5 fixpoint) — makes an image md5 a valid receipt ("hash X ⇒ result Y") | `tests/test_gh8c_canonical_replay.py` — (1) two bakes → equal md5; (2) two bake+run cycles → equal post-run md5 + equal receipt digests (steps is the instruction-count oracle); (3) run → P1, replay → P2, replay → P3: md5(P1)==md5(P2)==md5(P3); (4) runner zero-dev-import | ✅ done — 4/4 gate from clean; RED proven by mutating `_fs_pix_write` in a scratch engine copy (random bit XORed into persisted FS-window pixel writes): reproducibility + idempotence legs FAILED under mutation while the bake leg correctly still passed (bake never executes the engine), then GREEN on the real engine — the gate detects nondeterminism, not vacuous green. Full GH regression after the concurrent GH-12 session landed its fix: 81/81 from clean, exit 0 (18.99s), runner.py 199 lines. GH-8b suite untouched: 8/8 GH-8 file green. |
| GH-9 | Program loader: host/kernel injects new program bytes into a box via mailbox (builds on GH-3 patch window); program runs with argv block | `tests/test_gh9_loader.py` — injected prog computes on argv, result byte-exact vs native C reference | ✅ done — 5/5 gate (online exec, offline resident re-run, C-reference parity, fault leg, zero-dev-import); full GH-1..GH-9 regression 44/44 from clean, exit 0 (4.02s). Mechanism: kernel launches mailbox-armed programs by patching the GH-3 window (96 px words @ [800,896) mailbox, moved below 1024 to clear GH-8b's pixel-aliased FS window), copying the argv pair into BOX0 @ 750/751, then KJMP into the window USER-mode with r10 = argv ptr; kernel boot zeroes ONLY kernel-owned receipt words (mailbox flag/n_px + argv are host inputs — zeroing them broke both legs). Offline leg: cpu.run executes on the live image, so the post-run PNG carries the injected program as resident pixels; fresh runner seeds only argv → same text, new argv, byte-exact result. Impl adopted from stash@{1} (qwen14b WIP, recovered per stall rule) and extended in-tree (GH9_MAILBOX_DATA moved 964→800 for GH-8b coexistence; boot ABI fix); gate tests/test_gh9_loader.py authored in this run |
| GH-10 | Shell: resident program polls cmd buffer (MMIO); commands echo/ps/cp/rm/run map to kernel ops; writes prompt+output to uart buffer | `tests/test_gh10_shell.py` — host writes "echo hi" to cmd buffer, run to halt, uart contains "hi"; "ps" lists 2 GH-7 tasks; unknown cmd → error string | ✅ done — 7/7; full GH-1..10 regression 51/51 passed (4.39s). Mechanism: two-pass bake with packed-pixel PCs (:__g10poll/:__g10fault/:__g10done); host arms cmd buffer 903..905 pre-run, shell polls flag in-image, services echo/ps/unknown, reports via uart 910..912. Stall-adoption fixes vs frozen tree: (1) exit-word 0xFEED typo 65290→65261; (2) idle-prompt shift count moved r4→r7 (r4 clobbered the low-24 payload); (3) ps verb constant byte-swap 28787→29552 ('p' OR 's'<<8 = 0x7370, not 0x7073); (4) fault leg: entry KJMP is the one-shot latch consumer — arm MODE_LATCH=USER BEFORE KJMP so the poll leg lands USER and the out-of-box word-900 store trips E-K1 (GH-6/7/9 pattern). Owner lane only: baker.py + tests/test_gh10_shell.py. |
| GH-11 | Launcher final form ≤200 lines driving GH-6..GH-10 suites end-to-end | line-count assert + all GH suites green through launcher | ✅ done — 8/8 gate; full GH-1..GH-12 regression 61/61 from clean, exit 0 (8.5s), runner.py 199 lines (GH-5 gate re-verified through the change). Mechanism: GlyphRunner gained `drive(seeds=..., max_instructions=...)` — one generic end-to-end session (host seeds exec-state words: argv/mailbox/cmd-buffer = the loader role; kernel runs to HALT or fault on the LIVE image; shared `_fill_receipt` emits memory/status/fault). Gate tests/test_gh11_launcher_endtoend.py proves ONE driver type executes every kernel generation: GH-6 uart 'HELL'/'O' (exit 0xFEED0006), GH-7 round-robin 0x41414141/0x42424242 (status 0xCAFE0007), GH-8 FS readout 0x11223344 (status 0xCAFE0008), GH-9 injected program == native C ref (status 0xCAFE0009), GH-10 shell 'echo hi' → uart 'hi', flag consumed (status 0xCAFE000A), plus GH-7+GH-10 fault legs surfacing `faulted` with 0xFA171 verdicts; zero-dev-import AST gate re-asserted. WGSL section compressed (bind-group/buffer lines) to hold the 200-line budget; receipts unchanged. Owner lane only: runner.py + tests/test_gh11_launcher_endtoend.py. |
| GH-12 | Escalation router (orchestrator-layer, NOT GlyphGPT): atlas-miss → draft routine via local Ollama (qwen2.5-coder) → SB-2 ingest → oracle contract gate → register tile; Claude only for hard design forks, budget-capped | `tests/test_gh12_escalation.py` — force an atlas-miss routine, loop escalates to local model, candidate C passes native+Glyph parity before registration; failed candidates never touch the atlas; GlyphGPT untouched (no retrain) | ✅ done — landed out of order (before GH-11) at 025b2cc; stale-check verified: gate green at HEAD, full GH-1..GH-12 regression 61/61 from clean. escalate.py: contract spec → qwen2.5-coder:14b (local, temp 0) → oracle.run_oracle word-exact gate; unverified candidates never surface (negative control). Landed by a parallel session; status cell marked in this run per the stale-check rule. CAPSTONE (loop closure) landed 83d3c45: autoatlas.py ingest() = whitelist gate → escalate → oracle → atlas.register → GH-9 mailbox inject via runner.drive → kernel re-dispatch, word-exact vs oracle (standalone proof: kernel_result 16, exit 0xfeed0009, status 0xcafe0009); registered tile persists in-image and replays offline. Gate tests/test_gh12_autoatlas.py 4/4 (live model); full GH-6..13 regression 48/48 from clean (15.39s); runner.py 199 lines. Two gate fixes (autoatlas.py untouched — it was correct): (1) gate passed argv={1:...} but the kernel ABI is argv-key=offset-from-word-750 and the tile loads arg0 from mem[750] → POPCOUNT_ARGV={0:...}; (2) offline replay must seed memory[750] (seed_memory={GH9_ARGV_WORD:...}) not input_registers — the kernel-ABI tile's first LD clobbers r1. escalate.py ISA_PRIMER gained the stale-accumulator anti-pattern (XOR rd rd before AND/CMP) with the canonical low-bit idiom. |
| GH-13 | Multi-agent workspaces (agent = user task in its own box): generalize BOX0..BOXn to N per-agent arenas; each agent task runs in USER mode confined to its box; mailbox words for agent→agent and agent→kernel messages; kernel round-robins agents; a task CANNOT write outside its box (existing trap = isolation proof). Host-side builder agents attach one runner per agent box, each driven by a separate AI session | `tests/test_gh13_multiagent.py` — 3 agent tasks (A: writer, B: reader/verifier, C: coordinator via kernel syscall); A writes pattern to box-A arena, B reads ONLY via mailbox syscall and verifies, C receives both statuses via KSYS; zero box violations; interleaving proves kernel scheduling; host harness runs 3 GlyphRunner instances concurrently on the same image | ✅ done — 6/6 gate; full GH-1..GH-13 regression 67/67 from clean, exit 0 (8.55s) (61 committed baseline + 6 new; tests/test_gh12_autoatlas.py excluded — untracked WIP authored mid-run by a parallel session, failing identically with and without this diff, out of lane). Mechanism: BOX0/BOX1/BOX2 = three per-agent arenas [700..717)/[718..735)/[736..753) — BOX2 is the engine's third permitted range, first baked-kernel user of glyph_isa_v2 BOX2_LO/HI_ADDR; A(writer)→B(reader/verifier)→C(coordinator) round-robin via MODE_LATCH one-shot + KJMP (each agent's exit KJMP lands SUPER in the next dispatch leg, which re-arms the latch for the following agent); agent→agent + agent→kernel messages flow ONLY through the kernel-mediated mailbox (word 754) and KSYS read-outs — B never touches A's arena (mailbox syscall is the sole channel; in-box verify writes 'V'/'E'); selector dispatches SYS 6/7/8 (a single-number handler would strand the other agents, GH-7 lesson); fault leg (A's out-of-box word-900 store) records 0xFA171 and strands B/C unscheduled; 3 concurrent GlyphRunner instances on one baked image produce byte-identical green receipts (host-harness property). Two in-run fixes: SYS 6 must dereference the a0 buffer pointer (LD r7 r6), not echo it (uart read 713=0x2c9), and B's verify pointer is its read-out word 720, not scratch 727 (verdict read 'E'=69). Owner lane only: baker.py + tests/test_gh13_multiagent.py. |
| GH-14 | Agent work protocol (host-side): N AI sessions share ONE baked image; each session owns exactly one box (path-ownership extended to memory-ownership); coordination via mailbox MMIO words, never direct box writes to others' arenas; a "work ticket" file table (GH-8 FS) assigns tasks; receipts = uart buffer per box | `tests/test_gh14_agent_protocol.py` — 2 simulated agent sessions claim tickets from the in-image FS, do work in their boxes, signal done via mailbox; kernel arbitrates; final FS state byte-exact vs single-agent reference | ✅ done — landed at 28c730e by a parallel session; stale-check verified in this run: gate 6/6, full GH-1..14 regression 77/77 from clean, exit 0 (17.75s), runner.py 199 lines. Status cell marked in this run per the stale-check rule (commit omitted the receipt update). Gate legs: image_bakes, two_sessions_claim_work_and_combine, session_a_persists_across_reopen, fault_leg_isolates, zero_dev_imports, runner_line_budget. Mechanism (from 28c730e diff): baker.py +433 — agent_protocol_kernel_image with two-pass bake, ticket FS seeding (GH-8 pixel-FS), 4-slice syscall dispatcher, 2 USER agent slices claiming tickets from the in-image work-ticket table, mailbox done-signals, per-box uart receipts, FS receipts byte-exact vs single-agent reference; tests/test_gh14_agent_protocol.py +219. |
| GH-15 | Unified GlyphIR: Single semantic IR (CFG basic blocks, uniform Address model, explicit scratch pool, symbol relocations) + static contract verifier; transpiler / autoatlas / baker converge onto one lowering engine | `tests/test_gh15_ir_transpiler.py` — RV64I transpiler dual-path passes 100% byte-exact vs legacy on QEMU differential suites; negative mutation (mailbox collision to 964, scratch clobber) fails loudly at IR stage before emission | ✅ done — 8/8 Step 5 dedup gate (tests/test_gh15_step5_dedup.py: one terminator table, no lane hand-builds IR blocks, shared-verifier spy legs byte-exact, lane shapes preserved, stdlib-only AST scan); full GH regression 112/112 from clean @ 24bd1d6 (18.96s); transpiler differential suites 37/37 via pre-commit gate. Step 5 mechanism (legacy dedup, 24bd1d6): glyph_ir.py gains TERMINATOR_OPS / DEFAULT_SCRATCH_POOL / DEFAULT_CALLSTACK_REG constants + RaisePolicy + raise_lines_to_ir — the ONE glyph-text→GlyphIRModule raiser (label/block splitting, terminator recognition, operand classification, duplicate-label rejection, leading-label entry fusion, lazy continuation blocks so a program ending on its terminator grows no trailing empty block); rv64i_to_glyph._raise_to_ir, autoatlas.raise_tile_text_to_ir, baker._raise_lines_to_ir are now RaisePolicy + delegation shims (zero private parsing); use_ir=True is the transpiler DEFAULT at both entry points. Bug found by the flip: the empty data-section anchor recorded the RV BYTE text base as a glyph WORD index — ELFs linked at 0x10000+ (bump_alloc.elf @ 0x10094) spuriously escaped data_bounds; anchor now glyph word 0. Dead use_ir kwarg removed from atlas.register_from_c. Step 4 mechanism (baker/SB-2 IR migration, 5e5e88b): (1) atlas.register_from_c routes lowered C through the IR-verified transpile path (rejection loud, pre-emission); (2) baker._check_data_words rejects bake-time data seeds in kernel-reserved RAM (750..760, 800..896, 950..968, 1024..1280); (3) ir_bake_bytes raises linked program text to GlyphIRModule and StaticVerifier-checks window capacity and data bounds before pixel emission; (4) WGSL engine bugfix: OPCODE_ST uses cpu.registers[rs1] (matching GlyphCPUv2 and assembler) instead of unused rd; (5) RV32 GPU core return address initialized (ra=0x100). Gate tests/test_gh15_step4_baker_sb2.py 6/6. Step 3 mechanism (AutoAtlas IR migration, af9d41b): raise_tile_text_to_ir / ir_pixel_words / _verify_tile_ir in tools/glyph_gpt/autoatlas.py — every tile raised into a GlyphIRModule and StaticVerifier-checked before pixel emission; gate tests/test_gh15_step3_autoatlas.py 7/7. Steps 1–2 mechanism (3ed16cd): tools/glyph_ir.py (stdlib-only AST-gated) — GlyphIRModule/BasicBlock/IRInstruction/Operand/Address/SymbolReloc/CodeWindow/DataSection/PointerTable/IRContract/LoweringConfig + StaticVerifier; rv64i_to_glyph dual-path. Honest boundary: static verifier checks static invariants only; dynamic pointers still E-K1-guarded at runtime. |

Multi-agent notes: GH-13 needs GH-7 (scheduler) + GH-6 (syscalls for mailbox).
GH-14 needs GH-13 + GH-8 (FS for tickets).

RESOLVED DESIGN FORKS (decided 2026-09-06, record supersedes BLOCKED-human
parking for these two items only):
- GH-13 mailbox semantics: (a) KERNEL-MEDIATED message passing. All
  cross-agent communication via SWI sys_send(target_box, ptr, len) /
  sys_recv; kernel serializes, checks bounds, records each transaction in
  the in-image system trace ("the screen is the audit log"); a bad pointer
  faults only the sender. Reason: run_wgsl GPU workgroups make unbounded
  shared writes non-deterministic; the kernel write-port keeps CPU/WGSL
  three-way parity intact.
- GH-14 agent-to-box assignment: TIERED LOCAL-FIRST. Worker boxes driven by
  local Ollama (qwen2.5-coder). Cloud frontier models are NOT a standing
  coordinator — they engage ONLY through the GH-12 escalation router's
  existing 3-strikes trigger (atlas miss or 3 consecutive contract
  failures). One escalation mechanism, not two.

Feature-track ordering: GH-6 → GH-7 → GH-8 (independent of GH-9); GH-9
needs GH-3; GH-10 needs GH-6+GH-7+GH-8; GH-11 last.

### THE INGEST-FIRST POLICY (ratified 2026-09-09, post-GH-14 close)

All 14 milestones are complete. From here forward the glyph harness is
the FOUNDATION of the spatial software stratum — by adoption, not
rewrite. Three rules:

1. SINGLE INGRESS RULE — every new OS capability enters through
   `autoatlas.ingest()`, never as hand-written Python assembly
   generation or baker diffs:

       draft (escalate/local model or human .glyph)
         → oracle prove (run_oracle, word-exact registers)
         → register (RoutineAtlas.register, family-whitelisted)
         → mailbox inject (runner.drive, GH-9 ABI)
         → replay verify (kernel result == oracle result)

   The atlas IS the syscall table / dynamic linker. Tiles persist
   in-image (GH-8b pixels) and replay offline forever — write once,
   proven forever.

2. WHAT THE HARNESS GOVERNS — the spatial software stratum only:
   stdlib tiles (string/int/bitwise/matrix utils), shell utilities,
   device handlers, agent work tickets (GH-14 protocol), user apps.

   WHAT IT MUST NEVER REACH —
   - runner.py (the "silicon", ≤200 LOC, zero dev imports)
   - glyph_isa_v2.py trap core (MODE_LATCH, KJMP, E-K1/E-K2: the
     physical laws — mathematically immutable)
   - the acoustic codec substrate (voicebook/, UPIC, dual-band:
     protected, separate baselines per AGENTS.md)

3. TIERED LOCAL-FIRST ESCALATION (extends the GH-14 fork): workers
   draft via local Ollama; frontier models engage only through the
   GH-12 3-strikes trigger. One escalation mechanism, not two.

Post-arc work track (approved): (a) stdlib tile expansion through
ingest() in autonomous batches — string utils, integer math, bitwise
transforms, spatial matrix ops; (b) live-tile integration: baked image
into infinite_map_rs / WebGPU compute rendering; (c) the contribution
protocol above is binding on all future OS extensions.

### Automation rules for the GH loop (added when the loop went live)

- ONE roadmap item per run. Red test first; commit only after its gate
  AND the full GH regression (GH-1+ suites, spatial_builder, atlas) exit 0.
- Touch ONLY: tools/glyph_gpt/{baker,runner,kernel*}.py,
  tests/test_gh*.py, systems/GLYPH_SELF_HOSTING_ROADMAP.md. Never touch
  tests/test_rv64i_to_glyph_* (concurrent SB-3 session owns those) or
  glyph_dispatch/**.
- 3 failed attempts on one item → mark it BLOCKED in the status table with
  the failure receipt, move on. Never mark ⏳→✅ without the pasted receipt.
- Stale roadmap check: if git log shows the item already done (concurrent
  session), update table and stop — do not redo work.

Out of scope (explicitly): retraining GlyphGPT to run in-image (the 828K
model is a dev-time compiler); porting the assembler into glyph code
(the toolchain argument); running the WGSL core without any host.

## Item GH-1 — standalone image container (do first)

Design:
1. `bake_image(program_text, atlas, data_words) -> np.ndarray`: assemble the
   caller text into the code region at a fixed origin; lay `.data` words at
   their link addresses; append the atlas payload (each tile assembled at its
   registered offset) below the code region — one rectangle, one `np.save` +
   PNG wrapper (lossless, BGR24 like the VAC containers).
2. `GlyphRunner(path)`: ~100 lines — load image, construct `GlyphCPUv2` on it,
   `run_until_halt()`, emit the same receipt dict as `run_generated`. NO
   imports from atlas/builder/synth.
3. Gate: for each of the 4 builder tasks + 2 SB-2 ingested tiles,
   `receipt(runner(image)) == receipt(run_linked(text))` including memory
   and registers_full. Same-image `md5sum` recorded in the test.

Traps to pre-register (from the transpiler skill's landmines):
- Ingested C tiles need `.data`/`.sdata` seeded — use
  `parse_elf_data_sections()` at bake time, not load time.
- Local `:pc_*` labels inside two ingested tiles already namespaced by SB-2;
  the image must preserve that (bake from linked text, never re-link).

- **Status:** DONE. `tests/test_gh1_standalone_image.py` 8/8 passing:
  `GlyphRunner` (84 lines, zero dev imports verified via AST) executes baked
  PNG images on `GlyphCPUv2` matching `run_linked` byte-for-byte across all
  4 builder tasks (`double`, `accumulate`, `memcpy`, `tile_clear`), 2 SB-2
  ingested C tiles (`sum_c`, `max_c`), and bake-time `data_words` seeding.
  MD5 checksums recorded per task.

## Item GH-2 — kernel-in-image (trampolines + contracts resident)

Design:
1. Resident kernel tile in the image containing:
   - System entry / trampoline
   - Dispatch table for atlas routines
   - Calling convention setup and contract assertion in glyph code
2. The launcher shrinks to servicing only HALT/fault/print MMIO.
3. Gate: `tests/test_gh2_image_kernel.py` — spatial_builder contracts pass
   via kernel execution while host imports only `GlyphRunner`.

## Item GH-3 sketch — self-extension (the thesis test)

The kernel reserves a patch window in its own image. Host writes raw tile
bytes + entry offset into an MMIO mailbox; kernel copies the window into its
code region at the reserved slot, appends `:atlas_<name>` to its dispatch
table, returns the assigned slot id. Post-extension, the same image re-run
offline (no host write) executes the new capability — proving the patch
landed in the image, not in host-side state. Contract: pre- and post-patch
images differ ONLY inside the reserved window + dispatch slot.

- **Status:** DONE. `tests/test_gh3_self_extension.py` 2/2 passing:
  `bake_self_extending_kernel_image()` emits image with reserved patch window;
  kernel's resident `:__patch_loop` copies tile pixels from mailbox using
  `PARALLEL_ST`; patched image saved and re-run completely offline with zero
  host writes, successfully executing `triple(7) -> 21` and writing `0xCAFE0003`;
  patch isolation verified: diff between pre- and post-patch images is strictly
  confined within `:__patch_window` (8 pixels changed, 0 outside). Zero dev imports.

## Item GH-4 — same image, WGSL leg

Identical baked image container (.png, .npy) runs on `wgsl_glyph_isa_v2` (WGPU
compute pipeline) matching the Python oracle GlyphCPUv2:
- `GlyphRunner.run_wgsl(max_steps)` added to `tools/glyph_gpt/runner.py`.
- Three-way byte-exact verification across Native C == GlyphCPUv2 == WGSL.
- Arithmetic bit-twiddling routine: `mix(42, 15) = 205` identical across all 3 legs,
  with exact match across all 32 registers.
- Subroutine `CALL` and `RET` stack handling verified bit-exact between CPU and WGSL legs (r10=43).

- **Status:** DONE. `tests/test_gh4_wgsl_parity.py` 3/3 passing:
  `run_wgsl()` method available on runner; Native C ≡ GlyphCPUv2 ≡ WGSL parity
  holds across all registers and control flow conventions. Zero dev imports.

## Item GH-5 — launcher final form (≤ 200 lines)

The standalone launcher (`tools/glyph_gpt/runner.py`) shrinks to its final
canonical form as the pure spatial runtime (analogous to `spatial_runtime.rs`):
- Strict line count invariant: 173 lines (≤ 200 LOC target).
- Zero dev-time imports verified via AST (no atlas, spatial_builder, synth,
  generate, model, tokenizer, corpus, train, pack_dataset, baker).
- Exposes `launcher_info()` returning metadata and supported backends (`cpu`, `wgsl`).
- Unified CLI interface supporting `python3 runner.py <image> [--backend=cpu|wgsl]`.
- Drives GH-2 kernel (0xCAFE0004), GH-3 self-extension / offline execution (0xCAFE0003),
  and GH-4 WGSL GPU compute parity cleanly end-to-end.

- **Status:** DONE. `tests/test_gh5_launcher_final.py` 7/7 passing:
  Line count assert (173 <= 200) holds; zero dev imports; launcher_info validated;
  GH-2, GH-3, GH-4 suites pass cleanly through launcher; CLI CPU + WGSL backends verified.

## Item GH-15 — Unified GlyphIR Consolidation

Design:
1. Pure dataclass representation (`tools/glyph_ir.py`, zero dev-time imports):
   - `GlyphIRModule`: blocks, data sections, explicit pointer table, code window, contract, lowering config.
   - `BasicBlock`: scoped label, instruction list, terminator (`JMP`, `JZ`, `RET`, `HALT`, `JMPR`, `INDIRECT_JUMP`).
   - `IRInstruction`: op, dests, sources, metadata.
   - `Operand`: `phys_reg`, `virt_reg`, `imm`, `symbol_ref` (`SymbolReloc`), `mem_ref` (`Address`).
   - `Address`: canonical `(base_reg, imm_offset)` or `(None, flat_addr)`.
   - `CodeWindow`: origin symbol, max_words capacity, 2D wrapping factor (disentangled from data bounds).
   - `LoweringConfig`: explicit `scratch_pool` (e.g. `["r28", "r29", "r30"]`), callstack reg.
2. Invariants & Static Verification:
   - Lowering scratch pool asserts `scratch_pool ∩ contract.preserves == ∅` and `callstack_reg ∉ scratch_pool`.
   - Bounds verification asserts static memory and code window capacity (`total_words <= max_words`) before emission.
   - Honest boundary: static verifier checks static invariants only; runtime dynamic references remain guarded by E-K1.
3. Gates & Phased Rollout:
   - Step 1: Spec in `tools/glyph_ir.py` + unit tests in `tests/test_gh15_ir_spec.py`.
   - Step 2: Dual-path RV64I transpiler (`--use-ir`) tested in `tests/test_gh15_ir_transpiler.py`. Must pass 100% byte-exact against QEMU differential suites, AND include negative mutation test (mailbox base 964 collision or scratch conflict) proving loud rejection before emission.
   - Step 3: AutoAtlas migration, gated by live model + oracle (`tests/test_gh12_autoatlas.py`).
   - Step 4: Baker / SB-2 migration, gated by C-parity suites.
   - Step 5: Deduplication of legacy relocation / namespacing.

## Agent OS Arc (GH-16+) — ratified 2026-09-06

Positioning decision (Jericho, 2026-09-06): Glyph OS does NOT chase
Linux/Windows parity (30 years of driver ecosystems — unwinnable and
worthless). It competes as the PROVENANCE-FIRST AGENT OS: the OS whose
every syscall and extension was machine-proven before it can run, for
AI agent swarms as first-class users. What Linux bolts on
(namespaces, apparmor, verified boot) is native here; what we bolt on
(scale, preemption, ABI breadth) Linux has had for decades.

Gap analysis at ratification (measured):
- 1024-word RAM, MMIO @ 0x8000 — no paging, no growth
- Cooperative round-robin only (MODE_LATCH+KJMP) — no timer, no
  preemption; a spinning USER task starves the swarm
- ~8 syscalls vs Linux's 300+; FS is seeded tickets (no grow/rename)
- Strengths to defend: oracle-proven syscall table, in-image
  persistence + canonical replay (md5 receipts), GH-13/14 agent
  boxes+mailbox protocol native, CPU≡WGSL three-way parity

| # | Item | Oracle | State |
|---|------|--------|-------|
| GH-16 | Preemptive scheduling: timer MMIO word counts down per N steps; engine raises tick → kernel tick-handler saves context to box stack, advances round-robin; USER task cannot disable it (MODE_LATCH gate: tick only arms in SUPER) | `tests/test_gh16_preemption.py` (5/5) — spinning USER task in BOX0 cannot starve BOX1 (BOX1 completes while BOX0 spins); tick handler context save/restore register-exact (Task A r1/r2 verified vs clobbering by Task B, GH16_VERIFY_OK written at word 704); fault-in-handler privilege isolation; runner budget preserved (199 LOC, 0 dev imports) | ✅ done |
| GH-17 | Memory scaling: word space beyond 1024 via SPATIAL PAGING — page table region maps virtual word pages to tile/page frames in the wider pixel image (reuse PXC1/VAC container learnings); identical ABI, `MEM_WORDS` becomes page-table-backed | `tests/test_gh17_paging.py` (6/6) — memory map non-collision assertion; flat 64K-word space access; page fault on unmapped access records fault address & verdict word (0x000FA017); context switch with resident pages > 1024 words (Task A page 8, Task B page 16); CPU ≡ WGSL parity on paged pixel access (32-register exact); runner budget preserved (199 LOC, 0 dev imports) | ✅ done |
| GH-18 | Syscall ABI v2: syscalls ARE atlas tiles — kernel syscall table = in-image pointer table into registered, oracle-proven tiles; new syscalls enter ONLY via `autoatlas.ingest()` (proof = admission), kernel ABI versioned in-image. DISPATCH: indexed table lookup (LD TABLE_BASE+sys_n → KJMP packed pixel PC), replacing the linear CMP/JZ selector chain ONCE; the invariant baseline is the post-rewrite dispatcher image. GATE REQUIREMENTS: (1) patch-isolation is a positive WHITELIST — diff(post, pre) ⊆ (table_words ∪ atlas_rect) exactly, any byte outside fails; (2) sys_n bounds check is UNSIGNED (or power-of-two mask) — negative and 0x7FFFFFFF sys_n must vector to unknown-syscall handler ('E' + clean SYSRET), never OOB table read; (3) RE-ENTRANCY RULE: syscalls run to completion — tick masked on SYSCALL entry, unmasked on SYSRET (GH-16 timer cannot clobber SYS_N/A0/PC mid-call); (4) syscall-tile admission ties to GH-15 IRContract: clobbers ⊆ {scratch pool, return reg}, USER-visible regs preserved across KJMP (dispatcher restores or contract guarantees — pick one, prove it); (5) table + atlas rect pinned in identity-mapped low pages so SUPER dispatch never consults the page walker on the hot path; (6) ABI version word (word 952) = 0x00020018 | `tests/test_gh18_syscall_abi.py` — register new syscall tile via ingest, syscall number live in-image; hostile sys_n legs (negative, huge) trap cleanly; mid-syscall tick leg proves deferral; unproven tile registration rejected (E_ATLAS_UNVERIFIED, table untouched); version word bumped in-image | ✅ 2026-09-08 — 13/13 green, commit `e3d3c13`. Receipt: 9F→2F→0 across three sessions; final residue defects (A) patch-isolation drove a pre-seed image copy — pixel-surface table seed (pfn-5 window [1312,1328)) lives on the LIVE runner image; (B) admit_syscall tile-rect stamp used 4-pixel byte-split layout vs the bake's 1-word-per-pixel (receipt output/debug_gh18_rectdiff.py); (C) `_gh18_dispatch_resume` assembled baseline-mode coords for the tile KJMP home (0x0d0005 vs admit 0x110000) — mode-parametrized (output/debug_gh18_decode3.py). LANDED ABI FACTS for downstream items: BOX2 tile-ABI window = [736..768) (argv word 750, result word 754); table word 1570 → pixel via pfn-5 window; BOX0 [700..717), BOX1 [718..735). FOLLOW-UP: `.builder_queue/gh18-table-reservation.json` — pin words 1568..1583 to a reserved, asserted pixel range before GH-21 program-text growth erodes the zero-padding headroom the pfn-5 mapping currently relies on |
| GH-19 | stdlib tile pack: string utils (strlen/strcmp/memcpy/memmove), integer math (divmod, itoa/atoi), bitwise transforms (popcount, rotr32, rotl32) — ingest()-batched, oracle-proven, family-whitelisted; the libc-equivalent that makes C programs portable into the image. ADVERSARIAL MATRIX (word-exact vs native host GCC C reference): strlen/strcmp — empty "", 1-byte, max-length-64 boundary, mismatched suffix; memcpy/memmove — 0-length, 1-word, unaligned offsets, overlapping src/dst (dst=src+1 AND src=dst+1); divmod — divide by 1, by self, negative dividend/divisor (C99 truncation toward zero), zero divisor (return 0xFFFFFFFF status, no crash); atoi/itoa — negative "-12345", 0, INT32_MAX, INT32_MIN. ADMISSION: autoatlas.ingest() with IRContract (clobbers ⊆ {scratch, return_reg}, r31 preserved); unverified candidates rejected (E_ATLAS_UNVERIFIED), verified tiles persist to image | `tests/test_gh19_stdlib.py` — full adversarial matrix per tile, word-exact; batch N tiles per run; full GH regression stays green; PARALLEL-TRACK RULE: GH-19 work runs in isolated worktree, merges to glyph-transpiler-autoloop only after GH-18 is green AND full 123+ regression passes from clean on the merge result | ✅ done — `tests/test_gh19_stdlib.py` (27/27): all ten tiles 4-leg verified (native GCC golden → GlyphCPUv2 oracle word-exact w/ r31 preserved → IRContract StaticVerifier → autoatlas.ingest() admission). Adversarial matrix per roadmap row: strlen/strcmp (empty/1-byte/64-boundary/suffix), memcpy/memmove (0-len/1-word/unaligned/dst=src+1/src=dst+1), divmod (÷1/÷self/C99 truncation both signs/÷0 → 0xFFFFFFFF status no crash), itoa/atoi (-12345/0/INT32_MAX/INT32_MIN), popcount/rot gates (13 vectors incl. n=0). Implementation receipts: divmod+itoa avoid libgcc __divsi3/__modsi3 (JMPR frame leak — r10 came back 0 on INT32_MIN) via shift-subtract software divisors; strcmp 64-boundary fixture bug fixed (buffer words spaced 256B apart after dict-merge word 272 collision). Full GH regression from this branch: 150 passed / 0 failed (51.7s). MERGED 2026-09-08 `93d6843` per parallel-track rule (GH-18 13/13 green first). ROADMAP ROW COMPLETE — all 5 batches, 10 tiles |
| GH-20 | Pixel-FS v2: grow (append blocks), rename, unlink-with-refcount, directory nesting via FS-table chains — all mutations through syscall tiles so FS ops are proven like syscalls. GATE LEGS (finalized against the landed GH-18 ABI): (1) fs_append grows extents past initial allocation without clobbering neighbor windows; (2) fs_rename updates directory entry in-place, inode index preserved; (3) fs_unlink with non-zero refcount fails cleanly (errno, no dangling pointers); (4) canonical replay md5 fixpoint preserved across mutations; (5) all FS ops route through the syscall table as proven tiles | `tests/test_gh20_fs_v2.py` — legs above, finalized against real GH-18 ABI; refcount leg (unlink shared file → fault, not corruption); canonical replay md5 fixpoint preserved across mutations | ✅ 2026-09-09 — 5/5 green, commit `0d83f89`. Mechanism: `tools/glyph_gpt/fs_v2.py` bakes the admit-mode ABI-v2 kernel with mode=\"fs_v2\" — prologue programs the vpn-4 PIX-identity PTE INSIDE the pre-arming PTE loop (a post-arming store walks the live page table and never lands — receipt D1), static FSTAB (file 'A', 2-word extent, refcount=2 shared fixture) stamped into the GH-8b fs-alias window [1024,1280) at 2 px/word (engine-exact `_fs_pix_write` layout); image baked min_rows=81 so the alias block lands in zero padding, not program text. SYS 10/11/12 enter via `autoatlas.admit_syscall(abi=\"gh20\")` (proof = admission) and dispatch through the GH-18 table like every other tile. Three mode-coordinate defects fixed (receipts D1-D3 + probe22/23/25): tile-rect PC, dispatch-resume home, and in-tile jump relocation were all computed in admit/baseline coords — for fs_v2 the rect is 0x230006 (row 35, flat [1144,1240)), NOT the admit rect GH18_TILE_WORD=1600; leg-5's stray whitelist now derives the rect from the mode-correct PC. `admit_syscall` also no longer calls ingest() twice. ABI facts for downstream (GH-21+): receipt memory[] does NOT mirror bake-time seeds — read seeded words from the IMAGE (`_fs_word` helper); the unlink contract verdict is its clean-fail errno (FSV2_ERR_BUSY), not 0. LANDED receipt: docs/receipts/RECEIPT_GH20_FS_V2.md; RED/GREEN runs: output/gh20_gate_run5_red.txt / _green.txt; invariant output/run_gate_gh18.sh 14/14 exit 0 (baseline re-verified at HEAD with WIP stashed) |
| GH-21 | POSIX Syscall Shim: userspace ABI adapter tiles mapping standard RV32/RV64 Linux ECALLs (sys_read=63, sys_write=64, sys_openat=56, sys_close=57, sys_exit=93, sys_brk=214) to in-image Glyph syscalls / Pixel-FS tiles; enables standard compiled C binaries to run unmodified | `tests/test_gh21_posix_shim.py` — compiled C binary calling write(1, msg, len) + exit(0) links against shim, lowers to GlyphIR, executes with word-exact stdout at UART/mailbox; unrecognized ecall traps cleanly | ⏳ |
| GH-22 | Device Driver ABI: spatial microkernel protocol — drivers run as unprivileged USER tasks in isolated boxes communicating via non-blocking mailboxes (GH-13/14); hardware MMIO bounded per box; no monolithic kernel drivers or struct file_operations bloat. SOURCE RULE: drivers are written from hardware datasheets, NOT transcribed from Linux source (GPLv2 derivative-work risk for distributed visual_audio.mkv); Linux source may be MINED for register facts/quirks and any such reference is documented by file path. Where Linux later fixes a hardware bug (register errata, ordering quirks), port the FACT into our tile + oracle — the knowledge transfers, the code never does. TRUSTED-UNPROVEN BOUNDARY (same discipline as GH-15's static-verifier note): the oracle proves a driver tile emits correct register sequences against an in-image DEVICE MODEL; the model itself is trusted code not proven against real silicon — extend this list as devices are added | `tests/test_gh22_device_driver_abi.py` — simulated block/UART driver in BOX1 services requests from BOX0 application through kernel mailbox; corrupted packet or out-of-bounds MMIO traps cleanly (E-K1) without destabilizing kernel | ⏳ |
| GH-23 | Picolibc / Newlib Full Port: standard C library runtime (malloc/free backed by sys_brk, printf/puts, string/math) compiled for RV32I targeting Glyph OS POSIX shim; compiles real userspace C software directly to verified spatial tiles | `tests/test_gh23_libc_runtime.py` — standard C test suite (heap allocation, formatted output, qsort) compiles with standard cross-compiler, links against spatial libc, transpiles to GlyphIR, passes StaticVerifier, and runs to clean exit 0 on GlyphRunner | ⏳ |
| GH-24 | Spatial Observation Bridge (ASCII World Projection): the AI observation plane — pure-function projector from kernel memory to a fixed-layout ASCII canvas. S1 `tools/geos_ascii_bridge.py`: `project(memory, origin=(0,0), w=80, h=25) -> str`; address function MUST be `tools/geos_hilbert.py` d2xy (same implementation verified by `hilbert_reference_verify.py`) — one import shares the coordinate space with `tools/mkv_infinite_map.py` (storage map) instead of a parallel build. MONITORING INVARIANT: reads only COMMITTED bus state (mailbox words 700..767, box bounds, register file as of last tick boundary) — never mid-task speculative registers; non-invasive and deterministic by construction; read-only, zero GPU, VCC-trivial. S2 MCP tool `geos_read_surface(vx,vy,w,h)`; DUAL-ARTIFACT RULE: canvas is NEVER JSON-wrapped (fixed-stride string preserves 2D adjacency for attention; JSON only as sidecar meta — named boxes `{name, rect, memory_words, bus_lane, writable}` + tick, mirroring visual_audio + *.rts.meta.json). S3 write path `geos_emit(intent)` HUMAN-GATED separately: GlyphGPT drafts → oracle word-exact → GH-18 admit → VCC hash before/after; no freehand LLM assembly. Non-goal: PixiJS/dual-pane UI | `tests/test_gh24_ascii_bridge.py` — golden test: project a known GH-18 receipt, assert exact canvas bytes; box legend matches landed ABI (BOX2 [736..768), argv 750, result 754, table 1568..1583) | QUEUED — after GH-20 |
| GH-25 | Infinite Spatial Page Table & Map Substrate (HORIZON STUB — one PTE format change + one host service, NOT a new subsystem): GH-17's `V|W|U|PIX` PTE gains 2D virtual origin + Hilbert address (d2xy from `tools/geos_hilbert.py`); resident 16384-word frame = active viewport; unmapped access → spatial page fault → host-served page-in via GPU Patch-and-Copy. GATES in priority order: (1) CPU≡WGSL parity across a BARRIER-ALIGNED page swap (lockstep harness assumes static image today; swaps occur ONLY at tick boundary per BSP — reduces parity to a discrete state transition) — this is the actual work; (2) fault-on-unmapped vectors cleanly to host handler; (3) VCC SHA256 invariant across swap; (4) identity mapping preserved on re-residency; (5) canonical replay MD5 fixpoint across viewport panning. TWO-TABLE RULE: storage map (mkv_infinite_map.py: 1 cell = 1 artifact container, append-only) and page table (1 cell = mutable RAM page) are different zoom levels — never unified. CPU/GPU partition: CPU = emulation/transpile/syscalls/fault service; GPU SIMT = lockstep diff, batched box checks, blits, GlyphGPT. Reference only, not dependencies: `infinite_desktop/arch_design.md`, `systems/infinite_map_rs` | `tests/test_gh25_hilbert_paging.py` — legs above in priority order; leg 1 lands first | QUEUED — horizon after GH-24; do not start before GH-23 |

Ordering: GH-16 → GH-17 strictly (preemption changes context-save
layout that paging must preserve); GH-18 needs GH-16 (new syscalls must
be preemptable); GH-19 is independent — start anytime, it feeds
GH-18's admission pipeline; GH-20 needs GH-8b/c invariants locked;
GH-21 needs GH-18 (Syscall ABI v2) + GH-17 (Paging for sys_brk);
GH-22 needs GH-16 (Preemption) + GH-13/14 (Mailbox protocol);
GH-23 needs GH-21 (POSIX Shim) + GH-19 (stdlib foundation).
GH-24 needs GH-18 landed (fixed ABI for the box legend); queue after
GH-20. GH-25 is horizon — do not start before GH-23. The
gh18-table-reservation precondition is CLOSED (commit `07106ab`,
2026-09-08: table pinned to reserved pixel window [1312,1328),
guarded by test_gh18_syscall_table_reserved; gate 14/14) — GH-21 may
start once its other preconditions hold.

Linux knowledge feed: hardware register knowledge (datasheets, errata,
Linux driver quirks) flows in as PROVEN FACTS written into tiles and
their oracles — never as transcribed code (GPLv2). Each fact lands as
"(source file, register behavior)" in the tile's oracle comment, so a
future Linux fix can be diffed in as a fact-update without licensing
or provenance damage.

Positioning guard: every arc item must STRENGTHEN the provenance story
(proof before run, receipts as hashes). An item that adds Linux-like
features WITHOUT proof is out of scope regardless of demand — that is
the trap that turns this into a worse Linux. Drivers and libc runtimes
remain strictly sandboxed USER processes or oracle-proven atlas tiles;
the resident kernel remains micro-minimal (<300 lines of verified spatial assembly).

## Receipt discipline

Each item's commit message pastes the failing-test output BEFORE the fix
(or the gate run that proves it was already failing), then the passing run.
No summary-sentence receipts.
