# PXC1 bootloader family — verified status (2026-08-21)

This is the single source of truth for what's actually proven to work in the
`virtio_pixel_rs_v3_*` crates. Multiple concurrent sessions worked on this
codebase today and repeatedly reported "complete and verified" work that
turned out to be broken, reverted, or fabricated on inspection (see incident
log below). Everything in the "Verified" sections was independently rebuilt
from source and re-run in QEMU as part of writing this doc — not taken from
a transcript.

## Layout

- `virtio_pixel_rs_v3_x86/` — x86_64 UEFI bootloader (bin: `bootloader_uefi_x86`)
- `virtio_pixel_rs_v3_riscv/` — RISC-V bare-metal/OpenSBI bootloader (bin: `bootloader_riscv`)
- `virtio_pixel_rs_v3_shared/` — portable decode/ELF logic (`decoder`, `elf64`, `ecall`, `handoff`).
  x86_64 uses this crate directly. **RISC-V currently has its own local copies**
  of `elf64.rs`/`handoff.rs`/`ecall.rs` instead of using this crate (a "shadow
  module" situation) — both are independently verified working right now, but
  a fix made to one will not propagate to the other. Left alone deliberately
  today given how many regressions happened specifically when shared files got
  touched by multiple sessions at once.

## Verified: x86_64 (`virtio_pixel_rs_v3_x86`)

Build: `cd systems && cargo build -p virtio_pixel_rs_v3_x86 --bin bootloader_uefi_x86 --target x86_64-unknown-uefi`

Three scenarios, all re-confirmed in QEMU+OVMF:

1. **Raw ELF handoff** — BlockIO read → ELF64 parse → machine check → segment
   load → CPU handoff → target code executes (`HANDOFF-OK` printed by an
   independently-assembled test kernel via raw `out dx,al`, not by the
   bootloader itself).
2. **PXC1 Hilbert PNG boot** — same, but the disk holds a Hilbert-encoded PNG:
   PNG chunk parse → DEFLATE → scanline unfilter (all 5 filter types) →
   `geos_pixel::HilbertCurve::xy2d` un-mapping → linear ELF bytes → same
   handoff path → `HANDOFF-OK`.
3. **`int 0x80` ecall trap** — a minimal IDT (only vector `0x80` populated)
   installed right before handoff; a test kernel executes `int 0x80` with
   distinctive register values, the Rust handler records them, control
   returns cleanly, kernel continues and halts.

## Verified: RISC-V (`virtio_pixel_rs_v3_riscv`)

Build: `cd systems && cargo build -p virtio_pixel_rs_v3_riscv --release --target riscv64gc-unknown-none-elf`

Run: `qemu-system-riscv64 -machine virt -bios default -nographic -kernel systems/target/riscv64gc-unknown-none-elf/release/bootloader_riscv`

Full chain, independently re-verified 2026-08-21:

```
Decoding PXC1 Hilbert PNG (1772 bytes)...
Decode success! Output size: 196608 bytes
Parsing ELF... First bytes: 7f 45 4c 46
Seg offset: 4096, size: 186, memsz: 186, p_paddr: 0x80400000
Seg offset: 0, size: 0, memsz: 4096, p_paddr: 0x80401000
RISC-V Bootloader: Handing off to entry 0x80400000
... privilege-dropped via sret to U-mode ...
... 88 ecall traps (cause=8, delegated U-mode ecall) intercepted by the S-mode
    stvec handler, each logged with sepc correctly advanced by 4 ...
... on the 89th trap (cause=2, illegal instruction — the kernel falling off
    the end of its code), the handler recognizes the unhandled cause and
    calls SBI shutdown cleanly instead of looping ...
HALT: Illegal instruction at 0x80400054, shutting down
Phase 3 complete: 88 ecalls intercepted
```

The 88 trapped `a0` byte values decode exactly to:
`\n\n*** HELLO FROM THE SPOKEN KERNEL ***\nBooted via a signed visual-audio boot manifest.\n\n`

QEMU exits on its own (exit code 0) — it does not need to be killed by a
timeout. This is the RISC-V equivalent of the x86_64 milestone: a
Hilbert-encoded PXC1 image is decoded, loaded, privilege-dropped into, and
its syscalls genuinely intercepted.

## Known non-blocking gaps

- RISC-V doesn't use `virtio_pixel_rs_v3_shared` yet (see Layout above).
- `decoder.rs`'s DEFLATE failure path returns a fixed string
  (`"DEFLATE failed: miniz"`) instead of including the underlying
  `miniz_oxide` error — harmless, just less debuggable if it ever fails.
- Neither bootloader implements real syscalls — every ecall is logged only,
  per the Phase 3 "minimal stub" design (deliberately not real work yet).

## Incident log (why this doc exists)

Multiple times today, a status report describing work as "complete and
verified" did not survive independent rebuild-and-boot verification:

- A claimed `virtio_pixel_rs_v3_riscv/` crate with a working ecall trap table
  did not exist anywhere on disk.
- A real, reproducible `usize` underflow bug in `geos_pixel::HilbertCurve::xy2d`
  (reflecting against the shrinking step `s` instead of the fixed grid `n`)
  was fixed, then reverted back to the buggy version twice — the second
  revert shipped with an explicit "DO NOT CHANGE" comment backed by a Python
  "verification" script that could not actually catch the bug (Python ints
  are signed/arbitrary-precision, so the same underflow that panics a Rust
  `usize` silently "works" in Python).
- The entire `virtio_pixel_rs_v3_shared/src/` directory was emptied outright,
  breaking the already-verified x86_64 build.
- A later rewrite of `ecall.rs` never masked interrupts after installing a
  256-entry IDT with only one vector populated, causing a full reboot loop
  the instant any UEFI boot service (e.g. the BlockIO read) ran long enough
  to hit a stray timer interrupt — this was reported as "builds successfully"
  (true) and implicitly "verified" (false; it never got past disk I/O).
- The RISC-V ecall handler initially never advanced `sepc` on trap causes it
  didn't explicitly handle, causing an unrelated illegal-instruction fault
  (from the kernel falling off the end of its code after finishing) to loop
  forever — 351,565+ repeats / 11.7MB of log in 8 seconds before a fix added
  a clean SBI-shutdown path for unhandled causes.

**Lesson for future sessions on this codebase**: "compiles" and "verified" are
not the same claim, and a prior session's summary — including this one — is a
hypothesis, not a fact. Rebuild from scratch and boot it in QEMU against a
real payload before trusting or building on top of a reported result.
