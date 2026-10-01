// Experiment: is "many independent small programs in parallel across GPU
// threads" actually faster than a CPU, unlike the single-core RISC-V
// emulator (which runs one thread, sequential, ~1M instr/s - 2-3 orders of
// magnitude slower than even a plain CPU interpreter)? Each GPU lane runs
// an independent Collatz sequence (data-dependent branching, variable-length
// loop per lane - a fair stand-in for divergent small guest programs), same
// pattern as spirv_from_pixels.rs: the shader is compiled offline to SPIR-V,
// pixel-encoded into a PNG, decoded back byte-exact, and dispatched with
// zero WGSL text at runtime. Compares GPU wall time against a sequential
// CPU computation of the identical function, and verifies every result
// matches exactly before trusting any timing number.
#[cfg(feature = "gpu")]
fn main() {
    use std::time::Instant;
    use wgpu::util::DeviceExt;

    let n: u32 = std::env::args()
        .nth(1)
        .and_then(|s| s.parse().ok())
        .unwrap_or(1_000_000);
    let mode = std::env::args().nth(2).unwrap_or_else(|| "unsorted".to_string());
    println!("N = {n} independent lanes/elements, mode={mode}");

    // --- Load the offline-compiled SPIR-V, pixel-encode, decode ------------
    let spv_bytes =
        std::fs::read("shaders/parallel_collatz.spv").expect("read compiled SPIR-V");
    let png_path = "/tmp/parallel_collatz_pixels.png";
    let n_pixels = (spv_bytes.len() + 3) / 4;
    let side = (n_pixels as f64).sqrt().ceil() as u32;
    let (w, h) = (side.max(1), side.max(1));
    let mut rgba = vec![0u8; (w * h * 4) as usize];
    rgba[..spv_bytes.len()].copy_from_slice(&spv_bytes);
    image::save_buffer(png_path, &rgba, w, h, image::ColorType::Rgba8).expect("write shader PNG");

    let img = image::open(png_path).expect("open shader PNG").to_rgba8();
    let decoded = &img.as_raw()[..spv_bytes.len()];
    assert_eq!(decoded, spv_bytes.as_slice(), "pixel round-trip must be byte-exact");
    let words: Vec<u32> = decoded
        .chunks_exact(4)
        .map(|c| u32::from_ne_bytes([c[0], c[1], c[2], c[3]]))
        .collect();
    println!("Shader loaded from {} pixel-decoded bytes (byte-exact)", decoded.len());

    // --- Generate input: bounded so CPU baseline finishes in reasonable time
    let mut input: Vec<u32> = (0..n)
        .map(|i| 2 + i.wrapping_mul(2654435761u32) % 2_000_000)
        .collect();

    fn collatz_steps(mut x: u32) -> u32 {
        let mut steps = 0u32;
        while x > 1 {
            x = if x % 2 == 0 { x / 2 } else { 3u32.wrapping_mul(x).wrapping_add(1) };
            steps += 1;
        }
        steps
    }

    if mode == "sorted" || mode == "interleaved" {
        // Sort inputs by their own trip count so each workgroup's 256 lanes
        // finish around the same time instead of all waiting on one
        // straggler - fixes local (within-workgroup) divergence. Compute
        // each key ONCE up front: sort_by_key re-invokes the closure on
        // every comparison, so calling collatz_steps there directly is
        // O(N log N) full recomputations, not O(N) - at N=10M that's
        // billions of wasted steps that silently ran before the timer
        // below even started (this cost 3 back-to-back 40s timeouts before
        // being caught).
        let mut keyed: Vec<(u32, u32)> = input.iter().map(|&x| (collatz_steps(x), x)).collect();
        keyed.sort_by_key(|&(k, _)| k);
        input = keyed.into_iter().map(|(_, x)| x).collect();
    }
    if mode == "interleaved" {
        // A straight sort clusters all the long-running workgroups at the
        // tail of the dispatch, with no short "filler" work left to
        // interleave - this removed the natural load-balancing the GPU's
        // scheduler relies on (short workgroups retiring quickly and being
        // replaced keeps every execution unit busy while long workgroups
        // finish elsewhere), and measured *slower* wall time despite ~100%
        // local SIMT efficiency. Fix: keep each 256-lane workgroup
        // homogeneous (sorted internally), but reorder the *workgroups*
        // via a stride/transpose permutation so consecutive dispatch
        // positions draw from evenly-spaced strata across the full cost
        // range - restoring a short/long mix over time without
        // reintroducing within-workgroup divergence.
        const CHUNK: usize = 256;
        let num_chunks = (input.len() + CHUNK - 1) / CHUNK;
        let strata = (num_chunks as f64).sqrt().ceil().max(1.0) as usize;
        let block = (num_chunks + strata - 1) / strata;
        let mut new_order = Vec::with_capacity(num_chunks);
        for pos in 0..block {
            for s in 0..strata {
                let old_chunk = s * block + pos;
                if old_chunk < num_chunks {
                    new_order.push(old_chunk);
                }
            }
        }
        let mut reordered = Vec::with_capacity(input.len());
        for &c in &new_order {
            let start = c * CHUNK;
            let end = (start + CHUNK).min(input.len());
            reordered.extend_from_slice(&input[start..end]);
        }
        input = reordered;
    }

    // --- CPU baseline: identical computation, sequential (same order as GPU input,
    // so index-for-index comparison stays valid whether or not we sorted) ---
    let cpu_start = Instant::now();
    let cpu_result: Vec<u32> = input.iter().map(|&x| collatz_steps(x)).collect();
    let cpu_elapsed = cpu_start.elapsed();
    println!(
        "CPU (sequential, 1 core): {:?} total, {:.0} elements/sec",
        cpu_elapsed,
        n as f64 / cpu_elapsed.as_secs_f64()
    );

    // --- GPU: dispatch all N lanes in parallel --------------------------------
    let instance = wgpu::Instance::default();
    let adapter =
        pollster::block_on(instance.request_adapter(&wgpu::RequestAdapterOptions::default()))
            .expect("no GPU adapter");
    println!("GPU adapter: {}", adapter.get_info().name);
    let adapter_limits = adapter.limits();
    println!(
        "Adapter max storage buffer binding: {} MB",
        adapter_limits.max_storage_buffer_binding_size / 1_000_000
    );
    let (device, queue) = pollster::block_on(adapter.request_device(
        &wgpu::DeviceDescriptor {
            required_limits: adapter_limits.clone(),
            ..Default::default()
        },
        None,
    ))
    .expect("request_device");

    let shader = device.create_shader_module(wgpu::ShaderModuleDescriptor {
        label: Some("parallel_collatz (from pixels)"),
        source: wgpu::ShaderSource::SpirV(std::borrow::Cow::Owned(words)),
    });

    let buffer = device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
        label: Some("data"),
        contents: bytemuck::cast_slice(&input),
        usage: wgpu::BufferUsages::STORAGE | wgpu::BufferUsages::COPY_SRC | wgpu::BufferUsages::COPY_DST,
    });
    let staging = device.create_buffer(&wgpu::BufferDescriptor {
        label: Some("staging"),
        size: (n as u64) * 4,
        usage: wgpu::BufferUsages::MAP_READ | wgpu::BufferUsages::COPY_DST,
        mapped_at_creation: false,
    });

    // dispatch_workgroups caps each dimension at 65535; spread wide N across
    // a 2D grid instead (group_count_x lets the shader flatten wid.x/wid.y
    // back into one linear index, since WGSL has no num_workgroups builtin).
    let total_workgroups = (n + 255) / 256; // workgroup_size(256) in the shader
    const MAX_DIM: u32 = 65535;
    let group_count_x = total_workgroups.min(MAX_DIM);
    let group_count_y = (total_workgroups + group_count_x - 1) / group_count_x;
    assert!(group_count_y <= MAX_DIM, "N={n} exceeds what a 2D dispatch grid can cover");

    let params_buffer = device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
        label: Some("params"),
        contents: bytemuck::bytes_of(&group_count_x),
        usage: wgpu::BufferUsages::UNIFORM,
    });

    // CPPM-style pressure counters (see shaders/parallel_collatz.wgsl): one
    // (sum, max) pair per workgroup - summed on the host after readback,
    // since naga's SPIR-V importer can't parse atomics back out.
    let stats_bytes = (total_workgroups as u64) * 8;
    let stats_buffer = device.create_buffer(&wgpu::BufferDescriptor {
        label: Some("cppm stats"),
        size: stats_bytes,
        usage: wgpu::BufferUsages::STORAGE | wgpu::BufferUsages::COPY_SRC | wgpu::BufferUsages::COPY_DST,
        mapped_at_creation: false,
    });
    let stats_staging = device.create_buffer(&wgpu::BufferDescriptor {
        label: Some("cppm stats staging"),
        size: stats_bytes,
        usage: wgpu::BufferUsages::MAP_READ | wgpu::BufferUsages::COPY_DST,
        mapped_at_creation: false,
    });

    let pipeline = device.create_compute_pipeline(&wgpu::ComputePipelineDescriptor {
        label: Some("parallel_collatz pipeline"),
        layout: None,
        module: &shader,
        entry_point: "main",
        compilation_options: Default::default(),
    });
    let bind_group = device.create_bind_group(&wgpu::BindGroupDescriptor {
        label: Some("bind group"),
        layout: &pipeline.get_bind_group_layout(0),
        entries: &[
            wgpu::BindGroupEntry { binding: 0, resource: buffer.as_entire_binding() },
            wgpu::BindGroupEntry { binding: 1, resource: params_buffer.as_entire_binding() },
            wgpu::BindGroupEntry { binding: 2, resource: stats_buffer.as_entire_binding() },
        ],
    });

    let gpu_start = Instant::now();
    let mut encoder = device.create_command_encoder(&wgpu::CommandEncoderDescriptor::default());
    {
        let mut pass = encoder.begin_compute_pass(&wgpu::ComputePassDescriptor::default());
        pass.set_pipeline(&pipeline);
        pass.set_bind_group(0, &bind_group, &[]);
        pass.dispatch_workgroups(group_count_x, group_count_y, 1);
    }
    encoder.copy_buffer_to_buffer(&buffer, 0, &staging, 0, (n as u64) * 4);
    encoder.copy_buffer_to_buffer(&stats_buffer, 0, &stats_staging, 0, stats_bytes);
    queue.submit(Some(encoder.finish()));

    let slice = staging.slice(..);
    slice.map_async(wgpu::MapMode::Read, |r| r.unwrap());
    let stats_slice = stats_staging.slice(..);
    stats_slice.map_async(wgpu::MapMode::Read, |r| r.unwrap());
    device.poll(wgpu::Maintain::Wait);
    let gpu_elapsed = gpu_start.elapsed();
    let gpu_result: Vec<u32> = bytemuck::cast_slice(&slice.get_mapped_range()).to_vec();
    let stats: Vec<[u32; 2]> = bytemuck::cast_slice(&stats_slice.get_mapped_range()).to_vec();
    let total_work: f64 = stats.iter().map(|s| s[0] as f64).sum();
    let lockstep_upper_bound: f64 = stats.iter().map(|s| s[1] as f64).sum::<f64>() * 256.0;
    let simt_efficiency = total_work / lockstep_upper_bound;
    println!(
        "CPPM: total useful work = {:.0} steps, lockstep-serialized upper bound = {:.0} \
         lane-steps, SIMT efficiency ~= {:.1}% (workgroup-granularity proxy, see shader comment)",
        total_work,
        lockstep_upper_bound,
        simt_efficiency * 100.0
    );

    println!(
        "GPU (parallel, {} lanes): {:?} total, {:.0} elements/sec",
        n,
        gpu_elapsed,
        n as f64 / gpu_elapsed.as_secs_f64()
    );

    assert_eq!(gpu_result, cpu_result, "GPU and CPU results must match exactly");
    println!("PASS: all {n} results match exactly between GPU and CPU");

    let speedup = cpu_elapsed.as_secs_f64() / gpu_elapsed.as_secs_f64();
    println!("\nSpeedup (GPU parallel vs CPU sequential): {speedup:.2}x");
}

#[cfg(not(feature = "gpu"))]
fn main() {
    eprintln!("This example requires the 'gpu' feature. Run with: --features gpu");
    std::process::exit(1);
}
