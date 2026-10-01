# RECEIPT — L4-DESKTOP (SUPPLY_ROUND8.json item 17)

**Landed:** 2026-09-24 ~10:1x–10:4x CDT, builder cron af3e62239ce2.
**Receipt landed:** 2026-09-24 (this lane's follow-up tick, after the
prior session ended before committing — see "Continuity note").

## Deliverable

`experiments/glyph_desktop_env.py` — the HEADLESS desktop core:

- `DesktopConsole`: one GlyphL1Shell + one TextConsole ring per tab.
- `DesktopEditor`: open/save I/O strictly through the GPU's
  FILE_READ (0x04) / FILE_WRITE (0x03) arms — never a host file handle.
- `DesktopLauncher`: lists every L1 verb + `edit`, runnable in a console.
- `DesktopEnv`: tab lifecycle + JSON session save/restore, session root
  persisted in the payload (landing-time defect fix — see below).

Gate: `tests/test_l4_desktop.py` — 11 tests.

## Gate evidence (this receipt's own runs)

- RED-first (re-shown this tick on the pre-commit tree, module moved out):
  `pytest tests/test_l4_desktop.py` → collection ERROR, 0 tests ran
  (ImportError on absent `experiments.glyph_desktop_env`). The gate can
  fail.
- GREEN: 11 passed in 0.11s at working tree (pre-commit), twice
  (before and after the RED re-show).
- In-gate discriminating legs:
  - `test_n1_neutered_gpu_image_breaks_editor_save`: dispatch image
    swapped for build_shell() (no 0x03/0x04 arms) → editor save produces
    NO file. Proves editor I/O runs through the GPU's FILE_WRITE body,
    not a host shim.
  - `test_n2_corrupted_cat_expectation_fails`: corrupted expectation →
    RED. The gate cannot pass vacuously.
- Regression family: l1 personality + l2 files + l3 pipes + bk22 + text
  console = 82 passed (this tick).
- Continuous dogfood floor transcript re-run this tick:
  `.builder_queue/transcript_dtf_floor.py` → PASS, exit 0.

## Landing-time defect found + fixed in-session

`restore()` minted a fresh L1Session root, so files saved before
`save_session` were unreachable after restore (measured:
`cat memo.txt` → ERR:NOENT). Fix: the session root is persisted in the
payload and restored. This is the round-8 success criterion's
persistence leg (`test_l4s_session_save_restore_roundtrip`).

## What the PASS does NOT prove

- The Tk window itself (pixel/layout legs): operator-eyes PENDING per
  the GUI-receipt pattern. `glyph_desktop.py` is untouched — upgrading
  it to consume `DesktopEnv` is the operator-eyes follow-up.
- No WGSL twin of the desktop surface.
- No multi-user/network capability (documented non-goals).
- Dogfood/floor transcript exercises the L1/L2/L3 surface, not the
  desktop tab/editor objects directly.

## Continuity note (honest disclosure)

The prior session wrote `glyph_desktop_env.py` + `test_l4_desktop.py`
and updated PRODUCT_LANE_STATE.md ("LANDED") but exited BEFORE
committing the code — leaving the ledger's claim backed only by
untracked files, and this receipt never written. This tick: re-ran the
full gate arc on the actual tree (RED + GREEN + family + dogfood,
above), wrote this receipt, and committed code + receipt together so
HEAD backs the ledger's claim. Files: HEAD-revision committed in one
commit; nothing else in the lane's write set touched.

## Scope

Changed/added: `experiments/glyph_desktop_env.py` (NEW),
`tests/test_l4_desktop.py` (NEW, force-added past .gitignore's
test_*.py rule), `.builder_queue/RECEIPT_L4_desktop.md` (NEW),
`.builder_queue/PRODUCT_LANE_STATE.md` (continuity line).
Untouched: engine sources, twin sources, `glyph_desktop.py`, BK-21,
protected assets (voicebook/, .rts/, rs_fixtures.json).
