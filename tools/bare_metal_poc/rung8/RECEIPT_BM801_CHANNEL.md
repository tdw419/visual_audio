# RECEIPT_BM801_CHANNEL — the VGA text receipt channel, built and gated in emulation

**Date:** 2026-09-21T20:58Z, landed as `80030f63` (legs measured 20:44–20:56Z on this tree; an earlier draft of this line carried a 21:05Z guess, corrected against the commit's own timestamp).
**Row it serves:** `TASK_BM801`, whose blocker is a physical x86 box Jericho
designates. Its named fallback receipt channel — "VGA text beacon verified by
XOR-diff glyph matching, not OCR" — is host-side software, so it was buildable,
falsifiable and measurable today even though the boot is not.

## What exists now

| file | what it is |
|---|---|
| `rung8/bm801_beacon.asm` | 512-byte boot sector: paints the full 256-code page in a 16x16 block, then the same 33-glyph message on rows 20 and 21 in two different colours, fill code `0xB0` elsewhere |
| `rung8/bm801_vga.py` | the reader: PPM parse, per-cell canonical ink plane, measured atlas, nearest-glyph resolve by XOR, ambiguity set |
| `rung8/bm801_capture.py` | the capture: headless boot, `-snapshot` so the medium is never written, per-run monitor socket under `mktemp -d`, signals only the pid it spawned |
| `rung8/run_bm801_beacon_gate.py` | the gate, seven legs, each printing its prediction before it measures |

Re-run: `python3 rung8/run_bm801_beacon_gate.py` from `tools/bare_metal_poc/`
(two qemu boots, ~50 s).

## The property that makes this a receipt and not a picture

The reference font is **measured from the same frame it is used to read**: the
sector puts the whole code page on screen at every boot, so the reader never
carries an assumption about which font the display is. That is what has to
survive moving off QEMU — the calibration block is in the protocol, not in the
tool. Colours are likewise not assumed: a cell's background is whichever
thresholded level its four corners mostly take, so light-on-dark and
dark-on-light cells of one glyph produce the same mask (leg B proves it across
three colour pairs, at XOR distance 0).

## Measured — the three things that were guesses until this run

1. **The cell is 9 wide, not 8.** `screendump` of 80x25 text gives a 720x400
   PPM; summed per-column ink span is nonzero in **all nine** columns
   (`carve` leg), the ninth carrying 861,336 of it. The first version of the
   reader carved 8 and silently threw away ink — it read the message correctly
   anyway, which is exactly the failure mode a receipt channel must not have:
   a wrong carve that still confirms. The reader now uses the whole cell and
   the leg asserts every column is live.
2. **Glyph `0xDB` is blank in this font**, with `0x00`, `0x20` and `0xFF`
   (four flat codes, one shared plane). `0xDB` is the box-drawing character the
   sector originally used as its fill — so the fill cell that was supposed to
   cross-check the atlas was invisible, and a beacon written with a blank code
   would read as nothing while the medium booted fine. Fill is `0xB0`.
3. **Noise margin, per glyph cell, measured rather than asserted:** a single
   flipped pixel is always detected (distance >= 1 on all 33 cells), and no
   cell's identity flipped within 12 flipped pixels — `33/33 never misread
   within k<=12`. The channel degrades by *refusing*, not by substituting a
   plausible wrong character, which is the failure direction a receipt needs.

## Gate output, verbatim

```
# bm801 beacon gate | run dir /tmp/bm801_gate.c214anfc
--> carve                      predicts: the frame divides exactly into 80x25 cells, and the ink profile says which columns of the cell are live (an 8-wide carve would drop column 8)
PASS carve                      frame 720x400 cell 9x16, live columns [0, 1, 2, 3, 4, 5, 6, 7, 8] (last carries 861336 of the total ink span)
--> A identity                 predicts: row 20 reads back 'BM801-RECEIPT-OK>0123456789ABCDEF' with every cell at xor-distance 0
PASS A identity                 read 'BM801-RECEIPT-OK>0123456789ABCDEF', 33 cells, distances min/max 0/0
--> B colour-blind             predicts: row 21 carries the same glyphs in two other colours and still resolves at distance 0
PASS B colour-blind             row21 'BM801-RECEIPT-OK>0123456789ABCDEF' (dist<=0); off-layout fill cell -> 0xB0 at dist 0
--> C atlas-ambiguity          predicts: the 25 beacon glyphs are pairwise unique bitmaps; report how many of the 256 codes are NOT
PASS C atlas-ambiguity          4 codes share a bitmap across 1 planes; flat codes ['0x0', '0x20', '0xdb', '0xff']; 25 beacon codes, 0 of them ambiguous
--> D noise-margin             predicts: report, not assert: how many pixels must corrupt a cell before the reader switches to a different glyph
PASS D noise-margin             distance after 1 flipped pixel: min 1, median 1; first misread at k in []; 33/33 cells never misread within k<=12 (all cells)
--> E negative-control         predicts: a reader holding the wrong font must NOT confirm the message
PASS E negative-control         atlas-shifted-by-one reads 'CN912.SFDFJQU.PL?123456789:BCDEFG' (differs from truth: True); a held glyph is still found at dist 0
--> F determinism              predicts: a second boot of the same image gives all 2000 cell planes identical
PASS F determinism              0 of 2000 cells differ between boots
RESULT 7/7 legs pass
```

rc=0. `ps` after the run shows one `qemu-system-x86_64` — pid 1419204, the live
pixel VM, untouched by this lane and never signalled by it.

## What this does NOT establish

- **No hardware was booted.** `TASK_BM801` stays open; this retires the
  *reader* risk, not the transport risk.
- **A photograph is not a screendump.** The reader requires an exact 80x25
  pitch (`pitch_is_exact()`) and per-cell two-level thresholding. Off a real
  monitor the frame must first be deskewed and its levels fixed; the honest
  next step for that is a capture from a known display source with the same
  on-screen calibration block, not more emulation.
- **`0xDB` being blank is QEMU's font, not the VGA spec's.** Any real box
  re-measures its own atlas by construction — which is the point of painting
  the code page at every boot.
- Two glyphs that are complements of each other would collide only if the
  corner rule picked the wrong side; the corner rule is measured here on three
  colour pairs and held, but a real display with anti-aliased scaling would
  need the same check re-run.
