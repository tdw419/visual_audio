# RECEIPT: Rung 2 — Loader-Side Pixel Decode (no NBD shim)

**Date:** 2026-09-17
**Location:** `tools/bare_metal_poc/rung2/`
**Inherits:** `../RECEIPT.md` (rung 1: pixels boot a CPU when a host-side
decoder serves the bytes over NBD).

**Question:** Rung 1 still had a shim — nbdkit decoded the PNG outside the
machine. Can the machine do the pixel-domain decode itself, with nothing
underneath: pre-boot code reading a medium whose bytes are an RGBA pixel
stream, recovering executable code from it, and only then transferring
control?

**Answer: YES, at 144-byte payload scale.** The MBR reads the medium via
BIOS int 13h, de-interleaves four channel planes into the payload, enforces
a build-time checksum gate, and jumps into the decoded bytes. No nbdkit, no
NBD socket, no host process. QEMU receives a plain raw file whose bytes
ARE the pixel stream — this is the "raw-RGB variant where decode is one
step from memcpy" sketched in the rung-1 receipt, minus even the memcpy
(the loader builds the payload byte-by-byte out of planes).

## What ran (the chain)

```
stage2.asm (nasm)          payload: COM1 init, checksums its own decoded
  → stage2.bin             bytes, prints receipt, halts. 144B padded (÷4).
build step [0]             generates stage1_const.inc from stage2.bin:
  → stage1_const.inc       PLANE_LEN / PAYLOAD_LEN / PAYLOAD_SECTORS /
                           EXPECTED_SUM — payload-derived constants baked
                           into the loader (code-side twin of the codec's
                           tEXt dual-sha256 gates).
stage1.asm (nasm)          MBR: COM1 init; int 13h AH=42h reads payload
  → stage1.bin (512B)      sectors to 0x1000:0000; DEPLANE×4 de-interleaves
                           (payload byte i -> plane i%4, slot i//4) to
                           0x7E00; sum16 gate vs EXPECTED_SUM; jump
                           0x0000:0x7E00 only on GATE=PASS. sig 55aa.
rung2_codec.py             raw RGBA stream = the IDE disk image:
  → rung2_medium.raw       [0,512) stage1 consecutive (R=b0,G=b1,B=b2,
  → rung2_medium.png       A=b3, BIOS loads it directly); [512,512+4P)
  → rung2_meta.json        stage2 as FOUR CHANNEL PLANES. PNG is the
                           lossless archive (4096² RGBA, tEXt RUNG2_V1
                           dual sha256); 'bake' re-derives raw from PNG.
run_gate2.sh               the six-leg gate below.
```

## Measured results (all legs, `./run_gate2.sh` → GATE PASS ×2 consecutive)

| Leg | Expected | Measured | Verdict |
|---|---|---|---|
| Build + encode | stage2 144B, plane 36B, 1 sector, EXPECT2=4541 | as stated | PASS |
| Host roundtrips | bake(raw)==raw, decode(raw)==decode(png)==stage2.bin | byte-identical | PASS |
| GREEN: boot, MBR self-decodes | `GATE=PASS STAGE2 CKSUM=4541 EXEC` | exact | PASS |
| Boot-to-receipt latency | — | 0.082 s (TCG, serial polling, includes SeaBIOS+decode+stage2) | — |
| RED-A: corrupt payload PIXEL (byte16, plane0/slot4, raw offset 516, 0x00→0xFF) | specified refusal | `GATE=FAIL SUM=4640`, no control transfer; host arithmetic 0x4541−0x00+0xFF=0x4640 matches guest | PASS |
| RED-B: destroy 55AA | zero execution | 0 serial bytes | PASS |
| PNG untouched through corruption legs | unchanged | writes hit raw only; rebake re-verifies rgba sha256 | PASS |
| ABSENCE (leg 5) | payload not contiguous-recoverable | 0 of 129 16-byte payload windows occur contiguously in the payload region (offsets ≥512); 59 windows match only inside stage1's own contiguous copy (shared helper code — counted, not ignored) | PASS |
| RE-GREEN: rebake from PNG, boot | byte-identical serial | identical | PASS |

Controls on leg 5 (a negative claim must prove its search works):
stage1's 16-byte head (consecutive by design) found at offset 0; a planted
`ABSENCE_PROBE_01` needle inserted and found at the expected offset.

## Findings worth keeping

### 1. What "no shim" does and does not mean yet

The decode now lives in the guest's first 512 bytes — but the loader
itself is still stored **consecutively** (BIOS loads sector 0 verbatim;
that constraint is what rung 1 measured). Rung 2 proves the *consumer*
half: pixel-domain decode runs in the pre-boot environment with no host.
It does not yet make the loader itself pixel-resident (a recursive store
problem: the de-interleaver would itself need to be plane-encoded and
decoded by something below it).

### 2. Absence claims must be scoped, not absolute

Leg 5's first draft claimed "no two payload bytes adjacent anywhere on the
medium" and failed — correctly — because stage1's contiguous copy shares
helper code with stage2 byte-for-byte, so windows of shared code hit
inside stage1. The honest form scopes the claim (payload region, offsets
≥512), counts the shared-code matches, and plants a probe to prove the
search can find. A verification that cannot fail is not a verification.

### 3. nasm gotchas (cost two rebuild cycles)

`%%` local labels are only legal inside `%macro`, not inside `%rep` —
wrap repeated bodies in a macro and invoke explicitly. `($+3)&~3` is
rejected because `$` is section-relative at that point — use the
divide/multiply form `((x+3)/4)*4`.

### 4. Decode is free

4 × 36 `lodsb/stosb` iterations; boot-to-receipt 0.082 s under pure TCG.
Pixel-plane encoding costs the boot path nothing measurable at this scale.

## Files

- `stage1.asm` → `stage1.bin` — the self-decoding MBR (+ `stage1_const.inc`)
- `stage2.asm` → `stage2.bin` — the plane-encoded payload
- `rung2_codec.py` — encode/bake/decode; raw stream = disk, PNG = archive
- `run_gate2.sh` — the full gate (~20 s, ends GATE PASS)
- `rung2_medium.{raw,png}`, `rung2_meta.json`, `serial_*.log` — artifacts

## Why this de-risks Rung 3

The raw-RGB path is now proven end-to-end on both halves: host-side
archive/bake (rung 1's codec discipline, dual sha256, RE-GREEN from PNG =
base+jar semantics at file level) and loader-side decode (this receipt).
What remains for the PNG-native boot is exactly the inflate question:
zlib in the pre-boot environment (iPXE/OVMF payload) — nothing measured
here blocks it, and the plane-deinterleave gate pattern (build-time
constants + runtime sum16 + specified-failure RED legs) transfers as-is.

## Reproduce

```bash
cd tools/bare_metal_poc/rung2
./run_gate2.sh          # ~20 s, ends with GATE PASS
```
