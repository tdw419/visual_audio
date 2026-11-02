#!/usr/bin/env python3
"""
tools/test_virtio_blk_host.py
Pytest tests for VirtioBlkHost.service_queue in qemu_gpu_offload.py.
Uses FakeRam to simulate GPU memory without actual GPU access.
"""

import pytest
import struct
import tempfile
import os
import sys
import numpy as np

# Add the actual source directory to path to import the module being tested
# Source file is at: projects/zion/projects/visual_audio/tools/qemu_gpu_offload.py
_source_dir = '/home/jericho/projects/zion/projects/visual_audio/tools'
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from qemu_gpu_offload import VirtioBlkHost, QueueConfig

# VirtIO constants
VIRTIO_BLK_T_IN = 0
VIRTIO_BLK_T_OUT = 1
VQ_DESC_F_NEXT = 1
VQ_DESC_F_WRITE = 2


class FakeRam:
    """Pure-Python fake RAM implementing the GpuRam interface."""
    def __init__(self, size=1024*1024, ram_base=0x80000000):
        self.mem = bytearray(size)
        self.ram_base = ram_base
    
    def _offset(self, gpa: int) -> int:
        offset = gpa - self.ram_base
        if offset < 0 or offset >= len(self.mem):
            raise IndexError(f"Access out of bounds: GPA {hex(gpa)}, offset {offset}")
        return offset
    
    def read_u8(self, gpa: int) -> int:
        return self.mem[self._offset(gpa)]
    
    def read_u16(self, gpa: int) -> int:
        return struct.unpack_from('<H', self.mem, self._offset(gpa))[0]
    
    def read_u32(self, gpa: int) -> int:
        return struct.unpack_from('<I', self.mem, self._offset(gpa))[0]
    
    def read_u64(self, gpa: int) -> int:
        return struct.unpack_from('<Q', self.mem, self._offset(gpa))[0]
    
    def write_u8(self, gpa: int, val: int):
        self.mem[self._offset(gpa)] = val & 0xFF
    
    def write_u16(self, gpa: int, val: int):
        struct.pack_into('<H', self.mem, self._offset(gpa), val & 0xFFFF)
    
    def write_u32(self, gpa: int, val: int):
        struct.pack_into('<I', self.mem, self._offset(gpa), val & 0xFFFFFFFF)
    
    def write_u64(self, gpa: int, val: int):
        struct.pack_into('<Q', self.mem, self._offset(gpa), val & 0xFFFFFFFFFFFFFFFF)
    
    def write_bytes(self, gpa: int, data: bytes):
        offset = self._offset(gpa)
        self.mem[offset:offset+len(data)] = data
    
    def read_bytes(self, gpa: int, length: int) -> bytes:
        offset = self._offset(gpa)
        return bytes(self.mem[offset:offset+length])


@pytest.fixture
def temp_disk():
    """Create a temporary disk file with known pattern."""
    fd, path = tempfile.mkstemp(suffix='.img')
    with os.fdopen(fd, 'r+b') as f:
        # Write pattern: sector 0 = 'A'*512, sector 1 = 'B'*512
        f.write(b'A' * 512)
        f.write(b'B' * 512)
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def ram():
    """Create a FakeRam instance."""
    return FakeRam()


@pytest.fixture
def host(temp_disk):
    """Create VirtioBlkHost with temporary disk."""
    return VirtioBlkHost(disk_path=temp_disk)


def test_read_request(host, ram):
    """Test VIRTIO_BLK_T_IN: read sector 0 into memory."""
    ram_base = 0x80000000
    
    desc_addr = ram_base + 0x1000
    avail_addr = ram_base + 0x2000
    used_addr = ram_base + 0x3000
    q_num = 4
    
    hdr_addr = ram_base + 0x4000
    data_addr = ram_base + 0x5000
    status_addr = ram_base + 0x6000
    
    state = np.zeros(50, dtype=np.uint32)
    state[36] = desc_addr
    state[38] = avail_addr & 0xFFFFFFFF
    state[39] = (avail_addr >> 32) & 0xFFFFFFFF
    state[40] = used_addr & 0xFFFFFFFF
    state[41] = (used_addr >> 32) & 0xFFFFFFFF
    state[44] = q_num
    state[45] = 4096
    cfg = QueueConfig(state)
    
    ram.write_u64(desc_addr, hdr_addr)
    ram.write_u32(desc_addr + 8, 16)
    ram.write_u16(desc_addr + 12, VQ_DESC_F_NEXT)
    ram.write_u16(desc_addr + 14, 1)
    
    ram.write_u64(desc_addr + 16, data_addr)
    ram.write_u32(desc_addr + 24, 512)
    ram.write_u16(desc_addr + 28, VQ_DESC_F_NEXT | VQ_DESC_F_WRITE)
    ram.write_u16(desc_addr + 30, 2)
    
    ram.write_u64(desc_addr + 32, status_addr)
    ram.write_u32(desc_addr + 40, 1)
    ram.write_u16(desc_addr + 44, VQ_DESC_F_WRITE)
    ram.write_u16(desc_addr + 46, 0)
    
    ram.write_u32(hdr_addr, VIRTIO_BLK_T_IN)
    ram.write_u32(hdr_addr + 4, 0)
    ram.write_u64(hdr_addr + 8, 0)
    
    ram.write_u16(avail_addr, 0)
    ram.write_u16(avail_addr + 2, 1)
    ram.write_u16(avail_addr + 4, 0)
    
    ram.write_u16(used_addr, 0)
    ram.write_u16(used_addr + 2, 0)
    
    processed = host.service_queue(ram, cfg)
    
    assert processed == 1
    assert host.last_avail_idx == 1
    
    data = ram.read_bytes(data_addr, 512)
    assert data == b'A' * 512
    
    status = ram.read_u8(status_addr)
    assert status == 0
    
    used_idx = ram.read_u16(used_addr + 2)
    assert used_idx == 1
    
    used_elem_id = ram.read_u32(used_addr + 4)
    assert used_elem_id == 0
    
    used_elem_len = ram.read_u32(used_addr + 8)
    assert used_elem_len == 512
    
    print("PASS: test_read_request")


def test_write_request(host, ram):
    """Test VIRTIO_BLK_T_OUT: write data from memory to sector 1."""
    ram_base = 0x80000000
    
    desc_addr = ram_base + 0x1000
    avail_addr = ram_base + 0x2000
    used_addr = ram_base + 0x3000
    q_num = 4
    
    hdr_addr = ram_base + 0x4000
    data_addr = ram_base + 0x5000
    status_addr = ram_base + 0x6000
    
    state = np.zeros(50, dtype=np.uint32)
    state[36] = desc_addr
    state[38] = avail_addr & 0xFFFFFFFF
    state[39] = (avail_addr >> 32) & 0xFFFFFFFF
    state[40] = used_addr & 0xFFFFFFFF
    state[41] = (used_addr >> 32) & 0xFFFFFFFF
    state[44] = q_num
    state[45] = 4096
    cfg = QueueConfig(state)
    
    ram.write_u64(desc_addr, hdr_addr)
    ram.write_u32(desc_addr + 8, 16)
    ram.write_u16(desc_addr + 12, VQ_DESC_F_NEXT)
    ram.write_u16(desc_addr + 14, 1)
    
    ram.write_u64(desc_addr + 16, data_addr)
    ram.write_u32(desc_addr + 24, 512)
    ram.write_u16(desc_addr + 28, VQ_DESC_F_NEXT)
    ram.write_u16(desc_addr + 30, 2)
    
    ram.write_u64(desc_addr + 32, status_addr)
    ram.write_u32(desc_addr + 40, 1)
    ram.write_u16(desc_addr + 44, VQ_DESC_F_WRITE)
    ram.write_u16(desc_addr + 46, 0)
    
    ram.write_u32(hdr_addr, VIRTIO_BLK_T_OUT)
    ram.write_u32(hdr_addr + 4, 0)
    ram.write_u64(hdr_addr + 8, 1)
    
    test_data = b'HELLO' + b'X' * (512 - 5)
    ram.write_bytes(data_addr, test_data)
    
    ram.write_u16(avail_addr, 0)
    ram.write_u16(avail_addr + 2, 1)
    ram.write_u16(avail_addr + 4, 0)
    
    ram.write_u16(used_addr, 0)
    ram.write_u16(used_addr + 2, 0)
    
    processed = host.service_queue(ram, cfg)
    
    assert processed == 1
    assert host.last_avail_idx == 1
    
    with open(host.disk_path, 'r+b') as f:
        f.seek(1 * 512)
        file_data = f.read(512)
    assert file_data == test_data
    
    status = ram.read_u8(status_addr)
    assert status == 0
    
    used_idx = ram.read_u16(used_addr + 2)
    assert used_idx == 1
    
    used_elem_id = ram.read_u32(used_addr + 4)
    assert used_elem_id == 0
    
    print("PASS: test_write_request")


def test_two_requests_wrap(host, ram):
    """Test enqueueing 2 requests and draining both in one service_queue call."""
    ram_base = 0x80000000
    
    desc_addr = ram_base + 0x1000
    avail_addr = ram_base + 0x2000
    used_addr = ram_base + 0x3000
    q_num = 4
    
    h1, d1, s1 = ram_base + 0x4000, ram_base + 0x5000, ram_base + 0x6000
    h2, d2, s2 = ram_base + 0x7000, ram_base + 0x8000, ram_base + 0x9000
    
    state = np.zeros(50, dtype=np.uint32)
    state[36] = desc_addr
    state[38] = avail_addr & 0xFFFFFFFF
    state[39] = (avail_addr >> 32) & 0xFFFFFFFF
    state[40] = used_addr & 0xFFFFFFFF
    state[41] = (used_addr >> 32) & 0xFFFFFFFF
    state[44] = q_num
    state[45] = 4096
    cfg = QueueConfig(state)
    
    ram.write_u64(desc_addr, h1)
    ram.write_u32(desc_addr + 8, 16)
    ram.write_u16(desc_addr + 12, VQ_DESC_F_NEXT)
    ram.write_u16(desc_addr + 14, 1)
    
    ram.write_u64(desc_addr + 16, d1)
    ram.write_u32(desc_addr + 24, 512)
    ram.write_u16(desc_addr + 28, VQ_DESC_F_NEXT | VQ_DESC_F_WRITE)
    ram.write_u16(desc_addr + 30, 2)
    
    ram.write_u64(desc_addr + 32, s1)
    ram.write_u32(desc_addr + 40, 1)
    ram.write_u16(desc_addr + 44, VQ_DESC_F_WRITE)
    ram.write_u16(desc_addr + 46, 0)
    
    ram.write_u32(h1, VIRTIO_BLK_T_IN)
    ram.write_u32(h1 + 4, 0)
    ram.write_u64(h1 + 8, 0)
    
    ram.write_u64(desc_addr + 48, h2)
    ram.write_u32(desc_addr + 56, 16)
    ram.write_u16(desc_addr + 60, VQ_DESC_F_NEXT)
    ram.write_u16(desc_addr + 62, 4)
    
    ram.write_u64(desc_addr + 64, d2)
    ram.write_u32(desc_addr + 72, 512)
    ram.write_u16(desc_addr + 76, VQ_DESC_F_NEXT | VQ_DESC_F_WRITE)
    ram.write_u16(desc_addr + 78, 5)
    
    ram.write_u64(desc_addr + 80, s2)
    ram.write_u32(desc_addr + 88, 1)
    ram.write_u16(desc_addr + 92, VQ_DESC_F_WRITE)
    ram.write_u16(desc_addr + 94, 0)
    
    ram.write_u32(h2, VIRTIO_BLK_T_IN)
    ram.write_u32(h2 + 4, 0)
    ram.write_u64(h2 + 8, 1)
    
    ram.write_u16(avail_addr, 0)
    ram.write_u16(avail_addr + 2, 2)
    ram.write_u16(avail_addr + 4, 0)
    ram.write_u16(avail_addr + 6, 3)
    
    ram.write_u16(used_addr, 0)
    ram.write_u16(used_addr + 2, 0)
    
    processed = host.service_queue(ram, cfg)
    
    assert processed == 2
    assert host.last_avail_idx == 2
    
    used_idx = ram.read_u16(used_addr + 2)
    assert used_idx == 2
    
    used0_id = ram.read_u32(used_addr + 4)
    assert used0_id == 0
    
    used1_id = ram.read_u32(used_addr + 12)
    assert used1_id == 3
    
    data1 = ram.read_bytes(d1, 512)
    assert data1 == b'A' * 512
    
    data2 = ram.read_bytes(d2, 512)
    assert data2 == b'B' * 512
    
    print("PASS: test_two_requests_wrap")


def test_no_work(host, ram):
    """Test that service_queue returns 0 when avail.idx == last_avail_idx."""
    ram_base = 0x80000000
    
    desc_addr = ram_base + 0x1000
    avail_addr = ram_base + 0x2000
    used_addr = ram_base + 0x3000
    q_num = 4
    
    state = np.zeros(50, dtype=np.uint32)
    state[36] = desc_addr
    state[38] = avail_addr & 0xFFFFFFFF
    state[39] = (avail_addr >> 32) & 0xFFFFFFFF
    state[40] = used_addr & 0xFFFFFFFF
    state[41] = (used_addr >> 32) & 0xFFFFFFFF
    state[44] = q_num
    state[45] = 4096
    cfg = QueueConfig(state)
    
    ram.write_u16(avail_addr, 0)
    ram.write_u16(avail_addr + 2, 0)
    
    ram.write_u16(used_addr, 0)
    ram.write_u16(used_addr + 2, 0)
    
    processed = host.service_queue(ram, cfg)
    
    assert processed == 0
    assert host.last_avail_idx == 0
    
    used_idx = ram.read_u16(used_addr + 2)
    assert used_idx == 0
    
    print("PASS: test_no_work")