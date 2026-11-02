#!/usr/bin/env python3
"""
Inventory all EFI service call sites in a RISC-V PE32+ kernel.

Scans for:
1. BootServices table dereferences (ld aX, offset(bs_ptr))
2. RuntimeServices table dereferences
3. Protocol interface table dereferences

This is the "skeleton inventory" phase - no code changes, just enumeration.
"""

import struct
import sys
import re
from pathlib import Path
from collections import defaultdict

def disassemble_elf(elf_path):
    """Run objdump -d and return full disassembly."""
    import subprocess
    result = subprocess.run(
        ['riscv64-linux-gnu-objdump', '-d', elf_path],
        capture_output=True, text=True
    )
    return result.stdout

def parse_instruction_line(line):
    """Parse an objdump instruction line.
    Returns (addr, bytes, mnemonic, operands) or None."""
    line = line.strip()
    if not line or line.endswith(':') or 'Disassembly' in line or 'file format' in line:
        return None

    # Format: "   1000:\t0102f597          \tauipc\ta1,0x102f"
    match = re.match(r'^\s*([0-9a-f]+):\t([0-9a-f]+)\s+(\S+)(?:\s+(.*))?$', line)
    if not match:
        return None

    addr = int(match.group(1), 16)
    bytes_str = match.group(2)
    mnemonic = match.group(3)
    operands = match.group(4) or ''

    return (addr, bytes_str, mnemonic, operands)

def find_efi_call_sites(dump_text):
    """
    Scan for EFI service call patterns.
    Returns dict: {call_type: {offset: {from_addr, mnemonic, operands, likely_service}}}
    """
    bs_call_pattern = re.compile(r'ld\s+(a[0-9]),\s*(-?\d+)\((a[0-9])\)')
    rs_call_pattern = re.compile(r'ld\s+(a[0-9]),\s*(-?\d+)\((a[0-9])\)')
    ecall_pattern = re.compile(r'\becall\b')

    call_sites = {
        'BootServices': {},   # BS function calls via table offset
        'RuntimeServices': {},  # RS function calls via table offset
        'Protocol': {},        # Protocol interface calls
        'ecall': [],           # All ecall instructions (SBI/EFI extensions)
    }

    # Common EFI BS/RS function offsets (from EDK2 headers)
    BOOT_SERVICES_FUNCS = {
        # Table 0: 0x00-0x3F
        0x00: 'LoadImage',
        0x08: 'StartImage',
        0x10: 'Exit',
        0x18: 'UnloadImage',
        0x20: 'ExitBootServices',
        0x28: 'GetNextMonotonicCount',
        0x30: 'Stall',
        0x38: 'WatchdogTimer',
        # Table 1: 0x40-0x7F
        0x40: 'ConnectController',
        0x48: 'DisconnectController',
        0x50: 'OpenProtocol',
        0x58: 'CloseProtocol',
        0x60: 'OpenProtocolInformation',
        0x68: 'ProtocolsPerHandle',
        0x70: 'LocateHandleBuffer',
        0x78: 'LocateProtocol',
        # Table 2: 0x80-0xBF
        0x80: 'InstallProtocolInterface',
        0x88: 'ReinstallProtocolInterface',
        0x90: 'UninstallProtocolInterface',
        0x98: 'HandleProtocol',
        0xA0: 'RegisterProtocolNotify',
        0xA8: 'LocateHandle',
        0xB0: 'InstallMultipleProtocolInterfaces',
        0xB8: 'UninstallMultipleProtocolInterfaces',
        # Table 3: 0xC0-0xFF
        0xC0: 'AllocatePool',     # CRITICAL
        0xC8: 'FreePool',
        0xD0: 'SetWatchdogTimer',
        0xD8: 'ConnectController',  # Duplicate offset?
        0xE0: 'DisconnectController',
        0xE8: 'OpenProtocol',
        0xF0: 'CloseProtocol',
        0xF8: 'OpenProtocolInformation',
    }

    RUNTIME_SERVICES_FUNCS = {
        # GetTime, SetTime, GetWakeupTime, SetWakeupTime (0x00-0x38)
        # SetVirtualAddressMap, ConvertPointer (0x38-0x48)
        0x40: 'GetVariable',
        0x48: 'GetNextVariableName',
        0x50: 'SetVariable',
        0x58: 'GetNextHighMonotonicCount',
        0x60: 'ResetSystem',
        0x68: 'UpdateCapsule',
        0x70: 'QueryCapsuleCapabilities',
        0x78: 'QueryVariableInfo',
    }

    lines = dump_text.split('\n')
    for i, line in enumerate(lines):
        parsed = parse_instruction_line(line)
        if not parsed:
            continue

        addr, bytes_str, mnemonic, operands = parsed

        # Track ecall (SBI/EFI extension)
        if mnemonic == 'ecall':
            call_sites['ecall'].append({
                'addr': addr,
                'bytes': bytes_str,
                'context': line
            })

        # Track table dereferences (ld aX, offset(base_reg))
        if mnemonic == 'ld':
            match = re.match(r'(a[0-9]),\s*(-?\d+)\((a[0-9])\)', operands)
            if match:
                rd, offset_str, rs = match.groups()
                offset = int(offset_str)  # Negative values sign-extended

                # Skip small struct field loads (likely not function pointers)
                if abs(offset) < 8:
                    continue

                # BootServices table dereference?
                # BS functions typically: ld a5, N(bs_ptr); jalr a5
                if offset > 0 and offset <= 0xFF:
                    if offset in BOOT_SERVICES_FUNCS:
                        func_name = BOOT_SERVICES_FUNCS[offset]
                        call_sites['BootServices'][offset] = {
                            'offset': offset,
                            'name': func_name,
                            'callers': []
                        }
                        # Look ahead for jalr
                        for j in range(i+1, min(i+5, len(lines))):
                            next_line = lines[j]
                            if 'jalr' in next_line and rd in next_line:
                                call_sites['BootServices'][offset]['callers'].append({
                                    'addr': addr,
                                    'context': line
                                })
                                break

                # RuntimeServices table dereference?
                elif offset > 0 and offset <= 0x100:
                    if offset in RUNTIME_SERVICES_FUNCS:
                        func_name = RUNTIME_SERVICES_FUNCS[offset]
                        call_sites['RuntimeServices'][offset] = {
                            'offset': offset,
                            'name': func_name,
                            'callers': []
                        }

    return call_sites

def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <pe32+_binary>")
        sys.exit(1)

    elf_path = sys.argv[1]
    print(f"[*] Analyzing: {elf_path}")
    print("=" * 70)

    # Disassemble
    print("[*] Disassembling...")
    dump_text = disassemble_elf(elf_path)

    # Find call sites
    print("[*] Inventorying EFI service call sites...")
    call_sites = find_efi_call_sites(dump_text)

    # Print results
    print("\n" + "=" * 70)
    print("EFI BOOT SERVICES CALLS")
    print("=" * 70)

    if call_sites['BootServices']:
        for offset in sorted(call_sites['BootServices'].keys()):
            info = call_sites['BootServices'][offset]
            print(f"\nOffset 0x{offset:02x}: {info['name']}")
            for caller in info['callers']:
                print(f"  Called from: 0x{caller['addr']:08x}")
    else:
        print("(none found)")

    print("\n" + "=" * 70)
    print("EFI RUNTIME SERVICES CALLS")
    print("=" * 70)

    if call_sites['RuntimeServices']:
        for offset in sorted(call_sites['RuntimeServices'].keys()):
            info = call_sites['RuntimeServices'][offset]
            print(f"\nOffset 0x{offset:02x}: {info['name']}")
    else:
        print("(none found)")

    print("\n" + "=" * 70)
    print("ECALL INSTRUCTIONS (SBI/EFI EXTENSIONS)")
    print("=" * 70)

    if call_sites['ecall']:
        print(f"\nTotal ecall sites: {len(call_sites['ecall'])}")
        for ec in call_sites['ecall']:
            print(f"  0x{ec['addr']:08x}: {ec['context']}")
    else:
        print("(none found)")

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"BootServices functions called: {len(call_sites['BootServices'])}")
    print(f"RuntimeServices functions called: {len(call_sites['RuntimeServices'])}")
    print(f"Total ecall sites: {len(call_sites['ecall'])}")

if __name__ == '__main__':
    main()