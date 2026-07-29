with open("tools/SPATIAL_RV64I.wgsl", "r") as f:
    content = f.read()

target = """    } else if (addr == CSR_SIP) {
        csrs[CSR_MIP].x = (csrs[CSR_MIP].x & ~csrs[CSR_MIDELEG].x) | (val.x & csrs[CSR_MIDELEG].x);
        csrs[CSR_MIP].y = (csrs[CSR_MIP].y & ~csrs[CSR_MIDELEG].y) | (val.y & csrs[CSR_MIDELEG].y);
    } else {"""

replacement = """    } else if (addr == CSR_SIP) {
        csrs[CSR_MIP].x = (csrs[CSR_MIP].x & ~csrs[CSR_MIDELEG].x) | (val.x & csrs[CSR_MIDELEG].x);
        csrs[CSR_MIP].y = (csrs[CSR_MIP].y & ~csrs[CSR_MIDELEG].y) | (val.y & csrs[CSR_MIDELEG].y);
    } else if (addr == CSR_SATP) {
        let mode = val.y >> 28u;
        if (mode == 0u || mode == 8u) {
            csrs[addr] = val;
        }
    } else {"""

if target in content:
    content = content.replace(target, replacement)
    with open("tools/SPATIAL_RV64I.wgsl", "w") as f:
        f.write(content)
    print("Patched!")
else:
    print("Could not find target!")
