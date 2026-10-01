# BM903 step 2 receipt — kernel + initrd on the PXC1 pixel medium, CRC32 gate v2

Brief: `.builder_queue/brief_bm903_e2e_pixel_boot.md`, step 2.
Date: 2026-09-19. Lane: BM903 (single lane; no other `bm903_*` qemu running during
these legs — see "Serialization" below).

## What was built

| File | Role |
|---|---|
| `rung9/bm903_pxcodec.py` | rung-4's four-plane PXC1 convention, extended to 13.6 MiB: payload = 3 sub-images (header band, pm kernel, initrd) concatenated in whole 16 KiB interleave groups + whole-bank padding. Emits `bm903_px_layout.inc`, `bm903_crc32tab.inc`, `bm903_px_meta.json`. Round-trips itself (`decode(encode(x)) == x`) before anything consumes it. |
| `rung9/bm903_stage2_px.asm` | byte-copy of the committed step-1 stage2 with exactly four deltas (header read → sub-image 0; `load_region` → `px_walk`; CRC32 gate v2 on the only path to the handoff; nothing else moved). Zero page, cmdline, registers and the jump are step-1 text. |
| `rung9/bm903_mkimg_px.py` | builds `bm903_medium_px.raw` and refuses to write it unless five host-side proofs hold (below). |
| `rung9/bm903_anchor_boot.py` | boots a medium with no debugger and timestamps every checkpoint, so "slow" and "stalled" are different answers. |
| `rung9/bm903_px_memcmp.py` | dumps all three destinations out of the running guest at the handoff and byte-compares them to the host blobs. |

Medium: `bm903_medium_px.raw` = 26,641 sectors = 13,640,192 B; payload
13,631,488 B = 832 groups = 208 banks; plane 3,407,872 B = 6,656 sectors; base
LBA 17; `CRC=393950AA`. Step 1's medium (`bm903_medium.raw`, contiguous) is
untouched and its gate still passes (20/20, below).

## Host-side proofs, before a single byte boots (`bm903_mkimg_px.py`)

1. `decode(encode(payload)) == payload` — codec round-trip.
2. **Guest-walk replay**: `guest_walk()` re-derives every plane chunk LBA as
   `BASE + group*CHUNK + plane*PLANE_SECTORS`, de-interleaves `byte 4j+p = PBp[j]`,
   and slots each group through the `.inc` sub-image table — all read from
   `bm903_px_layout.inc`, the same text the asm `%includes`, not from the
   codec's Python constants. The replay reproduces the payload byte-for-byte and
   each destination receives exactly its own group range.
3. Every sub-image destination is contiguous: a group that lands at a non-next
   offset trips `table or stride drift`.
4. **One CRC algorithm, not two**: the 256-entry table in `bm903_crc32tab.inc`
   is compared entry-by-entry to the host table, and the CRC8 macro's recurrence
   is replayed over all 13,631,488 bytes and compared to `zlib.crc32` AND to
   `EXPECTED_CRC` in the `.inc`.
5. Assembles warning-free at exactly 8,192 B (16 sectors), and `bm903_stage1.bin`
   is byte-identical to step 1's — the medium's front end did not change.

`python3 bm903_mkimg_px.py` →
`walk replay + sub-image slotting + CRC parity all green`.

## Gate v2 discipline on the executed path

The walk computes the whole CRC **before** printing anything (rung-4's
DEFECT-R4PRINT), then prints computed-then-expected, then decides:

```
BM903-S2 PIXEL WALK DONE
BM903-S2 GATE2 CRC=393950AA EXP=393950AA
BM903-S2 GATE2=PASS
BM903-S2 HANDOFF BUILT
```

`CRC=393950AA` is the value the *guest* computed over the bytes it decoded; the
guest arithmetic and the host arithmetic are the same table and the same
recurrence (proof 4). `px_refuse` is the only other exit and it hangs without
building the handoff (step 3's L6 exercises it).

## Executed-leg results

Capture (`bm903_capture.py bm903_medium_px.raw bm903_px`, probe34 structure,
`hbreak *0x100000`): both legs reached checkpoint 6/6 `HANDOFF BUILT`, stop at
`rip=0x100000 rsi=0x13ab0 rsp=0x1f784 cr0=0x11 eflags=0x46`, wall 0.7 s.

Differential (`bm903_differ.py`, baselines = `bm902_zp.bin` / `bm902_cmdline.bin`,
whitelist = BM902 field plan ∪ BM903 addendum, 517 offsets; the addendum may
re-license, never widen — asserted):

```
L1 PASS: 4 zeropage byte(s) differ from bm902_zp.bin, all inside the whitelist
         union (517 offsets): 0x21b, 0x21c, 0x21d, 0x21e
L2 PASS: cmdline byte-identical all 512 B (82 chars)
L2b PASS: ramdisk_image=0x10000000 ramdisk_size=0x8d4f07 == bm903_layout.json
L3 PASS: all 25 registers match the oracle, including rsp=0x1f784
BM903 DIFFER PASS: L1+L2+L2b+L3 green      (identical on leg 0 and leg 1)
```

The only 4 bytes that differ are the constructed initrd pair — the pixel medium
produces the same handoff the contiguous medium did.

Determinism and cross-medium identity: `cmp` of `bm903_px_zp_leg0/1`,
`bm903_px_cmdline_leg0/1`, `bm903_px_regs_leg0/1` → byte-identical; and the px
dumps vs step-1's dumps → byte-identical. The step-1 gate
(`run_bm903_step1.sh`) still reports `STEP 1 TALLY: 20 pass, 0 red` after the
capture script gained its optional `[medium] [prefix]` arguments (defaults
unchanged).

Guest RAM (`rung9/bm903_px_memcmp.py`): all 13,556,135 B of the three
destinations — header band at `0x20000`, pm kernel at `0x100000`, initrd at
`0x10000000` — byte-identical to the host blobs.

Boot to anchor (`rung9/bm903_anchor_boot.py`, no debugger, wall budget 200 s):

```
  [+   1.0s] stage2 enter      [+  11.0s] login msg
  [+   1.0s] walk done         [+  11.0s] anchor            tc@box seen
  [+   1.0s] gate verdict      medium=bm903_medium_px.raw elapsed=11.0s rc=0
```

Step-1 control at the same moment: `elapsed=12.0s rc=0`. The pixel walk adds
nothing measurable: 832 groups × 4 plane reads = 3,328 ATA commands, 26,624
sectors, 13.6 MiB decoded and CRCed, in under a second of guest time.

## Serialization — a measured trap, not a theory

The first two pixel boots "failed" with the kernel stalling right after
`login: root login on 'tty1'`, and the capture failed with
`could not connect: Connection timed out`. Both were artifacts of running legs
concurrently:

* QEMU takes a **write lock on the image** even for a read-only boot, so a
  second qemu on the same medium cannot start (the runner saw an empty serial
  log and a dead gdb connection).
* With three TCG guests plus another lane's 4-vCPU KVM guest contending, the
  stalled boot showed the pixel walk finished (`HANDOFF BUILT`, gate PASS) but
  `tc@box` never appeared inside 240 s; the same medium alone reaches it in 11 s.

Consequently the step-3 row gate runs its legs **sequentially**, asserts no
other `bm903_*` qemu is alive before starting, and treats a budget miss as a
FAIL that names the budget.

## Status

Step 2 is green: the kernel and initrd live in the PXC1 pixel medium, the
de-interleave is the rung-4 convention extended to the bank walk at 13.6 MiB,
CRC32 gate v2 sits on the only path to the handoff, and the boot reaches the
serial anchor. Next: step 3, `run_bm903_e2e.sh` (L1-L6).
