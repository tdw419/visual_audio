"""BM902 scratch probe: read measured values from the oracle zeropage.

Not part of the gate — evidence helper for implementing stage2's zeropage
construction. Reads the pinned oracle dump; prints field values + low-region
stats + e820 table so the stage2 builder sets bytes from measurement, not
from doc prose.
"""
import struct

zp = open('oracle_zp_leg0.bin', 'rb').read()
assert len(zp) == 4096
print('e820_entries', zp[0x1e8])
print('setup_sects', hex(zp[0x1f1]))
print('syssize', hex(struct.unpack_from('<I', zp, 0x1f4)[0]))
print('root_flags', hex(struct.unpack_from('<H', zp, 0x1f2)[0]))
print('ram_size', hex(struct.unpack_from('<I', zp, 0x1f8)[0]))
print('vid_mode', hex(struct.unpack_from('<H', zp, 0x1fa)[0]))
print('root_dev', hex(struct.unpack_from('<H', zp, 0x1fc)[0]))
print('boot_flag', hex(struct.unpack_from('<H', zp, 0x1fe)[0]))
print('header', zp[0x202:0x206])
print('version', hex(struct.unpack_from('<H', zp, 0x206)[0]))
print('type_of_loader', hex(zp[0x210]))
print('loadflags', hex(zp[0x211]))
print('realmode_swtch', hex(struct.unpack_from('<I', zp, 0x208)[0]))
print('start_sys_seg', hex(struct.unpack_from('<I', zp, 0x20c)[0]))
print('code32_start', hex(struct.unpack_from('<I', zp, 0x214)[0]))
print('ramdisk', hex(struct.unpack_from('<I', zp, 0x218)[0]),
      hex(struct.unpack_from('<I', zp, 0x21c)[0]))
print('heap_end_ptr', hex(struct.unpack_from('<H', zp, 0x224)[0]))
print('cmd_line_ptr', hex(struct.unpack_from('<I', zp, 0x228)[0]))
print('initrd_addr_max', hex(struct.unpack_from('<I', zp, 0x22c)[0]))
print('kernel_alignment', hex(struct.unpack_from('<I', zp, 0x230)[0]))
print('relocatable', zp[0x234], 'min_alignment', hex(zp[0x235]))
print('xloadflags', hex(struct.unpack_from('<H', zp, 0x236)[0]))
print('cmdline_size', hex(struct.unpack_from('<I', zp, 0x238)[0]))
print('hardware_subarch', struct.unpack_from('<I', zp, 0x23c)[0])
print('payload_offset', hex(struct.unpack_from('<I', zp, 0x248)[0]))
print('payload_length', hex(struct.unpack_from('<I', zp, 0x24c)[0]))
print('pref_address', hex(struct.unpack_from('<Q', zp, 0x258)[0]))
print('init_size', hex(struct.unpack_from('<I', zp, 0x260)[0]))
print('handover_offset', hex(struct.unpack_from('<I', zp, 0x264)[0]))
low = zp[:0x1e8]
nz = [i for i, b in enumerate(low) if b]
print('low region nonzero bytes:', len(nz), 'of', len(low),
      'first:', [hex(i) for i in nz[:10]], 'last:', [hex(i) for i in nz[-5:]])
for i in range(zp[0x1e8]):
    off = 0x2d0 + i * 20
    addr, size, typ = struct.unpack_from('<QQI', zp, off)
    print(f'e820[{i}] {addr:#x} size={size:#x} type={typ}')
