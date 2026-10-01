# RESEARCH — BK-58 residual: the manual-checklist mouse hit-testing legs
# (real clientX→cell pixel math) close GREEN at HEAD 1c1a297f — the last
# "NOT proved" item on the BK-58 viewer row (builder af3e62239ce2, 2026-10-01)

## Question

BK-58's landing receipt disclosed "real MOUSE hit-testing on the canvas
(mousedown/click geometry; legs drive openDrawer/termSend directly at the
handler-called functions, the clientX→cell pixel math itself unexercised)"
as an open item. Does the viewer's pick math hold when real (trusted)
mouse events are dispatched through Chromium's input pipeline?

## Method (what was measured/read)

- Real headless Chromium 153 (CDP :9222) drove the REAL viewer HTML
  (byte-identical to HEAD, md5 4dd0b8132c927cd1d4af4e25b7a41385 before AND
  after all runs) served over http://127.0.0.1:8091.
- Real input: `Input.dispatchMouseEvent` (mouseMoved / mousePressed /
  mouseReleased / mouseWheel) at viewport coordinates computed with the
  viewer's OWN inverse mapping
  (clientX = rect.left + panX + (cx+0.5)·cellSize·zoom).
- Probe: `.builder_queue/probe_bk58_mouse_legs_af3e.py`
  (md5 ac8eb6097f097a539194e7045504302f).
- RED-first: `.builder_queue/probe_bk58_mouse_red_af3e.py`
  (md5 22b2cccc6ebff2aa91a242dd6121a93f) — served-copy neuter shifts the
  pick math, page force-reloaded (Page.reload ignoreCache, the landed
  BK-58 lesson).

## Findings (measured, this tick)

- GREEN 4/4 legs, twice, deterministic:
  - M1 hover: real mousemove over cell (0,0) center → hoverCell=(0,0),
    tooltip block, exact title text "fix(bare_metal_poc): …" rendered.
  - M2 click: real mousedown+mouseup at the same point → drawer opens,
    selectedCell=(0,0), drawer title == the cell's title, badge "commit".
  - M3 wheel: real mouseWheel deltaY=120 at canvas center → zoom
    0.4619140625 → 0.4016644021739131, ratio EXACTLY 1.15 (the handler's
    zoomFactor; cursor-anchored pan math intact).
  - M4 negative: real mousemove over an unoccupied map cell →
    hoverCell=null, tooltip hidden (the clear leg).
- RED-first (neutered tree, exit 1, "2 / 4 legs green"): M1 FAIL —
  hover=(1,0) with the WRONG title ("ruling(ps012): stop at RV32 …");
  M2 FAIL — drawer opens on the wrong cell (sel 1,0); M3/M4 controls stay
  green (the neuter touches only the pick line). The legs DISCRIMINATE:
  they assert the exact cell identity + exact title, not "any tooltip".

## Two harness lessons (both caught by the RED check being vacuous first)

1. **Boundary FP vacuity:** the first neuter (+4) lands the shifted pick
   EXACTLY on the cell boundary (map x 8.0); FP rounding kept it in cell
   (0,0) — RED check passed vacuously. Fixed by measuring, not assuming.
2. **Chromium truncates dispatched clientX:** measured live — a
   dispatched MouseEvent at clientX 405.347 arrives at the handler as 405
   (tooltip.left rendered "421px" = 405+16). At panX=403.5, zoom=0.4619,
   the truncated map x is 3.247, so +4 (→7.25) is STILL cell (0,0) — the
   second RED attempt passed vacuously against a genuinely neutered tree
   (live handler source read over CDP confirmed the neuter WAS running).
   Final shift +5 (→8.25) crosses into cell (1,0) in both the truncated
   and non-truncated worlds; RED then fired with the exact mis-pick shape.
   LESSON generalized: a RED-first harness must compute its corruption's
   effect THROUGH the same pipeline (including input truncation) the code
   under test will see — twice the neuter was live and the leg still
   couldn't see it.

## Numbers policy

All numbers above are structural verdicts (cell ids, md5s, exact zoom
ratios from the page's own state) — no rates, no floors; rule 1 does not
attach. Priority signal source: PRODUCT_LANE_STATE.md:5 "real MOUSE
hit-testing on the canvas … unexercised" (the row's own NOT-proved line).

## Candidate backlog item (NOT claimable without Jericho per header rules)

- **BK-58b — mouse-hit-testing rot-guard gate.** Promote the probe to
  `tests/test_bk58_mouse_hit.py` (subprocess harness: boot chromium +
  http.server, run the 4 legs + RED neuter, pinned md5s). Gate: 4/4 GREEN
  + RED-first discriminating; prereq: none (tools-only); source: this
  receipt + the two probe files.

## NOT proved / open

- Real GPU-composited hit-testing at devicePixelRatio ≠ 1 (headless ran
  at DPR 1; the viewer's math is DPR-independent by construction but that
  is reasoned, not measured).
- Touch/pen input paths (pointer events) — mouse only, per the row text.
- The `speak` launch class remains unreachable (no speak-class cell in
  map data) — unchanged from the prior tick's disclosure.
