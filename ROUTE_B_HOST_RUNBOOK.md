# Route B — Host Runbook (GPU-gated steps)

Every step here needs a **real GPU adapter** (not llvmpipe) and, for Phase 1,
`qemu-system-riscv64` on the host. None of this runs in the compute-blocked
sandbox or the llvmpipe guest. Branch under test: `route-b-gpu-offload`
(shader pinned — do not edit `tools/SPATIAL_RV64I.wgsl` mid-run).

Pre-flight:

```bash
cd ~/projects/zion/projects/visual_audio
git checkout route-b-gpu-offload
python3 -c "import wgpu, wgpu.utils; a=wgpu.utils.get_default_device().adapter_info; print(a)"   # must NOT say llvmpipe/lavapipe
which qemu-system-riscv64
python3 -m pytest tools/test_virtio_blk_host.py tools/verify_virtio_offload.py -q   # 5 passed, no GPU needed
```

---

## Phase 1 — regression gate

**Goal:** prove the `mmio_write` virtio-branch edit changed nothing for a
non-virtio boot.

```bash
# 1a. GPU trace on the patched shader (non-virtio path: vq_ready stays 0)
python3 tools/boot_xv6_gpu_trace.py --out /tmp/p1/gpu_xv6.jsonl --max-steps 12000

# 1b. QEMU reference trace, same kernel, same entry
python3 tools/qemu_cpu_trace.py --kernel <xv6 kernel.img> --out /tmp/p1/qemu_xv6.jsonl --max-steps 12000

# 1c. register-for-register diff
python3 tools/diff_qemu_gpu_traces.py /tmp/p1/qemu_xv6.jsonl /tmp/p1/gpu_xv6.jsonl
```

**Pass:** diff reports 0 divergences across the full trace.
**Also:** `python3 tools/boot_xv6_gpu.py` reaches the `$` shell prompt.
**If it fails:** divergence in the shared `mmio_write` prologue, not the virtio
code — bisect the four `if (virtio_offset == …)` latches added in `716244d`.
**Watch:** trace buffer was cut 128MB→16MB (`bd172e0`); if the diff stops
early, the GPU trace is truncated — raise the trace allocation and re-run.

Record result in `ROUTE_B_OFFLOAD_ROADMAP.md` Phase 1 and flip it from
⚠️ PARTIAL to ✅ / ❌.

---

## Phase 2 — standalone virtio path (vq_ready = 0)

**Goal:** the in-shader `process_virtqueue_spatial()` works with the new
PFN→ring-address latching, and the addresses match a real Linux driver.

```bash
# boot Alpine GPU-only, virtio walked in-shader, to the first block read
python3 standalone_alpine_boot.py 2>&1 | tee /tmp/p2/standalone.log
```

Instrument (add a one-shot print in `mmio_write` 0x40 handler, or read the
state buffer after the 0x40 write via a debug hook):

- `vq_desc_low`  should equal the driver's `desc` (byte address, = PFN*4096)
- `vq_avail_low` should equal `desc + queue_num*16`
- `vq_used_low`  should equal `align_up(avail + 6 + queue_num*2, align)`

Compare against the guest kernel's `vring_init` result (from a QEMU boot of
the same image with `virtio_mmio.debug`, or kernel log).

**Pass:** ring addresses match; one real sector read returns correct bytes
into the guest buffer; used ring advances.
**Note:** before `716244d` nothing populated `vq_avail_low` / `vq_used_low`,
so this is first-run bring-up of the in-shader walker, not just regression.

---

## Phase 3 — offload path end-to-end (vq_ready = 2)

```bash
# host-serviced virtio-blk, same kernel + same disk image as Phase 2
python3 tools/boot_offload_alpine.py --disk /tmp/alpine_rootfs/alpine_disk.img \
        --max-steps 200000000 --slice 1000000 2>&1 | tee /tmp/p3/offload.log
```

**Pass criteria:**
1. no hang — the `halted==2 → service_queue → halted=0` loop resumes each time
   (`virtio offloads` counter climbs, `total_steps` keeps advancing)
2. same UART milestone as the Phase 2 standalone run
3. block data byte-identical to Phase 2: diff the mounted rootfs contents, or
   hash the first N sectors read, against the standalone run
4. reaches a mounted rootfs / shell over ttyS0

**If it hangs at the first notify:** `QueueConfig` read wrong addresses —
dump `state_arr[36,38,40,44,45]` and check against Phase 2's known-good values.
**If data is wrong but no hang:** descriptor-chain parsing in
`VirtioBlkHost.service_queue` — compare its chain walk to
`process_virtqueue_spatial` in the shader.

---

## Phase 4 — performance

Only after Phase 3 is byte-correct.

- `VirtioBlkHost` already uses one persistent FD (`_get_file`).
- `GpuRam.read_bytes` does one `read_mem_word` per 4 bytes → one GPU readback
  per word. For multi-KB block payloads add a bulk staging-buffer copy path
  (mirror `SpatialRV64ICore.write_mem_bytes`'s chunk-shader, in reverse).
- Measure notify→resume latency; target a full rootfs mount inside the
  standing boot-time budget.

---

## Phase 5 — interrupt path (only if a driver blocks instead of polling)

Add yield code 3: host sets `SEIP` in `csrs[CSR_MIP]`, model minimal PLIC
(pending/enable/claim/complete for IRQ 1), wire claim/complete reads in
`mmio_read` at `0x0c000000`. Skip entirely if the polling driver boots.

---

## Phase 6 — consolidation

- fold `tools/boot_offload_alpine.py` into the standard boot-script family
- document the `vq_ready` switch in `RV64_DEVELOPMENT_GUIDE.md`
- write `ROUTE_B_OFFLOAD_RECEIPT.md` with the Phase 1–3 logs and diff output

---

## Committed and verified without a GPU (branch `route-b-gpu-offload`)

| commit | contents |
|---|---|
| `716244d` | shader virtio-branch patch, `qemu_gpu_offload.py`, `verify_virtio_offload.py`, roadmap |
| `bd172e0` | Hermes guest toolchain fixes (ELF loader, trace buffer 128→16MB, binding type) |
| `5150929` | `tools/test_virtio_blk_host.py` — 4 mock-RAM ring-walk tests |
| `280a010` | GpuRam bounds/zero-length, `_disk_read` EOF pad, size from `memory.buffer.size` |
| `b504000` | `tools/boot_offload_alpine.py` Phase 3 driver |

`python3 -m pytest tools/test_virtio_blk_host.py tools/verify_virtio_offload.py -q` → 5 passed.
