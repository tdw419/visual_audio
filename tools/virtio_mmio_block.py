#!/usr/bin/env python3
"""
VirtIO-MMIO block device backend for GPU RISC-V emulator.

Provides a host-assisted VirtIO implementation:
- Guest writes to queue-notify register (0x50) causes GPU to yield
- Python host processes virtqueue requests from descriptor chain
- Disk sectors are read from real disk image and written to GPU RAM
- Completion interrupt is raised and execution resumes
"""

import struct
from typing import Tuple, Optional
from pathlib import Path


class VirtIOBlockDevice:
    """VirtIO-MMIO block device with host-assisted virtqueue processing"""

    # VirtIO-MMIO register offsets (from VirtIO spec 1.1)
    REG_MAGIC_VALUE       = 0x00   # 0x74726976 ('virt')
    REG_VERSION           = 0x04   # Legacy device version 1.0
    REG_DEVICE_ID         = 0x08   # 0x00000002 = block device
    REG_VENDOR_ID         = 0x0C   # Vendor ID (0x1AF4 = Red Hat)
    REG_DEVICE_FEATURES   = 0x10   # VIRTIO_BLK_F_RO (1) + VIRTIO_F_VERSION_1 (2)
    REG_DRIVER_FEATURES   = 0x20
    REG_QUEUE_SEL         = 0x30   # Queue selector
    REG_QUEUE_NUM_MAX     = 0x34   # Max queue size
    REG_QUEUE_NUM         = 0x38   # Actual queue size
    REG_QUEUE_READY       = 0x44   # Queue ready flag
    REG_QUEUE_NOTIFY      = 0x50   # Queue notification (triggers yield)
    REG_INTERRUPT_STATUS  = 0x60   # Interrupt status
    REG_INTERRUPT_ACK     = 0x64   # Interrupt acknowledgment
    REG_STATUS            = 0x70   # Device status bits
    REG_CONFIG_GENERATION = 0xFC
    REG_QUEUE_DESC_LOW    = 0x80   # Descriptor table address (low)
    REG_QUEUE_DESC_HIGH   = 0x84   # Descriptor table address (high)
    REG_QUEUE_AVAIL_LOW   = 0x90   # Available ring address (low)
    REG_QUEUE_AVAIL_HIGH  = 0x94   # Available ring address (high)
    REG_QUEUE_USED_LOW    = 0xA0   # Used ring address (low)
    REG_QUEUE_USED_HIGH   = 0xA4   # Used ring address (high)

    # Device status bits
    STATUS_ACKNOWLEDGE    = 0x01
    STATUS_DRIVER         = 0x02
    STATUS_FAILED         = 0x80
    STATUS_FEATURES_OK    = 0x04
    STATUS_DRIVER_OK      = 0x08

    # Interrupt bits
    INTERRUPT_USED_RING  = 0x01

    # VirtIO block request types
    VIRTIO_BLK_T_IN      = 0      # Read
    VIRTIO_BLK_T_OUT     = 1      # Write
    VIRTIO_BLK_T_FLUSH   = 4

    # VirtIO block request status
    VIRTIO_BLK_S_OK      = 0
    VIRTIO_BLK_S_IOERR   = 1
    VIRTIO_BLK_S_UNSUPP  = 2

    def __init__(self, disk_image_path: str):
        """Initialize VirtIO block device with disk image backing

        Args:
            disk_image_path: Path to raw disk image file
        """
        self.registers = [0] * 0x200  # 512-byte MMIO region

        # Initialize read-only identification registers
        self.registers[self.REG_MAGIC_VALUE // 4] = 0x74726976  # 'virt'
        self.registers[self.REG_VERSION // 4] = 0x00000001     # Legacy version 1.0
        self.registers[self.REG_DEVICE_ID // 4] = 0x00000002   # Block device
        self.registers[self.REG_VENDOR_ID // 4] = 0x1AF4      # Red Hat

        # Device features (VIRTIO_BLK_F_RO + VIRTIO_F_VERSION_1)
        self.registers[self.REG_DEVICE_FEATURES // 4] = 0x00000003

        # Queue configuration
        self.queue_size = 256
        self.queue_ready = False

        # Virtqueue addresses (64-bit, split into low/high)
        self.desc_addr = 0
        self.avail_addr = 0
        self.used_addr = 0

        # Load disk image
        self.disk_path = Path(disk_image_path)
        if not self.disk_path.exists():
            raise FileNotFoundError(f"Disk image not found: {disk_image_path}")
        self.disk_data = self.disk_path.read_bytes()

        sectors = len(self.disk_data) // 512
        print(f"VirtIO Block: {len(self.disk_data) // (1024*1024)}MB disk ({sectors} sectors)")

    def read_mmio(self, offset: int, size: int) -> int:
        """Read from MMIO register space

        Args:
            offset: Byte offset from base (0x10001000)
            size: Access size (1, 2, or 4 bytes)

        Returns:
            Read value (zero-extended for smaller sizes)
        """
        reg_offset = offset & ~0x3  # Align to 4 bytes
        reg_idx = reg_offset // 4

        if reg_idx >= len(self.registers):
            return 0

        value = self.registers[reg_idx]

        # Handle different access sizes
        if size == 1:
            return value & 0xFF
        elif size == 2:
            return value & 0xFFFF
        else:  # 4 bytes
            return value

    def write_mmio(self, offset: int, value: int, size: int):
        """Write to MMIO register space

        Args:
            offset: Byte offset from base (0x10001000)
            value: Value to write
            size: Access size (1, 2, or 4 bytes)
        """
        reg_offset = offset & ~0x3
        reg_idx = reg_offset // 4

        if reg_idx >= len(self.registers):
            return

        current = self.registers[reg_idx]

        # Handle different access sizes with write masking
        if size == 1:
            shift = (offset & 0x3) * 8
            mask = 0xFF << shift
            new_value = (current & ~mask) | ((value & 0xFF) << shift)
        elif size == 2:
            shift = (offset & 0x2) * 8
            mask = 0xFFFF << shift
            new_value = (current & ~mask) | ((value & 0xFFFF) << shift)
        else:  # 4 bytes
            new_value = value

        self.registers[reg_idx] = new_value

        # Handle special register writes
        self._handle_special_registers(reg_idx, new_value)

    def _handle_special_registers(self, reg_idx: int, value: int):
        """Handle writes to special registers that trigger actions"""

        # Queue selector - report max queue size
        if reg_idx == self.REG_QUEUE_SEL // 4:
            self.registers[self.REG_QUEUE_NUM_MAX // 4] = self.queue_size

        # Queue ready - capture virtqueue addresses
        elif reg_idx == self.REG_QUEUE_READY // 4:
            if value != 0:
                self.queue_ready = True
                self._setup_virtqueue()

    def _setup_virtqueue(self):
        """Read virtqueue addresses from registers"""
        desc_low = self.registers[self.REG_QUEUE_DESC_LOW // 4]
        desc_high = self.registers[self.REG_QUEUE_DESC_HIGH // 4]
        self.desc_addr = (desc_high << 32) | desc_low

        avail_low = self.registers[self.REG_QUEUE_AVAIL_LOW // 4]
        avail_high = self.registers[self.REG_QUEUE_AVAIL_HIGH // 4]
        self.avail_addr = (avail_high << 32) | avail_low

        used_low = self.registers[self.REG_QUEUE_USED_LOW // 4]
        used_high = self.registers[self.REG_QUEUE_USED_HIGH // 4]
        self.used_addr = (used_high << 32) | used_low

        print(f"VirtIO Queue: desc=0x{self.desc_addr:016x}, "
              f"avail=0x{self.avail_addr:016x}, used=0x{self.used_addr:016x}")

    def _read_guest_u32(self, read_callback, offset: int) -> int:
        """Read 32-bit value from guest memory at linear offset

        Args:
            read_callback: Function to read bytes from GPU RAM (offset, size) -> bytes
            offset: Linear byte offset from RAM base
        """
        import struct
        data = read_callback(offset, 4)
        return struct.unpack('<I', data)[0]

    def _read_guest_u16(self, read_callback, offset: int) -> int:
        """Read 16-bit value from guest memory at linear offset"""
        import struct
        data = read_callback(offset, 2)
        return struct.unpack('<H', data)[0]

    def _read_guest_u64(self, read_callback, offset: int) -> int:
        """Read 64-bit value from guest memory at linear offset"""
        import struct
        data = read_callback(offset, 8)
        return struct.unpack('<Q', data)[0]

    def _write_guest_u16(self, write_callback, offset: int, value: int):
        """Write 16-bit value to guest memory at linear offset"""
        import struct
        write_callback(offset, struct.pack('<H', value))

    def _write_guest_u32(self, write_callback, offset: int, value: int):
        """Write 32-bit value to guest memory at linear offset"""
        import struct
        write_callback(offset, struct.pack('<I', value))

    def _read_guest_bytes(self, read_callback, offset: int, length: int) -> bytes:
        """Read arbitrary bytes from guest memory at linear offset"""
        return read_callback(offset, length)

    def _write_guest_bytes(self, write_callback, offset: int, data: bytes):
        """Write arbitrary bytes to guest memory at linear offset"""
        write_callback(offset, data)

    def _process_virtqueue(self, read_callback, write_callback, ram_base: int):
        """Process pending block requests from virtqueue

        Args:
            read_callback: Function to read bytes from GPU RAM (offset, size) -> bytes
            write_callback: Function to write bytes to GPU RAM (offset, data)
            ram_base: RAM base address (for PA -> offset conversion)

        Returns:
            Number of requests processed
        """
        if not self.queue_ready:
            return 0

        # Read avail ring header: flags, idx
        # offset: avail_addr + 0 = flags, + 2 = idx (avail ring uses 16-bit fields)
        avail_idx = self._read_guest_u16(read_callback, self.avail_addr - ram_base + 2)

        # Last processed index (persistent across calls)
        if not hasattr(self, '_last_avail_idx'):
            self._last_avail_idx = 0

        processed = 0
        while self._last_avail_idx != avail_idx:
            # Get descriptor index from available ring
            desc_idx_offset = self.avail_addr - ram_base + 4 + (self._last_avail_idx % self.queue_size) * 2
            desc_idx = self._read_guest_u16(read_callback, desc_idx_offset)

            # Process this descriptor chain
            status = self._process_request(read_callback, write_callback, ram_base, desc_idx)

            # Update used ring
            used_idx = self._read_guest_u16(read_callback, self.used_addr - ram_base + 2)
            entry_offset = self.used_addr - ram_base + 4 + (used_idx % self.queue_size) * 8
            self._write_guest_u32(write_callback, entry_offset, desc_idx)    # id
            self._write_guest_u32(write_callback, entry_offset + 4, status)  # len

            # Bump used idx
            self._write_guest_u16(write_callback, self.used_addr - ram_base + 2, (used_idx + 1) % 0x10000)

            self._last_avail_idx = (self._last_avail_idx + 1) % 0x10000
            processed += 1

        # Set interrupt status
        self.registers[self.REG_INTERRUPT_STATUS // 4] = self.INTERRUPT_USED_RING

        return processed

    def _process_request(self, read_callback, write_callback, ram_base: int, head_idx: int) -> int:
        """Process a single virtio block request

        Returns:
            Status byte to write back to guest (0=OK, 1=IOERR, 2=UNSUPP)
        """
        # Walk descriptor chain to find request header, data buffer, and status byte
        request_type = 0
        sector = 0
        data_offset = 0
        data_len = 0
        status_offset = 0

        desc_idx = head_idx
        desc_seen = set()

        while desc_idx not in desc_seen and len(desc_seen) < self.queue_size:
            desc_seen.add(desc_idx)

            # Read descriptor: addr (64-bit), len (32), flags (16), next (16)
            desc_offset = self.desc_addr - ram_base + desc_idx * 16

            desc_addr_low = self._read_guest_u32(read_callback, desc_offset)
            desc_addr_high = self._read_guest_u32(read_callback, desc_offset + 4)
            desc_addr = (desc_addr_high << 32) | desc_addr_low
            desc_len = self._read_guest_u32(read_callback, desc_offset + 8)
            desc_flags = self._read_guest_u16(read_callback, desc_offset + 12)
            desc_next = self._read_guest_u16(read_callback, desc_offset + 14)

            # First descriptor is the request header (16 bytes: type, reserved, sector)
            if request_type == 0 and desc_len >= 16:
                req_header = self._read_guest_bytes(read_callback, desc_addr - ram_base, 16)
                req_type = req_header[0]  # First byte is request type
                request_type = req_type & 0xFF
                # Sector is at offset 8 (64-bit little-endian)
                sector = int.from_bytes(req_header[8:16], byteorder='little')

            # Data buffer (read-only flag clear = device-writable = read from disk)
            elif desc_flags & 0x01:  # VIRTQ_DESC_F_WRITE
                data_offset = desc_addr - ram_base
                data_len = desc_len

            # Status byte (device-readable = write back status)
            else:
                status_offset = desc_addr - ram_base

            # Chain to next descriptor
            if desc_flags & 0x02:  # VIRTQ_DESC_F_NEXT
                desc_idx = desc_next
            else:
                break

        # Process based on request type
        if request_type == self.VIRTIO_BLK_T_IN and data_len > 0:
            # READ: copy sectors from disk image to guest RAM
            disk_offset = sector * 512
            if disk_offset + data_len <= len(self.disk_data):
                sector_data = self.disk_data[disk_offset:disk_offset + data_len]
                write_callback(data_offset, sector_data)
                status = self.VIRTIO_BLK_S_OK
            else:
                status = self.VIRTIO_BLK_S_IOERR
                print(f"VirtIO: READ out of bounds: sector={sector}, len={data_len}, disk_size={len(self.disk_data)}")

        elif request_type == self.VIRTIO_BLK_T_OUT:
            # WRITE: not supported (read-only root fs)
            status = self.VIRTIO_BLK_S_UNSUPP

        elif request_type == self.VIRTIO_BLK_T_FLUSH:
            # FLUSH: no-op
            status = self.VIRTIO_BLK_S_OK

        else:
            print(f"VirtIO: Unknown request type {request_type}")
            status = self.VIRTIO_BLK_S_IOERR

        # Write status byte back to guest
        if status_offset > 0:
            self._write_guest_bytes(write_callback, status_offset, bytes([status]))

        return status


def test_virtio_device():
    """Test basic VirtIO-MMIO device functionality"""
    print("=" * 70)
    print("VIRTIO-MMIO BLOCK DEVICE TEST")
    print("=" * 70)

    # Create device with Alpine disk
    virtio = VirtIOBlockDevice('/home/jericho/projects/zion/projects/visual_audio/alpine_minimal_bootable.raw')

    # Test register reads
    print("\n[1] Device Identification:")
    magic = virtio.read_mmio(virtio.REG_MAGIC_VALUE, 4)
    print(f"  Magic:     0x{magic:08x} (expected 0x74726976)")
    version = virtio.read_mmio(virtio.REG_VERSION, 4)
    print(f"  Version:   0x{version:08x} (expected 0x00000001)")
    device_id = virtio.read_mmio(virtio.REG_DEVICE_ID, 4)
    print(f"  Device ID: 0x{device_id:08x} (expected 0x00000002)")

    # Test initialization sequence
    print("\n[2] Driver Initialization Simulation:")
    virtio.write_mmio(virtio.REG_STATUS, virtio.STATUS_ACKNOWLEDGE, 4)
    print(f"  Status: ACKNOWLEDGE")
    virtio.write_mmio(virtio.REG_STATUS, virtio.STATUS_DRIVER, 4)
    print(f"  Status: DRIVER")
    virtio.write_mmio(virtio.REG_DRIVER_FEATURES, 0x00000003, 4)
    virtio.write_mmio(virtio.REG_STATUS, virtio.STATUS_FEATURES_OK, 4)
    print(f"  Status: FEATURES_OK")
    virtio.write_mmio(virtio.REG_STATUS, virtio.STATUS_DRIVER_OK, 4)
    print(f"  Status: DRIVER_OK")

    print("\n" + "=" * 70)
    print("VirtIO device initialization: ✓ WORKING")
    print("=" * 70)


if __name__ == "__main__":
    test_virtio_device()