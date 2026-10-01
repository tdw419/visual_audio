# BK-58 Manual-Checklist Viewer Legs — CLOSED (headless browser, 2026-10-01 ~06:0x CDT)

Builder: af3e62239ce2 (Glyph OS Event Chain cron). Landing being verified:
349ef238 (BK-58 Stage 2 viewer: bridge + drawer terminal + launch_class).

## What the landing left open (PRODUCT_LANE_STATE.md 05:5x entry, "NOT proved")

> the drawer legs stay the row's MANUAL-CHECKLIST (headless browser not
> exercised; JS syntax-verified via node parse only); ollama/speak handlers
> gated at validation level only (no live ollama round-trip in the gate —
> ollama may not be serving ...)

This receipt closes the headless-browser legs and the live ollama leg.

## Method

- REAL artifacts only: the viewer HTML byte-identical to HEAD
  (md5 4dd0b8132c927cd1d4af4e25b7a41385), the committed build_map_data.json /
  build_map.png, served by `python3 -m http.server 8091` from a scratch copy
  (/tmp/bk58_checklist); the REAL bridge (tools/build_map_bridge.py) live on
  the canonical port 127.0.0.1:8765 with the REAL decision_log.jsonl.
- Driver: snap Chromium headless (--headless=new), DevTools protocol over its
  WebSocket, Runtime.evaluate against the page's own functions
  (launchClassFor / openDrawer / termSend / termLine) — the exact code paths
  the click handlers run. Page RELOADED with ignoreCache before every leg set
  (this bit us once — see harness defects).
- Legs script: .builder_queue/probe_bk58_viewer_legs_af3e.py (md5
  a62eb27643f39b4125c1d5b3d99b50c4). Run shape: `python3 probe...py <cdp_port>`
  with bridge on :8765 and the map served on :8091.

## GREEN run (pristine viewer, exit 0)

```
PASS V1-hud - {"commits": "400", "pct": "730 / 16384 (4.5%)", "frontier":
  "Frontier Cell (24, 20) \u00b7 e9a8a451", "cells": 730, "imgLoaded": true}
PASS V2-drawer - {"drawerOpen": true, "btnVisible": true, "btnText":
  "\u25b6 Run / Teleoperate (glyphdbg)", "cell": "0,0", "cls": "glyphdbg"}
PASS V2b-term-connect - {"open": true, "ready": 1, "termShown": "block", ...}
PASS V3-glyphdbg-output - '7'
PASS V4-ollama-route - 'pong'
SUMMARY: 5 / 5 legs green
```

- V1: map data + PNG fetch, HUD counters populated, image decoded.
- V2/V2b: cell selection opens the drawer, Run button visible with the
  per-cell class in its label, click → WebSocket connects to the bridge,
  term + input panes shown.
- V3: the default demo program (LDI r7 7 / PRT r7 / HALT) round-trips over
  the viewer's OWN WebSocket frame path — output `7` rendered into the term
  pane via termLine (textContent, the no-innerHTML path).
- V4: an ollama-class verdict cell routes a prompt through the SAME open
  socket; LIVE ollama round-trip — qwen2.5-coder:7b on 127.0.0.1:11434
  answered `pong`. The landing's "ollama may not be serving" caveat: it is
  serving, and the full path works end-to-end.

## RED-first / non-vacuity (the legs discriminate)

`neuter_launch_class.py` reduces `launchClassFor` to `return null;` in the
SERVED copy (viewer md5 changes 4dd0b813→(neutered), `return "glyphdbg"`
count 1→0, verified on the wire), page reloaded with ignoreCache:

```
PASS V1-hud - {...}
FAIL V2-drawer - {"err": "no glyphdbg cell"}
FAIL V2b-term-connect - {"open": false, "ready": -1, "termShown": "none", ...}
FAIL V3-glyphdbg-output - '! bridge not connected'
FAIL V4-ollama-route - '! bridge not connected'
SUMMARY: 1 / 5 legs green
RED-EXIT=1
```

Pristine copy restored → 5/5 again (GREEN-EXIT=0). V1 is the control (it
passes on both trees — the map itself is unaffected by the launch-class
wiring, exactly as designed).

## Harness defects caught by the legs' own runs (receipted, not hidden)

1. **Stale-page false PASS (the important one):** the first RED attempt
   "passed" 5/5 on the neutered HTML — the browser tab still ran the page
   loaded BEFORE the neuter; http.server serves no cache headers, but the tab
   simply never refetched. Exposed by inspecting `launchClassFor.toString()`
   LIVE over CDP (still showed the original body). Fix: the legs script now
   issues `Page.reload {ignoreCache:true}` and sleeps before V1. After the
   fix, RED run on neutered → 1/5 exit 1; GREEN on pristine → 5/5 exit 0.
   A headless verification without a forced reload verifies the FIRST page
   load forever — lesson recorded.
2. Port/posture: first bridge was started on :8766 (non-canonical) — viewer
   hardcodes ws://127.0.0.1:8765, so V2b correctly failed with "bridge
   unreachable" until the bridge ran on its canonical port (that failure was
   the viewer behaving correctly, not a defect).
3. Response-render race: fixed 3s/35s sleeps missed or blurred the response
   line under load; replaced with bounded polling for a NEW term child node
   (baseline childElementCount delta), then reading the LAST line only.

## Live log evidence

The GREEN runs appended real `bk58_bridge_launch` rows to the LIVE
.builder_queue/decision_log.jsonl (311 total rows; the 27 bk58 rows include
glyphdbg ok + ollama ok verdicts with 16-hex evidence hashes, e.g.
2026-10-01T11:04:45 glyphdbg ok 3eb8250b744d4eb1). These rows are genuine
launch history from the verification, left in place (they are true records,
unlike the 05:4x probe purge which removed self-cleaning test artifacts).

## What this does NOT prove

- Real MOUSE hit-testing on the canvas (mousedown/move/click geometry) —
  legs drive openDrawer/termSend directly at the functions the handlers call;
  the pixel-math hit test itself (clientX→cell) is still unexercised.
- The `speak` launch class end-to-end (spawns speak.py subprocesses; no
  speak-class cell exists in the current map data — launchClassFor never
  returns it, so the viewer cannot reach it; the bridge handler remains
  validation-gated only).
- Multi-client bridge behavior in the browser context (single tab used;
  gate L3 owns socket isolation).
- BK-59's Stage 3+ desktop gate UNCHANGED (fence-family open set still bars
  compositor-native work). The backlog BK-58 row's status cell stays as-is
  (backlog header reserves row edits; this ledger + receipt are the record).

## Gate hygiene

- tools/build_map_bridge.py, tools/build_map_viewer.html,
  tools/spatial_build_map.py, tests/, engine/: UNTOUCHED (md5-verified viewer
  restore; `git status` shows only the pre-existing build_map regen dirt from
  the live chain + monitor-fix files, none of them this session's edits).
- New artifacts: .builder_queue/probe_bk58_viewer_legs_af3e.py (the legs),
  .builder_queue/neuter script embedded as a receipt appendix below, this
  receipt, one ledger entry.

## Appendix — the neuter (exactly what RED ran)

```python
target = ('if (cell.type === "commit") return "glyphdbg";\n'
          '      if (["clean", "defect", "noise"].includes(cell.type))'
          ' return "ollama";\n      return null;')
neutered = src.replace(target, 'return null;')
```
