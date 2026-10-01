import struct
import sys

with open("ubuntu_vmlinuz", "rb") as f:
    data = f.read(1024)

version = struct.unpack_from("<H", data, 0x206)[0]
handover_offset = struct.unpack_from("<I", data, 0x264)[0]
xloadflags = struct.unpack_from("<H", data, 0x236)[0]

print(f"Version: 0x{version:04x}")
print(f"Handover Offset: 0x{handover_offset:08x}")
print(f"XLoadFlags: 0x{xloadflags:04x}")
print(f" - XLF_EFI_HANDOVER_32 (bit 2): {bool(xloadflags & (1 << 2))}")
print(f" - XLF_EFI_HANDOVER_64 (bit 3): {bool(xloadflags & (1 << 3))}")

