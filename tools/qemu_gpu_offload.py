#!/usr/bin/env python3
"""
tools/qemu_gpu_offload.py
Route B Co-Simulation: Host-side Device Model and Transaction Protocol.
Implements Python-side UART and VirtIO-MMIO device models that interact 
directly with the GPU RAM buffer, bypassing heavy GDB CSR sync protocols.
"""

import sys
import os
import struct
import numpy as np
from typing import Dict, List, Tuple

class GpuRam:
    """Access over the Hilbert memory buffer using the core's native word helpers, optimized for word-aligned reads/writes."""
    def __init__(self, core, ram_base: int):
        self.core = core
        self.ram_base = ram_base
        # Size is derived from the core's memory configuration. SpatialRV64ICore
        # exposes it as memory.buffer.size; fall back to an explicit ram_size
        # attribute, then to 256MB for bare mocks.
        size = getattr(core, 'ram_size', None)
        if size is None:
            mem = getattr(core, 'memory', None)
            buf = getattr(mem, 'buffer', None)
            size = getattr(buf, 'size', None)
        self.size = size if size is not None else 256 * 1024 * 1024

    def _check_bounds(self, gpa: int, length: int = 1):
        """Raise IndexError if access crosses ram_base + size boundary."""
        if length < 0:
            raise IndexError(f"Length must be non-negative, got {length}")
        if gpa < self.ram_base:
            raise IndexError(f"Access below ram_base: {gpa:#x} < {self.ram_base:#x}")
        end = gpa + length
        limit = self.ram_base + self.size
        if end > limit:
            raise IndexError(
                f"Access beyond RAM: [{gpa:#x}, {end:#x}) crosses ram_base+size={limit:#x}"
            )

    def read_u8(self, gpa: int) -> int:
        offset = gpa - self.ram_base
        word_addr = (offset & ~3)
        word = self.core.read_mem_word(word_addr)
        shift = (offset & 3) * 8
        return (word >> shift) & 0xFF

    def read_u16(self, gpa: int) -> int:
        offset = gpa - self.ram_base
        # If 2-byte aligned, we can read a single word
        if (offset & 1) == 0:
            word_addr = (offset & ~3)
            word = self.core.read_mem_word(word_addr)
            shift = (offset & 3) * 8
            if shift <= 16:
                return (word >> shift) & 0xFFFF
        return self.read_u8(gpa) | (self.read_u8(gpa + 1) << 8)

    def read_u32(self, gpa: int) -> int:
        offset = gpa - self.ram_base
        if (offset & 3) == 0:
            return self.core.read_mem_word(offset)
        return self.read_u16(gpa) | (self.read_u16(gpa + 2) << 16)

    def read_u64(self, gpa: int) -> int:
        return self.read_u32(gpa) | (self.read_u32(gpa + 4) << 32)

    def write_u8(self, gpa: int, val: int):
        offset = gpa - self.ram_base
        word_addr = (offset & ~3)
        word = self.core.read_mem_word(word_addr)
        shift = (offset & 3) * 8
        mask = 0xFF << shift
        word = (word & ~mask) | ((val & 0xFF) << shift)
        self.core.write_mem_word(word_addr, word)

    def write_u16(self, gpa: int, val: int):
        offset = gpa - self.ram_base
        if (offset & 1) == 0:
            word_addr = (offset & ~3)
            word = self.core.read_mem_word(word_addr)
            shift = (offset & 3) * 8
            if shift <= 16:
                mask = 0xFFFF << shift
                word = (word & ~mask) | ((val & 0xFFFF) << shift)
                self.core.write_mem_word(word_addr, word)
                return
        self.write_u8(gpa, val & 0xFF)
        self.write_u8(gpa + 1, (val >> 8) & 0xFF)

    def write_u32(self, gpa: int, val: int):
        offset = gpa - self.ram_base
        if (offset & 3) == 0:
            self.core.write_mem_word(offset, val)
        else:
            self.write_u16(gpa, val & 0xFFFF)
            self.write_u16(gpa + 2, (val >> 16) & 0xFFFF)

    def write_u64(self, gpa: int, val: int):
        self.write_u32(gpa, val & 0xFFFFFFFF)
        self.write_u32(gpa + 4, (val >> 32) & 0xFFFFFFFF)

    def read_bytes(self, gpa: int, length: int) -> bytes:
        # Handle zero-length reads
        if length == 0:
            return b""
        # Bounds check
        self._check_bounds(gpa, length)
        # Optimized: read word-by-word where possible to minimize GPU readbacks
        offset = gpa - self.ram_base
        res = bytearray(length)
        i = 0
        while i < length:
            curr_gpa = gpa + i
            curr_offset = curr_gpa - self.ram_base
            # If we have at least 4 bytes left and are 4-byte aligned, read a whole word
            if (length - i) >= 4 and (curr_offset & 3) == 0:
                word = self.core.read_mem_word(curr_offset)
                res[i:i+4] = struct.pack("<I", word)
                i += 4
            else:
                res[i] = self.read_u8(curr_gpa)
                i += 1
        return bytes(res)

    def write_bytes(self, gpa: int, data: bytes):
        length = len(data)
        # Handle zero-length writes
        if length == 0:
            return
        # Bounds check
        self._check_bounds(gpa, length)
        i = 0
        while i < length:
            curr_gpa = gpa + i
            curr_offset = curr_gpa - self.ram_base
            if (length - i) >= 4 and (curr_offset & 3) == 0:
                word = struct.unpack("<I", data[i:i+4])[0]
                self.core.write_mem_word(curr_offset, word)
                i += 4
            else:
                self.write_u8(curr_gpa, data[i])
                i += 1


def align_up(addr: int, align: int) -> int:
    return (addr + align - 1) & ~(align - 1)


class QueueConfig:
    """Parses and recovers descriptor/available/used rings' addresses directly from the raw GPU state buffer array."""
    def __init__(self, state_arr: np.ndarray):
        # Mapping from CPUState struct offsets in SPATIAL_RV64I.wgsl
        self.num = int(state_arr[44]) if len(state_arr) > 44 else 256
        self.align = int(state_arr[45]) if len(state_arr) > 45 else 4096
        if self.align == 0:
            self.align = 4096
        
        # vq_desc_low is at index 36. The shader writes the absolute physical byte address here, not PFN.
        self.desc = int(state_arr[36]) if len(state_arr) > 36 else 0
        
        vq_avail_low = int(state_arr[38]) if len(state_arr) > 38 else 0
        vq_avail_high = int(state_arr[39]) if len(state_arr) > 39 else 0
        if vq_avail_low != 0:
            self.avail = vq_avail_low | (vq_avail_high << 32)
        else:
            self.avail = self.desc + self.num * 16 if self.desc != 0 else 0
            
        vq_used_low = int(state_arr[40]) if len(state_arr) > 40 else 0
        vq_used_high = int(state_arr[41]) if len(state_arr) > 41 else 0
        if vq_used_low != 0:
            self.used = vq_used_low | (vq_used_high << 32)
        else:
            self.used = align_up(self.avail + 6 + self.num * 2, self.align) if self.avail != 0 else 0


class VirtioBlkHost:
    """A legacy virtio-mmio split-ring walker that processes requests against a host disk file."""
    def __init__(self, disk_path: str = None):
        self.disk_path = disk_path
        self.last_avail_idx = 0
        self.disk_file = None
        
    def _get_file(self):
        if self.disk_file is None and self.disk_path and os.path.exists(self.disk_path):
            self.disk_file = open(self.disk_path, "r+b")
        return self.disk_file

    def close(self):
        if self.disk_file is not None:
            self.disk_file.close()
            self.disk_file = None

    def service_queue(self, ram: GpuRam, cfg: QueueConfig) -> int:
        if cfg.desc == 0:
            return 0
        avail_idx = ram.read_u16(cfg.avail + 2)
        processed = 0
        
        while self.last_avail_idx != avail_idx:
            ring_slot = self.last_avail_idx % cfg.num
            desc_idx = ram.read_u16(cfg.avail + 4 + ring_slot * 2)
            
            # Walk descriptor chain
            curr_desc = desc_idx
            chain = []
            while True:
                desc_addr = cfg.desc + curr_desc * 16
                addr = ram.read_u64(desc_addr)
                length = ram.read_u32(desc_addr + 8)
                flags = ram.read_u16(desc_addr + 12)
                next_desc = ram.read_u16(desc_addr + 14)
                
                chain.append((addr, length, flags))
                
                if not (flags & 0x01):  # VQ_DESC_F_NEXT
                    break
                curr_desc = next_desc
                
            # Process the descriptor request chain
            if len(chain) >= 2:
                hdr_addr, _, _ = chain[0]
                data_addr, data_len, _ = chain[1]
                status_addr = None
                
                if len(chain) >= 3:
                    status_addr, _, _ = chain[2]
                else:
                    status_addr = data_addr + data_len - 1
                
                req_type = ram.read_u32(hdr_addr)
                sector = ram.read_u64(hdr_addr + 8)
                
                if req_type == 1:  # VIRTIO_BLK_T_OUT (Write)
                    data = ram.read_bytes(data_addr, data_len)
                    self._disk_write(sector, data)
                else:              # VIRTIO_BLK_T_IN (Read)
                    data = self._disk_read(sector, data_len)
                    ram.write_bytes(data_addr, data)
                
                # Report status OK (0)
                if status_addr is not None:
                    ram.write_u8(status_addr, 0)
                    
                # Write to used ring
                used_idx = ram.read_u16(cfg.used + 2)
                used_ring_slot = used_idx % cfg.num
                used_elem_addr = cfg.used + 4 + used_ring_slot * 8
                
                ram.write_u32(used_elem_addr, desc_idx)
                ram.write_u32(used_elem_addr + 4, data_len)
                
                # Advance used index
                ram.write_u16(cfg.used + 2, (used_idx + 1) & 0xFFFF)
                
            self.last_avail_idx = (self.last_avail_idx + 1) & 0xFFFF
            processed += 1
            
        return processed

    def _disk_read(self, sector: int, size: int) -> bytes:
        f = self._get_file()
        if not f:
            return b"\x00" * size
        f.seek(sector * 512)
        data = f.read(size)
        if len(data) < size:            # past EOF — zero-pad to the requested length
            data += b"\x00" * (size - len(data))
        return data

    def _disk_write(self, sector: int, data: bytes):
        f = self._get_file()
        if not f:
            return
        f.seek(sector * 512)
        f.write(data)
        f.flush()


def run_with_offload(core, disk_path: str, ram_base: int = 0x80000000, slice_steps: int = 50000,
                     max_steps: int = 2_000_000_000) -> dict:
    """The co-simulation loop: steps the core, detects yields, processes requests, and resumes."""
    ram = GpuRam(core, ram_base)
    blk_host = VirtioBlkHost(disk_path)
    
    offloads = 0
    total_steps = 0
    
    # Configure CPUState to route QueueNotify to the host (vq_ready = 2)
    # vq_ready is at offset 43 in the state buffer
    core.queue.write_buffer(core.state_buffer, 43 * 4, np.array([2], dtype=np.uint32).tobytes())
    
    try:
        while True:
            # Read state directly from GPU state buffer array
            state_bytes = core.queue.read_buffer(core.state_buffer)
            state_arr = np.frombuffer(state_bytes, dtype=np.uint32)
            halted = int(state_arr[2])
            
            if halted == 1:
                print("[Offload] Core clean halt (halted=1) detected.")
                break
                
            if halted == 2:
                offloads += 1
                cfg = QueueConfig(state_arr)
                processed = blk_host.service_queue(ram, cfg)

                # Raise the virtio completion interrupt: latch SEIP (bit 9) in
                # mip so maybe_take_interrupt() delivers a cause-9 S-mode
                # external interrupt. The guest's PLIC claim reads source 1
                # (shader), the virtio_mmio IRQ handler drains the used ring,
                # and InterruptACK / PLIC-complete clear the bit. Only assert
                # when there was work to report.
                if processed > 0:
                    CSR_MIP = 0x344
                    core.write_csr(CSR_MIP, core.read_csr(CSR_MIP) | 0x200)

                # Clear yield code to resume (halted = 0 at offset 2 * 4 = 8)
                core.queue.write_buffer(core.state_buffer, 2 * 4, np.array([0], dtype=np.uint32).tobytes())
                
            uart_out = core.read_uart_output()
            if uart_out:
                sys.stdout.write(uart_out.decode('utf-8', errors='replace'))
                sys.stdout.flush()
                
            core.step(slice_steps)
            total_steps += slice_steps

            if total_steps > max_steps:
                print(f"[Offload] step budget reached ({max_steps})")
                break
    finally:
        blk_host.close()
            
    # Return final mapped dictionary using get_state()
    final_state = core.get_state()
    return {
        "final_state": final_state,
        "total_steps": total_steps,
        "offloads": offloads
    }
