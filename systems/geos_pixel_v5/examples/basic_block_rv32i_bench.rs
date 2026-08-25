// Measures whether basic-block threading (decode once on the host,
// execute pre-decoded ops with zero runtime bitfield/sign-extension work)
// recovers the 31-46x decode-tax measured in multi_instance_rv32i_bench.rs.
// Decodes the SAME machine-code bytes (tools/rv32i_assembler.py's
// sum-1-to-N program, independently verified against objdump) rather than
// a different/simplified program, so this isolates exactly one variable:
// runtime decode vs. precomputed ops.
#[cfg(feature = "gpu")]
fn main() {
    use std::time::Instant;
    use wgpu::util::DeviceExt;

    let n_instances: u32 = std::env::args()
        .nth(1)
        .and_then(|s| s.parse().ok())
        .unwrap_or(1_000_000);
    println!("N = {n_instances} independent RV32I machines (basic-block threaded)");

    // Same bytes as multi_instance_rv32i_bench.rs, verified against
    // `riscv64-linux-gnu-objdump -m riscv:rv32` before use.
    const PROGRAM: [u32; 9] = [
        0x00000093, 0x00002103, 0x00100193, 0x00314863, 0x003080b3,
        0x00118193, 0xff5ff06f, 0x00102223, 0x00000073,
    ];

    #[repr(C)]
    #[derive(Clone, Copy, bytemuck::Pod, bytemuck::Zeroable)]
    struct DecodedOp {
        op: u32,
        rd: u32,
        rs1: u32,
        rs2: u32,
        imm: u32,
    }

    // Host-side decoder: mirrors multi_instance_rv32i.wgsl's field
    // extraction exactly, but runs ONCE per program instead of once per
    // instruction per lane per step. Branch/jump byte offsets are
    // resolved to op-indices here (op_index = byte_addr / 4), removing
    // that arithmetic from the hot loop too.
    fn decode(words: &[u32]) -> Vec<DecodedOp> {
        words
            .iter()
            .enumerate()
            .map(|(i, &instr)| {
                let opcode = instr & 0x7F;
                let rd = (instr >> 7) & 0x1F;
                let funct3 = (instr >> 12) & 0x7;
                let rs1 = (instr >> 15) & 0x1F;
                let rs2 = (instr >> 20) & 0x1F;
                let imm_i = ((instr as i32) >> 20) as u32;
                let imm_s = ((((instr & 0xFE000000) as i32) >> 20) as u32) | ((instr >> 7) & 0x1F);
                let b12 = (instr >> 31) & 1;
                let b11 = (instr >> 7) & 1;
                let b10_5 = (instr >> 25) & 0x3F;
                let b4_1 = (instr >> 8) & 0xF;
                let imm_b_raw = (b12 << 12) | (b11 << 11) | (b10_5 << 5) | (b4_1 << 1);
                let imm_b = (((imm_b_raw << 19) as i32) >> 19) as u32;
                let j20 = (instr >> 31) & 1;
                let j19_12 = (instr >> 12) & 0xFF;
                let j11 = (instr >> 20) & 1;
                let j10_1 = (instr >> 21) & 0x3FF;
                let imm_j_raw = (j20 << 20) | (j19_12 << 12) | (j11 << 11) | (j10_1 << 1);
                let imm_j = (((imm_j_raw << 11) as i32) >> 11) as u32;

                let pc = (i as u32) * 4;
                match (opcode, funct3) {
                    (0x13, 0x0) => DecodedOp { op: 0, rd, rs1, rs2: 0, imm: imm_i }, // ADDI
                    (0x03, 0x2) => DecodedOp { op: 1, rd, rs1, rs2: 0, imm: imm_i }, // LW
                    (0x23, 0x2) => DecodedOp { op: 2, rd: rs2, rs1, rs2: 0, imm: imm_s }, // SW (value in rd slot)
                    (0x63, 0x4) => {
                        // BLT: target op-index = (pc + imm_b) / 4
                        let target = ((pc as i32) + (imm_b as i32)) as u32 / 4;
                        DecodedOp { op: 3, rd: rs1, rs1: rs2, rs2: 0, imm: target }
                    }
                    (0x6F, _) => {
                        let target = ((pc as i32) + (imm_j as i32)) as u32 / 4;
                        DecodedOp { op: 4, rd, rs1: 0, rs2: 0, imm: target } // JAL
                    }
                    (0x33, 0x0) => DecodedOp { op: 5, rd, rs1, rs2, imm: 0 }, // ADD
                    (0x73, _) => DecodedOp { op: 6, rd: 0, rs1: 0, rs2: 0, imm: 0 }, // ECALL/HALT
                    _ => panic!("unsupported instruction 0x{instr:08x} at pc={pc}"),
                }
            })
            .collect()
    }

    let decoded_ops = decode(&PROGRAM);
    println!("Decoded {} ops once on host (shared read-only across all lanes)", decoded_ops.len());

    const RAM_WORDS_PER_INSTANCE: u32 = 2;
    let inputs: Vec<u32> = (0..n_instances).map(|i| 2 + i % 150).collect();
    let mut ram = vec![0u32; (n_instances * RAM_WORDS_PER_INSTANCE) as usize];
    for i in 0..n_instances as usize {
        ram[i * RAM_WORDS_PER_INSTANCE as usize] = inputs[i];
    }

    fn native_sum(n: u32) -> u32 {
        let mut sum = 0u32;
        let mut i = 1u32;
        while i <= n {
            sum = sum.wrapping_add(i);
            i += 1;
        }
        sum
    }
    let cpu_start = Instant::now();
    let cpu_result: Vec<u32> = inputs.iter().map(|&n| native_sum(n)).collect();
    let cpu_elapsed = cpu_start.elapsed();
    println!(
        "CPU (native loop, sequential): {:?} total, {:.0} instances/sec",
        cpu_elapsed,
        n_instances as f64 / cpu_elapsed.as_secs_f64()
    );

    let instance = wgpu::Instance::default();
    let adapter = pollster::block_on(instance.request_adapter(&wgpu::RequestAdapterOptions::default()))
        .expect("no GPU adapter");
    println!("GPU adapter: {}", adapter.get_info().name);
    let limits = adapter.limits();
    let (device, queue) = pollster::block_on(adapter.request_device(
        &wgpu::DeviceDescriptor { required_limits: limits, ..Default::default() },
        None,
    ))
    .expect("request_device");

    let spv_bytes = std::fs::read("shaders/basic_block_rv32i.spv").expect("read compiled SPIR-V");
    let words: Vec<u32> = spv_bytes
        .chunks_exact(4)
        .map(|c| u32::from_ne_bytes([c[0], c[1], c[2], c[3]]))
        .collect();
    let shader = device.create_shader_module(wgpu::ShaderModuleDescriptor {
        label: Some("basic_block_rv32i"),
        source: wgpu::ShaderSource::SpirV(std::borrow::Cow::Owned(words)),
    });

    let program_buffer = device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
        label: Some("program (shared, read-only)"),
        contents: bytemuck::cast_slice(&decoded_ops),
        usage: wgpu::BufferUsages::STORAGE,
    });
    let ram_buffer = device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
        label: Some("ram"),
        contents: bytemuck::cast_slice(&ram),
        usage: wgpu::BufferUsages::STORAGE | wgpu::BufferUsages::COPY_SRC | wgpu::BufferUsages::COPY_DST,
    });
    let ram_staging = device.create_buffer(&wgpu::BufferDescriptor {
        label: Some("ram staging"),
        size: (ram.len() * 4) as u64,
        usage: wgpu::BufferUsages::MAP_READ | wgpu::BufferUsages::COPY_DST,
        mapped_at_creation: false,
    });

    let pipeline = device.create_compute_pipeline(&wgpu::ComputePipelineDescriptor {
        label: Some("basic_block_rv32i pipeline"),
        layout: None,
        module: &shader,
        entry_point: "main",
        compilation_options: Default::default(),
    });
    let bind_group = device.create_bind_group(&wgpu::BindGroupDescriptor {
        label: Some("bind group"),
        layout: &pipeline.get_bind_group_layout(0),
        entries: &[
            wgpu::BindGroupEntry { binding: 0, resource: program_buffer.as_entire_binding() },
            wgpu::BindGroupEntry { binding: 1, resource: ram_buffer.as_entire_binding() },
        ],
    });

    let workgroups = (n_instances + 63) / 64;
    let gpu_start = Instant::now();
    let mut encoder = device.create_command_encoder(&wgpu::CommandEncoderDescriptor::default());
    {
        let mut pass = encoder.begin_compute_pass(&wgpu::ComputePassDescriptor::default());
        pass.set_pipeline(&pipeline);
        pass.set_bind_group(0, &bind_group, &[]);
        pass.dispatch_workgroups(workgroups, 1, 1);
    }
    encoder.copy_buffer_to_buffer(&ram_buffer, 0, &ram_staging, 0, (ram.len() * 4) as u64);
    queue.submit(Some(encoder.finish()));

    let slice = ram_staging.slice(..);
    slice.map_async(wgpu::MapMode::Read, |r| r.unwrap());
    device.poll(wgpu::Maintain::Wait);
    let gpu_elapsed = gpu_start.elapsed();
    let ram_result: Vec<u32> = bytemuck::cast_slice(&slice.get_mapped_range()).to_vec();

    println!(
        "GPU (basic-block threaded, {} independent machines): {:?} total, {:.0} instances/sec",
        n_instances,
        gpu_elapsed,
        n_instances as f64 / gpu_elapsed.as_secs_f64()
    );

    let mut failures = 0;
    for i in 0..n_instances as usize {
        let got = ram_result[i * RAM_WORDS_PER_INSTANCE as usize + 1];
        if got != cpu_result[i] {
            failures += 1;
            if failures <= 5 {
                eprintln!("MISMATCH instance {i}: N={} cpu={} gpu={got}", inputs[i], cpu_result[i]);
            }
        }
    }
    if failures > 0 {
        panic!("{failures}/{n_instances} instances produced wrong results");
    }
    println!("PASS: all {n_instances} basic-block-threaded machines match the CPU baseline exactly");

    let speedup_vs_cpu = cpu_elapsed.as_secs_f64() / gpu_elapsed.as_secs_f64();
    println!("\nSpeedup (basic-block GPU vs CPU sequential): {speedup_vs_cpu:.2}x");
    println!(
        "\nCompare against multi_instance_rv32i_bench.rs's own numbers at this N to see how much \
         of the 31-46x decode tax basic-block threading recovers."
    );
}

#[cfg(not(feature = "gpu"))]
fn main() {
    eprintln!("This example requires the 'gpu' feature. Run with: --features gpu");
    std::process::exit(1);
}
