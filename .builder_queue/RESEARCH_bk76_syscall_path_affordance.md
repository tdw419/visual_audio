# RESEARCH — Does the BK-76 vector-word lock generalize to the SYSCALL path?

**Tick:** 2026-09-29 ~09:2x CDT, builder af3e62239ce2 (glyph cron, HEAD 965b691b)
**Question (why):** the BK-76 clause-4 twin refusal (141e87e9) guards the ST
dispatch arm — a post-USER SUPER store to {KFAULT_PC, KSYS_PC, KTICK_PC} is
dropped, no vector. The refusal sits at the ST opcode arm, ABOVE walk_st.
The twin's dispatch-to-SUPER mechanisms are: (a) SYSCALL (E-K2, KSYS armed),
(b) E-K1/E-K2-class fault vectors, (c) tick preemption (GH-16). If ANY
mechanism re-enters USER or executes guest-chosen handler pixels BEFORE the
ST arm's `bk76_ever_user` latch can cover the store, the lock has a
mechanism-shaped hole, not a site-shaped one. This probe asks whether the
lock covers the FULL SYSCALL-into-SUPER path end-to-end on-device.

## Method (what ran, single-run affordance check, NOT a pinned gate)

- Harness: the exact BK-76-twin gate harness (tests/
  test_bk76_exemption_refusal_twin.py `run_leg` shape — run_wgsl real
  buffers + build_shader(OpcodeMapV2()), seeded cpu.mode=1, tile
  (5,0,8,8) armed via mmio[88..91], KSYS_PC=(0<<16)|3, kf=0).
- Probe: .builder_queue/afford_syscall_path_af3e.py (kept).
- Program: the gate's own DISPATCHER_TEXT — SYSCALL into the SUPER
  handler at pixel (0,3), handler LDI r6 sentinel; LDI r7 target; ST
  r7 r6; PRT; SYSRET. Only the target word varies.
- ONE run per leg (affordance check; a claim row would need 2-3 pinned
  identical runs before landing anything).

## Findings (measured this tick, single runs)

1. **H1a — handler ST to KSYS_PC (8194), the gate's own leg, reproduced
   clean as a harness sanity check:** steps 4, word 8194 == 3 (handler
   value unchanged — the LDI, not the sentinel), fault 32776 = 8194<<2,
   mode SUPER post-mortem, no PRT, halted. Matches TW-L1 exactly.
2. **H2 — handler ST to KFAULT_PC (8193), the site the gate pins
   STRUCTURALLY (receipt: "no separate KFAULT device leg"): REFUSED** —
   steps 4, word 8193 == 0 (sentinel did NOT land), fault 32772 =
   8193<<2, mode SUPER, no PRT, halted. The structural pin holds when
   actually exercised: the refusal predicate's term set is identical per
   site and the device agrees. This closes the receipt's "pinned
   structurally, not measured" caveat for the twin's KFAULT site with a
   real on-device leg (single run).

## Consequence for the backlog

- No new defect. The BK-76-twin lock survives its first mechanism-level
  affordance probe: the SYSCALL path's handler stores to locked vector
  words refuse at BOTH measured sites (KSYS measured by the gate, KFAULT
  measured here). ever_user latches at dispatch top of the FIRST USER
  instruction, before SYSCALL flips mode — the latch covers every
  post-arm mechanism on this path.
- Candidate follow-up (NOT filed as a BK row — scope judgment belongs to
  Jericho per backlog header rules): the remaining unexercised
  vector-writing mechanism on the twin is the TICK path (GH-16 KTICK
  preemption re-entering SUPER mid-USER). TW-L1b exercises the KTICK
  word from the SYSCALL handler, not from a live tick. If a later round
  wants belt-and-braces, a tick-driven device leg is the shape.

## Honesty

- Single-run numbers; deterministic harness (gate runs byte-identical
  pinned), but these two legs were not multi-run pinned. Affordance
  check only — nothing landed, no engine/shader file touched.
- rule-1 floors do not attach (structural device verdicts, no rates).
- What this does NOT prove: tick-path coverage (see above);
  oracle-side KFAULT refusal re-measured (oracle EX-L1 already covers
  it, gate green in TW-L6 family); PARALLEL staging (structurally
  unreachable on the twin, _OPCODE_ORDER).
