import struct
with open("ubuntu_vmlinuz", "rb") as f:
    data = f.read(1024)

# PE header offset is at 0x3c
pe_offset = struct.unpack_from("<I", data, 0x3c)[0]
print(f"PE header offset: 0x{pe_offset:x}")

# PE signature
if data[pe_offset:pe_offset+4] == b"PE\0\0":
    print("PE signature found!")
    # Optional header is at pe_offset + 24
    magic = struct.unpack_from("<H", data, pe_offset + 24)[0]
    if magic == 0x20b:
        print("PE32+ (64-bit) optional header")
        entry_point = struct.unpack_from("<I", data, pe_offset + 24 + 16)[0]
        print(f"AddressOfEntryPoint: 0x{entry_point:x}")
