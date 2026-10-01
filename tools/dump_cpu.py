import struct
import sys

def dump_cpu(filename):
    with open(filename, 'rb') as f:
        data = f.read(1024)
        
    fields = struct.unpack('<' + 'I'*64, data[:256])
    
    print(f"PC: {fields[0]:08x}")
    print(f"running: {fields[1]}")
    print(f"priv_mode: {fields[2]}")
    print(f"mstatus: {fields[3]:08x}")
    print(f"mie: {fields[4]:08x}")
    print(f"mip: {fields[5]:08x}")
    print(f"mideleg: {fields[6]:08x}")
    print(f"medeleg: {fields[7]:08x}")
    print(f"mtvec: {fields[8]:08x}")
    print(f"stvec: {fields[9]:08x}")
    print(f"mtime_low: {fields[10]:08x}")
    print(f"mtimecmp_low: {fields[12]:08x}")
    print(f"timer_fired: {fields[14]}")
    print(f"total_irq: {fields[15]}")
    print(f"timer_irq: {fields[16]}")
    print(f"instr: {fields[17]}")

dump_cpu('cpu_dump.bin')
