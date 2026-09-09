import wgpu
import wgpu.utils
import numpy as np
import os
from pathlib import Path
from typing import Optional

# Hilbert LUT disk cache (keyed by side length N): building the full linear->spatial
# mapping is O(N^2) and takes seconds in pure Python, so we compute it once per N with
# vectorized numpy and reuse it across core instances / test runs.
_HILBERT_LUT_CACHE = Path(os.environ.get('XDG_CACHE_HOME', str(Path.home() / '.cache'))) / 'visual_audio'

def _build_hilbert_lut(n: int) -> np.ndarray:
    """Return lut[d] = y*N + x for every linear word d in a Hilbert-mapped N*N buffer.

    Vectorized mirror of hilbert_d2xy()/d2idx() from SPATIAL_RV64I.wgsl so the GPU can
    do O(1) lookups instead of the 12-iteration loop per memory access.
    """
    size = n * n
    d = np.arange(size, dtype=np.uint32)
    x = np.zeros(size, dtype=np.uint32)
    y = np.zeros(size, dtype=np.uint32)
    t = d.copy()
    s = 1
    while s < n:
        rx = (t // 2) & 1
        ry = (t ^ rx) & 1
        # where ry==0: if rx==1 reflect, then always swap x<->y
        reflect = (ry == 0) & (rx == 1)
        x_r = np.where(reflect, s - 1 - x, x)
        y_r = np.where(reflect, s - 1 - y, y)
        swap = ry == 0
        x_s = np.where(swap, y_r, x_r)
        y_s = np.where(swap, x_r, y_r)
        x = x_s + s * rx
        y = y_s + s * ry
        t = t // 4
        s *= 2
    return (y * n + x).astype(np.uint32)

def _get_hilbert_lut(n: int) -> np.ndarray:
    """Build or load from disk the Hilbert LUT for side length n."""
    _HILBERT_LUT_CACHE.mkdir(parents=True, exist_ok=True)
    cache_path = _HILBERT_LUT_CACHE / f'hilbert_lut_{n}.npy'
    if cache_path.exists():
        lut = np.load(cache_path)
        if lut.shape == (n * n,):
            return lut
    lut = _build_hilbert_lut(n)
    np.save(cache_path, lut)
    return lut

class MemoryRegion:
    """
    GPU-resident, Hilbert-ordered memory region for spatial computation.
    """
    def __init__(self, device: wgpu.GPUDevice, size_bytes: int):
        self.size_bytes = size_bytes
        # Ensure size is aligned to 4 bytes for u32 array
        aligned_size = (size_bytes + 3) & ~3
        self.buffer = device.create_buffer(
            size=aligned_size,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC
        )
        
    def write_data(self, queue: wgpu.GPUQueue, data: bytes, offset: int = 0):
        queue.write_buffer(self.buffer, offset, data)
        
    def read_data(self, queue: wgpu.GPUQueue, size: int, offset: int = 0) -> bytes:
        return queue.read_buffer(self.buffer, buffer_offset=offset, size=size)

class RegisterFile:
    """
    32 x 64-bit GPU memory representing RV64I registers.
    Each register is vec2<u32> (low, high).
    """
    def __init__(self, device: wgpu.GPUDevice):
        self.buffer = device.create_buffer(
            size=32 * 8,  # 64 bits per register
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC
        )

class SpatialRV64ICore:
    """
    GPU-native RV64I core without CPU-side instruction emulation.
    """
    def __init__(self, memory_size_bytes: int = 1024 * 1024, trace_file: Optional[str] = None):
        self.device = wgpu.utils.get_default_device()
        self.queue = self.device.queue

        self.memory = MemoryRegion(self.device, memory_size_bytes)
        self.registers = RegisterFile(self.device)

        # instr_len, last_d2idx_d, last_d2idx_result, _pad[2],
        # bb_total_insts, bb_ctl_insts, bb_fallback_insts, bb_threaded_insts,
        # bb_threading_enabled, tlb_hits, tlb_misses,
        # timer_interrupts_fired, interrupts_delivered,
        # sbi_ecall_console, sbi_ecall_time, sbi_ecall_unknown
        # virtio_status, vq_desc_low, vq_desc_high,
        # vq_avail_low, vq_avail_high, vq_used_low, vq_used_high,
        # vq_idx, vq_ready, vq_queue_num, vq_queue_align
        # Total: 46 u32 fields = 184 bytes
        self.state_buffer = self.device.create_buffer(
            size=184, usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC
        )

        # Flat CSR file, addressed directly by the 12-bit CSR index (array<u32, 4096>)
        self.csr_buffer = self.device.create_buffer(
            size=4096 * 8, usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC
        )

        # UART TX ring buffer: one byte per u32 slot (array<u32, 4096>)
        self.uart_capacity = 4096
        self.uart_buffer = self.device.create_buffer(
            size=self.uart_capacity * 4,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC
        )
        self._uart_consumed = 0

        # Direct-mapped Sv39 TLB (see SPATIAL_RV64I.wgsl binding 7): 256 entries of
        # {tag, ppn, perm, pad} = 16 bytes each. Invalidated GPU-side on satp writes and
        # sfence.vma; zeroed here so a reused core doesn't leak stale mappings across loads.
        self.tlb_entries = 256
        self.tlb_buffer = self.device.create_buffer(
            size=self.tlb_entries * 16,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC
        )

        # Hilbert LUT: hilbert_lut[d] = spatial index of linear word d, precomputed once
        # on the host (vectorized, disk-cached) and read-only on the GPU. Replaces the
        # per-access hilbert_d2xy() loop in the shader with an O(1) lookup.
        mem_len_words = self.memory.buffer.size // 4
        hilbert_n = int(np.sqrt(mem_len_words))
        self.hilbert_lut_np = _get_hilbert_lut(hilbert_n)
        self.hilbert_lut_buffer = self.device.create_buffer(
            size=mem_len_words * 4,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC
        )
        self.queue.write_buffer(self.hilbert_lut_buffer, 0, self.hilbert_lut_np.tobytes())

        # Pre-decoded instruction buffer (basic-block threading): decoded_ops[phys/2]
        # is a DecodedOp (8 u32s) for the instruction at physical byte address phys,
        # decoded ONCE on the host (see tools/rv64i_decode.py) so the shader executes
        # pre-decoded ops instead of re-extracting bitfields every step. Indexed by
        # halfword (2 bytes), so RVC 16-bit and standard 32-bit instructions both
        # resolve by phys/2. Filled lazily on load; upload happens in _sync_decoded_ops.
        n_halfwords = mem_len_words * 2
        self.decoded_ops_buffer = self.device.create_buffer(
            size=n_halfwords * 9 * 4,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC
        )
        # Lazily-decoded linear image copy + dirty flag: the memory buffer itself is
        # Hilbert-mapped, so the host decoder needs a linear view. We keep a flat u32
        # shadow of everything written via load_program/write_mem_* and decode from it.
        self._linear_shadow = np.zeros(mem_len_words, dtype=np.uint32)
        self._decoded_ops_dirty = False
        # Written byte ranges (start, end) that need decoding; only these are decoded,
        # so a boot image (~24MB of code) doesn't pay the full 64MB per-slot decode.
        self._dirty_ranges = []
        # Content hash of the ranges last decoded (for the decoded-ops disk cache).
        self._decoded_cache_key = None

        self.pipeline = None
        self.bind_group = None
        self._init_pipeline()

        # Optional trace file for diff_qemu_gpu_traces.py
        self.trace_file = trace_file
        self.trace_fd = None
        if trace_file:
            self.trace_fd = open(trace_file, 'w')

    def __del__(self):
        if self.trace_fd:
            self.trace_fd.close()

    def _trace_state(self, pc, regs):
        if not self.trace_fd:
            return

        import json
        entry = {
            'pc': int(pc),
            'regs': {f'x{i}': int(regs[i]) for i in range(32)},
        }
        self.trace_fd.write(json.dumps(entry) + '\n')
        self.trace_fd.flush()  # Ensure immediate write for debugging
        
    def _init_pipeline(self):
        """Load SPATIAL_RV64I.wgsl and initialize pipeline"""
        shader_path = Path(__file__).parent / 'SPATIAL_RV64I.wgsl'
        shader_code = shader_path.read_text()

        # Bake the Hilbert-mapping side length in as a compile-time constant instead of
        # having d2idx() recompute sqrt(f32(mem_len)) on every single memory access — see
        # SPATIAL_RV64I.wgsl's HILBERT_N_PLACEHOLDER comment for why this matters.
        mem_len_words = self.memory.buffer.size // 4
        hilbert_n = int(np.sqrt(mem_len_words))
        shader_code = shader_code.replace(
            'const HILBERT_N: u32 = 8192u; // HILBERT_N_PLACEHOLDER — replaced at load time, do not rely on this literal',
            f'const HILBERT_N: u32 = {hilbert_n}u;',
        )

        shader_module = self.device.create_shader_module(code=shader_code)
        
        bind_group_layout = self.device.create_bind_group_layout(entries=[
            {'binding': 0, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
            {'binding': 1, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
            {'binding': 2, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
            {'binding': 3, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
            {'binding': 4, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
            {'binding': 5, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'read-only-storage'}},
            {'binding': 6, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'read-only-storage'}},
            {'binding': 7, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
        ])

        self.bind_group = self.device.create_bind_group(
            layout=bind_group_layout,
            entries=[
                {'binding': 0, 'resource': {'buffer': self.memory.buffer, 'offset': 0, 'size': self.memory.buffer.size}},
                {'binding': 1, 'resource': {'buffer': self.registers.buffer, 'offset': 0, 'size': self.registers.buffer.size}},
                {'binding': 2, 'resource': {'buffer': self.state_buffer, 'offset': 0, 'size': self.state_buffer.size}},
                {'binding': 3, 'resource': {'buffer': self.csr_buffer, 'offset': 0, 'size': self.csr_buffer.size}},
                {'binding': 4, 'resource': {'buffer': self.uart_buffer, 'offset': 0, 'size': self.uart_buffer.size}},
                {'binding': 5, 'resource': {'buffer': self.hilbert_lut_buffer, 'offset': 0, 'size': self.hilbert_lut_buffer.size}},
                {'binding': 6, 'resource': {'buffer': self.decoded_ops_buffer, 'offset': 0, 'size': self.decoded_ops_buffer.size}},
                {'binding': 7, 'resource': {'buffer': self.tlb_buffer, 'offset': 0, 'size': self.tlb_buffer.size}},
            ]
        )
        
        pipeline_layout = self.device.create_pipeline_layout(bind_group_layouts=[bind_group_layout])
        self.pipeline = self.device.create_compute_pipeline(
            layout=pipeline_layout,
            compute={'module': shader_module, 'entry_point': 'main'},
        )
        
    def _d2xy(self, n: int, d: int):
        t = d
        x = 0
        y = 0
        s = 1
        while s < n:
            rx = (t // 2) & 1
            ry = (t ^ rx) & 1
            if ry == 0:
                if rx == 1:
                    x = s - 1 - x
                    y = s - 1 - y
                x, y = y, x
            x += s * rx
            y += s * ry
            t //= 4
            s *= 2
        return x, y
        
    def load_asm(self, source: str, entry_point: int = 0):
        """Assemble RV32I source and load it, preserving Hilbert mapping."""
        from rv32i_asm import assemble
        self.load_program(assemble(source), entry_point)

    def load_program(self, binary_data: bytes, entry_point: int = 0, ram_base: int = 0):
        """Load binary into memory and set PC, preserving Hilbert mapping.

        `ram_base` is the guest physical address that maps to word 0 of our memory buffer
        (word 0 of the Hilbert-mapped array corresponds to guest address ram_base). Bare-metal
        test programs use the default of 0; a real kernel image (e.g. one linked to run at
        0x80000000) should pass that as ram_base, with entry_point given as an absolute guest
        address >= ram_base.
        """
        # Convert to u32 array
        # Pad with 0 to make it multiple of 4
        padded_data = binary_data + b'\x00' * ((4 - len(binary_data) % 4) % 4)
        linear_arr = np.frombuffer(padded_data, dtype=np.uint32)

        # Keep the linear shadow in sync for the host-side pre-decoder.
        n_copy = min(len(linear_arr), self._linear_shadow.shape[0])
        self._linear_shadow[:n_copy] = linear_arr[:n_copy]
        self._mark_range_dirty(0, n_copy * 4)

        # Create full VRAM array
        mem_len = self.memory.buffer.size // 4
        spatial_arr = np.zeros(mem_len, dtype=np.uint32)

        # N = sqrt(mem_len)
        N = int(np.sqrt(mem_len))
        if N * N != mem_len:
            raise ValueError("Memory length must be a perfect square for Hilbert mapping")

        for i, val in enumerate(linear_arr):
            x, y = self._d2xy(N, i)
            idx = y * N + x
            spatial_arr[idx] = val

        self.memory.write_data(self.queue, spatial_arr.tobytes())

        # Reset state (RV64I CPUState struct):
        # [pc_low, pc_high, halted, steps_remaining, mode, trap_pending,
        #  reservation_valid, reservation_addr_low, reservation_addr_high,
        #  uart_tx_len, mtime_low, mtime_high, mtimecmp_low, mtimecmp_high,
        #  ram_base_low, ram_base_high,
        #  uart_rx_data_pending, uart_rx_byte, instr_len,
        #  last_d2idx_d, last_d2idx_result, _pad[2],
        #  bb_total_insts, bb_ctl_insts, bb_fallback_insts, bb_threaded_insts,
        #  bb_threading_enabled, tlb_hits, tlb_misses,
        #  timer_interrupts_fired, interrupts_delivered,
        #  sbi_ecall_console, sbi_ecall_time, sbi_ecall_unknown,
        #  virtio_status, vq_desc_low, vq_desc_high,
        #  vq_avail_low, vq_avail_high, vq_used_low, vq_used_high,
        #  vq_idx, vq_ready, vq_queue_num, vq_queue_align]
        state_data = np.array(
            [entry_point & 0xFFFFFFFF, entry_point >> 32,  # pc_low, pc_high
             0,  # halted = 0
             1_000_000,  # steps_remaining (default to 1M steps)
             3,  # mode = 3 (M-mode)
             0,  # trap_pending = 0
             0,  # reservation_valid = 0
             0, 0,  # reservation_addr
             0,  # uart_tx_len = 0
             0, 0,  # mtime = 0
             0xFFFFFFFF, 0xFFFFFFFF,  # mtimecmp = max (no timer interrupt)
             ram_base & 0xFFFFFFFF, ram_base >> 32,  # ram_base
             0,  # uart_rx_data_pending = 0
             0,  # uart_rx_byte = 0
             0,  # instr_len = 0
             0, 0,  # d2idx cache
             0, 0,  # padding
             0, 0, 0, 0,  # bb counters
             1,  # bb_threading_enabled = 1 (on by default; tests can turn off)
             0, 0,  # tlb_hits, tlb_misses
             0, 0,  # timer_interrupts_fired, interrupts_delivered
             0, 0, 0,  # sbi_ecall counters
             0,  # virtio_status
             0, 0,  # vq_desc_low/high
             0, 0, 0, 0,  # vq_avail_low/high, vq_used_low/high
             0,  # vq_idx
             0,  # vq_ready
             0,  # vq_queue_num
             0],  # vq_queue_align
            dtype=np.uint32
        ).tobytes()
        self.queue.write_buffer(self.state_buffer, 0, state_data)

        # Reset CSRs so state doesn't leak across program loads on a reused core
        self.queue.write_buffer(self.csr_buffer, 0, np.zeros(4096 * 2, dtype=np.uint32).tobytes())
        self.queue.write_buffer(self.tlb_buffer, 0, np.zeros(self.tlb_entries * 4, dtype=np.uint32).tobytes())
        self._uart_consumed = 0

        # Trace initial state
        self._trace_state(entry_point, np.zeros(32, dtype=np.uint32))
        
    def get_state(self) -> dict:
        state_bytes = self.queue.read_buffer(self.state_buffer)
        state_arr = np.frombuffer(state_bytes, dtype=np.uint32)
        
        regs_bytes = self.queue.read_buffer(self.registers.buffer)
        regs_arr = np.frombuffer(regs_bytes, dtype=np.uint32)
        
        return {
            'pc_low': state_arr[0],
            'pc_high': state_arr[1],
            'pc': int(state_arr[0]) | (int(state_arr[1]) << 32),
            'halted': state_arr[2],
            'steps_remaining': state_arr[3],
            'mode': state_arr[4],
            'trap_pending': state_arr[5],
            'reservation_valid': state_arr[6],
            'reservation_addr_low': state_arr[7],
            'reservation_addr_high': state_arr[8],
            'uart_tx_len': state_arr[9],
            'mtime_low': state_arr[10],
            'mtime_high': state_arr[11],
            'mtimecmp_low': state_arr[12],
            'mtimecmp_high': state_arr[13],
            'ram_base_low': state_arr[14],
            'ram_base_high': state_arr[15],
            'uart_rx_data_pending': state_arr[16],
            'uart_rx_byte': state_arr[17],
            'bb_cur_slot': int(state_arr[21]) if len(state_arr) > 21 else 0,
            'bb_active': int(state_arr[22]) if len(state_arr) > 22 else 0,
            'bb_total_insts': int(state_arr[23]) if len(state_arr) > 23 else 0,
            'bb_ctl_insts': int(state_arr[24]) if len(state_arr) > 24 else 0,
            'bb_fallback_insts': int(state_arr[25]) if len(state_arr) > 25 else 0,
            'bb_threaded_insts': int(state_arr[26]) if len(state_arr) > 26 else 0,
            'bb_threading_enabled': int(state_arr[27]) if len(state_arr) > 27 else 0,
            'tlb_hits': int(state_arr[28]) if len(state_arr) > 28 else 0,
            'tlb_misses': int(state_arr[29]) if len(state_arr) > 29 else 0,
            'timer_interrupts_fired': int(state_arr[30]) if len(state_arr) > 30 else 0,
            'interrupts_delivered': int(state_arr[31]) if len(state_arr) > 31 else 0,
            'sbi_ecall_console': int(state_arr[32]) if len(state_arr) > 32 else 0,
            'sbi_ecall_time': int(state_arr[33]) if len(state_arr) > 33 else 0,
            'sbi_ecall_unknown': int(state_arr[34]) if len(state_arr) > 34 else 0,
            'regs': regs_arr.reshape((32, 2)).tolist(),
        }

    def _mark_range_dirty(self, start_byte: int, end_byte: int):
        """Record a written byte range for incremental pre-decode."""
        end_byte = min(end_byte, self._linear_shadow.shape[0] * 4)
        if start_byte >= end_byte:
            return
        # Merge with existing overlapping/adjacent ranges to keep the list small.
        merged = []
        for (s, e) in self._dirty_ranges:
            if e >= start_byte and s <= end_byte:
                start_byte = min(start_byte, s)
                end_byte = max(end_byte, e)
            else:
                merged.append((s, e))
        merged.append((start_byte, end_byte))
        self._dirty_ranges = merged
        self._decoded_ops_dirty = True

    def _sync_decoded_ops(self):
        """Decode written byte ranges into DecodedOps and upload to the GPU buffer.

        Called lazily before step() when any memory write invalidated the cache.
        Only the ranges written since the last sync are decoded, so a boot image
        doesn't pay the full 64MB per-slot decode cost.
        """
        if not self._decoded_ops_dirty:
            return
        # Works whether the repo root or the tools/ dir itself is on sys.path
        # (tests use both conventions).
        try:
            from tools.rv64i_decode import decode_image
        except ModuleNotFoundError:
            from rv64i_decode import decode_image

        mem_len_words = self._linear_shadow.shape[0]
        n_halfwords = mem_len_words * 2

        # Disk cache: the boot image is static across runs, so decoding ~12M halfword
        # slots in Python (~10s) can be skipped on repeat boots. Key = RAM size + hash
        # of the written ranges.
        import hashlib
        h = hashlib.sha256()
        h.update(str(n_halfwords).encode())
        for (s, e) in self._dirty_ranges:
            h.update(s.to_bytes(8, 'little'))
            h.update(e.to_bytes(8, 'little'))
            h.update(self._linear_shadow[s >> 2:(e + 3) >> 2].tobytes())
        cache_key = h.hexdigest()
        cache_path = _HILBERT_LUT_CACHE / f'decoded_ops_{cache_key}.npy'
        if self._decoded_cache_key != cache_key and cache_path.exists():
            try:
                ops = np.load(cache_path)
                if ops.shape == (n_halfwords, 9):
                    self.queue.write_buffer(self.decoded_ops_buffer, 0, ops.astype(np.uint32).tobytes())
                    self._decoded_cache_key = cache_key
                    self._decoded_ops_dirty = False
                    self._dirty_ranges = []
                    self.queue.write_buffer(self.state_buffer, 22 * 4, np.array([0], dtype=np.uint32).tobytes())
                    return
            except Exception:
                pass  # corrupt cache — fall through to re-decode

        ops = np.full((n_halfwords, 9), 0xFFFFFFFF, dtype=np.uint32)
        for (start_byte, end_byte) in self._dirty_ranges:
            chunk = decode_image(self._linear_shadow, byte_offset=start_byte,
                                 byte_len=end_byte - start_byte)
            # chunk is indexed by GLOBAL slot (= byte/2), same as ops.
            start_slot = start_byte >> 1
            end_slot = (end_byte + 1) >> 1
            ops[start_slot:end_slot] = chunk[start_slot:end_slot]
        self.queue.write_buffer(self.decoded_ops_buffer, 0, ops.astype(np.uint32).tobytes())
        try:
            np.save(cache_path, ops)
        except Exception:
            pass  # cache write is best-effort
        self._decoded_cache_key = cache_key
        self._decoded_ops_dirty = False
        self._dirty_ranges = []
        # Invalidate cross-dispatch basic-block cache on memory modification
        self.queue.write_buffer(self.state_buffer, 22 * 4, np.array([0], dtype=np.uint32).tobytes())

    def step(self, steps: int = 1):
        """Execute `steps` instructions, batching large requests to avoid GPU timeouts.

        The WGSL kernel loops internally per dispatch (SPATIAL_RV64I.wgsl main()), so this
        only needs to write steps_remaining (offset 12) before each dispatch — every other
        CPUState field already lives in the GPU-resident state buffer and persists across
        dispatches untouched. Reading the full state back before *and* after every call (as
        a prior revision of this method did, to "preserve" fields that were never actually
        being clobbered) adds two ~500ms-1s syncs per call and cuts throughput by roughly an
        order of magnitude — verified by direct measurement, not assumed. Do not reintroduce
        that pattern; if you need to preserve/reset last_d2idx_d/last_d2idx_result, do it via
        a targeted partial write_buffer, not a full get_state()+rewrite.
        """
        MAX_STEPS_PER_DISPATCH = 100_000

        # Re-decode + upload if any memory write happened since the last step.
        self._sync_decoded_ops()

        remaining = steps
        while remaining > 0:
            batch = min(remaining, MAX_STEPS_PER_DISPATCH)

            self.queue.write_buffer(self.state_buffer, 12, np.array([batch], dtype=np.uint32).tobytes())

            encoder = self.device.create_command_encoder()
            compute_pass = encoder.begin_compute_pass()
            compute_pass.set_pipeline(self.pipeline)
            compute_pass.set_bind_group(0, self.bind_group)
            compute_pass.dispatch_workgroups(1)
            compute_pass.end()
            self.queue.submit([encoder.finish()])

            remaining -= batch

        if self.trace_fd:
            new_state = self.get_state()
            self._trace_state(new_state['pc'], new_state['regs'])

    def read_uart_output(self) -> bytes:
        """Drain bytes written to the UART TX MMIO register since the last call."""
        state = self.get_state()
        total = int(state['uart_tx_len'])
        new_count = total - self._uart_consumed
        if new_count <= 0:
            return b''
        if new_count > self.uart_capacity:
            # Backlog overran the ring buffer since the last drain; only the most
            # recent uart_capacity bytes are still recoverable.
            new_count = self.uart_capacity
            self._uart_consumed = total - self.uart_capacity

        # Bulk GPU read: fetch all new words at once instead of per-byte reads
        start_pos = (self._uart_consumed) % self.uart_capacity
        # Read in up to two chunks for wraparound handling
        chunk1_len = min(new_count, self.uart_capacity - start_pos)
        chunk2_len = new_count - chunk1_len

        data_bytes = bytearray()
        if chunk1_len > 0:
            chunk1 = self.queue.read_buffer(self.uart_buffer, buffer_offset=start_pos * 4, size=chunk1_len * 4)
            data_bytes.extend(chunk1)
        if chunk2_len > 0:
            chunk2 = self.queue.read_buffer(self.uart_buffer, buffer_offset=0, size=chunk2_len * 4)
            data_bytes.extend(chunk2)

        # Extract bytes from u32 words (little-endian, byte at low position)
        words = np.frombuffer(data_bytes, dtype=np.uint32)
        out = bytes([w & 0xFF for w in words])
        self._uart_consumed = total
        return out

    def write_uart_input(self, data: bytes):
        """Feed bytes into the UART RX FIFO. Non-blocking: each byte overwrites the previous one."""
        for byte in data:
            # Write uart_rx_data_pending=1, uart_rx_byte=byte at offsets 16 and 17 (u32 indices)
            self.queue.write_buffer(self.state_buffer, 16 * 4, np.array([1], dtype=np.uint32).tobytes())
            self.queue.write_buffer(self.state_buffer, 17 * 4, np.array([byte & 0xFF], dtype=np.uint32).tobytes())

    def write_mem_word(self, byte_addr: int, value: int):
        """Write a single word directly into (Hilbert-mapped) physical memory, e.g. to build page tables.
        byte_addr is buffer-relative (word 0 == guest ram_base), not a guest address."""
        mem_len = self.memory.buffer.size // 4
        N = int(np.sqrt(mem_len))
        x, y = self._d2xy(N, byte_addr // 4)
        idx = y * N + x
        self.queue.write_buffer(self.memory.buffer, idx * 4, np.array([value], dtype=np.uint32).tobytes())
        # Keep the linear shadow in sync so the pre-decoder sees the same bytes.
        self._linear_shadow[byte_addr // 4] = value & 0xFFFFFFFF
        self._mark_range_dirty(byte_addr, byte_addr + 4)

    def write_mem_bytes(self, byte_addr: int, data: bytes):
        """Write an arbitrary byte blob into (Hilbert-mapped) physical memory, e.g. a DTB.
        byte_addr is buffer-relative; must be 4-byte aligned. Pads the tail to a whole word."""
        assert byte_addr >= 0, f"byte_addr must be non-negative, got {byte_addr}"
        assert byte_addr % 4 == 0
        assert byte_addr < self.memory.buffer.size
        padded = data + b'\x00' * ((4 - len(data) % 4) % 4)
        words = np.frombuffer(padded, dtype=np.uint32)

        # Keep the linear shadow in sync (both the small and chunk paths below write
        # the same words to the Hilbert-mapped buffer).
        start_word = byte_addr // 4
        self._linear_shadow[start_word:start_word + len(words)] = words
        self._mark_range_dirty(byte_addr, byte_addr + len(words) * 4)

        # For small writes (<64KB), use the word-by-word approach (simpler, less overhead)
        if len(words) < 16384:  # 64KB
            for i, word in enumerate(words):
                self.write_mem_word(byte_addr + i * 4, int(word))
            return

        # Large writes: scatter linear words into their Hilbert cells via the SAME
        # precomputed LUT the shader reads memory back through (hilbert_lut_np), then
        # upload the whole buffer once. The previous per-chunk copy-shader
        # (inline d2xy, dest[hilbert_idx]=src[i]) corrupted large writes — sparse
        # word-level scramble that left ~1/4 of a 20MB kernel image with zeroed /
        # neighbour-shifted words, so Linux never got past its head.S BSS clear.
        # Readback+scatter+writeback of 64MB costs a few seconds; a boot does this
        # ~3 times (kernel/initrd/dtb) and gets a bit-correct image.
        start_word = byte_addr // 4
        sidx = self.hilbert_lut_np[start_word:start_word + len(words)]
        buf = np.frombuffer(
            self.memory.read_data(self.queue, self.memory.buffer.size),
            dtype=np.uint32,
        ).copy()
        buf[sidx] = words
        self.memory.write_data(self.queue, buf.tobytes())
        return

        # --- dead: old chunked copy-shader path (kept for reference) ---
        mem_len = self.memory.buffer.size // 4
        N = int(np.sqrt(mem_len))
        num_words = len(words)
        BASE_OFFSET = byte_addr // 4

        # Write raw linear data to staging buffer
        staging_buffer = self.device.create_buffer(
            size=len(words) * 4,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST
        )
        self.queue.write_buffer(staging_buffer, 0, words.tobytes())

        # Dispatch in chunks to respect 65535 workgroup limit
        WORKGROUP_SIZE = 64
        WORDS_PER_DISPATCH = 65535 * WORKGROUP_SIZE  # ~4MB per dispatch

        for dispatch_offset in range(0, num_words, WORDS_PER_DISPATCH):
            dispatch_words = min(WORDS_PER_DISPATCH, num_words - dispatch_offset)
            workgroups = (dispatch_words + WORKGROUP_SIZE - 1) // WORKGROUP_SIZE
            chunk_offset = BASE_OFFSET + dispatch_offset

            chunk_shader = self.device.create_shader_module(code=f'''
@group(0) @binding(0) var<storage, read_write> dest: array<u32>;
@group(0) @binding(1) var<storage, read> src: array<u32>;
const N: u32 = {N}u;
const OFFSET: u32 = {chunk_offset}u;

fn d2xy(n: u32, d: u32) -> vec2<u32> {{
    var t = d;
    var x: u32 = 0u;
    var y: u32 = 0u;
    var s: u32 = 1u;
    while (s < n) {{
        let rx = (t / 2u) & 1u;
        let ry = (t ^ rx) & 1u;
        if (ry == 0u) {{
            if (rx == 1u) {{
                x = s - 1u - x;
                y = s - 1u - y;
            }}
            let tmp = x;
            x = y;
            y = tmp;
        }}
        x = x + s * rx;
        y = y + s * ry;
        t = t / 4u;
        s = s * 2u;
    }}
    return vec2<u32>(x, y);
}}

@compute @workgroup_size({WORKGROUP_SIZE})
fn main(@builtin(global_invocation_id) global_id: vec3<u32>) {{
    let i = global_id.x;
    if (i >= arrayLength(&src)) {{ return; }}

    let linear_idx = OFFSET + i;
    let xy = d2xy(N, linear_idx);
    let hilbert_idx = xy.y * N + xy.x;
    dest[hilbert_idx] = src[i];
}}
''')

            chunk_pipeline = self.device.create_compute_pipeline(
                layout=self.device.create_pipeline_layout(bind_group_layouts=[
                    self.device.create_bind_group_layout(entries=[
                        {'binding': 0, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
                        {'binding': 1, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'read-only-storage'}},
                    ])
                ]),
                compute={'module': chunk_shader, 'entry_point': 'main'},
            )

            chunk_bind_group = self.device.create_bind_group(
                layout=chunk_pipeline.get_bind_group_layout(0),
                entries=[
                    {'binding': 0, 'resource': {'buffer': self.memory.buffer, 'offset': 0, 'size': self.memory.buffer.size}},
                    {'binding': 1, 'resource': {'buffer': staging_buffer, 'offset': dispatch_offset * 4, 'size': dispatch_words * 4}},
                ]
            )

            encoder = self.device.create_command_encoder()
            compute_pass = encoder.begin_compute_pass()
            compute_pass.set_pipeline(chunk_pipeline)
            compute_pass.set_bind_group(0, chunk_bind_group)
            compute_pass.dispatch_workgroups(workgroups)
            compute_pass.end()
            self.queue.submit([encoder.finish()])

    def write_register(self, index: int, value: int):
        """Write a GPR directly (e.g. a0/a1 boot arguments before the first step())."""
        # For 64-bit registers, write low word at index*8 and high word at index*8+4
        self.queue.write_buffer(self.registers.buffer, index * 8, np.array([value & 0xFFFFFFFF], dtype=np.uint32).tobytes())
        self.queue.write_buffer(self.registers.buffer, index * 8 + 4, np.array([(value >> 32) & 0xFFFFFFFF], dtype=np.uint32).tobytes())

    def set_bb_threading(self, enabled: bool):
        """Enable/disable basic-block threading (host-side toggle at state u32 index 27)."""
        self.queue.write_buffer(self.state_buffer, 27 * 4, np.array([1 if enabled else 0], dtype=np.uint32).tobytes())

    def read_mem_word(self, byte_addr: int) -> int:
        """Read a single word directly from (Hilbert-mapped) physical memory."""
        mem_len = self.memory.buffer.size // 4
        N = int(np.sqrt(mem_len))
        x, y = self._d2xy(N, byte_addr // 4)
        idx = y * N + x
        data = self.queue.read_buffer(self.memory.buffer, buffer_offset=idx * 4, size=4)
        return int(np.frombuffer(data, dtype=np.uint32)[0])

    def read_csr(self, addr: int) -> int:
        """Read a CSR directly from the flat CSR file (bypasses csrrX instructions)."""
        csr_bytes = self.queue.read_buffer(self.csr_buffer, buffer_offset=addr * 8, size=8)
        low, high = np.frombuffer(csr_bytes, dtype=np.uint32)
        return int(np.uint64((int(high) << 32) | int(low)))

    def write_csr(self, addr: int, value: int):
        """Write a CSR directly into the flat CSR file (e.g. to install a trap vector before running)."""
        low = value & 0xFFFFFFFF
        high = (value >> 32) & 0xFFFFFFFF
        self.queue.write_buffer(self.csr_buffer, addr * 8, np.array([low, high], dtype=np.uint32).tobytes())

    def set_mode(self, mode: int):
        """Force the privilege mode directly (test/debug helper — real code should reach a
        given mode via mret/sret/traps, not this)."""
        self.queue.write_buffer(self.state_buffer, 4 * 4, np.array([mode], dtype=np.uint32).tobytes())

    def set_ram_base(self, base_addr: int):
        """Set the base physical address that maps to buffer word 0.
        All physical addresses accessed by the guest are offset by this value."""
        # ram_base_low is at offset 56 (14 * 4)
        # ram_base_high is at offset 60 (15 * 4)
        base_low = base_addr & 0xFFFFFFFF
        base_high = (base_addr >> 32) & 0xFFFFFFFF
        self.queue.write_buffer(self.state_buffer, 56, np.array([base_low], dtype=np.uint32).tobytes())
        self.queue.write_buffer(self.state_buffer, 60, np.array([base_high], dtype=np.uint32).tobytes())

    def run_until_halt(self, max_cycles: int = 100_000, chunk_size: int = 256) -> dict:
        """
        Dispatch batched compute passes (each running up to `chunk_size`
        instructions inside the shader's inner loop) until the CPU halts or
        max_cycles is exhausted. Returns the final state; raises TimeoutError
        if the program never halts within max_cycles.

        Legacy SBI ecalls (console putchar, set timer) are serviced natively inside
        the GPU shader itself (see SPATIAL_RV64I.wgsl's ecall handling) and never halt
        execution, so they need no special handling here.
        """
        cycles_run = 0
        while cycles_run < max_cycles:
            n = min(chunk_size, max_cycles - cycles_run)
            self.step(steps=n)
            cycles_run += n

            state = self.get_state()
            if state['halted']:
                return state

        raise TimeoutError(f"Program did not halt within {max_cycles} cycles")

    def run_program(self, source: str, entry_point: int = 0,
                     max_cycles: int = 100_000, chunk_size: int = 256) -> dict:
        """Assemble, load, and run RV64I source to completion. Returns final state."""
        self.load_asm(source, entry_point)
        return self.run_until_halt(max_cycles=max_cycles, chunk_size=chunk_size)

if __name__ == "__main__":
    print("Testing SpatialRV64ICore initialization...")
    core = SpatialRV64ICore(1024)
    print("✓ Pipeline initialized successfully")