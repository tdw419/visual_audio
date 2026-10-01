# RECEIPT — RUNG2 gate re-executed INSIDE the pixel-booted VM (nested)

**Date:** 2026-09-18. **Trigger:** Jericho: "maybe you could launch qemu and
linux inside the vm and see what pixels change inside of the container."
**Executor:** host-side Hermes, driving guest Hermes' host over SSH
(`ssh -p 2222 jericho@127.0.0.1`, the AGENTS.md guest bridge).

## Environment (all measured)

- Host backend: `virtio_pixel_backend` serving `ubuntu_desktop_pxc1_v3_selfhost`
  via `/tmp/virtio-pixel-interactive.sock`; QEMU with `vhost-user-blk-pci`
  bootindex=1 (the guest's ONLY disk is pixels).
- Guest: Ubuntu 24.04, 4 vCPU, ~6G RAM, `/dev/kvm` present (nested KVM OK).
- Guest toolchain: qemu-system-x86_64 (present), PIL 10.2.0, **no numpy**
  (host codec imports numpy — guest audit used PIL-only paths),
  **no nasm** (host binary could not be transferred; see Limitations).

## Legs (all run from INSIDE the guest, guest-local /tmp/r2audit)

| Leg | Result | Serial (guest-local) | sha256[:16] |
|-----|--------|----------------------|-------------|
| PNG→raw identity (PIL decode, 64MB) | byte-for-byte match; sha256 == meta rgba_sha256 | — | ef8b83b269ec2a7b |
| [1] GREEN nested boot | `PXC1-RUNG2 / GATE=PASS / STAGE2 CKSUM=4541 EXEC` | serial_nested.log | 33e059eb33559229 |
| [2] RED-A (byte516 := 0xFF) | `GATE=FAIL SUM=4640` = (4541 − 0 + 255) mod 2^16 | serial_ra4.log | 43fb1d525af99bd3 |
| [3] RED-B (55AA zeroed) | 0 serial bytes (loader never ran) | serial_rb.log | e3b0c44298fc1c14 (empty) |
| [6] RE-GREEN (byte restored from PNG pixels) | `CKSUM=4541 EXEC`, **byte-identical** to first nested boot | serial_rg2.log | 33e059eb33559229 |
| [5] absence (pure-stdlib, 8.4s in guest) | 0 of 129 payload 16B-windows contiguous in payload region; 59 match only inside stage1's contiguous copy; planted-probe control OK | — | — |

Matches `RECEIPT_RUNG2.md` numbers exactly: CKSUM=4541, RED-A 4640, RED-B 0.

## Audit findings (things the host script's own legs don't surface)

1. **RED-A's offset 516 holds 0x00 in the pristine medium.** A port that
   writes 0x00 (or `qemu-io -P 0`) "lands" per the
   corruption-landed check but corrupts nothing — the leg then boots GREEN
   and the gate fails loudly (as designed), but the operator-visible symptom
   is a silent-looking empty serial. The write-value must be
   `ORIG XOR 0xFF`; the landed-check should additionally assert `ORIG != NEW`.
2. **Leg sequencing is load-bearing.** RED-B destroys 55AA and the rebake
   only happens at leg [4]. Any reordering (or partial rerun) leaves the
   medium unbootable and every later serial silently empty — misreadable as
   "loader produced nothing" instead of "BIOS refused the disk." Observed
   first-hand during this audit; recovery was re-deriving 510..512 AND 516
   from the PNG (the source of truth) — which is itself a nice demo of
   PNG-as-recovery-medium.
3. **The absence scan is O(n·m) and takes 8.4s per 129 windows in-guest**
   without numpy; fine for rung2's 144B payload, will not scale to
   kernel-sized payloads — the rung7+ absence design needs a suffix-array or
   block-hash approach.

## What this proves

The rung2 thesis — pixels are the disk, the loader decodes itself, no host
shim — holds **nested one level deeper**: inside a machine whose own disk is
itself a pixel stream served by the backend. The proof chain is now
pixel-disk(all the way down to the outer guest) with no rung2-specific host
process at the inner level. This is evidence for the ladder's environment-
independence claim, not a new rung.

## Limitations

- stage1/stage2 were NOT re-assembled in-guest (no nasm; binary transfer to
  the guest failed — OpenSSH 9.6 scp/SFTP channel stalls over the slirp
  hostfwd, exec channel works). The audit re-verified the SHIPPED stage1 from
  the medium; a from-source guest rebuild remains open (needs guest nasm via
  a sudo one-liner, Jericho-owned like the udisksd one).
- Legs ran against a copy in guest `/tmp` (ephemeral); this receipt is the
  durable record. Repo tree untouched (read-only from guest except nothing —
  all writes were guest-local).
