# RECEIPT — glyph_desktop.py GUI wrapper (surface-only, un-gated addition)

**Date:** 2026-09-24 ~00:0x CDT · **Landed:** commit with glyph_desktop.py
**Class:** SURFACE — no engine, shell-program, or gate changes
**Verified by:** seat lane headless smoke + OPERATOR independent re-run

## Why this one has no RED-first gate (and why it still gets a receipt)

Every DTF rung changes something the gates own, so it gets a gate. This file
is deliberately gate-free surface: it imports the same run_turn(),
build_dispatch_shell(), and TextConsole the terminal entry uses, and produces
the same artifacts (/tmp/glyph_sh_write.dat, /tmp/glyph_sh_audio.wav,
/tmp/glyph_sh_console_band.png). New gates would duplicate existing coverage.
Per operator feedback: shipped with commit-message-only verification —
recorded here so the practice is explicit, not a silent norm. Rule going
forward: ANY future addition that touches gate-owned surface gets a gate;
pure-surface additions get a receipt stating why none is needed (this file).

## Headless verification (no Tk required — re-runnable)

Engine plumbing exercised exactly as the GUI's on_submit path does:

```
'what time is it'  -> ERR:UNKNOWN_CMD   (item-11 grammar discipline holds)
'w desktop smoke'  -> FILE_WRITE 14 bytes to /tmp path at 1024
'r'                -> read back ' desktop smoke' BYTE-EXACT (byte list verified)
console band       -> 128x320x3 rendered; decode_band() glyph-side == fed text
```

Operator independently re-ran the same headless path and confirmed:
grammar holds, w/r byte-exact (' desktop smoke test' round-trip), code
reuses run_turn/build_dispatch_shell/TextConsole without mocking, engine
exceptions surface as transcript lines (no UI crash on fault).

## Live-window verification (signer: operator's eyes, PENDING)

Tk window constructed on DISPLAY=:1 and pumped 6s with one real engine
turn ('w window smoke test' -> FILE_WRITE 18 bytes, no exceptions). PIXEL
CORRECTNESS OF THE RENDERED WINDOW IS NOT YET OPERATOR-CONFIRMED — the
operator has no display access from the verification session. This leg
closes the first time the operator runs `python3 glyph_desktop.py` and
sees the band render. Until then this receipt is GREEN on engine, PENDING
on pixels.

## What this is NOT

- Not a desktop environment: no file browser, no window manager, no apps.
- Not a new gated rung: zero gate-owned surface touched (this file is the
  proof-of-discipline for that claim — diff shows imports + UI code only).
- Not certified for usability by anyone, per the standing amendment.
