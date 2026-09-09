# Debugging the GPU RV64 emulator: checkpoints + a QEMU oracle

How to find where `tools/SPATIAL_RV64I.wgsl` (via `SpatialRV64ICore`) diverges
from a real RISC-V machine during a long Linux boot, without re-running the
whole ~10-minute boot for every hypothesis.

Two tools do the heavy lifting:

1. **`tools/rv64i_checkpoint.py`** — snapshot/restore full emulator state so you
   resume from an interesting point in seconds.
2. **`qemu-system-riscv64`** — a reference ("oracle") that tells you what
   *should* happen. QEMU never touches the GPU; it runs the same kernel image
   by itself so you can diff behaviour.

This is the same method that found the `write_mem_bytes` large-write corruption
(commit `76e102b`) and is being used on the Alpine 6.18 `percpu:` stall.

---

## 1. Checkpoints

`SpatialRV64ICore` state lives in GPU buffers (Hilbert-mapped 64 MB RAM, GPRs,
CSR file, CPUState, UART ring). The checkpoint tool reads it all back, stores a
**de-Hilbert-mapped linear** copy, and can rebuild a fresh core from it.

Captured: linear guest memory, 32 GPRs, the full 4096-entry CSR file, CPUState
(pc/mode/halted/mtime/mtimecmp/ram_base/uart_tx_len…), and the UART
consumed-byte offset so `read_uart_output()` resumes correctly.

Not captured (regenerated on load): the TLB (a cache, invalidated on load) and
the basic-block `decoded_ops` buffer (re-derived from memory).

### Library API

```python
from rv64i_checkpoint import save_checkpoint, load_checkpoint

save_checkpoint(core, "boot_percpu.rv64ckpt")     # ~14 MB compressed
core2 = load_checkpoint("boot_percpu.rv64ckpt")   # fresh core, ready to .step()
```

### Save checkpoints as the boot passes UART milestones

```python
core = SpatialRV64ICore(RAM_SIZE)
load_opensbi_kernel_dtb(core)          # your boot loader
core.write_register(10, 0); core.write_register(11, dtb_addr)

MARKS = [b"Zone ranges", b"Ticket spinlock", b"percpu:", b"Kernel command line"]
saved = set(); u = bytearray(); steps = 0; idle = 0; last = 0
while steps < 60_000_000:
    core.step(steps=500_000); steps += 500_000
    b = core.read_uart_output()
    if b: u += b; sys.stdout.write(b.decode("latin-1")); sys.stdout.flush()
    for m in MARKS:
        if m in bytes(u) and m not in saved:
            saved.add(m); save_checkpoint(core, f"ck_{m.decode().split()[0]}.rv64ckpt")
    if len(u) == last: idle += 1
    else: idle = 0; last = len(u)
    if idle >= 20:                     # ~10M steps with no new UART = stalled
        print("STALL at pc=0x%x" % core.get_state()["pc"]); break
```

**Pick a marker that prints *before* the divergence.** A marker that prints too
late captures an already-broken state — e.g. `percpu:` is the last line before
the 6.18 stall, so a checkpoint taken there is already stuck. Use the line
before it (`Ticket spinlock`).

### CLI

```bash
python3 tools/rv64i_checkpoint.py save --program alpine \
    --stop-on-uart "Kernel command line" -o cmdline.rv64ckpt
python3 tools/rv64i_checkpoint.py resume cmdline.rv64ckpt --steps 5000000
```

Resume steps in ~1M chunks with a `get_state()` sync between them — large
`step()` right after a fresh load can hang under concurrent GPU load.

---

## 2. The QEMU oracle

Run the **exact same** kernel image + firmware in QEMU by itself.

```bash
# Reliable: QEMU's own OpenSBI (fw_dynamic). Boots a distro Image to a shell.
qemu-system-riscv64 -nographic -machine virt -m 256M \
  -kernel boot_images/alpine_Image -initrd boot_images/alpine_initrd \
  -append "console=ttyS0" -no-reboot
```

`-bios /path/to/fw_jump.bin -kernel Image` is **fragile** (fixed FDT/next-addr in
the Debian fw_jump) — only use it to match the GPU's OpenSBI exactly, and expect
to fight address alignment.

What QEMU answers:

- **Are the inputs good?** If QEMU boots the image to a shell and the GPU
  doesn't, the bug is in the emulator, not the kernel/initrd/DTB. (This is how
  we learned `alpine_riscv64.lnx.bin` was broken — QEMU couldn't boot it
  either. See `ROUTE_B_BOOT_IMAGE_FINDING.md`.)
- **What is the correct instruction stream at address X?**
  `-d in_asm` prints each translation block's disassembly once — small, and the
  instruction boundaries are *correct* (unlike `objdump -D -b binary` on a raw
  Image, which mis-aligns after every RVC instruction).
- **What are the correct register values at address X?** `-d cpu` dumps the full
  register block per translation block.

### Disk hazard

`-d cpu`, `-d exec`, `-d exec,nochain` produce **gigabytes per minute** and will
fill `/` (37 GB, usually <5 GB free). Always either:

- scope to an address range: `-dfilter 0xffffffff808a4380..0xffffffff808a4c20`
- time-box hard and watch `df`:

```bash
nohup qemu-system-riscv64 ... -d cpu,in_asm -D /tmp/scratch/q.log &
QP=$!; for i in $(seq 30); do sleep 2
  [ "$(df --output=avail / | tail -1)" -lt 2000000 ] && { kill $QP; break; }
  grep -qa "Run /init" /tmp/scratch/q_out.txt && { kill $QP; break; }
done; kill $QP 2>/dev/null
```

Delete the log the moment you've grepped what you need.

---

## 3. The bisection workflow

1. **Boot once, checkpoint at milestones** (§1). Note where UART stops.

2. **Characterise the stall.** From the nearest checkpoint, dump PC + trap CSRs
   and single-step ~60 instructions:

   ```python
   core = load_checkpoint("ck_percpu.rv64ckpt")
   g = core.read_csr
   print("pc=0x%x mcause=0x%x mepc=0x%x scause=0x%x sepc=0x%x stval=0x%x"
         % (core.get_state()["pc"], g(0x342), g(0x341), g(0x142), g(0x141), g(0x143)))
   for _ in range(60):
       st = core.get_state(); print("0x%016x" % st["pc"]); core.step(1)
   ```

   A tight repeating set of PCs = a spin loop. A single PC with a fault CSR
   (`scause`=13 load fault, 12 instr fault, 2 illegal) = a trap the emulator
   can't make progress past.

3. **Cross-check the stuck PC against QEMU.** Grep QEMU's exec trace for the
   virtual address:

   ```bash
   grep -ac "808a49f6\|808a4aa2" /tmp/scratch/q_exec.log
   ```

   - **QEMU executes it too** → it's real code; the emulator's loop
     *condition/counter* is wrong → some memory or register it reads is
     corrupt (→ step 5).
   - **QEMU never executes it** (0 hits over tens of millions of TBs) → the
     emulator's *control flow* is bogus: a wrong branch/jump target, a wrong
     trap vector, or a wrong `sret`/`mret` return. (This is the 6.18 case.)

4. **Bisect to the divergence step.** From a checkpoint *before* the stall, step
   in chunks until PC first enters the bad region:

   ```python
   core = load_checkpoint("ck_ticket.rv64ckpt"); step = 0
   while step < 600_000:
       core.step(20_000); step += 20_000
       if BAD_LO <= core.get_state()["pc"] <= BAD_HI:
           print("entered bad region by step", step); break
   ```

5. **Single-step the last chunk.** Reload, step to `(entered_step − chunk − 300)`,
   then `step(1)` in a loop recording PCs. Catch the transition from a valid PC
   into the bad region and dump full GPR + CSR state at that instant:

   ```python
   hist = []
   for i in range(25_000):
       st = core.get_state(); pc = st["pc"]; hist.append(pc)
       if BAD_LO <= pc <= BAD_HI:
           print("last 24 PCs:", [hex(p) for p in hist[-25:]])
           # dump regs + scause/sepc/stvec here
           break
       core.step(1)
   ```

   The buggy instruction is the last valid PC before entry — either the
   branch/jump whose target is miscomputed, or (one or two back) the
   instruction that clobbered a register used as that target.

6. **Compare that instruction's inputs/outputs to QEMU.** Get QEMU's `-d cpu`
   dump for the same VA (§2, filtered) and diff the register values. Now you
   know which field the emulator computes wrong.

7. **Fix the WGSL, re-verify.** After any `SPATIAL_RV64I.wgsl` change:
   - `python3 tools/test_route_b_gpu_synthetic.py` (+ `--standalone`)
   - `python3 tools/_p1_regression_probe.py` — the state hashes at 50k/150k/…
     must be unchanged for anything outside the edited path (a DTB change *is*
     expected to shift them; do a pre/post-shader-edit comparison with the same
     DTB to isolate).
   - re-run from the last good checkpoint to confirm the stall is gone.

---

## Worked example: the `write_mem_bytes` bug (commit `76e102b`)

1. Alpine 6.12 boot: OpenSBI banner, then silence; PC looping in firmware.
2. Single-stepped the GPU across the OpenSBI→kernel handoff: fetched
   instruction at `0x802010f2` read as `0x00000000` — memory was zero where
   code should be.
3. QEMU `-d in_asm` on the same kernel: `0x802010f2: 013e1717 auipc a4,…` — a
   valid instruction. So the GPU had *wrong bytes*, not a decode bug.
4. Bulk-read GPU RAM, `numpy`-diff against the kernel file: sparse word-level
   corruption near `0x802010f0` in the 20 MB write, clean at 4 KB boundaries →
   the large-write path.
5. `_d2xy` vs `hilbert_lut_np` agreed → the Hilbert *mapping* was fine, so the
   bug was `write_mem_bytes`'s chunked copy-shader specifically. Replaced it
   with a `hilbert_lut_np` scatter → Linux booted through full kernel init.

---

## Gotchas

- **Checkpoint before the divergence**, not at the last UART line.
- **`objdump -D -b binary` boundaries are unreliable** after RVC — use QEMU
  `-d in_asm`.
- **`-d cpu`/`-d exec` fill the disk** — `-dfilter` + time-box + `df` watch +
  delete immediately.
- **`~/.cache/visual_audio` grows ~1.2 GB per distinct boot config**
  (`decoded_ops_*.npy`). `rm -f ~/.cache/visual_audio/decoded_ops_*.npy` when
  `/home` gets tight; keep `hilbert_lut_*.npy`.
- **Resume stepping in ~1M chunks** with a `get_state()` between them.
- Keep scratch (traces, checkpoints, extracted kernels) in a scratch dir on a
  filesystem with space, not next to the repo.
