# RECEIPT: Bare-Metal Boot-Chain Proof (512-byte scale)

**Date:** 2026-09-17
**Location:** `tools/bare_metal_poc/`
**Question:** Can a PXC1 pixel container boot a machine with no OS, no
QEMU disk file, and no virtio backend underneath it — i.e., is the
"pixels are the disk" mechanism viable on bare metal?

**Answer: YES, at 512-byte scale.** A 512-byte x86 boot sector lives only
as RGBA pixels in a PNG; a standalone decoder serves those bytes to QEMU
over NBD; SeaBIOS loads them; a real CPU executes them; the guest prints a
receipt whose checksum the host recomputed independently from the decoded
pixels. Full gate: `./run_gate.sh` → `GATE PASS` (re-run 2026-09-17).

## What ran (the chain)

```
boot.asm (nasm)            512-byte MBR: COM1 init, prints receipt, prints
  → boot.bin               checksum of its own 512 bytes, halts. sig 55aa.
pxc1_boot_codec.py encode  bytes → PNG 4096×4096 RGBA, PXC1 byte packing
  → boot_sector.png        (R=b0,G=b1,B=b2,A=b3, row-major), dual sha256
                           gates in a tEXt chunk (payload + RGBA stream).
nbdkit + pxc1_nbd_plugin   THE BARE-METAL STAND-IN for virtio_pixel_rs:
  → unix socket            decodes pixels → payload at load; serves preads
                           from a live view; pwrites journal in RAM; the
                           PNG is never touched (base+jar, like prod).
QEMU 8.2.2                 plain BIOS (SeaBIOS) → reads "disk" over NBD →
  -drive file.driver=nbd   0x7C00 → real CPU executes the pixel bytes.
    ,format=raw,if=ide     TCG, no KVM, no virtio, no initrd, no -kernel.
```

## Measured results (all legs)

| Leg | Expected | Measured | Verdict |
|---|---|---|---|
| PNG encode/decode roundtrip | byte-identical | md5 `911ddf5c...` both sides | PASS |
| GREEN: boot from live pixels | `CKSUM=5F3B EXEC` | `CKSUM=5F3B EXEC` | PASS |
| Guest checksum vs host (pristine) | equal | 5F3B = 5F3B (independent paths) | PASS |
| RED-A: byte0 0xFC→0x5A | guest sees new CKSUM | `CKSUM=5E99 EXEC` | PASS |
| Checksum arithmetic | 0x5F3B−0xFC+0x5A | = 0x5E99, guest agrees | PASS |
| RED-B: destroy 55AA | zero execution | 0 serial bytes | PASS |
| PNG immutability under journal writes | unchanged | sha256 gates re-verify after 2 boots + 2 writes | PASS |
| RE-GREEN after server restart | journal evaporates | byte-identical serial, `CKSUM=5F3B` | PASS |

End-to-end timing note: a full QEMU boot-to-receipt at this scale takes
well under the 8s `timeout` used (SeaBIOS+MBR; total wall dominated by the
timeout itself). The disk has been 512 bytes from the CPU's point of view
and *pixels-only* from the storage point of view for the entire session.

## The two findings worth keeping

### 1. SeaBIOS IDE requires a writable disk (measured, not assumed)

A read-only NBD export or `readonly=on` drive fails instantly:
`qemu-system-x86_64: Block node is read-only`. True for the plain file too.
So the production backend's write path isn't optional even for boot-only
flows — BIOS/DiskIO probes may write. Consequence: the plugin implements
the production pattern — pwrites land in a RAM COW journal; base PNG is
frozen (md5 unchanged through the whole gate; sha256 gates re-verified).
Shutdown without `/writeback` ⇒ journal evaporates ⇒ RE-GREEN leg proves
the base re-derives cleanly.

### 2. The corruption leg: "different CKSUM" is a one-sided verification

RED-A corrupts byte 0 (0xFC `cld` → 0x5A `pop dx`), and the guest still
EXECs — nop-for-nop, same length. The gate therefore checks that the guest
reports a *different* checksum (5E99), which it does. Lesson: a one-byte
payload can't survive arbitrary single-byte corruption; "corrupt it and
expect failure" needs the failure to be *specified*. RED-B (55AA
destruction → zero serial) is the hard negative; RED-A is the
observability leg. Also learned: qemu-io `-P` takes **decimal** patterns
(`-P 90` wrote 0x5A, not 0x90 — the plugin trace settled a wrong theory
about QEMU overwriting the MBR; it didn't).

## Files

- `boot.asm` → `boot.bin` — the payload (checksum + message + `55aa`)
- `pxc1_boot_codec.py` — encode/decode, PXC1 packing, dual sha256 gates
- `pxc1_nbd_plugin.py` — nbdkit plugin: pixels → block device, COW journal,
  per-request trace at `/tmp/pxc1_trace.log`
- `run_gate.sh` — the full gate (run it; it re-derives every number above)
- `serial_g.log` / `serial_ra.log` / `serial_rb.log` / `serial_rg.log` — legs' raw output

## Why this de-risks the bare-metal rewrite

The transcript's open question was whether PNG decode can run with
"nothing underneath." This proves the *serving* half: with NBD as the
only shim (which real hardware won't have), BIOS + a real CPU will boot
pixel-resident code, and the pixel bytes fully determine execution
(RED legs). What remains genuinely unsolved for bare metal — the other
half — is the *consumer* half: a pre-boot environment decoding PNGs
itself (PNG inflate in firmware/asm, or a raw-RGB container variant to
dodge inflate entirely), plus a pixel-backed disk driver the bootloader
can read. That's rung 2: PXE/iPXE + wimboot-style initrd, or the raw-RGB
variant where "decode" is a `memcpy`. Nothing in this receipt's measured
behavior blocks rung 2.

## Reproduce

```bash
cd tools/bare_metal_poc
./run_gate.sh          # ~45s, ends with GATE PASS
```

Gate legs are individually re-runnable per the script; logs land beside it.

## Rung 2 — landed 2026-09-17 (see `rung2/RECEIPT_RUNG2.md`)

The NBD shim is gone: `rung2/` boots a medium whose bytes are a raw RGBA
pixel stream, and the MBR itself does the pixel-domain work — BIOS int 13h
read, four-channel-plane de-interleave, checksum gate, then jump into the
decoded bytes. Gate (`rung2/run_gate2.sh` → GATE PASS): GREEN
`CKSUM=4541 EXEC` at 0.082 s boot-to-receipt; RED-A corrupt payload pixel →
specified `GATE=FAIL SUM=4640` with host arithmetic matching the guest;
RED-B silent; ABSENCE proves 0/129 payload 16-byte windows are contiguous
in the payload region (de-interleave is required, not decorative);
RE-GREEN byte-identical after PNG rebake. The "consumer half" this receipt
left open is therefore measured and closed at plane-encoding scale; PNG
inflate in firmware (rung 3) remains the open rung.
