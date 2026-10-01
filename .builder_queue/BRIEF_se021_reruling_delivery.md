# BRIEF — SE021 re-ruling delivery (mailbox word, holding loop)

**Status: HELD / BLOCKED-ON-JERICHO** — the six fields below are written and stand ready, but the
loop cannot execute this brief until Jericho answers the ruling request already sitting in the
substrate maildrop (63+ consecutive holds as of addendum 183, 2026-09-17).

## Spec pointer

- Ruling request: `.geos/maildrop/content/hermes.0001.ruling.md` (md5 `ab846c18`, from: hermes, kind: ruling)
- RCA: `.builder_queue/SE021_RED_LEG_RCA_20260916.md`
- Prior addendum trail: `TICKET_SUPPLY_STATE_ADDENDUM{49,57,182}.md` (option (a) premise measured FALSE —
  aliasing is structural, not path length)
- Landing that holds: `tests/test_glyph_app_glyph_on_glyph.py` 4 passed at HEAD `0f8b113` (committed 02:44,
  ancestor of current HEAD `8d1af6cf`)

## Scope

- Positive: the SE021 row in `systems/GLYPH_SELF_HOSTING_ROADMAP.md` (status flip + receipt pointer only);
  one new receipt file `systems/RECEIPT_SE021_RERULING_<option>.md`; implementation confined to the module(s)
  the chosen option names.
- Negative: no engine/ABI change outside the option's named surface; no edits to `.geos/maildrop/**` (the
  maildrop is Jericho's channel — the loop appends addenda to `TICKET_SUPPLY_STATE_ADDENDUM*.md` only);
  no change to the landing `tests/test_glyph_app_glyph_on_glyph.py`.

## Gate command

```
python3 -m pytest tests/test_glyph_app_glyph_on_glyph.py tests/test_se021_<chosen_option>.py -q
```

expected: all passed, exit 0.

## Gate clause

- `tests/test_glyph_app_glyph_on_glyph.py` 4/4 passed (the landing holds — pinned-PATH gate at the SE021 word).
- The new option gate module exists, is collected (>0 tests), and 0 failed.
- RED leg evidence: the currently-RED leg at `tests/test_glyph_app_glyph_on_glyph.py:158` (38+ consecutive RED)
  goes GREEN under the chosen option's implementation, with the run pasted in the receipt.
- Roadmap SE021 status cell flips only after the conjunction above is pasted.

## Failure evidence (discriminating requirement)

- The RED leg must be shown RED before the option's fix is applied (re-run at pre-fix HEAD, paste the tail).
- The new gate must be shown able to fail: neuter the option's core assertion → that gate module reports
  FAILED (non-vacuity probe), then revert byte-identical (`md5sum -c`).

## Definition of done

Jericho's option pick ((a) variant / (b)+ / (c) / GH-25 paging route) appears in-channel or as
`RULING_SE021_*.md`; the gate conjunction is green at a committed HEAD; the receipt names what the PASS does
not prove. Until the pick, the loop holds — this brief exists so the next tick executes rather than re-asks.
