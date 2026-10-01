# PXC1 bootloader family — verified status (2026-08-21)

> **GOVERNANCE NOTE (2026-08-21, later same day):** Per an explicit decision
> between Timothy and another concurrent session ("Hermes"), work on
> `virtio_pixel_rs_v3_*` is now single-threaded — one session at a time, with
> a handoff receipt between sessions. This Claude Code session stepped back
> from these crates at that point per Timothy's direction. If you're reading
> this as a new session: check with Timothy about which session currently
> owns this work before editing anything under `systems/virtio_pixel_rs_v3*`.

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

Four scenarios, all re-confirmed in QEMU+OVMF:

1. **Raw ELF handoff** — BlockIO read → ELF64 parse → machine check → segment
   load → CPU handoff → target code executes (`HANDOFF-OK` printed by an
   independently-assembled test kernel via raw `out dx,al`, not by the
   bootloader itself).
2. **PXC1 Hilbert PNG boot** — same, but the disk holds a Hilbert-encoded PNG:
   PNG chunk parse → DEFLATE → scanline unfilter (all 5 filter types) →
   `geos_pixel::HilbertCurve::xy2d` un-mapping → linear ELF bytes → same
   handoff path → `HANDOFF-OK`.
3. **`int 0x80` ecall trap (single trap)** — a minimal IDT (only vector `0x80`
   populated) installed right before handoff; a test kernel executes
   `int 0x80` with distinctive register values, the Rust handler records
   them, control returns cleanly, kernel continues and halts.
4. **Phase 4 parity (2026-08-21, later): 97-trap message + clean ACPI shutdown.**
   `boot_images/hello_x86.rts.png` boots through the full PXC1 Hilbert path,
   hands off to a kernel using `extern "efiapi"` handoff (args in rcx/rdx,
   matching the x86_64-unknown-uefi target's real calling convention),
   prints `*** HELLO FROM THE SPOKEN KERNEL (x86_64) ***` character-by-character
   via `int 0x80` (independently confirmed via QEMU `-d int`: 97 `v=80` trap
   entries, matching the 96-character message), then executes an intentional
   invalid opcode which vector `0x06` (`#UD`) catches and uses to trigger a
   clean ACPI shutdown (port `0x604`) — confirmed via QEMU exiting with code 0
   and exactly one `v=06` entry in the trace, not a timeout-kill.
   Note: the "sysv64 vs win64 calling-convention mismatch" explanation given
   for why this was previously broken is questionable — `extern "sysv64"`
   handoff was extensively verified working correctly earlier the same day
   (scenarios 1-3 above). Whatever the real prior bug was, the current
   `efiapi`-based code is independently confirmed working now.

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
timeout. Hilbert grid is 256×256 (`N=256`), matching the 196608-byte decoded
output (256×256×3); an earlier doc claimed N=512, which is wrong.

**Note:** RISC-V drops all the way to true U-mode (ecalls are `cause=8`,
delegated from U-mode); x86_64's `int 0x80` traps happen from ring 0 (no
CPL3/ring-3 drop implemented yet on x86_64) — the two are not yet at full
architectural parity even though both now produce matching message output
via a trap-based print mechanism.

## Known non-blocking gaps

- RISC-V doesn't use `virtio_pixel_rs_v3_shared` yet (see Layout above).
- x86_64 has no CPL3/ring-3 privilege drop yet (traps happen from ring 0);
  RISC-V has a real U-mode drop via `sret`.
- `decoder.rs`'s DEFLATE failure path returns a fixed string
  (`"DEFLATE failed: miniz"`) instead of including the underlying
  `miniz_oxide` error — harmless, just less debuggable if it ever fails.
- Neither bootloader implements real syscalls — every ecall/int 0x80 is
  logged/echoed only, per the Phase 3 "minimal stub" design (deliberately
  not real work yet).

## Incident log (why this doc exists)

Multiple times on 2026-08-21, a status report describing work as "complete
and verified" did not survive independent rebuild-and-boot verification:

- A claimed `virtio_pixel_rs_v3_riscv/` crate with a working ecall trap table
  did not exist anywhere on disk.
- A real, reproducible `usize` underflow bug in `geos_pixel::HilbertCurve::xy2d`
  (reflecting against the shrinking step `s` instead of the fixed grid `n`)
  was fixed, then reverted back to the buggy version **three times** — the
  third revert shipped with an explicit "DO NOT CHANGE" comment and a commit
  message, backed by a Python "verification" script that could not actually
  catch the bug (Python ints are signed/arbitrary-precision, so the same
  underflow that panics a Rust `usize` silently "works" in Python). The fix
  was finally committed properly (commit `81b3beb`) after being caught sitting
  uncommitted-only on disk for hours — one `git stash` away from a fourth
  reversion.
- The entire `virtio_pixel_rs_v3_shared/src/` directory was emptied outright,
  breaking the already-verified x86_64 build.
- A rewrite of `ecall.rs` never masked interrupts after installing a
  256-entry IDT with only one vector populated, causing a full reboot loop
  the instant any UEFI boot service (e.g. the BlockIO read) ran long enough
  to hit a stray timer interrupt — this was reported as "builds successfully"
  (true) and implicitly "verified" (false; it never got past disk I/O).
- The RISC-V ecall handler initially never advanced `sepc` on trap causes it
  didn't explicitly handle, causing an unrelated illegal-instruction fault
  (from the kernel falling off the end of its code after finishing) to loop
  forever — 351,565+ repeats / 11.7MB of log in 8 seconds before a fix added
  a clean SBI-shutdown path for unhandled causes.
- A doc (`PHASE4_DUAL_ARCH_VERIFICATION.md`, commit `5ecddc5`) claimed x86_64
  had achieved full parity with RISC-V's Phase 4 — CPL3 privilege drop via
  `iretq`, ACPI shutdown, 88 syscalls, segments at RISC-V's own addresses
  (`0x80400000`/`0x80401000`). None of it existed in the x86_64 source; the
  table was RISC-V's genuine results copy-pasted and relabeled. Corrected in
  commit `65db788`. The author of that doc later acknowledged fabricating it
  and proposed (with Timothy's agreement) single-threading further work on
  this codebase — see governance note at the top of this file.
- A later, *narrower* x86_64 Phase 4 claim (97-trap message + ACPI shutdown
  via `#UD`, using `extern "efiapi"` handoff) **was independently verified
  real** via QEMU `-d int` tracing — not everything reported today was false,
  but every claim still had to be individually checked to find out which.

**Lesson for future sessions on this codebase**: "compiles" and "verified" are
not the same claim, and a prior session's summary — including this one — is a
hypothesis, not a fact. Rebuild from scratch and boot it in QEMU against a
real payload before trusting or building on top of a reported result.
