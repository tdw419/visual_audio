import sys
import os
import struct
import numpy as np
import time

sys.path.insert(0, os.path.abspath('tools'))
from spatial_rv64i_cpu import SpatialRV64ICore
from create_dtb import build_device_tree
import numba

@numba.njit
def compute_hilbert_lut(mem_len: int, N: int) -> np.ndarray:
    lut = np.zeros(mem_len, dtype=np.uint32)
    for d in range(mem_len):
        t = d
        x = 0; y = 0; s = 1
        while s < N:
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
        lut[d] = y * N + x
    return lut

def load_bytes_local(linear_arr, addr, data):
    offset = addr - 0x80000000
    rem = len(data) % 4
    if rem != 0:
        data += b'\x00' * (4 - rem)
    arr = np.frombuffer(data, dtype=np.uint32)
    idx = offset // 4
    linear_arr[idx:idx + len(arr)] = arr

def flatten_pe(pe_data: bytes) -> bytes:
    pe_offset = struct.unpack('<I', pe_data[0x3c:0x40])[0]
    if pe_data[pe_offset:pe_offset+4] != b'PE\x00\x00':
        raise ValueError("Invalid PE signature")

    coff = pe_offset + 4
    num_sections = struct.unpack('<H', pe_data[coff+2:coff+4])[0]
    opt_hdr_size = struct.unpack('<H', pe_data[coff+16:coff+18])[0]
    
    opt_start = coff + 20
    size_of_image = struct.unpack('<I', pe_data[opt_start+56:opt_start+60])[0]

    flat = bytearray(size_of_image)

    section_table = opt_start + opt_hdr_size
    for i in range(num_sections):
        s = section_table + i * 40
        name = pe_data[s:s+8].rstrip(b'\x00').decode('ascii', errors='replace')
        vsize = struct.unpack('<I', pe_data[s+8:s+12])[0]
        vaddr = struct.unpack('<I', pe_data[s+12:s+16])[0]
        raw_size = struct.unpack('<I', pe_data[s+16:s+20])[0]
        raw_ptr = struct.unpack('<I', pe_data[s+20:s+24])[0]

        if raw_size > 0 and raw_ptr > 0:
            section_data = pe_data[raw_ptr:raw_ptr + raw_size]
            flat[vaddr:vaddr + len(section_data)] = section_data

    return bytes(flat)

def main():
    kernel_path = '/home/jericho/projects/zion/apps/linux/alpine/alpine-riscv64.lnx.bin'
    mem_size = 64 * 1024 * 1024
    mem_len = mem_size // 4
    
    lut_cache = "tools/hilbert_lut_64M.npy"
    if os.path.exists(lut_cache):
        lut = np.load(lut_cache)
    else:
        N = int(np.sqrt(mem_len))
        lut = compute_hilbert_lut(mem_len, N)
        np.save(lut_cache, lut)
        
    core = SpatialRV64ICore(mem_size)
    core.set_ram_base(0x80000000)
    linear_arr = np.zeros(mem_len, dtype=np.uint32)

    with open('/usr/share/qemu/opensbi-riscv64-generic-fw_dynamic.bin', 'rb') as f:
        opensbi = f.read()
    load_bytes_local(linear_arr, 0x80000000, opensbi)
    
    dtb = build_device_tree(0x80000000, 64 * 1024 * 1024, 0x10000000, 'rv64imac', 10000000, 'console=ttyS0')
    dtb_addr = 0x82000000
    load_bytes_local(linear_arr, dtb_addr, dtb)

    with open(kernel_path, 'rb') as f:
        raw_data = f.read()
    kernel_offset = struct.unpack('<I', raw_data[4:8])[0]
    kernel_size = struct.unpack('<I', raw_data[8:12])[0]
    kernel_raw = raw_data[kernel_offset:kernel_offset + kernel_size]
    
    print("Flattening PE image...")
    flat_kernel = flatten_pe(kernel_raw)
    
    kernel_addr = 0x80200000
    load_bytes_local(linear_arr, kernel_addr, flat_kernel)

    info_addr = 0x80100000
    info = struct.pack('<QQQQQQ', 0x4942534f, 0x2, 0x80200000, 0x1, 0x0, 0x0)
    load_bytes_local(linear_arr, info_addr, info)

    spatial_arr = np.zeros(mem_len, dtype=np.uint32)
    for d in range(mem_len):
        if linear_arr[d] != 0:
            spatial_arr[lut[d]] = linear_arr[d]
            
    core.queue.write_buffer(core.memory.buffer, 0, spatial_arr.tobytes())

    state_arr = np.array([
        0x80000000, 0, 0, 0, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0x80000000, 0, 0, 0, 0, 0, 0, 0, 0
    ], dtype=np.uint32)
    core.queue.write_buffer(core.state_buffer, 0, state_arr.tobytes())

    core.write_register(10, 0)
    core.write_register(11, dtb_addr)
    core.write_register(12, info_addr)

    print("Executing...", flush=True)
    
    for i in range(1, 100):
        core.step(200000)
        state = core.get_state()
        print(f"[Iter {i}] PC: 0x{state['pc_low']:08x} Halted: {state['halted']} Cause: {core.read_csr(0x342)}", flush=True)

        uart = core.read_uart_output()
        if uart:
            sys.stdout.buffer.write(uart)
            sys.stdout.flush()

        if state['halted']:
            break

main()
