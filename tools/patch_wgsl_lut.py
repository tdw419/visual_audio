import re
with open("tools/SPATIAL_RV64I.wgsl", "r") as f:
    code = f.read()

# Add LUT binding
lut_binding = """@group(0) @binding(4) var<storage, read_write> uart_tx: array<u32, 4096>;
@group(0) @binding(5) var<storage, read> hilbert_lut: array<u32>;"""
code = code.replace("@group(0) @binding(4) var<storage, read_write> uart_tx: array<u32, 4096>;", lut_binding)

# Replace d2idx
old_d2idx = """fn d2idx(d: u32) -> u32 {
    let xy = d2xy(16777216u, d);
    let width = 4096u;
    return xy.y * width + xy.x;
}"""
new_d2idx = """fn d2idx(d: u32) -> u32 {
    return hilbert_lut[d];
}"""
code = code.replace(old_d2idx, new_d2idx)

with open("tools/SPATIAL_RV64I.wgsl", "w") as f:
    f.write(code)
