#!/usr/bin/env python3
"""
Create a minimal device tree blob for OpenSBI testing
"""

import struct

def build_minimal_dtb():
    """
    Build a minimal DTB that OpenSBI can use.
    Based on OpenSBI's minimal DTB requirements.
    """
    # DTB header (struct fdt_header)
    magic = 0xd00dfeed
    totalsize = 4096  # Start with 4KB
    off_dt_struct = 0x28  # Header is 40 bytes, aligned to 8
    off_dt_strings = 0x1000 - 64  # Strings at end
    off_mem_rsvmap = 0x100
    version = 17
    last_comp_version = 16

    header = struct.pack('>IIIIIIII',
        magic,
        totalsize,
        off_dt_struct,
        off_dt_strings,
        off_mem_rsvmap,
        version,
        last_comp_version,
        0  # boot_cpuid_phys
    )

    # Memory reservation map (two entries, each 16 bytes)
    # Entry 1: no reservations
    rsvmap1 = struct.pack('>QQ', 0, 0)
    # Entry 2: terminator
    rsvmap2 = struct.pack('>QQ', 0, 0)

    # DT structure (FDT_BEGIN_NODE, properties, FDT_END_NODE)
    # Root node
    begin_node = struct.pack('>I', 0x1)  # FDT_BEGIN_NODE
    root_name = b'\x00'  # Empty root node name
    root_padding = b'\x00' * (4 - (len(root_name) % 4))

    # model property
    prop_model = struct.pack('>I', 0x3)  # FDT_PROP
    model_len = 20
    model_name_off = 0
    model_data = b'RISC-V OpenSBI Test\x00'
    model_padding = b'\x00' * (4 - (model_len % 4))

    # compatible property
    prop_compat = struct.pack('>I', 0x3)  # FDT_PROP
    compat_len = 17
    compat_name_off = 21
    compat_data = b'riscv-virtio\x00'
    compat_padding = b'\x00' * (4 - (compat_len % 4))

    # Memory node
    begin_mem = struct.pack('>I', 0x1)  # FDT_BEGIN_NODE
    mem_name = b'memory@80000000\x00'
    mem_padding = b'\x00' * (4 - (len(mem_name) % 4))

    # reg property (address, size)
    prop_reg = struct.pack('>I', 0x3)  # FDT_PROP
    reg_len = 16
    reg_name_off = 39
    reg_data = struct.pack('>QQ', 0x80000000, 0x04000000)  # 64MB @ 0x80000000
    reg_padding = b'\x00' * (4 - (reg_len % 4))

    # device_type property
    prop_dtype = struct.pack('>I', 0x3)  # FDT_PROP
    dtype_len = 7
    dtype_name_off = 44
    dtype_data = b'memory\x00'
    dtype_padding = b'\x00' * (4 - (dtype_len % 4))

    end_mem = struct.pack('>I', 0x2)  # FDT_END_NODE
    end_root = struct.pack('>I', 0x2)  # FDT_END_NODE
    end = struct.pack('>I', 0x9)  # FDT_END

    # Strings block
    strings = b'model\x00compatible\x00reg\x00device_type\x00'
    strings_padding = b'\x00' * (64 - (len(strings) % 64))

    dt_struct = (begin_node + root_name + root_padding +
                prop_model + struct.pack('>I', model_len) + struct.pack('>I', model_name_off) +
                model_data + model_padding +
                prop_compat + struct.pack('>I', compat_len) + struct.pack('>I', compat_name_off) +
                compat_data + compat_padding +
                begin_mem + mem_name + mem_padding +
                prop_reg + struct.pack('>I', reg_len) + struct.pack('>I', reg_name_off) +
                reg_data + reg_padding +
                prop_dtype + struct.pack('>I', dtype_len) + struct.pack('>I', dtype_name_off) +
                dtype_data + dtype_padding +
                end_mem + end_root + end)

    dt_struct_padding = b'\x00' * (8 - (len(dt_struct) % 8))

    # Assemble DTB
    dtb = (header + dt_struct + dt_struct_padding + rsvmap1 + rsvmap2 +
           dt_struct_padding + strings + strings_padding)

    # Pad to 4KB
    dtb = dtb + b'\x00' * (4096 - len(dtb))

    return dtb

if __name__ == '__main__':
    dtb = build_minimal_dtb()
    print(f"Generated {len(dtb)} byte DTB")

    # Write to file
    with open('/tmp/test_dtb.dtb', 'wb') as f:
        f.write(dtb)

    print("Written to /tmp/test_dtb.dtb")

    # Verify header
    magic = struct.unpack('>I', dtb[0:4])[0]
    print(f"Magic: 0x{magic:08x} {'OK' if magic == 0xd00dfeed else 'BAD'}")