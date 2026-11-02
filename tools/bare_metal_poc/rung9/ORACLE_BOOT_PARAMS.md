# ORACLE_BOOT_PARAMS.md — TASK_BM901: field-by-field reference of the real
# Linux protected-mode handoff, captured from the real chain in QEMU.

**Chain:** SeaBIOS → isolinux (El Torito) → bzImage vmlinuz64
**Kernel:** TinyCore 4.19.10-tinycore (bzImage setup protocol **2.13**),
`vmlinuz64.extracted` from rung7's extraction of TinyCore-current.iso
(ISO sha256 pinned in `rung7/RECEIPT_TC_PROBE.md`: `c4654240…`, 28,135,424 B).
**Capture point:** the kernel's first protected-mode instruction at
`code32_start=0x100000`. The chain reaches 0x100000 TWICE: hit 0 is
isolinux's own trampoline (rsi=0x160005, no HdrS — distinguishes it), hit 1
is the kernel handoff with `rsi=0x13ab0` = &boot_params (HdrS verified at
capture). Registers captured BEFORE the kernel executes any instruction.
**Legs:** ×2 independent QEMU boots; all captured artifacts byte-identical
across legs — **zero variability fields observed** (see Variability, below).
**Gate:** `bash rung9/run_oracle.sh` → GATE PASS (phases A–D, RED legs included).
**Mechanism:** GDB stub hw-breakpoint at 0x100000. The QEMU gdbstub re-fires
a code breakpoint when PC has not advanced, so between stop 0 and stop 1 the
session does `stepi 24` then `continue`; the resulting stop-1 registers are
pre-first-insruction kernel state (probe33 measured the same stop at
0x100053 after the step — the state sampled here is the handoff instant).

## Register state at PM entry (identical both legs)

| Reg | Value | Notes vs boot protocol spec |
|---|---|---|
| rip | 0x100000 | = hdr.code32_start ✅ |
| rsi | 0x13ab0 | & boot_params (struct boot_params, 4KB) ✅ |
| cs | 0x10 | flat 32-bit, base 0 limit 4G ✅ |
| ds / ss / es | 0x18 / 0x18 / 0x18 | flat data ✅ |
| eflags | 0x46 | IF=0 (interrupts off) ✅, ZF PF set |
| cr0 | 0x11 | PE=1, PG=0 ✅ |
| cr3 | 0x0 | no paging ✅ |
| cr4 | 0x0 | ✅ |
| rax | 0x100000 | loader artifact — spec says undefined |
| rbx, rcx, rdx, rdi | 0 | |
| rbp | 0x0 | |
| rsp | 0x1f784 | stack just below cmdline buffer at 0x1f800 |

## boot_params (zero-page) — measured fields

All offsets are byte offsets within the 4KB struct at 0x13ab0.
`size_of_boot_params` per spec = 4096 bytes (full page captured: sha256
`c3120d8e…` both legs, `oracle_zp_leg{0,1}.bin`).

| Offset | Size | Field | Measured ×2 | Spec expectation | Delta |
|---|---|---|---|---|---|
| 0x1f1 | 1 | setup_sects | 27 | from bzImage ✅ (matches file) | — |
| 0x1f4 | 4 | syssize | 0x4152a paras (4,280,976 B) | = (vmlinuz size)/16 − setup ✅ | — |
| 0x1f6 | 2 | root_flags | 0x0004 | loader-set | — |
| 0x1f8 | 4 | ram_size | 0xfffc0000 | loader leftover | — |
| 0x1fc | 4 | vid_mode | 0xaa44aa00 region | loader-set | — |
| 0x1fe | 2 | boot_flag | **0xaa55** | ✅ mandatory | — |
| 0x202 | 4 | header | `HdrS` | ✅ mandatory | — |
| 0x206 | 2 | version | 2.13 | = bzImage protocol ✅ | — |
| 0x208 | 4 | realmode_swtch | 0x0 | default ✅ | — |
| 0x20c | 4 | start_sys_seg | 0x34201000 | loader-set | — |
| 0x210 | 1 | type_of_loader | **0x33** | isolinux = type 3 (boot loader ID), `0x30 \| 0x03` | chainload-specific: QEMU-direct shows 0xff/other — this field is HOW the kernel was loaded, flags in BM902 diffing |
| 0x211 | 1 | loadflags | 0x81 | 0x80 = heap-use-ok (CAN_USE_HEAP), 0x01 = LOADED_HIGH ✅ | — |
| 0x212 | 2 | setup_move_size | 0x8000 | loader-set | — |
| 0x214 | 4 | code32_start | 0x100000 | ✅ = actual PM entry | — |
| 0x218 | 4 | ramdisk_image | 0x1f6ea000 | initrd placed top-of-mem-adjacent | — |
| 0x21c | 4 | ramdisk_size | 0x8d4f07 (9,263,879 B ≈ core.gz) | ✅ matches initrd | — |
| 0x220 | 4 | bootsect_kludge | 0x0 | ✅ | — |
| 0x224 | 2 | heap_end_ptr | 0xf5f4 | loader-set (real-mode heap) | — |
| 0x226 | 1 | ext_loader_ver | 0 | ✅ | — |
| 0x227 | 1 | ext_loader_type | 0 | ✅ | — |
| 0x228 | 4 | cmd_line_ptr | 0x1f800 | ✅ (verified: cmdline readable there) | — |
| 0x22c | 4 | initrd_addr_max | 0x7fffffff | ✅ protocol 2.13 | — |
| 0x230 | 4 | kernel_alignment | 0x100000 | ✅ relocatable kernel | — |
| 0x234 | 1 | relocatable | 1 | ✅ | — |
| 0x235 | 1 | min_alignment | 13 (2^13=8KB… spec: 2^20 for this kernel via kernel_alignment) | kernel-baked ✅ | — |
| 0x236 | 2 | xloadflags | 0x4 | XLF_CAN_BE_LOADED_ABOVE_4G off; 0x4 = XLF_EFI_HANDOVER_32 available ✅ | — |
| 0x238 | 4 | cmdline_size | 0x7ff | ✅ | — |
| 0x23c | 4 | hardware_subarch | 0x0 | PC ✅ | — |
| 0x248 | 4 | payload_offset | 0x104 | ✅ matches bzImage file | — |
| 0x24c | 4 | payload_length | 0x40d69a | ✅ | — |
| 0x258 | 8 | pref_address | 0x100000 | ✅ | — |
| 0x260 | 4 | init_size | 0x959000 | ✅ matches file | — |
| 0x264 | 4 | handover_offset | 0xc0 | EFI handover — present, unused here | — |
| 0x1e8 | 1 | e820_entries | 7 | ✅ SeaBIOS map | — |
| 0x1e9 | 1 | eddbuf_entries | 0 | ✅ (no EDDBUF this QEMU config) | — |
| 0x1ea | 1 | edd_mbr_sig_buf_entries | 0 | ✅ | — |
| 0x290+ | 64B | edd_mbr_sig_buffer | all 0 | ✅ consistent with count 0 | — |
| 0x2c0 | 4 | ext_ramdisk_image | 0 | ✅ (initrd < 4G) | — |
| 0x2c4 | 4 | ext_ramdisk_size | 0 | ✅ | — |
| 0x2d0+ | 7×20B | e820_table | see below | ✅ | — |
| rest | — | remainder of 4KB | zeros | zero-filled by loader ✅ | — |

**Unnamed offsets byte-checked:** the gate's Phase B compares the FULL 4KB
struct byte-for-byte across legs; the table above lists every non-zero
region of the captured struct (any field not listed here measured 0x00).

## E820 table as the real chain built it (7 entries)

| # | addr | size | type |
|---|---|---|---|
| 0 | 0x000000000000 | 0x00000009fc00 | 1 (usable) |
| 1 | 0x00000009fc00 | 0x000000000400 | 2 (reserved) |
| 2 | 0x0000000f0000 | 0x000000010000 | 2 (reserved) |
| 3 | 0x000000100000 | 0x00001fee0000 | 1 (usable) |
| 4 | 0x00001ffe0000 | 0x000000020000 | 2 (reserved) |
| 5 | 0x0000fffc0000 | 0x000000040000 | 2 (reserved) |
| 6 | 0x00fd00000000 | 0x000300000000 | 2 (reserved) |

## cmdline (cmd_line_ptr=0x1f800)

```
loglevel=3 cde console=ttyS0,115200 initrd=/boot/core.gz BOOT_IMAGE=/boot/vmlinuz
```
sha256 (512B dump incl. zero padding, both legs): `30cd829f…`
(`oracle_cmdline_leg{0,1}.bin`). NUL-terminated at byte 83.

## Variability table

**Empty.** ×2 legs were byte-identical on zeropage, cmdline, and registers.
Named candidates that were checked and did NOT vary between legs (but are
structurally time/entropy-dependent and MUST be re-checked on any kernel or
QEMU change): `eflags` reserved bits, runtime-set loader scratch fields
(0x1f8 ram_size leftover, 0x1fc vid_mode region, 0x20c start_sys_seg),
stack pointer rsp. This determinism is a QEMU/TCG property, not a hardware
property — do not carry it to Rung 8.

## What this oracle does NOT prove (honest boundary)

- It is the REAL-chain reference only. It says nothing about what stage2
  must do differently (that is BM902's differential test against THIS dump).
- Chainload-specific fields (type_of_loader=0x33, isolinux's real-mode
  scratch: 0x1f8/0x1fc/0x20c/0x212/0x224) are what ISOLINUX produced. A
  pixel stage2 building its own handoff should NOT expect to reproduce them
  byte-for-byte; BM902's diff must classify them LOADER-SPECIFIC.
- QEMU-only: SeaBIOS E820 (512MB -M pc) is emulated-firmware truth, not
  board truth.
- No variability fields were observed in ×2 legs — this bounds, but does not
  eliminate, run-to-run nondeterminism (two legs is the brief's bar, not a
  proof of determinism).

## Artifacts & pins

| Artifact | sha256 |
|---|---|
| oracle_zp_leg0.bin = oracle_zp_leg1.bin | c3120d8ef78f6a66a8fe09e5f1f6ba967f216e07a2fabbd9430a32daca051f16 |
| oracle_cmdline_leg0.bin = leg1 | 30cd829f2a88c80cb80bfef1d056c9d0d85683cc9e58dbd7b9e4c62ce03c43c3 |
| probe34_leg0.log (registers leg 0) | dfb6b4fafcefd6016d89c24cb736c6e625b6c0341e5bc6f5e04a3f1eb46a47b6 |
| probe34_leg1.log (registers leg 1) | f18005e8d0519da1c42a465af25a744b550780d3094a1efa04a5bda1edd0831c |

Reproduce end-to-end: `bash rung9/run_oracle.sh` (capture ×2 → differ →
RED legs → pins; exit 0).
