import re
with open("tools/SPATIAL_RV64I.wgsl", "r") as f:
    code = f.read()

code = code.replace("@group(0) @binding(4) var<storage, read_write> uart_tx: array<u32, 4096>;\n@group(0) @binding(5) var<storage, read> hilbert_lut: array<u32>;", "@group(0) @binding(4) var<storage, read_write> uart_tx: array<u32, 4096>;")

old_d2idx = """fn d2idx(d: u32) -> u32 {
    return hilbert_lut[d];
}"""
new_d2idx = """fn d2idx(d: u32) -> u32 {
    let xy = d2xy(16777216u, d);
    let width = 4096u;
    return xy.y * width + xy.x;
}"""
code = code.replace(old_d2idx, new_d2idx)

with open("tools/SPATIAL_RV64I.wgsl", "w") as f:
    f.write(code)

with open("tools/spatial_rv64i_cpu.py", "r") as f:
    code = f.read()

code = re.sub(r'        self\.lut_buffer = self\.device\.create_buffer\(\n            size=\(memory_size_bytes // 4\) \* 4,\n            usage=wgpu\.BufferUsage\.STORAGE \| wgpu\.BufferUsage\.COPY_DST\n        \)\n', '', code)
code = re.sub(r'                    \{\n                        "binding": 5,\n                        "visibility": wgpu\.ShaderStage\.COMPUTE,\n                        "buffer": \{"type": wgpu\.BufferBindingType\.read_only_storage\}\n                    \},\n', '', code)
code = re.sub(r'                    \{"binding": 5, "resource": \{"buffer": self\.lut_buffer, "offset": 0, "size": self\.lut_buffer\.size\}\},\n', '', code)

with open("tools/spatial_rv64i_cpu.py", "w") as f:
    f.write(code)
