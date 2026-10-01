# RECEIPT — item-37: interactive multi-tile desktop application suite

- **Claim:** QUEUE_STATE.json item-37 (blocks_on item-33 + item-36, both landed).
- **Commit:** 3183e7f7 on glyph-transpiler-autoloop (implementation + gate; brief included).
- **Builder:** af3e62239ce2, tick 2026-09-26 ~20:2x–20:4x CDT.
- **Gate:** `SEED=af3e_item37 .venv/bin/python -m pytest tests/test_item37_desktop_suite.py -q -p no:cacheprovider` → **10 passed in 722.00s, EXIT=0** (output/item37_gate_af3e_green2.txt), run on the exact tree committed.

## Continuity

A prior tick staged the brief, tools/glyph_desktop_suite.py, and
tests/test_item37_desktop_suite.py, and left RED/GREEN output files whose
GREEN tail (704s) was inconsistent with the evidence: both files were written
~5 s apart at 20:14:2x while tools/glyph_desktop_suite.py was edited at
20:12:14 — mid-"run". The staged GREEN did not provably cover the final
module. This tick **resumed, did not rewrite**, and re-ran BOTH legs fresh on
the final tree. The old GREEN is superseded (its file remains on disk,
untrusted); RED was re-demonstrated as output/item37_gate_af3e_red2.txt.

## RED evidence (this tree, run before the green)

Driver: output/item37_red_driver.py (brief's mandated sabotages, unchanged).

- RED 1 — A2 with the byte-loop mask corrupted 0xFF → 0x00:
  `RED 1 (A2 mask corrupted 0xFF->0x00): FAILED as required (gate discriminates)`
- RED 2 — A3 with the channel commit suppressed:
  `RED 2 (A3 commit suppressed): FAILED as required (gate discriminates)`

Tail file: output/item37_gate_af3e_red2.txt — `ALL RED LEGS DISCRIMINATED (2/2 RED FAILED AS REQUIRED)`.

## GREEN evidence (tail, literal)

```
..........                                                               [100%]
10 passed in 722.00s (0:12:01)
EXIT=0
```

Legs: A1 topology (bar + 3 runtimes, contract words inside own tiles, rects
disjoint, composed `GlyphDesktopSuite.open` re-proves it), A2 terminal echo
(32-byte payload, guest XOR/OR/AND/SHR byte-loop, byte-identical), A3 monitor
tracks live state (wire → translate → approach band from painted_color() →
guest metric ST into own tile), A4 explorer (0x13 lists /etc → rc==2,
NUL-separated `hostname\0motd\0`; missing dir rc==-1), A5 click-to-app
(inbox count 1 == exit status), C1 cross-app wire with the commit-suppressed
isolation difference, C2/C2B item-33 + item-36 migration via subprocess, N1
engine byte-guard, N2 in-suite non-vacuity (zeroed slot → ChannelError, B
stays scan).

## Honesty — what the PASS does NOT prove

- No GPU/WGSL execution: host-side Phase-2 composition over the CPU-oracle
  engine (N1 pins tools/glyph_isa_v2.py byte-identical to HEAD).
- The monitor's wire-word → percept translation is kernel-class HOST logic;
  guests still cannot sense or store across fences (private RAM copies;
  item-36 X8 discipline carries over unchanged).
- The explorer lists the landed VFS staging-union-image view via the LANDED
  0x13 arm — there is no in-guest ext2 parser in this item.
- Delivery is cooperative (commit between runs), never preemptive.
- The suite's apps are 4-row tiles whose data rows live inside the tile; the
  reactive runtimes use the locked item-35 full-width 3-row geometry. No new
  window/ABI surface was introduced; all layers consumed, none edited.
- **Rule-1 floors do not attach**: no rate, latency, cost, or throughput
  number is claimed anywhere in this receipt.

## Scope check

`git status --short` before landing showed exactly the three staged in-scope
files (brief, gate, suite) — nothing else tracked was modified. Ledger +
QUEUE_STATE updated in the follow-up commit per the brief's definition of
done.
