# ROADMAP AMENDMENT (RATIFIED)

## AMENDMENT DTF-1: "Desktop Floor" — early-personal-computer capability bar

**Proposed:** 2026-09-22, seat lane, from R5.3 day-1 use finding (R53_USE_LOG.md,
commit 3d0b09d5 — "no user surface exists yet").
**Bar definition (Jericho, 2026-09-22):** GPU OS comparable to first CPU desktop
systems (Altair/Apple II/early-DOS era) BEFORE the operator resumes daily
real-use testing. Capability matrix measured 2026-09-22:

| Capability | Now | Floor target |
|---|---|---|
| Runs real programs | YES | (met) |
| Multiprogramming | YES | (met) |
| User programmable | YES | (met) |
| Keyboard input | line-at-a-time, 64B | (acceptable for floor) |
| Text output | host console only | **IN-IMAGE TEXT CONSOLE** |
| Bundled apps | echo only | **DISPATCH SHELL + 5 COREUTILS** |
| Persistent files | flat, fixed-size | **FILES THAT GROW (append)** |
| Directories/paths | none | (deferred — post-floor) |
| Pipes | none | (deferred — post-floor) |

**Ratification effect when signed:** rows below become PRODUCT_ROADMAP.md rungs,
claimable in order by the product lane under standing policy. Nothing in this
amendment is claimable before sign-off.

---

## DTF-1 — glyph-sh v1 dispatch (base: brief_se020_shell_dispatch.md)

Spec authority: `.builder_queue/brief_se020_shell_dispatch.md` + ROADMAP.md
TASK_SE020 row (read both first — brief is the working spec, row is the ruling
history). NOTE (Jericho, 2026-09-22): the brief is a SPECIFIED DESIGN, not a
ruling; this amendment is the approval that activates it.

- **Scope:** dispatch-on-first-byte — `e` echo / `s` speak (SYSCALL 0x08) /
  `w` FILE_WRITE / `r` FILE_READ+PRT / unknown byte → LOUD named error, never
  silent echo. Turn-based harness preserved; batch-never-touches-stdin
  invariant preserved. No engine changes (`tools/glyph_isa_v2.py` read-only).
- **Gate:** `pytest tests/test_glyph_app_shell_dispatch.py
  tests/test_glyph_interactive_shell.py tests/test_glyph_isa_v2.py -q` all
  green, exit 0. Five legs per the brief: echo / speak (Phy16Tone.decode
  round-trip) / write (byte-exact on-disk) / read (round-trip) /
  unrecognized-command DISCRIMINATING leg (neutered-CMP build must fail it).
- **RED first:** `tests/test_glyph_app_shell_dispatch.py` does not exist yet —
  its absence is the RED leg (per ROADMAP row: "this row authorizes creating it").
- **Receipt:** `RECEIPT_DTF1_shell_dispatch.md` — transcript of all five legs on
  ONE shell instance, no restart between commands.

## DTF-2 — in-image text console

Goal: a shell session is visible ON the GPU screen, not only the host terminal.
- **Scope:** text-glyph-to-pixel renderer (font atlas → image rows below the
  program region), a `CONSOLE_WRITE`-class path from shell output into that
  region, and the existing browser compositor / screen reader displaying it.
  Engine change is ADDITIVE (new syscall or documented MMIO band); no existing
  opcode re-verified. WGSL twin parity required (same-commit rule).
- **Gate (write at claim time, minimum legs):** (a) RED-first — a pixel-region
  read of the console band before first write shows blank sentinel; (b) after a
  known string is written, a pixel-region read decodes back to that string
  (glyph-side assertion, not host print); (c) WGSL twin produces byte-identical
  console band for the same write sequence; (d) full engine + twin regression
  green.
- **Honest boundary to record:** text mode here means glyph-rendered text in
  the observation image, comparable to a glass TTY — not a blitter/scroll
  hardware claim. Scrolling = renderer concern, bounded ring of text rows.

## DTF-3 — FS grow (base: backlog BK-7, unchanged)

Goal: files that grow. SYS append + resize with FSTAB compaction (moves
blocks, updates start/len).
- **Gate (from BK-7 row, binding):** `tests/test_bk7_fs_grow.py` — write,
  append 2×, read back whole byte-exact; delete creates a hole; new create
  reuses it. RED-first (test file does not exist; row authorizes creating it).
  WGSL twin: FS handlers are host-side; record twin-boundary note per
  SYSCALL_ABI_SPEC convention.
- **Blast-radius note:** touches GH-8b FSTAB + FILE_WRITE/READ handlers;
  worktree isolation per AGENTS.md if the implementer judges it core. Full
  defect_d + fs suites green post-landing.

## DTF-4 — coreutils volume #1 (base: backlog BK-11, unchanged)

Goal: `cat`, `echo`, `wc`, `cmp`, `head` compile with riscv64-gcc + libc,
transpile via glyph_cc, run on Glyph.
- **Gate (from BK-11 row, binding):** `tests/test_bk11_coreutils.py` — per
  tool: output byte-exact vs native on 3 fixtures each; arc regression green.
  RED-first. KNOWN RISK carried from BK-14 receipt: the `wc` red is a known
  DEFECT-18 class issue — the rung's gate must show `wc` green or the defect
  fixed, no waiver.
- **Dependency:** DTF-3 (files that grow) is a prereq for `cat`/`head` on
  non-trivial fixtures; DTF-1's shell is the delivery vehicle for the demo.

---

## Floor exit criteria (all four green = the bar is met)

A user can, in one sitting: sit at the shell, see the session ON the GPU
screen (DTF-2), run `w`/`r`/`s` commands that do real things (DTF-1), build a
file across multiple appends and read it back whole (DTF-3), and run `cat`,
`echo`, `wc`, `cmp`, `head` as real compiled programs (DTF-4). Measured by
one end-to-end transcript receipt (`RECEIPT_DTF_floor.md`) exercising all of
it in sequence — plus each row's own gates. Apple-II-comparable, in the
specific checkable sense defined above.

## Agent pre-verification of the floor (Jericho-approved 2026-09-22, clarifying addition)

Before operator day-2, the seat lane executes the full floor transcript
agent-driven (batch harness, programmatic input, asserted output — same
pattern as the installer pre-use sanity check) and files
`RECEIPT_DTF_agent_use.md`.

**Scope of what that receipt certifies — binding wording:** the
agent-driven transcript certifies CORRECTNESS of the four legs (dispatch
fires right, file grows right, bytes match, pixels decode). It does not
and cannot certify USABILITY. Usability's failure mode is precisely what
day 1 found: the shell was 100% correct at doing the one thing it did,
and a human still sat down and immediately hit "I don't know how to use
this." Batch mode asserts against expectations someone already wrote
down; "I don't know what to type" is not assertable. Therefore this
receipt must never be cited — in receipts, ledger entries, commit
messages, or roadmap prose — as evidence the floor is usable, and it
does not substitute for, precede in authority, or diminish the
operator's day-2 R5.3 entry, which remains the sole artifact that
certifies human usability. Agent receipt = the floor is built right.
Operator entry = the floor is usable. Different artifacts, different
signers, neither laundered into the other.

## Clock handling (Jericho-directed, binding)

R5.3's 30-day window is NOT reset, extended, or paused. Day 1 stands
(3d0b09d5). No manufactured entries in the gap while the floor lands; the
next entry lands when there's a real day. The clock's only obligation is
that every entry which exists is true — a 20-day gap between day 1 and day 2
is a legitimate record of what happened.

## Standing policy applies in full

Rule 1 floors on any rate claim; rule 4 RED legs at landing; rule 3 fenced
speculation; one-active-ticket cadence; worktree isolation where core files
are touched; mailbox rule (newer RULING_* wins over this amendment if one
lands after sign-off).

---
**STATUS: RATIFIED 2026-09-22 (Jericho). Read in full before ratification, no
changes requested. DTF-1 claimable on the product lane's next tick, DTF-2/3/4
in order thereafter.**
