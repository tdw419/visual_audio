import re

with open('tools/spatial_rv64i_cpu.py', 'r') as f:
    py = f.read()

py = py.replace('size=4096 * 4, usage=wgpu.BufferUsage.STORAGE', 'size=4096 * 8, usage=wgpu.BufferUsage.STORAGE')
py = py.replace('np.zeros(4096, dtype=np.uint32)', 'np.zeros(4096 * 2, dtype=np.uint32)')

py = re.sub(
    r'def read_csr\(self, addr: int\) -> int:[\s\S]*?return int\(np\.frombuffer\(csr_bytes, dtype=np\.uint32\)\[0\]\)',
    r'''def read_csr(self, addr: int) -> int:
        """Read a CSR directly from the flat CSR file (bypasses csrrX instructions)."""
        csr_bytes = self.queue.read_buffer(self.csr_buffer, buffer_offset=addr * 8, size=8)
        low, high = np.frombuffer(csr_bytes, dtype=np.uint32)
        return int(np.uint64((int(high) << 32) | int(low)))''',
    py
)

py = re.sub(
    r'def write_csr\(self, addr: int, value: int\):[\s\S]*?self\.queue\.write_buffer\(self\.csr_buffer, addr \* 4, np\.array\(\[value\], dtype=np\.uint32\)\.tobytes\(\)\)',
    r'''def write_csr(self, addr: int, value: int):
        """Write a CSR directly into the flat CSR file (e.g. to install a trap vector before running)."""
        low = value & 0xFFFFFFFF
        high = (value >> 32) & 0xFFFFFFFF
        self.queue.write_buffer(self.csr_buffer, addr * 8, np.array([low, high], dtype=np.uint32).tobytes())''',
    py
)

with open('tools/spatial_rv64i_cpu.py', 'w') as f:
    f.write(py)

with open('tools/SPATIAL_RV64I.wgsl', 'r') as f:
    wgsl = f.read()

wgsl = wgsl.replace('var<storage, read_write> csrs: array<u32, 4096>;', 'var<storage, read_write> csrs: array<vec2<u32>, 4096>;')

# Update csr_read / csr_write
wgsl = re.sub(
    r'fn csr_read\(addr: u32\) -> u32 \{[\s\S]*?return csrs\[addr\];\n\}',
    r'''fn csr_read(addr: u32) -> vec2<u32> {
    if (addr == CSR_SSTATUS) {
        return vec2<u32>(csrs[CSR_MSTATUS].x & SSTATUS_MASK, csrs[CSR_MSTATUS].y);
    }
    return csrs[addr];
}''',
    wgsl
)

wgsl = re.sub(
    r'fn csr_write\(addr: u32, val: u32\) \{[\s\S]*?csrs\[addr\] = val;\n    \}\n\}',
    r'''fn csr_write(addr: u32, val: vec2<u32>) {
    if (addr == CSR_SSTATUS) {
        csrs[CSR_MSTATUS].x = (csrs[CSR_MSTATUS].x & ~SSTATUS_MASK) | (val.x & SSTATUS_MASK);
        csrs[CSR_MSTATUS].y = val.y;
    } else {
        csrs[addr] = val;
    }
}''',
    wgsl
)

# Update MIP access
wgsl = wgsl.replace('csrs[CSR_MIP] = csrs[CSR_MIP] & ~0x80u;', 'csrs[CSR_MIP].x = csrs[CSR_MIP].x & ~0x80u;')
wgsl = wgsl.replace('csrs[CSR_MIP] = csrs[CSR_MIP] | 0x80u;', 'csrs[CSR_MIP].x = csrs[CSR_MIP].x | 0x80u;')
wgsl = wgsl.replace('((csrs[CSR_MIP] & csrs[CSR_MIE]) & 0x80u)', '((csrs[CSR_MIP].x & csrs[CSR_MIE].x) & 0x80u)')

# Update raise_trap
old_raise_trap = r'''fn raise_trap\(cause: u32, tval: u32, pc: u32\) -> u32 \{
    let delegate = \(state\.mode != 3u\) && \(\(\(csrs\[CSR_MEDELEG\] >> cause\) & 1u\) == 1u\);
    if \(delegate\) \{
        csrs\[CSR_SEPC\] = pc;
        csrs\[CSR_SCAUSE\] = cause;
        csrs\[CSR_STVAL\] = tval;
        var mstatus = csrs\[CSR_MSTATUS\];
        let sie = \(mstatus >> 1u\) & 1u;
        let spp = select\(0u, 1u, state\.mode == 1u\);
        mstatus = \(mstatus & ~SSTATUS_MASK\) \| \(sie << 5u\) \| \(spp << 8u\);
        csrs\[CSR_MSTATUS\] = mstatus;
        state\.mode = 1u;
        if \(csrs\[CSR_STVEC\] == 0u\) \{
            state\.halted = 1u;
            return pc;
        \}
        // RV64: trap vectors are zero-extended to 64-bit \(CSRs are 32-bit\)
        let vec = csrs\[CSR_STVEC\] & 0xFFFFFFFCu;
        state\.pc_low = vec;
        state\.pc_high = 0u;
        return vec;
    \} else \{
        csrs\[CSR_MEPC\] = pc;
        csrs\[CSR_MCAUSE\] = cause;
        csrs\[CSR_MTVAL\] = tval;
        var mstatus = csrs\[CSR_MSTATUS\];
        let mie = \(mstatus >> 3u\) & 1u;
        mstatus = \(mstatus & ~MSTATUS_TRAP_MASK\) \| \(mie << 7u\) \| \(state\.mode << 11u\);
        csrs\[CSR_MSTATUS\] = mstatus;
        state\.mode = 3u;
        if \(csrs\[CSR_MTVEC\] == 0u\) \{
            state\.halted = 1u;
            return pc;
        \}
        // RV64: trap vectors are zero-extended to 64-bit \(CSRs are 32-bit\)
        let vec = csrs\[CSR_MTVEC\] & 0xFFFFFFFCu;
        state\.pc_low = vec;
        state\.pc_high = 0u;
        return vec;
    \}
\}'''

new_raise_trap = '''fn raise_trap(cause: u32, tval: vec2<u32>, pc: vec2<u32>) -> vec2<u32> {
    let delegate = (state.mode != 3u) && (((csrs[CSR_MEDELEG].x >> cause) & 1u) == 1u);
    let cause_hi = select(0u, 0x80000000u, (cause >> 31u) != 0u);
    let cause_lo = cause & 0x7FFFFFFFu;
    if (delegate) {
        csrs[CSR_SEPC] = pc;
        csrs[CSR_SCAUSE] = vec2<u32>(cause_lo, cause_hi);
        csrs[CSR_STVAL] = tval;
        var mstatus = csrs[CSR_MSTATUS].x;
        let sie = (mstatus >> 1u) & 1u;
        let spp = select(0u, 1u, state.mode == 1u);
        mstatus = (mstatus & ~SSTATUS_MASK) | (sie << 5u) | (spp << 8u);
        csrs[CSR_MSTATUS].x = mstatus;
        state.mode = 1u;
        if (u64_is_zero(csrs[CSR_STVEC])) {
            state.halted = 1u;
            return pc;
        }
        let vec = vec2<u32>(csrs[CSR_STVEC].x & 0xFFFFFFFCu, csrs[CSR_STVEC].y);
        state.pc_low = vec.x;
        state.pc_high = vec.y;
        return vec;
    } else {
        csrs[CSR_MEPC] = pc;
        csrs[CSR_MCAUSE] = vec2<u32>(cause_lo, cause_hi);
        csrs[CSR_MTVAL] = tval;
        var mstatus = csrs[CSR_MSTATUS].x;
        let mie = (mstatus >> 3u) & 1u;
        mstatus = (mstatus & ~MSTATUS_TRAP_MASK) | (mie << 7u) | (state.mode << 11u);
        csrs[CSR_MSTATUS].x = mstatus;
        state.mode = 3u;
        if (u64_is_zero(csrs[CSR_MTVEC])) {
            state.halted = 1u;
            return pc;
        }
        let vec = vec2<u32>(csrs[CSR_MTVEC].x & 0xFFFFFFFCu, csrs[CSR_MTVEC].y);
        state.pc_low = vec.x;
        state.pc_high = vec.y;
        return vec;
    }
}'''
wgsl = re.sub(old_raise_trap, new_raise_trap, wgsl)

# Update do_mret
wgsl = re.sub(
    r'fn do_mret\(\) -> u32 \{[\s\S]*?return csrs\[CSR_MEPC\];\n\}',
    r'''fn do_mret() -> vec2<u32> {
    var mstatus = csrs[CSR_MSTATUS].x;
    let mpie = (mstatus >> 7u) & 1u;
    let mpp = (mstatus >> 11u) & 3u;
    mstatus = (mstatus & ~MSTATUS_TRAP_MASK) | (mpie << 3u) | (1u << 7u);
    csrs[CSR_MSTATUS].x = mstatus;
    state.mode = mpp;
    return csrs[CSR_MEPC];
}''',
    wgsl
)

# Update do_sret
wgsl = re.sub(
    r'fn do_sret\(\) -> u32 \{[\s\S]*?return csrs\[CSR_SEPC\];\n\}',
    r'''fn do_sret() -> vec2<u32> {
    var mstatus = csrs[CSR_MSTATUS].x;
    let spie = (mstatus >> 5u) & 1u;
    let spp = (mstatus >> 8u) & 1u;
    mstatus = (mstatus & ~SSTATUS_MASK) | (spie << 1u) | (1u << 5u);
    csrs[CSR_MSTATUS].x = mstatus;
    state.mode = spp;
    return csrs[CSR_SEPC];
}''',
    wgsl
)

# Update maybe_take_interrupt
old_mti = r'''    csrs\[CSR_MEPC\] = state\.pc_low;
    csrs\[CSR_MCAUSE\] = 0x80000007u; // interrupt bit set, code 7 = machine timer interrupt
    csrs\[CSR_MTVAL\] = 0u;
    let mie_bit = \(mstatus >> 3u\) & 1u;
    csrs\[CSR_MSTATUS\] = \(mstatus & ~MSTATUS_TRAP_MASK\) \| \(mie_bit << 7u\) \| \(state\.mode << 11u\);
    state\.mode = 3u;

    if \(csrs\[CSR_MTVEC\] == 0u\) \{
        state\.halted = 1u;
    \} else \{
        // RV64: trap vectors are zero-extended to 64-bit \(CSRs are 32-bit\)
        let vec = csrs\[CSR_MTVEC\] & 0xFFFFFFFCu;
        state\.pc_low = vec;
        state\.pc_high = 0u;
    \}'''

new_mti = '''    csrs[CSR_MEPC] = vec2<u32>(state.pc_low, state.pc_high);
    csrs[CSR_MCAUSE] = vec2<u32>(7u, 0x80000000u); // interrupt bit 63 set
    csrs[CSR_MTVAL] = vec2<u32>(0u, 0u);
    let mie_bit = (mstatus >> 3u) & 1u;
    csrs[CSR_MSTATUS].x = (mstatus & ~MSTATUS_TRAP_MASK) | (mie_bit << 7u) | (state.mode << 11u);
    state.mode = 3u;

    if (u64_is_zero(csrs[CSR_MTVEC])) {
        state.halted = 1u;
    } else {
        let vec = vec2<u32>(csrs[CSR_MTVEC].x & 0xFFFFFFFCu, csrs[CSR_MTVEC].y);
        state.pc_low = vec.x;
        state.pc_high = vec.y;
    }'''
wgsl = re.sub(old_mti, new_mti, wgsl)

wgsl = wgsl.replace('let mstatus = csrs[CSR_MSTATUS];', 'let mstatus = csrs[CSR_MSTATUS].x;')

# translate_address SATP usage
wgsl = wgsl.replace('if (((csrs[CSR_SATP] >> 31u) & 1u) == 0u) {', 'if (((csrs[CSR_SATP].y >> 31u) & 1u) == 0u) {')
wgsl = wgsl.replace('let root_ppn = csrs[CSR_SATP] & 0x3FFFFFu;', 'let root_ppn = csrs[CSR_SATP].x & 0x3FFFFFu;')

# Calls to raise_trap
wgsl = wgsl.replace('raise_trap(12u, state.pc_low, state.pc_low)', 'raise_trap(12u, vec2<u32>(state.pc_low, state.pc_high), vec2<u32>(state.pc_low, state.pc_high)).x')
# Wait, fetch returns 0u if trapping, so the return value of raise_trap isn't strictly needed for fetch, except to set pc
# But raise_trap updates state.pc_low and state.pc_high directly, so the caller doesn't actually need the return value!
wgsl = wgsl.replace('state.pc_low = raise_trap(12u, state.pc_low, state.pc_low); // instruction page fault', 'let _dummy = raise_trap(12u, vec2<u32>(state.pc_low, state.pc_high), vec2<u32>(state.pc_low, state.pc_high)); // instruction page fault')

# In decode_and_execute
wgsl = wgsl.replace('next_pc = vec2<u32>(raise_trap(cause, 0u, state.pc_low), 0u);', 'next_pc = raise_trap(cause, vec2<u32>(0u, 0u), vec2<u32>(state.pc_low, state.pc_high));')
wgsl = wgsl.replace('next_pc = vec2<u32>(raise_trap(3u, 0u, state.pc_low), 0u); // ebreak', 'next_pc = raise_trap(3u, vec2<u32>(0u, 0u), vec2<u32>(state.pc_low, state.pc_high)); // ebreak')
wgsl = wgsl.replace('next_pc = vec2<u32>(do_mret(), 0u);', 'next_pc = do_mret();')
wgsl = wgsl.replace('next_pc = vec2<u32>(do_sret(), 0u);', 'next_pc = do_sret();')

# CSR instructions inside decode_and_execute
old_csr = r'''            if \(funct3 == 1u\) \{
                new_val = rs1_val\.x; // csrrw
            \} else if \(funct3 == 2u\) \{
                new_val = old_val \| rs1_val\.x; // csrrs
            \} else if \(funct3 == 3u\) \{
                new_val = old_val & ~rs1_val\.x; // csrrc
            \} else if \(funct3 == 5u\) \{
                new_val = rs1; // csrrwi
            \} else if \(funct3 == 6u\) \{
                new_val = old_val \| rs1; // csrrsi
            \} else if \(funct3 == 7u\) \{
                new_val = old_val & ~rs1; // csrrci'''
new_csr = '''            if (funct3 == 1u) {
                new_val = rs1_val; // csrrw
            } else if (funct3 == 2u) {
                new_val = vec2<u32>(old_val.x | rs1_val.x, old_val.y | rs1_val.y); // csrrs
            } else if (funct3 == 3u) {
                new_val = vec2<u32>(old_val.x & ~rs1_val.x, old_val.y & ~rs1_val.y); // csrrc
            } else if (funct3 == 5u) {
                new_val = vec2<u32>(rs1, 0u); // csrrwi
            } else if (funct3 == 6u) {
                new_val = vec2<u32>(old_val.x | rs1, old_val.y); // csrrsi
            } else if (funct3 == 7u) {
                new_val = vec2<u32>(old_val.x & ~rs1, old_val.y); // csrrci'''
wgsl = re.sub(old_csr, new_csr, wgsl)

wgsl = wgsl.replace('if (rd != 0u) { registers.x[rd] = vec2<u32>(old_val, 0u); }', 'if (rd != 0u) { registers.x[rd] = old_val; }')

# Fix other raise_trap calls inside decode_and_execute (page faults, etc)
# e.g., next_pc = vec2<u32>(raise_trap(13u, addr.x, state.pc_low), 0u);
wgsl = re.sub(r'next_pc = vec2<u32>\(raise_trap\(([^,]+), ([^,]+), state\.pc_low\), 0u\);', r'next_pc = raise_trap(\1, vec2<u32>(\2, 0u), vec2<u32>(state.pc_low, state.pc_high));', wgsl)
wgsl = re.sub(r'next_pc = vec2<u32>\(raise_trap\(([^,]+), state\.pc_low, state\.pc_low\), 0u\);', r'next_pc = raise_trap(\1, vec2<u32>(state.pc_low, state.pc_high), vec2<u32>(state.pc_low, state.pc_high));', wgsl)


with open('tools/SPATIAL_RV64I.wgsl', 'w') as f:
    f.write(wgsl)
