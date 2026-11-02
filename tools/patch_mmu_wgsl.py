import re

with open('tools/RISCV_CPU_MMU.wgsl', 'r') as f:
    code = f.read()

# Fix VPN2 extraction
code = re.sub(
    r'fn extract_vpn2\(va: vec2<u32>\) -> u32 \{.*?\}',
    '''fn extract_vpn2(va: vec2<u32>) -> u32 {
    let high_vpn = (va.y & 0x7Fu) << 2u;
    let low_vpn = va.x >> 30u;
    return high_vpn | low_vpn;
}''',
    code, flags=re.DOTALL
)

# Fix VPN1
code = re.sub(
    r'fn extract_vpn1\(va: vec2<u32>\) -> u32 \{.*?\}',
    '''fn extract_vpn1(va: vec2<u32>) -> u32 {
    return (va.x >> 21u) & 0x1FFu;
}''',
    code, flags=re.DOTALL
)

# Fix VPN0
code = re.sub(
    r'fn extract_vpn0\(va: vec2<u32>\) -> u32 \{.*?\}',
    '''fn extract_vpn0(va: vec2<u32>) -> u32 {
    return (va.x >> 12u) & 0x1FFu;
}''',
    code, flags=re.DOTALL
)

# Fix PPN additions (shift PPN by 12)
code = code.replace(
    'let l1_pte_pa = add64(root_ppn, vec2<u32>(l1_vpn * 4u, 0u));',
    'let l1_pte_pa = add64(vec2<u32>(root_ppn.x << 12u, root_ppn.y), vec2<u32>(l1_vpn * 4u, 0u));'
)
code = code.replace(
    'let l2_pte_pa = add64(l2_ppn, vec2<u32>(l2_vpn * 4u, 0u));',
    'let l2_pte_pa = add64(vec2<u32>(l2_ppn.x << 12u, l2_ppn.y), vec2<u32>(l2_vpn * 4u, 0u));'
)
code = code.replace(
    'let l3_pte_pa = add64(l3_ppn, vec2<u32>(l3_vpn * 4u, 0u));',
    'let l3_pte_pa = add64(vec2<u32>(l3_ppn.x << 12u, l3_ppn.y), vec2<u32>(l3_vpn * 4u, 0u));'
)

# Set SATP_MODE_SV39 to 8 just in case
code = re.sub(r'const SATP_MODE_SV39: u32 = .*?;', 'const SATP_MODE_SV39: u32 = 8u;', code)

with open('tools/RISCV_CPU_MMU.wgsl', 'w') as f:
    f.write(code)
