#!/usr/bin/env python3
"""
Annotated disassembly overlay for hello.img.
"""

import struct
import sys
from pathlib import Path

RISCV_ELF_MAGIC = b'\x7fELF'

def parse_elf_headers(img_path: Path):
    """Parse ELF headers to get section information."""
    data = img_path.read_bytes()

    # Check ELF magic
    if data[:4] != RISCV_ELF_MAGIC:
        print(f"Not an ELF file: {img_path}")
        return None, None, None

    # ELF64 header structure
    e_type = struct.unpack('<H', data[16:18])[0]
    e_machine = struct.unpack('<H', data[18:20])[0]
    e_entry = struct.unpack('<Q', data[24:32])[0]
    e_phoff = struct.unpack('<Q', data[32:40])[0]
    e_shoff = struct.unpack('<Q', data[40:48])[0]
    e_phentsize = struct.unpack('<H', data[54:56])[0]
    e_phnum = struct.unpack('<H', data[56:58])[0]
    e_shentsize = struct.unpack('<H', data[58:60])[0]
    e_shnum = struct.unpack('<H', data[60:62])[0]
    e_shstrndx = struct.unpack('<H', data[62:64])[0]

    print(f"ELF Type: {e_type}, Machine: {e_machine}")
    print(f"Entry: 0x{e_entry:x}")
    print(f"Program headers: {e_phnum} @ 0x{e_phoff:x}")
    print(f"Section headers: {e_shnum} @ 0x{e_shoff:x}")

    # Parse section headers
    sections = []
    sh_strtab_off = data[e_shoff + e_shstrndx * e_shentsize + 24:e_shoff + e_shstrndx * e_shentsize + 32]
    sh_strtab_off = struct.unpack('<Q', sh_strtab_off)[0]

    for i in range(e_shnum):
        sh_off = e_shoff + i * e_shentsize
        sh_name = struct.unpack('<I', data[sh_off:sh_off+4])[0]
        sh_type = struct.unpack('<I', data[sh_off+4:sh_off+8])[0]
        sh_flags = struct.unpack('<Q', data[sh_off+8:sh_off+16])[0]
        sh_addr = struct.unpack('<Q', data[sh_off+16:sh_off+24])[0]
        sh_offset = struct.unpack('<Q', data[sh_off+24:sh_off+32])[0]
        sh_size = struct.unpack('<Q', data[sh_off+32:sh_off+40])[0]

        # Get section name from string table
        name_end = data.find(b'\x00', sh_strtab_off + sh_name)
        sh_name_str = data[sh_strtab_off + sh_name:name_end].decode('utf-8', errors='replace')

        sections.append({
            'name': sh_name_str,
            'type': sh_type,
            'flags': sh_flags,
            'addr': sh_addr,
            'offset': sh_offset,
            'size': sh_size
        })

    # Parse program headers (for segment info)
    phdrs = []
    for i in range(e_phnum):
        ph_off = e_phoff + i * e_phentsize
        p_type = struct.unpack('<I', data[ph_off:ph_off+4])[0]
        p_offset = struct.unpack('<Q', data[ph_off+8:ph_off+16])[0]
        p_vaddr = struct.unpack('<Q', data[ph_off+16:ph_off+24])[0]
        p_filesz = struct.unpack('<Q', data[ph_off+32:ph_off+40])[0]
        p_memsz = struct.unpack('<Q', data[ph_off+40:ph_off+48])[0]

        phdrs.append({
            'type': p_type,
            'offset': p_offset,
            'vaddr': p_vaddr,
            'filesz': p_filesz,
            'memsz': p_memsz
        })

    return data, sections, phdrs


def generate_overlay(sections, phdrs):
    """Generate overlay data with bounding boxes."""
    overlay = []

    # Section boxes (blue)
    for sec in sections:
        if sec['size'] == 0:
            continue
        overlay.append({
            'type': 'section',
            'name': sec['name'],
            'addr': f"0x{sec['addr']:x}",
            'size': f"0x{sec['size']:x}",
            'color': '#0000ff',
            'bounds': [sec['offset'], sec['offset'] + sec['size']]
        })

    # Segment boxes (green)
    for ph in phdrs:
        if ph['filesz'] == 0:
            continue
        overlay.append({
            'type': 'segment',
            'p_type': ph['type'],
            'vaddr': f"0x{ph['vaddr']:x}",
            'size': f"0x{ph['filesz']:x}",
            'color': '#00ff00',
            'bounds': [ph['offset'], ph['offset'] + ph['filesz']]
        })

    return overlay


def main():
    img_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('boot_images/hello.img')

    print(f"=== Analyzing {img_path} ===")
    data, sections, phdrs = parse_elf_headers(img_path)

    if data is None:
        return

    print("\n=== Sections ===")
    for sec in sections:
        if sec['size'] > 0:
            flags = []
            if sec['flags'] & 0x1: flags.append('W')
            if sec['flags'] & 0x2: flags.append('A')
            if sec['flags'] & 0x4: flags.append('X')
            print(f"{sec['name']:12s} @ 0x{sec['addr']:08x} [0x{sec['offset']:06x}+0x{sec['size']:06x}] {''.join(flags)}")

    print("\n=== Program Headers ===")
    p_types = {1: 'LOAD', 2: 'DYNAMIC', 3: 'INTERP', 4: 'NOTE'}
    for ph in phdrs:
        if ph['filesz'] > 0:
            ptype = p_types.get(ph['type'], f"TYPE_{ph['type']}")
            print(f"{ptype:12s} @ 0x{ph['vaddr']:08x} [0x{ph['offset']:06x}+0x{ph['filesz']:06x}] memsz=0x{ph['memsz']:06x}")

    overlay = generate_overlay(sections, phdrs)

    print(f"\n=== Overlay Data ({len(overlay)} boxes) ===")
    for box in overlay:
        name = box['name'] if 'name' in box else str(box.get('p_type', ''))
        print(f"{box['type']:12s} {name:12s} "
              f"@ {box['bounds'][0]:06d}-{box['bounds'][1]:06d} "
              f"[{box['color']}]")

    # Save overlay JSON
    overlay_path = img_path.with_suffix('.overlay.json')
    import json
    with open(overlay_path, 'w') as f:
        json.dump(overlay, f, indent=2)
    print(f"\nSaved overlay to {overlay_path}")


if __name__ == "__main__":
    main()