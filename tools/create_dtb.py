#!/usr/bin/env python3
"""
create_dtb.py - Generate a minimal RISC-V Device Tree Blob for the GPU machine.

Describes the hardware the GPU-native RISC-V emulator (RISCV_CPU_MMU.wgsl)
actually implements:

  - 1 hart, RV64, SV39 MMU
  - RAM (default: 16MB at 0x80000000, the standard RISC-V load convention;
    use --ram-base 0x0 for the no-MMU remapped layout)
  - 16550-compatible UART at 0x10000000 (byte-spaced registers, no reg-shift)

The FDT (flattened device tree) is serialized in pure Python - no libfdt or
dtc dependency. If dtc is installed, the output is round-trip verified and a
human-readable .dts is written alongside the .dtb.

At boot, pass the DTB physical address in a1 and hart ID 0 in a0, with
satp = 0 (MMU off). Linux reads this blob to find RAM and the console.

Usage:
    python3 tools/create_dtb.py                          # gpu_machine.dtb
    python3 tools/create_dtb.py --ram-base 0x0 -o no_mmu.dtb
"""

import argparse
import struct
import subprocess
import shutil
import sys
from pathlib import Path

# FDT structure block tokens
FDT_BEGIN_NODE = 0x1
FDT_END_NODE = 0x2
FDT_PROP = 0x3
FDT_END = 0x9

FDT_MAGIC = 0xD00DFEED
FDT_VERSION = 17
FDT_LAST_COMP_VERSION = 16


class Node:
    """A device tree node: named properties plus child nodes."""

    def __init__(self, name: str):
        self.name = name
        self.props = []  # list of (name, bytes)
        self.children = []

    def prop(self, name: str, value: bytes = b''):
        """Raw property. Empty value = boolean/marker property (e.g. 'ranges')."""
        self.props.append((name, value))
        return self

    def prop_str(self, name: str, *values: str):
        """String or string-list property (each string null-terminated)."""
        return self.prop(name, b''.join(v.encode() + b'\0' for v in values))

    def prop_u32(self, name: str, *values: int):
        """Cell property: big-endian u32 array."""
        return self.prop(name, b''.join(struct.pack('>I', v & 0xFFFFFFFF) for v in values))

    def prop_u64(self, name: str, *values: int):
        """u64 property encoded as hi/lo cell pairs."""
        cells = []
        for v in values:
            cells += [(v >> 32) & 0xFFFFFFFF, v & 0xFFFFFFFF]
        return self.prop_u32(name, *cells)

    def child(self, name: str) -> 'Node':
        node = Node(name)
        self.children.append(node)
        return node


class FDTWriter:
    """Serialize a Node tree into a flattened device tree blob (v17)."""

    def __init__(self, root: Node):
        self.root = root
        self.struct_block = bytearray()
        self.strings_block = bytearray()
        self.string_offsets = {}

    def _string_offset(self, name: str) -> int:
        if name not in self.string_offsets:
            self.string_offsets[name] = len(self.strings_block)
            self.strings_block += name.encode() + b'\0'
        return self.string_offsets[name]

    def _pad4(self):
        while len(self.struct_block) % 4:
            self.struct_block += b'\0'

    def _emit_node(self, node: Node):
        self.struct_block += struct.pack('>I', FDT_BEGIN_NODE)
        self.struct_block += node.name.encode() + b'\0'
        self._pad4()
        for name, value in node.props:
            self.struct_block += struct.pack('>III', FDT_PROP, len(value), self._string_offset(name))
            self.struct_block += value
            self._pad4()
        for child in node.children:
            self._emit_node(child)
        self.struct_block += struct.pack('>I', FDT_END_NODE)

    def serialize(self) -> bytes:
        self._emit_node(self.root)
        self.struct_block += struct.pack('>I', FDT_END)

        header_size = 40
        # Empty memory reservation block: single (0, 0) terminator entry
        rsvmap = struct.pack('>QQ', 0, 0)
        off_rsvmap = header_size
        off_struct = off_rsvmap + len(rsvmap)
        off_strings = off_struct + len(self.struct_block)
        totalsize = off_strings + len(self.strings_block)

        header = struct.pack(
            '>10I',
            FDT_MAGIC,
            totalsize,
            off_struct,
            off_strings,
            off_rsvmap,
            FDT_VERSION,
            FDT_LAST_COMP_VERSION,
            0,  # boot_cpuid_phys
            len(self.strings_block),
            len(self.struct_block),
        )
        return header + rsvmap + bytes(self.struct_block) + bytes(self.strings_block)


def build_device_tree(ram_base: int, ram_size: int, uart_base: int,
                      isa: str, timebase: int, bootargs: str) -> bytes:
    uart_path = f'/soc/serial@{uart_base:x}'

    root = Node('')
    root.prop_u32('#address-cells', 2)
    root.prop_u32('#size-cells', 2)
    root.prop_str('compatible', 'riscv-virtio')
    root.prop_str('model', 'visual-audio,gpu-riscv-pixel-machine')

    chosen = root.child('chosen')
    chosen.prop_str('bootargs', bootargs)
    chosen.prop_str('stdout-path', uart_path)

    mem = root.child(f'memory@{ram_base:x}')
    mem.prop_str('device_type', 'memory')
    mem.prop_u64('reg', ram_base, ram_size)

    cpus = root.child('cpus')
    cpus.prop_u32('#address-cells', 1)
    cpus.prop_u32('#size-cells', 0)
    cpus.prop_u32('timebase-frequency', timebase)

    cpu0 = cpus.child('cpu@0')
    cpu0.prop_str('device_type', 'cpu')
    cpu0.prop_u32('reg', 0)
    cpu0.prop_str('status', 'okay')
    cpu0.prop_str('compatible', 'riscv')
    cpu0.prop_str('riscv,isa', isa)
    cpu0.prop_str('mmu-type', 'riscv,sv39')

    intc = cpu0.child('interrupt-controller')
    intc.prop_u32('#interrupt-cells', 1)
    intc.prop('interrupt-controller')
    intc.prop_str('compatible', 'riscv,cpu-intc')
    intc.prop_u32('phandle', 1)

    soc = root.child('soc')
    soc.prop_u32('#address-cells', 2)
    soc.prop_u32('#size-cells', 2)
    soc.prop_str('compatible', 'simple-bus')
    soc.prop('ranges')  # 1:1 bus-to-cpu address mapping

    uart = soc.child(f'serial@{uart_base:x}')
    uart.prop_str('compatible', 'ns16550a')
    uart.prop_u64('reg', uart_base, 0x100)
    uart.prop_u32('clock-frequency', 3686400)
    # No 'interrupts' property: there is no PLIC yet, so the 8250 driver
    # runs without an IRQ; earlycon output is unaffected.

    return FDTWriter(root).serialize()


def verify_with_dtc(dtb_path: Path) -> bool:
    """Round-trip the blob through dtc if available; write .dts alongside."""
    dtc = shutil.which('dtc')
    if not dtc:
        print('  dtc not found - skipping verification')
        return True

    dts_path = dtb_path.with_suffix('.dts')
    result = subprocess.run(
        [dtc, '-I', 'dtb', '-O', 'dts', '-o', str(dts_path), str(dtb_path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f'  dtc FAILED to parse blob:\n{result.stderr}')
        return False

    for line in result.stderr.splitlines():
        print(f'  dtc: {line}')
    print(f'  dtc verified OK -> {dts_path}')
    return True


def main():
    parser = argparse.ArgumentParser(description='Generate minimal RISC-V DTB for the GPU machine')
    parser.add_argument('-o', '--output', default='gpu_machine.dtb')
    parser.add_argument('--ram-base', type=lambda s: int(s, 0), default=0x80000000,
                        help='Physical RAM base as seen by the CPU (default 0x80000000; '
                             'use 0x0 for the no-MMU remapped pixel layout)')
    parser.add_argument('--ram-size', type=lambda s: int(s, 0), default=16 * 1024 * 1024,
                        help='RAM size in bytes (default 16MB)')
    parser.add_argument('--uart-base', type=lambda s: int(s, 0), default=0x10000000)
    parser.add_argument('--isa', default='rv64imafdc',
                        help='riscv,isa string advertised to the kernel')
    parser.add_argument('--timebase', type=int, default=10_000_000,
                        help='timebase-frequency in Hz (default 10MHz)')
    parser.add_argument('--bootargs', default=None,
                        help='Kernel command line (default: earlycon+console on the UART)')
    args = parser.parse_args()

    bootargs = args.bootargs
    if bootargs is None:
        bootargs = f'earlycon=uart8250,mmio,{args.uart_base:#x} console=ttyS0'

    print('=' * 70)
    print('DEVICE TREE BLOB GENERATOR - GPU RISC-V Machine')
    print('=' * 70)
    print(f'  RAM:      {args.ram_size // (1024 * 1024)}MB @ {args.ram_base:#x}')
    print(f'  UART:     ns16550a @ {args.uart_base:#x}')
    print(f'  ISA:      {args.isa} (sv39)')
    print(f'  bootargs: {bootargs}')

    dtb = build_device_tree(args.ram_base, args.ram_size, args.uart_base,
                            args.isa, args.timebase, bootargs)

    out_path = Path(args.output)
    out_path.write_bytes(dtb)
    print(f'\n[1] Wrote {out_path} ({len(dtb)} bytes)')

    print('\n[2] Verifying with dtc...')
    if not verify_with_dtc(out_path):
        sys.exit(1)

    # Suggested placement: DTB at the end of RAM, 8-byte aligned, clear of the
    # kernel image. Linux requires the DTB not overlap the kernel's own pages.
    dtb_addr = (args.ram_base + args.ram_size - len(dtb)) & ~0x7
    print('\n[3] Boot protocol:')
    print(f'  Place kernel at:  {args.ram_base + 0x200000:#x} (RAM base + 2MB)')
    print(f'  Place DTB at:     {dtb_addr:#x} (end of RAM, 8-byte aligned)')
    print('  Registers:        a0 = 0 (hart ID), a1 = DTB address')
    print('  CSRs:             satp = 0 (MMU off - kernel builds its own SV39 tables)')


if __name__ == '__main__':
    main()
