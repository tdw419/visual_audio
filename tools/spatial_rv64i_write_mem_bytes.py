"""write_mem_bytes GPU-accelerated implementation to be pasted into spatial_rv64i_cpu.py"""

    def write_mem_bytes(self, byte_addr: int, data: bytes):
        """Write an arbitrary byte blob into (Hilbert-mapped) physical memory, e.g. a DTB.
        byte_addr is buffer-relative; must be 4-byte aligned. Pads the tail to a whole word."""
        assert byte_addr >= 0, f"byte_addr must be non-negative, got {byte_addr}"
        assert byte_addr % 4 == 0, f"byte_addr must be 4-byte aligned, got {byte_addr}"
        assert byte_addr < self.memory.buffer.size, f"byte_addr {byte_addr} exceeds buffer size {self.memory.buffer.size}"

        padded = data + b'\x00' * ((4 - len(data) % 4) % 4)
        words = np.frombuffer(padded, dtype=np.uint32)

        # For small writes (<64KB), use the word-by-word approach (simpler, less overhead)
        if len(words) < 16384:  # 64KB
            for i, word in enumerate(words):
                self.write_mem_word(byte_addr + i * 4, int(word))
            return

        mem_len = self.memory.buffer.size // 4
        N = int(np.sqrt(mem_len))
        num_words = len(words)
        BASE_OFFSET = byte_addr // 4

        # Write raw linear data to staging buffer
        staging_buffer = self.device.create_buffer(
            size=len(words) * 4,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST
        )
        self.queue.write_buffer(staging_buffer, 0, words.tobytes())

        # Dispatch in chunks to respect 65535 workgroup limit
        WORKGROUP_SIZE = 64
        WORDS_PER_DISPATCH = 65535 * WORKGROUP_SIZE  # ~4MB per dispatch

        for dispatch_offset in range(0, num_words, WORDS_PER_DISPATCH):
            dispatch_words = min(WORDS_PER_DISPATCH, num_words - dispatch_offset)
            workgroups = (dispatch_words + WORKGROUP_SIZE - 1) // WORKGROUP_SIZE
            chunk_offset = BASE_OFFSET + dispatch_offset

            chunk_shader = self.device.create_shader_module(code=f'''
@group(0) @binding(0) var<storage, read_write> dest: array<u32>;
@group(0) @binding(1) var<storage, read> src: array<u32>;
const N: u32 = {N}u;
const OFFSET: u32 = {chunk_offset}u;

fn d2xy(n: u32, d: u32) -> vec2<u32> {{
    var t = d;
    var x: u32 = 0u;
    var y: u32 = 0u;
    var s: u32 = 1u;
    while (s < n) {{
        let rx = (t / 2u) & 1u;
        let ry = (t ^ rx) & 1u;
        if (ry == 0u) {{
            if (rx == 1u) {{
                x = s - 1u - x;
                y = s - 1u - y;
            }}
            let tmp = x;
            x = y;
            y = tmp;
        }}
        x = x + s * rx;
        y = y + s * ry;
        t = t / 4u;
        s = s * 2u;
    }}
    return vec2<u32>(x, y);
}}

@compute @workgroup_size({WORKGROUP_SIZE})
fn main(@builtin(global_invocation_id) global_id: vec3<u32>) {{
    let i = global_id.x;
    if (i >= arrayLength(&src)) {{ return; }}

    let linear_idx = OFFSET + i;
    let xy = d2xy(N, linear_idx);
    let hilbert_idx = xy.y * N + xy.x;
    dest[hilbert_idx] = src[i];
}}
''')

            chunk_pipeline = self.device.create_compute_pipeline(
                layout=self.device.create_pipeline_layout(bind_group_layouts=[
                    self.device.create_bind_group_layout(entries=[
                        {'binding': 0, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
                        {'binding': 1, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'read-only-storage'}},
                    ])
                ]),
                compute={'module': chunk_shader, 'entry_point': 'main'},
            )

            chunk_bind_group = self.device.create_bind_group(
                layout=chunk_pipeline.get_bind_group_layout(0),
                entries=[
                    {'binding': 0, 'resource': {'buffer': self.memory.buffer, 'offset': 0, 'size': self.memory.buffer.size}},
                    {'binding': 1, 'resource': {'buffer': staging_buffer, 'offset': dispatch_offset * 4, 'size': dispatch_words * 4}},
                ]
            )

            encoder = self.device.create_command_encoder()
            compute_pass = encoder.begin_compute_pass()
            compute_pass.set_pipeline(chunk_pipeline)
            compute_pass.set_bind_group(0, chunk_bind_group)
            compute_pass.dispatch_workgroups(workgroups)
            compute_pass.end()
            self.queue.submit([encoder.finish()])