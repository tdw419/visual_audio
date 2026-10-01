import struct
with open("ubuntu_vmlinuz", "rb") as f:
    data = f.read(1024)
setup_sects = data[0x1f1]
if setup_sects == 0: setup_sects = 4
setup_size = (setup_sects + 1) * 512
handover_offset = struct.unpack_from("<I", data, 0x264)[0]
total_offset = setup_size + handover_offset
print(f"Setup size: {setup_size}")
print(f"Handover offset: {handover_offset}")
print(f"Total offset from start of file: {total_offset} (0x{total_offset:x})")
