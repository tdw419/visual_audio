# RECEIPT — BK-13 Mailbox Net Stack Skeleton

**Date:** 2026-09-12
**Row:** `systems/GLYPH_SELF_HOSTING_ROADMAP.md` → BK-13 *"Mailbox net stack skeleton:
SYS 18 = net_send / SYS 19 = net_recv frames between two Glyph OS instances, both kernels
inside ONE image"*
**Doer/verifier split:** implementation delegated to the Antigravity CLI (`agy`) under
`.builder_queue/brief_bk13_net.md`; the gate was re-run, the mechanism read, and the commit
made by the orchestrator (builder cron `af3e62239ce2`). Nothing here is taken on agy's word.

---

## 1. What landed

| artefact | sha/commit | notes |
|---|---|---|
| `tools/glyph_gpt/net_stack.py` (NEW, 678 lines) | commit below | module + `net_stack_kernel_image()` |
| `tests/test_bk13_net.py` (NEW, 401 lines) | commit below | the gate, 5 legs |
| `.builder_queue/brief_bk13_net.md` | this commit | the delegated brief |

Scoped so that **no core file changed**: the module is standalone (it *imports* `baker`
primitives, it does not edit them), and the gate imports it directly instead of through the
`baker.py` re-export block that GH-20/21/22/23 use. Consequence: AGENTS.md worktree isolation
is not triggered for this row, and the tree carries no co-mingled core edits. The re-export
convention divergence is deliberate and is the reason the diff is 3 files, not 4.

## 2. Mechanism (read, not assumed) — `tools/glyph_gpt/net_stack.py`

- **Two instances, one image.** `net_stack_kernel_image()` (`:598`) is a two-pass bake
  (`assemble_glyph_to_pixels` pass 1 → packed pixel PCs → `bake_image` pass 2).
  Instance A = BOX0 `[600,640)` (`:60-64`), Instance B = BOX1 `[700,740)` (`:73-77`).
  Both task bodies are emitted into the same image and entered/kernelled by the same
  kernel text: `:__task_A` (`:448`), `:__dispatch_B` (`:409`), `:__task_B` (`:503`).
- **The transport is runtime, not a bake-time stamp.** Task A *builds* its 16-word frame in
  its own box (`:449-476`) and sends it **word-by-word through SYS 18** (`:478-492`,
  `SYSCALL r12` inside `:__send_loop`). The kernel handler copies
  `a1 → mailbox[a0]` (`:__ksys_18`, `:379-388`). Task B receives word 0 through
  **SYS 19**, validates length + checksum **in-image** (`:511-545`), and only then pulls
  words 1..15 into its own buffer (`:552-568`). A malformed header jumps to `:__b_reject`
  (`:576-582`) which writes `'E'` and leaves B's buffer untouched.
  Killing the bake-time shortcut matters: a stamped frame would satisfy "byte-exact" without
  any transport existing.
- **Frame format:** 64 B = 16 words; word 0 = `op | (len<<8) | (cksum<<24)`,
  `cksum = (op + len) & 0xFF` (`make_header`, `:138-149`); payload = words 1..15.
- **Box ABI words** (the DEFECT-19 lesson applied): `EXIT_A=620`, `STATUS_A=621` (`:68-70`);
  `EXIT_B=720`, `VERDICT_B=721`, `STATUS_B=722` (`:81-84`); mailbox window `[754,770)`
  (`:91-93`). Frame buffers `[600,616)` and `[700,716)` do not intersect them, and
  `net_span_conflict()` (`:187`) is the checker the gate calls.
- **Admission path:** `admit_net_syscall()` (`:217-244`) is a thin wrapper over
  `autoatlas.admit_syscall()` (proof = admission) that writes a JSON receipt on both the
  admitted and refused outcomes. SYS 18/19 table slots = 1580/1581, pixel words 1324/1325.

## 3. Evidence (all re-run by the orchestrator on the landed working tree)

| run | command | result | artifact |
|---|---|---|---|
| RED | `python3 -m pytest tests/test_bk13_net.py -q` with `net_stack.py` absent | `ERROR … ModuleNotFoundError: No module named 'tools.glyph_gpt.net_stack'` — interrupted on collection, **exit 2** | `output/bk13_gate_run1_red.txt` |
| GREEN | same command, module restored | **5 passed in 14.45s, exit 0** | `output/bk13_gate_run2_green.txt` |
| GREEN (canonical) | `/usr/bin/python3 -m pytest tests/test_bk13_net.py -q` (Python 3.12.3) | **5 passed, exit 0** | `output/bk13_gate_run3_green_py312.txt` |
| arc (canonical) | `/usr/bin/python3 -m pytest` over GH-22, GH-9 window-span, GH-18 ABI, BK-12, BK-1 argv, GH-9 loader, BK-10, BK-11 gates | **51 passed, 1 skipped, exit 0** | `output/bk13_arc_regression.txt` |

Gate legs, and what each actually proves (`tests/test_bk13_net.py`):
- **L1** (`:100`) bakes the image, asserts shape/dtype, asserts the arena/mailbox/ABI geometry,
  and asserts **no span conflict** for both frame buffers (DEFECT-19 lesson).
- **L2** (`:143`) — *the row's core clause*: one `GlyphRunner` on one baked image, A sends,
  B receives; the 16 words read back **from the runner's own memory** at B's buffer equal the
  source list, A's source is intact, the mailbox window carries the frame, both exit words and
  B's `'V'` verdict are checked, kernel status word `0xCAFE000D`.
- **L3** (`:196`) refusal direction is real oracle behaviour: `aa.escalate` is monkeypatched to
  fail verification, and the refused tile comes back `E_ATLAS_UNVERIFIED` with
  `table_word == 0`, the in-image table pixel still `(0,0,0)`, and the *unadmitted image run*
  marking the unknown-syscall word `758 == 69`.
- **L4** (`:268`) two malformed variants (bad checksum, bad length) run as separate bakes:
  B's buffer stays `[0]*16`, verdict is `'E'`, engine does not fault, exits and kernel status
  stay clean.
- **L5** (`:345`) AST scan of the module for `socket/ssl/http/urllib/requests/subprocess/
  multiprocessing/threading/asyncio` (zero found) plus a single-runner single-image run.

## 4. What is NOT claimed (limitations, stated plainly)

1. **Dispatch is not yet a GH-18 table KJMP.** The kernel lights slots 1580/1581, but `:__ksys`
   dispatches SYS 18/19 through inline `CMP/JZ` slices (`:369-377`), and the `:__tile_18/:__tile_19`
   anchors (`:436-439`) are one-instruction `SYSRET` stubs. So "syscalls ARE atlas tiles" is
   *not* demonstrated here — the admission wrapper is exercised in the refusal direction only,
   and the positive direction is a bake flag (`admit_tiles=True`). A follow-up could route 18/19
   through the table PC like GH-18 does; BK-13's clause does not require it.
2. **L4's malformed-frame receipt is harness-written.** The test calls `record_net_receipt()`
   itself; the *rejection* is measured in-image (verdict `'E'`, buffer untouched, clean halt),
   but the JSON receipt is not emitted by the substrate. The clause's word "receipt" is
   satisfied at the artefact level, not the substrate level.
3. **Box/ABI word maps are module-local.** `BK13_BOX0_ABI_WORDS`/`BK13_BOX1_ABI_WORDS` are
   declared by the same module that uses them, so L1's no-overlap leg is a self-consistency
   assertion against those declarations, not `GH9_ABI_BLOCKED`. It would not have caught
   DEFECT-19's class of bug inside the GH-9 loader — the real guard for that remains
   `tests/test_gh9_window_span.py` + the bake-time `gh9_window_span_conflict` (both re-run here).
4. **Skeleton only:** 16-word frames, no retransmit/windowing/flow control, two instances,
   one image. No throughput claim is made.
5. **Interpreter:** the gate and the arc were run under **both** interpreters — the cron's default
   `python3` (Hermes venv, 3.11.15) and the project-canonical `/usr/bin/python3` (3.12.3) — green
   in each case (`output/bk13_gate_run3_green_py312.txt`, `output/bk13_arc_regression.txt`). The
   py3.12 MCP/aperture suites were not part of this arc.

## 5. Parallel-session note (not a BK-13 defect)

`tests/test_bk14_demo.py` (BK-14's landed gate) fails on this working tree — **and fails
identically with both BK-13 files removed**, so BK-13 is not the cause. Cause: another session
is live-editing `tools/glass_box_demo.py` while this run proceeded (md5 `316793fdd2…` at
11:14:43 → `2639f56c24…` at 11:14:48; tracked `M`), so its ACK-gate shape is mid-flight.
Evidence: `output/bk13_bk14_foreign_edit_evidence.txt`. That file is deliberately **not staged**
in this commit, and the human gate (`.geos_emit_ack` / `GEOS_EMIT_ACK`) was not bypassed,
weakened, or touched by this run.

## 6. Provenance

- Ruling that unblocked the row: `.builder_queue/RULING_20260912_defect19_bk13_worktree.md` §2
  (Q1 SYS 18/19; Q2 two kernels in one image).
- Brief: `.builder_queue/brief_bk13_net.md`; agy run log: `output/agy/agy_impl_20260912_110000.log`.
- Stale REPAIR_PENDING for this row (`REPAIR_PENDING_bk13_syscall_numbers.md`) moved to
  `.builder_queue/resolved/` — both questions it parked are answered.
