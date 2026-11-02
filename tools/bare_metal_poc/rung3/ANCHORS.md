# Rung 3 Anchors — measured 2026-09-17 (QEMU 8.2.2 SeaBIOS, TCG, defaults)

`memprobe.asm` (512B, gate-style serial receipt) boots bare and reports
what a real-mode pre-boot stub can see on this machine:

```
MEMPROBE
EXT88=FC00            int 15h AH=88h: 64512 KB extended (legacy 16-bit cap)
E801A=3C00 E801B=06FE AX=15360 KB (1-16M) + BX=1792*64KB=114688 KB (>16M)
E820=0007             full INT 15h E820 map: 7 entries, works from real mode
```

E801A+E801B+640K = 128 MiB — the QEMU default `-m`, correctly reported.

## What this decides

1. **Real mode sees 128 MB of RAM but can only address 1 MB of it.** The
   EDD disk-read DAP transfer buffer is segment:offset (16-bit), so
   multi-MB payloads cannot be staged by int 13h alone without a PMODE/
   unreal-mode switch. Two viable paths follow:
   - **Path A (raw-RGB, pure real mode):** keep the decoded payload
     ≤ ~500 KB (conventional memory budget), read plane chunks through a
     window, scatter-decode streaming. Zero new primitives beyond rung 2;
     the de-interleave is a per-byte scatter that streams naturally.
   - **Path B (PNG-native):** needs zlib in the pre-boot environment.
     A 512-byte stub cannot carry an inflator; use iPXE (which inflates
     gzip'd initrd natively) or an OVMF payload rather than hand-rolling.
     Rung-2's gate pattern (build-time consts + runtime sum16 + specified
     RED legs) transfers unchanged.
2. **E820 works from the stub** (7 entries measured) — the loader can size
   staging buffers from the real map instead of assuming.
3. Decode remains free (rung 2: 0.082 s boot-to-receipt incl. SeaBIOS).

## Gotchas paid for (do not re-pay)

- E820 SMAP magic is `0x534D4150`. Written byte-reversed (`0x504D5341`,
  "ASMP" in memory), SeaBIOS correctly rejects every call — CF set, zero
  entries. Symptom: `E820=0000` with a silently-working probe.
- nasm `%%` local labels live only inside `%macro`; bottom-of-file local
  data labels attach to the *last non-local label* (a subroutine), not to
  `start:` — use non-local names for data (rung-1 `msg1` convention).

## Recommendation

Path A next (cheap, proven pattern, no inflate question), targeting a
payload big enough to matter (~64-256 KB stage2 — e.g. a real sector
reader + PNG archiver). Path B later via iPXE. Nothing here blocks either.

## Artifacts

- `memprobe.asm` → `memprobe.bin` (512B) — the probe
- `serial_memprobe.log` — raw receipt (qemu exit 124 = hlt-idle until
  timeout; receipt printed long before)

Commit note (for whenever Jericho ratifies): sources + receipts in;
`*.raw` (64 MB), `*.png` artifacts, serial logs out — they re-derive via
the gate scripts.
