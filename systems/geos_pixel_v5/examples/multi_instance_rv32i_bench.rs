// Verifies "architecture (B)" from tonight's design discussion: N fully
// independent RV32I machines running as N GPU lanes, zero shared state,
// zero atomics - as opposed to (A), a coordinated multi-hart SMP guest,
// which would need CAS loops/IPI routing (shared-state serialization,
// the exact thing that loses on SIMT hardware). Each lane runs the same
// assembled RISC-V machine code (tools/rv32i_assembler.py's sum-1-to-N
// program), decoded and executed by multi_instance_rv32i.wgsl - a real
// interpreted CPU, not a native GPU op standing in for one.
//
// Correctness is checked two ways per instance: against the closed-form
// N*(N+1)/2 (an oracle with zero shared code path with either the shader
// or this harness) and against a native Rust loop computing the same sum
// (the CPU throughput baseline, same style as parallel_pixels_bench.rs).
#[cfg(feature = "gpu")]
fn main() {
    use std::time::Instant;
    use wgpu::util::DeviceExt;

    let n_instances: u32 = std::env::args()
        .nth(1)
        .and_then(|s| s.parse().ok())
        .unwrap_or(1000);
    println!("N = {n_instances} independent RV32I machines");

    // Assembled by tools/rv32i_assembler.py, independently verified against
    // `riscv64-linux-gnu-objdump -m riscv:rv32` before use - see that
    // script's output. sum 1..N (mem[0]) -> mem[4], then ECALL.
    const PROGRAM: [u32; 9] = [
        0x00000093, 0x00002103, 0x00100193, 0x00314863, 0x003080b3,
        0x00118193, 0xff5ff06f, 0x00102223, 0x00000073,
    ];
    const RAM_WORDS_PER_INSTANCE: u32 = 64;

    #[repr(C)]
    #[derive(Clone, Copy, bytemuck::Pod, bytemuck::Zeroable)]
    struct CpuState {
        pc: u32,
        status: u32,
        regs: [u32; 32],
    }

    // Bounded so the loop actually halts inside the shader's per-dispatch
    // step budget (1000 steps; this program takes roughly 6*N instructions).
    let inputs: Vec<u32> = (0..n_instances).map(|i| 2 + i % 150).collect();

    let mut vcpus = vec![
        CpuState { pc: 0, status: 0, regs: [0u32; 32] };
        n_instances as usize
    ];
    let mut ram = vec![0u32; (n_instances * RAM_WORDS_PER_INSTANCE) as usize];
    for i in 0..n_instances as usize {
        let base = i * RAM_WORDS_PER_INSTANCE as usize;
        ram[base] = inputs[i]; // mem[0] = N for this instance
        for (w, &word) in PROGRAM.iter().enumerate() {
            // program starts at guest address 16 (words 4..12), leaving
            // mem[0]=input and mem[4]=output (bytes 0-15) undisturbed
            ram[base + 4 + w] = word;
        }
        vcpus[i].pc = 16; // guest address of first program word
    }

    // --- CPU baseline: native Rust loop, same computation, sequential ---
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

    // --- GPU: dispatch all N independent RV32I machines in parallel -------
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

    let spv_bytes = std::fs::read("shaders/multi_instance_rv32i.spv").expect("read compiled SPIR-V");
    let words: Vec<u32> = spv_bytes
        .chunks_exact(4)
        .map(|c| u32::from_ne_bytes([c[0], c[1], c[2], c[3]]))
        .collect();
    let shader = device.create_shader_module(wgpu::ShaderModuleDescriptor {
        label: Some("multi_instance_rv32i"),
        source: wgpu::ShaderSource::SpirV(std::borrow::Cow::Owned(words)),
    });

    let vcpus_buffer = device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
        label: Some("vcpus"),
        contents: bytemuck::cast_slice(&vcpus),
        usage: wgpu::BufferUsages::STORAGE | wgpu::BufferUsages::COPY_SRC | wgpu::BufferUsages::COPY_DST,
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
        label: Some("multi_instance_rv32i pipeline"),
        layout: None,
        module: &shader,
        entry_point: "main",
        compilation_options: Default::default(),
    });
    let bind_group = device.create_bind_group(&wgpu::BindGroupDescriptor {
        label: Some("bind group"),
        layout: &pipeline.get_bind_group_layout(0),
        entries: &[
            wgpu::BindGroupEntry { binding: 0, resource: vcpus_buffer.as_entire_binding() },
            wgpu::BindGroupEntry { binding: 1, resource: ram_buffer.as_entire_binding() },
        ],
    });

    let workgroups = (n_instances + 63) / 64; // workgroup_size(64) in the shader
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
        "GPU (parallel, {} independent RV32I machines): {:?} total, {:.0} instances/sec",
        n_instances,
        gpu_elapsed,
        n_instances as f64 / gpu_elapsed.as_secs_f64()
    );

    // Verify every instance two ways: against the closed-form oracle AND
    // against the native-loop CPU baseline.
    let mut failures = 0;
    for i in 0..n_instances as usize {
        let n = inputs[i] as u64;
        let expected_closed_form = (n * (n + 1) / 2) as u32;
        let got = ram_result[i * RAM_WORDS_PER_INSTANCE as usize + 1]; // mem[4] = word offset 1
        if got != expected_closed_form || got != cpu_result[i] {
            failures += 1;
            if failures <= 5 {
                eprintln!(
                    "MISMATCH instance {i}: N={n} closed_form={expected_closed_form} cpu={} gpu={got}",
                    cpu_result[i]
                );
            }
        }
    }

    if failures > 0 {
        panic!("{failures}/{n_instances} instances produced wrong results");
    }
    println!(
        "PASS: all {n_instances} independently-executed RV32I machines match both the \
         closed-form oracle and the CPU native-loop baseline"
    );

    let speedup = cpu_elapsed.as_secs_f64() / gpu_elapsed.as_secs_f64();
    println!("\nSpeedup (GPU interpreted vs CPU sequential): {speedup:.2}x");

    // --- Decode-tax isolation: same algorithm, same N per lane, zero ---
    // --- instruction fetch/decode - just a native WGSL loop. -----------
    let native_spv = std::fs::read("shaders/native_sum_baseline.spv").expect("read native baseline SPIR-V");
    let native_words: Vec<u32> = native_spv
        .chunks_exact(4)
        .map(|c| u32::from_ne_bytes([c[0], c[1], c[2], c[3]]))
        .collect();
    let native_shader = device.create_shader_module(wgpu::ShaderModuleDescriptor {
        label: Some("native_sum_baseline"),
        source: wgpu::ShaderSource::SpirV(std::borrow::Cow::Owned(native_words)),
    });

    let inputs_buffer = device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
        label: Some("native inputs"),
        contents: bytemuck::cast_slice(&inputs),
        usage: wgpu::BufferUsages::STORAGE | wgpu::BufferUsages::COPY_SRC | wgpu::BufferUsages::COPY_DST,
    });
    let outputs_buffer = device.create_buffer(&wgpu::BufferDescriptor {
        label: Some("native outputs"),
        size: (n_instances as u64) * 4,
        usage: wgpu::BufferUsages::STORAGE | wgpu::BufferUsages::COPY_SRC | wgpu::BufferUsages::COPY_DST,
        mapped_at_creation: false,
    });
    let outputs_staging = device.create_buffer(&wgpu::BufferDescriptor {
        label: Some("native outputs staging"),
        size: (n_instances as u64) * 4,
        usage: wgpu::BufferUsages::MAP_READ | wgpu::BufferUsages::COPY_DST,
        mapped_at_creation: false,
    });

    let native_pipeline = device.create_compute_pipeline(&wgpu::ComputePipelineDescriptor {
        label: Some("native_sum_baseline pipeline"),
        layout: None,
        module: &native_shader,
        entry_point: "main",
        compilation_options: Default::default(),
    });
    let native_bind_group = device.create_bind_group(&wgpu::BindGroupDescriptor {
        label: Some("native bind group"),
        layout: &native_pipeline.get_bind_group_layout(0),
        entries: &[
            wgpu::BindGroupEntry { binding: 0, resource: inputs_buffer.as_entire_binding() },
            wgpu::BindGroupEntry { binding: 1, resource: outputs_buffer.as_entire_binding() },
        ],
    });

    let native_start = Instant::now();
    let mut native_encoder = device.create_command_encoder(&wgpu::CommandEncoderDescriptor::default());
    {
        let mut pass = native_encoder.begin_compute_pass(&wgpu::ComputePassDescriptor::default());
        pass.set_pipeline(&native_pipeline);
        pass.set_bind_group(0, &native_bind_group, &[]);
        pass.dispatch_workgroups(workgroups, 1, 1);
    }
    native_encoder.copy_buffer_to_buffer(&outputs_buffer, 0, &outputs_staging, 0, (n_instances as u64) * 4);
    queue.submit(Some(native_encoder.finish()));

    let native_slice = outputs_staging.slice(..);
    native_slice.map_async(wgpu::MapMode::Read, |r| r.unwrap());
    device.poll(wgpu::Maintain::Wait);
    let native_elapsed = native_start.elapsed();
    let native_result: Vec<u32> = bytemuck::cast_slice(&native_slice.get_mapped_range()).to_vec();

    for i in 0..n_instances as usize {
        assert_eq!(native_result[i], cpu_result[i], "native GPU baseline diverged from CPU at instance {i}");
    }
    println!(
        "\nGPU (native compute, same algorithm, zero decode): {:?} total, {:.0} instances/sec \
         [PASS: matches CPU baseline exactly]",
        native_elapsed,
        n_instances as f64 / native_elapsed.as_secs_f64()
    );

    let decode_tax = gpu_elapsed.as_secs_f64() / native_elapsed.as_secs_f64();
    println!(
        "\nMeasured decode-tax multiplier (interpreted / native, same algorithm, same N): {decode_tax:.1}x"
    );
}

#[cfg(not(feature = "gpu"))]
fn main() {
    eprintln!("This example requires the 'gpu' feature. Run with: --features gpu");
    std::process::exit(1);
}
