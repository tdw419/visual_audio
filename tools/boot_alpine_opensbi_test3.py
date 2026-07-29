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
def map_hilbert_array(linear_arr: np.ndarray, N: int) -> np.ndarray:
    mem_len = len(linear_arr)
    spatial_arr = np.zeros(mem_len, dtype=np.uint32)
    for d in range(mem_len):
        if linear_arr[d] == 0:
            continue
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
        spatial_arr[y * N + x] = linear_arr[d]
    return spatial_arr

def load_bytes_local(linear_arr, addr, data):
    offset = addr - 0x80000000
    rem = len(data) % 4
    if rem != 0:
        data += b'\x00' * (4 - rem)
    arr = np.frombuffer(data, dtype=np.uint32)
    idx = offset // 4
    linear_arr[idx:idx + len(arr)] = arr

def main():
    print("Starting Alpine OpenSBI boot test...", flush=True)
    kernel_path = '/home/jericho/projects/zion/apps/linux/alpine/alpine-riscv64.lnx.bin'
    opensbi_path = '/usr/share/qemu/opensbi-riscv64-generic-fw_dynamic.bin'
    mem_size = 64 * 1024 * 1024
    mem_len = mem_size // 4
    
    lut_cache = "tools/hilbert_lut_64M.npy"
    print("Loading Hilbert LUT from cache...", flush=True)
    lut = np.load(lut_cache)

    core = SpatialRV64ICore(mem_size)
    core.set_ram_base(0x80000000)
    linear_arr = np.zeros(mem_size // 4, dtype=np.uint32)

    with open(opensbi_path, 'rb') as f:
        opensbi_raw = f.read()
    opensbi_addr = 0x80000000
    load_bytes_local(linear_arr, opensbi_addr, opensbi_raw)

    with open(kernel_path, 'rb') as f:
        raw_data = f.read()
    kernel_offset = struct.unpack('<I', raw_data[4:8])[0]
    kernel_size = struct.unpack('<I', raw_data[8:12])[0]
    kernel_raw = raw_data[kernel_offset:kernel_offset + kernel_size]
    kernel_addr = 0x80200000
    load_bytes_local(linear_arr, kernel_addr, kernel_raw)

    dtb = build_device_tree(0x80000000, 64 * 1024 * 1024, 0x10000000, 'rv64imafdc', 10000000, 'console=ttyS0')
    dtb_addr = 0x82000000
    load_bytes_local(linear_arr, dtb_addr, dtb)

    print("Mapping memory...", flush=True)
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

    print("Executing...", flush=True)
    
    for i in range(1, 2000):
        t0 = time.time()
        core.step(200000)
        t1 = time.time()
        
        uart = core.read_uart_output()
        if uart:
            sys.stdout.buffer.write(uart)
            sys.stdout.flush()

        state = core.get_state()
        if state['halted']:
            print(f"\nHalted. mcause: 0x{core.read_csr(0x342):08x}, pc: 0x{state['pc_low']:08x}")
            break
            
        print(f"[Iter {i}] PC: 0x{state['pc_low']:08x} Mode: {state['mode']} ({t1-t0:.4f}s)", flush=True)

main()
