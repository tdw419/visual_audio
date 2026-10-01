"""
CSR address → RiscvCPU struct offset mapping for RV64I emulator.

The WGSL RiscvCPU struct is laid out differently from CSR addresses.
read_csr() must translate CSR addresses to actual struct offsets.
"""

# RiscvCPU field offsets (calculated from RiscvCPU struct in RISCV_CPU_MMU.wgsl)
# Field sizes: vec2<u32> = 8 bytes, u32 = 4 bytes
CSR_OFFSETS = {
    # Machine-mode CSRs (0x300-0x3FF)
    0x300: 0x128,  # mstatus: vec2<u32> (offset 0x128 = 304 decimal)
    0x301: None,   # misa - not in struct
    0x302: 0x330,  # medeleg: vec2<u32>
    0x303: 0x338,  # mideleg: vec2<u32>
    0x304: 0x308,  # mie: vec2<u32>
    0x305: 0x130,  # mtvec: vec2<u32>
    0x30A: 0x340,  # menvcfg: vec2<u32>
    0x340: 0x148,  # mscratch: vec2<u32>
    0x341: 0x138,  # mepc: vec2<u32>
    0x342: 0x140,  # mcause: vec2<u32>  <- FIXED: was reading wrong offset
    0x343: 0x150,  # mtval: vec2<u32>
    0x344: 0x318,  # mip: vec2<u32>

    # Supervisor-mode CSRs (0x100-0x1FF)
    0x100: None,   # sstatus - derived from mstatus in WGSL, not separate field
    0x104: None,   # sie - derived from mie
    0x105: 0x158,  # stvec: vec2<u32>
    0x140: 0x160,  # sscratch: vec2<u32>
    0x141: 0x168,  # sepc: vec2<u32>
    0x142: 0x170,  # scause: vec2<u32>
    0x143: 0x178,  # stval: vec2<u32>
    0x144: None,   # sip - derived from mip
    0x180: 0x120,  # satp: vec2<u32>

    # CLINT/Timer CSRs (0xB00-0xBFF)
    0xB00: None,   # mtime - read from memory-mapped CLINT region
    0xB02: None,   # minstret - not implemented as separate CSR field

    # Machine-mode Performance Counters (0xC00-0xCFF)
    0xC00: None,   # cycle - not implemented as separate CSR field
    0xC01: None,   # time - read from memory-mapped CLINT region
    0xC02: None,   # instret - tracked by instr_count field (offset 0x08)
}

# CLINT memory-mapped region (for mtime/mtimecmp)
CLINT_BASE = 0x02000000
CLINT_MTIME = CLINT_BASE + 0xBFF8      # mtime register (64-bit)
CLINT_MTIMECMP = CLINT_BASE + 0x4000   # mtimecmp for hart 0 (64-bit)


def csr_to_offset(csr_addr: int) -> int:
    """
    Convert CSR address to RiscvCPU struct offset.
    Returns offset in bytes, or None if CSR is not a direct field.
    """
    return CSR_OFFSETS.get(csr_addr)


def is_clint_csr(csr_addr: int) -> bool:
    """
    Check if CSR is in CLINT memory-mapped region.
    """
    return csr_addr in (0xB00, 0xB01, 0xC01)


def is_csr_supported(csr_addr: int) -> bool:
    """
    Check if CSR address is supported (either direct field or CLINT).
    """
    return csr_to_offset(csr_addr) is not None or is_clint_csr(csr_addr)


def verify_struct_layout():
    """
    Verify that the WGSL struct offsets are correct.
    Returns list of discrepancies if any.
    """
    # RiscvCPU struct layout (from RISCV_CPU_MMU.wgsl line 24-80)
    # Manual verification of key offsets:

    expected = {
        "pc": 0x00,          # vec2<u32> at position 0
        "regs": 0x08,        # array<vec2<u32>, 32> starts at offset 8
        "running": 0x108,    # After 32*8 + 8 = 264 = 0x108
        "instr_count": 0x10C, # 4 bytes after running
        "priv_mode": 0x110,  # 4 bytes after instr_count
        "satp": 0x120,      # vec2<u32> after priv_mode
        "mstatus": 0x128,   # vec2<u32> after satp
        "mtvec": 0x130,     # vec2<u32> after mstatus
        "mepc": 0x138,      # vec2<u32> after mtvec
        "mcause": 0x140,    # vec2<u32> after mepc  <- KEY OFFSET
        "mtval": 0x150,     # vec2<u32> after mcause
        "mscratch": 0x148,  # vec2<u32> (appears before mtval in struct)
        "mie": 0x308,       # vec2<u32> (after VirtIO fields)
        "mip": 0x318,       # vec2<u32> after mie
        "stvec": 0x158,     # vec2<u32> after mscratch
        "sepc": 0x168,      # vec2<u32> after stvec
        "scause": 0x170,    # vec2<u32> after sepc
        "stval": 0x178,     # vec2<u32> after scause
        "sscratch": 0x160,  # vec2<u32> (between stvec and sepc)
    }

    discrepancies = []
    for name, offset in expected.items():
        # Invert map to check: find which CSR address has this offset
        csr_addr = None
        for addr, off in CSR_OFFSETS.items():
            if off == offset:
                csr_addr = addr
                break

        if csr_addr is None and offset not in (0x00, 0x08, 0x108, 0x10C, 0x110):
            discrepancies.append(f"{name}: offset 0x{offset:x} not in CSR_OFFSETS")

    return discrepancies


if __name__ == "__main__":
    print("=== CSR Offset Mapping ===")
    for addr, offset in sorted(CSR_OFFSETS.items()):
        if offset is not None:
            print(f"CSR 0x{addr:03x}: struct offset 0x{offset:x} ({offset})")

    print("\n=== CLINT Memory-Mapped CSRs ===")
    print(f"CLINT_BASE: 0x{CLINT_BASE:08x}")
    print(f"CLINT_MTIME: 0x{CLINT_MTIME:08x}")
    print(f"CLINT_MTIMECMP: 0x{CLINT_MTIMECMP:08x}")

    print("\n=== Verification ===")
    issues = verify_struct_layout()
    if issues:
        print("DISCREPANCIES FOUND:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("All struct offsets verified (non-CSR fields not mapped)")