# Alpine 6.18 on the GPU RV64 emulator — status & resume points (2026-08-30)

## TL;DR — BOOTS TO A SHELL

A **fresh continuous boot** of Linux 6.18.35 on the GPU RV64 core reaches an
**interactive busybox `~ #` prompt**. Verified from clean:

```
python3 tools/fresh_boot_ckpt.py --batch 100000 --initrd .ckpt/bbird.gz \
    --max-steps 4000000000 --stop-at-uart "BUSYBOX SHELL RUNNING"
```
-> `[47.98] Run /init as init process` -> `BUSYBOX SHELL RUNNING ON THE GPU
RV64 EMULATOR` -> `Linux (none) 6.18.35-0-lts ... riscv64` -> `~ #`
(logs: `.work/SHELL_REACHED_clean_fresh_boot.log`,
`.work/SHELL_REACHED_via_resume.log`). ~497M emulated instructions, ~14 min
wall (the pre-decoded fast path is off — see the workaround below).

### What it took
| fix | what |
|---|---|
| `2579bde` | preserve `sstatus.SUM`/`MXR` across S-mode trap entry & `sret` -> fixes EFAULT-on-execve |
| `bc4e316` | translate `pc+2` for a page-straddling 32-bit instruction fetch -> fixes a U-mode SIGSEGV in the ELF/loader path |
| `DECODED_FASTPATH_DISABLED = true` (`SPATIAL_RV64I.wgsl`) | workaround for the `percpu:` deadlock at pc `0x808a4aa2` — an unpinned op divergence between `execute_decoded()` and `decode_and_execute()`. Costs ~3-5x throughput. TODO: pin the op and re-enable. |

### Misdiagnoses corrected this session
The "post-`workingset` stall" and the "`~0x8033b` tight loop" were **both
slowness, not hangs** — the X.509 kernel-cert RSA verify and crypto self-test
stretches run ~10-20x denser than average code with the fast path off, and a
peer `boot_xv6_gpu` job repeatedly had the shared GPU 50-100x throttled. A
no-UART timeout fired during those stretches and I killed runs right before
they broke through. On an uncontended GPU with enough patience they all
complete. The ONLY real fresh-boot bug was the `percpu:` deadlock.

## Verified this session

- **`2579bde` — sstatus.SUM/MXR wiped on every S-mode trap entry & `sret`.**
  `raise_trap()` (delegate path), the interrupt-delivery path and `do_sret()`
  did `mstatus & ~SSTATUS_MASK | (sie<<5) | (spp<<8)`, zeroing every SSTATUS bit
  they didn't rewrite — including **SUM (bit 18)**. The spec changes only
  SIE/SPIE/SPP on a trap; SUM/MXR are untouched. Effect: a demand page fault (or
  timer IRQ) inside a `copy_to_user`/`__clear_user` window during the first
  `execve` cleared SUM -> `do_page_fault` saw SUM=0 -> `no_context` -> uaccess
  extable fixup -> `load_elf_binary` returned **-EFAULT**. Fix: touch only
  `SIE(1)/SPIE(5)/SPP(8)` (`& ~0x122u`). Verified from `.ckpt/v618_preexec`:
  execve succeeds, U-mode runs, demand faults are serviced and retried.

- **`bc4e316` — page-straddling 32-bit instruction fetch.** `fetch()` translated
  only `pc`, then read the high halfword from `phys + 2`. When the instruction
  sits at page offset `0xFFE` its high halfword is in the *next virtual page*,
  which is not physically contiguous -> the top 16 bits came from unrelated RAM
  -> garbage immediate. Confirmed: a 4-byte `JAL` at VA `0x2ac3a6fffe` (opcode
  `0x6F`, low half `0x90ef`) fetched with a garbage high half -> jump to
  unmapped `0x2ac3b0903e` -> U-mode SIGSEGV -> "Attempted to kill init!".
  ld-musl PLT thunks land a `jalr`/`jal` at `0xFFE`, so dynamic binaries hit it
  readily. Fix: when `(phys & 0xFFF) == 0xFFE`, translate `pc+2` separately.

- **`1f04b2c` (earlier) — LR reservation not cleared on trap/interrupt.** Still
  in place; unblocked `percpu:` onward for the checkpoint path.

## Where userspace gets to (resume `.ckpt/v618_preexec.rv64ckpt`, current shader)

`tools/run_preexec_forward.py .ckpt/v618_preexec.rv64ckpt <maxsteps> <batch>`:

`Alpine Init 3.14.0-r0` -> module loads (busybox `finit_module`) -> one
**non-fatal** `riscv_cpufeature_patch_func` WARN (ext id 7680) -> `loop: module
loaded` -> `squashfs 4.0` -> `Loading boot drivers: ok.` -> `Mounting boot
media:` -> `virtio_blk virtio0: virtio: device refuses features: 0` (expected —
DTB has a virtio-mmio node, no `--offload` backend) -> **`nlplug-findfs` never
returns**. Guest is not wedged (probe shows userspace + syscalls). nlplug-findfs
reads `NETLINK_KOBJECT_UEVENT`; suspected uevent/netlink delivery gap (a kernel
worker not being scheduled — same timer/tick family as the jitterentropy and
vgaarb issues). Alpine's init would drop to `recovery_shell` (`/bin/busybox sh`)
on a *non-zero return*, but a hang never gets there.

## Open items

### 1. `percpu:` deadlock — worked around, real fix pending
With the pre-decoded fast path live, a fresh continuous boot deadlocks/Oopses in
`queued_spin_lock_slowpath` at `pc 0xffffffff808a4aa2` right after the `percpu:`
line (symptom varies with `--batch`: 5M wedges on the GPU hangcheck; 50k Oopses
with `stval` = `ffffffff01c6b7a0` = a valid `…81c6b7a0` minus bit 31 of the low
word; 200k deadlocks). `execute_decoded()` and `decode_and_execute()` diverge
for some op, and which path an instruction takes is host-dispatch-alignment
sensitive (`decoded_ops_epoch` is `var<private>`, reset per GPU dispatch, bumped
by the first `sfence.vma`/`satp` write). **Workaround in `SPATIAL_RV64I.wgsl`:
`DECODED_FASTPATH_DISABLED = true`** — routes everything through
`decode_and_execute`, ~3-5x slower but fresh boots then run clean to the shell.
TODO: pin the op (the shift / `*W` / AMO / LR-SC bodies were checked and match;
suspect the RVC decode in `rv64i_decode.py`, or a field-extraction / `aux`
mismatch for some other op) and re-enable the fast path. A GLM-4.7 pass on this
diff **fabricated** a finding — verify any claim against the real lines.

### 2. `nlplug-findfs` hang — blocks *full Alpine* userspace (not bbird)
Resuming `.ckpt/v618_preexec.rv64ckpt` reaches `Alpine Init 3.14.0-r0` ->
module loads -> `squashfs` -> `Loading boot drivers: ok.` -> `Mounting boot
media:` -> `virtio_blk virtio0: virtio: device refuses features: 0` (expected —
DTB virtio-mmio node, no `--offload` backend) -> **`nlplug-findfs` never
returns** (reads `NETLINK_KOBJECT_UEVENT`; suspected uevent/netlink delivery
gap — a kernel worker not scheduled, same timer/tick family as the
jitterentropy / vgaarb issues). The `.ckpt/bbird.gz` static-busybox path (used
for the shell above) has no musl/nlplug/netlink and sidesteps this entirely.
Paths for full Alpine: fix uevent delivery, or Route B `--offload` + a real
rootfs so `virtio_blk` negotiates before `nlplug` matters.

### 3. Speed
The fast-path workaround makes the boot ~14 min wall (~497M instr). Pinning
item 1 and re-enabling the fast path should cut that ~3-5x. Also: keep the GPU
uncontended — a peer `boot_xv6_gpu` job repeatedly throttled it 50-100x this
session and caused several wedge/stall misreads.

## Resume points (`.ckpt/`, gitignored)

| checkpoint | where | notes |
|---|---|---|
| `v618_preexec.rv64ckpt` | at `Run /init`, pre-execve | pre-session; resume reaches Alpine `Mounting boot media` on the current shader |
| `v618_zone.rv64ckpt` | before the `percpu:` spinlock | pre-session |
| `fresh_workingset_fpd.rv64ckpt` | at `workingset:` | this session, current shader, Alpine initrd; resume progresses fine |
| `fresh_pre_percpu_50k.rv64ckpt` / `fresh_pre_percpu_jit.rv64ckpt` | at `Ticket spinlock` | this session; earlier experimental shaders |
| `bbird.gz` | initramfs, not a checkpoint | static busybox `/init` -> `exec /bin/busybox sh` — **the shell path** |
| `bbird_pre8033b.rv64ckpt` | fresh bbird boot at `Freeing initrd memory` | this session; resume -> `~ #` shell (`.work/SHELL_REACHED_via_resume.log`) |

## Session tools (`tools/`)

`run_preexec_forward.py` (resume + stream UART, configurable batch/stall),
`fresh_boot_ckpt.py` (fresh boot with checkpoint-on-UART-marker + stop-on-Oops),
`trace_preexec_efault.py`, `trace_umode_segv.py` / `_segv2.py` (Python Sv39
walker + single-step ring), `probe_mountmedia_stall.py`,
`trace_percpu_oops.py`, `trace_qspin_deadlock.py`, `trace_ws_stall.py`,
`trace_8033b_loop.py`.
