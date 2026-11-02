import re

with open('tools/SPATIAL_RV64I.wgsl', 'r') as f:
    wgsl = f.read()

# 1. Add read_dword_phys
if 'fn read_dword_phys' not in wgsl:
    read_word_phys_idx = wgsl.find('fn read_word_phys')
    # Find end of read_word_phys
    end_idx = wgsl.find('}', read_word_phys_idx) + 1
    wgsl = wgsl[:end_idx] + '\n\nfn read_dword_phys(byte_addr: u32) -> vec2<u32> {\n    return vec2<u32>(read_word_phys(byte_addr), read_word_phys(byte_addr + 4u));\n}' + wgsl[end_idx:]

# 2. Replace translate_address
old_translate = r'''// Sv32 two-level page table walk\. Returns \(phys_addr, fault\) where fault != 0 means
// the translation failed \(invalid/misconfigured PTE or a permission violation\)\.
// Bypassed entirely when satp\.MODE \(bit 31\) is 0, i\.e\. translation is off \(M-mode default\)\.
fn translate_address\(va: u32, need_write: bool, need_exec: bool\) -> vec2<u32> \{[\s\S]*?return vec2<u32>\(\(leaf_ppn0 << 12u\) \| off, 0u\);\n\}'''

new_translate = '''// Sv39 three-level page table walk.
fn translate_address(va: vec2<u32>, need_write: bool, need_exec: bool) -> vec2<u32> {
    let satp_mode = csrs[CSR_SATP].y >> 28u;
    let is_m_mode = (state.mode == 3u);
    // TODO: proper MPRV handling. For now, M-mode bypasses translation.
    if (satp_mode != 8u || is_m_mode) {
        return vec2<u32>(va.x, 0u);
    }

    // Check VA sign extension from bit 38
    let bit38 = (va.y >> 6u) & 1u;
    let expected_hi = select(0u, 0x03FFFFFFu, bit38 == 1u);
    if ((va.y >> 6u) != expected_hi) {
        return vec2<u32>(0u, 1u); // page fault
    }

    let vpn0 = (va.x >> 12u) & 0x1FFu;
    let vpn1 = (va.x >> 21u) & 0x1FFu;
    let vpn2_lo = (va.x >> 30u) & 0x3u;
    let vpn2_hi = (va.y & 0x7Fu) << 2u;
    let vpn2 = vpn2_lo | vpn2_hi;
    let off = va.x & 0xFFFu;

    // We assume 32-bit physical addresses for our GPU memory limits
    let root_ppn = csrs[CSR_SATP].x; 
    
    // Level 2
    var pte_addr = (root_ppn * 4096u) + vpn2 * 8u;
    var pte = read_dword_phys(pte_addr);
    var v = pte.x & 1u;
    var r = (pte.x >> 1u) & 1u;
    var w = (pte.x >> 2u) & 1u;
    var x = (pte.x >> 3u) & 1u;
    if (v == 0u || (r == 0u && w == 1u)) { return vec2<u32>(0u, 1u); }
    if (r == 1u || x == 1u) {
        if (!check_perm(pte.x, need_write, need_exec)) { return vec2<u32>(0u, 1u); }
        let ppn0 = (pte.x >> 10u) & 0x1FFu;
        let ppn1 = (pte.x >> 19u) & 0x1FFu;
        if (ppn0 != 0u || ppn1 != 0u) { return vec2<u32>(0u, 1u); }
        let ppn2 = (pte.x >> 28u) | ((pte.y & 0xFFFFu) << 4u);
        return vec2<u32>((ppn2 << 30u) | (vpn1 << 21u) | (vpn0 << 12u) | off, 0u);
    }

    // Level 1
    let pt1_ppn = (pte.x >> 10u) | ((pte.y & 0xFFFFu) << 22u);
    pte_addr = (pt1_ppn * 4096u) + vpn1 * 8u;
    pte = read_dword_phys(pte_addr);
    v = pte.x & 1u;
    r = (pte.x >> 1u) & 1u;
    w = (pte.x >> 2u) & 1u;
    x = (pte.x >> 3u) & 1u;
    if (v == 0u || (r == 0u && w == 1u)) { return vec2<u32>(0u, 1u); }
    if (r == 1u || x == 1u) {
        if (!check_perm(pte.x, need_write, need_exec)) { return vec2<u32>(0u, 1u); }
        let ppn0 = (pte.x >> 10u) & 0x1FFu;
        if (ppn0 != 0u) { return vec2<u32>(0u, 1u); }
        let ppn1_2 = (pte.x >> 19u) | ((pte.y & 0xFFFFu) << 13u);
        return vec2<u32>((ppn1_2 << 21u) | (vpn0 << 12u) | off, 0u);
    }

    // Level 0
    let pt0_ppn = (pte.x >> 10u) | ((pte.y & 0xFFFFu) << 22u);
    pte_addr = (pt0_ppn * 4096u) + vpn0 * 8u;
    pte = read_dword_phys(pte_addr);
    v = pte.x & 1u;
    r = (pte.x >> 1u) & 1u;
    w = (pte.x >> 2u) & 1u;
    x = (pte.x >> 3u) & 1u;
    if (v == 0u || (r == 0u && w == 1u)) { return vec2<u32>(0u, 1u); }
    if (r == 0u && w == 0u && x == 0u) { return vec2<u32>(0u, 1u); } // no further levels
    if (!check_perm(pte.x, need_write, need_exec)) { return vec2<u32>(0u, 1u); }
    let ppn_all = (pte.x >> 10u) | ((pte.y & 0xFFFFu) << 22u);
    return vec2<u32>((ppn_all << 12u) | off, 0u);
}'''
wgsl = re.sub(old_translate, new_translate, wgsl)

# 3. Fix callers of translate_address
wgsl = wgsl.replace('let translated = translate_address(state.pc_low, false, true);', 'let translated = translate_address(vec2<u32>(state.pc_low, state.pc_high), false, true);')

wgsl = wgsl.replace('let addr64 = u64_add(rs1_val, sext_32_to_64(bitcast<i32>(imm)));\n        let addr = addr64.x;', 'let addr = u64_add(rs1_val, sext_32_to_64(bitcast<i32>(imm)));')
wgsl = wgsl.replace('let translated = translate_address(addr, false, false);', 'let translated = translate_address(addr, false, false);') # wait, addr is now vec2<u32>!
# but wait! mmio_read takes addr (which was u32). We need to change mmio_read to use addr.x!
wgsl = wgsl.replace('let mm = mmio_read(addr);', 'let mm = mmio_read(addr.x);')
wgsl = wgsl.replace('if (mmio_write(addr, rs2_val.x)) {', 'if (mmio_write(addr.x, rs2_val.x)) {')
wgsl = wgsl.replace('next_pc = raise_trap(13u, vec2<u32>(addr, 0u),', 'next_pc = raise_trap(13u, addr,')
wgsl = wgsl.replace('next_pc = raise_trap(15u, vec2<u32>(addr, 0u),', 'next_pc = raise_trap(15u, addr,')

wgsl = wgsl.replace('let translated = translate_address(rs1_val.x, !is_lr, false);', 'let translated = translate_address(rs1_val, !is_lr, false);')

with open('tools/SPATIAL_RV64I.wgsl', 'w') as f:
    f.write(wgsl)
