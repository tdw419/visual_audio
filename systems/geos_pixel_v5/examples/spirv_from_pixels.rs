// Proof: a compute shader can be stored as, decoded from, and dispatched
// directly from pixel data — the SPIR-V bytes never pass through WGSL
// compilation at runtime. Same pattern as PXC1's "picture boots a computer"
// (bytes encoded as pixels, decoded, executed), applied to the GPU instead
// of the CPU: shaders/double_buffer.wgsl was compiled offline with `naga`
// to shaders/double_buffer.spv; this example encodes that SPIR-V into a
// PNG, decodes it back, and loads it with wgpu's unsafe raw-SPIR-V path.
#[cfg(feature = "gpu")]
fn main() {
    use wgpu::util::DeviceExt;

    let spv_bytes = std::fs::read("shaders/double_buffer.spv").expect("read compiled SPIR-V");
    assert_eq!(spv_bytes.len() % 4, 0, "SPIR-V must be a whole number of 32-bit words");

    // --- Encode: pack the raw SPIR-V bytes into an RGBA8 PNG -----------------
    let png_path = "/tmp/spirv_shader_pixels.png";
    let n_pixels = (spv_bytes.len() + 3) / 4;
    let side = (n_pixels as f64).sqrt().ceil() as u32;
    let (w, h) = (side.max(1), side.max(1));
    let mut rgba = vec![0u8; (w * h * 4) as usize];
    rgba[..spv_bytes.len()].copy_from_slice(&spv_bytes);
    image::save_buffer(png_path, &rgba, w, h, image::ColorType::Rgba8).expect("write shader PNG");
    println!(
        "Encoded {} bytes of SPIR-V into {} ({}x{} pixels)",
        spv_bytes.len(),
        png_path,
        w,
        h
    );

    // --- Decode: read the PNG back and recover the exact SPIR-V bytes ------
    let img = image::open(png_path).expect("open shader PNG").to_rgba8();
    let decoded = &img.as_raw()[..spv_bytes.len()];
    assert_eq!(decoded, spv_bytes.as_slice(), "pixel round-trip must be byte-exact");
    println!("Decoded {} bytes from pixels — byte-exact match with original SPIR-V", decoded.len());

    let words: Vec<u32> = decoded
        .chunks_exact(4)
        .map(|c| u32::from_ne_bytes([c[0], c[1], c[2], c[3]]))
        .collect();

    // --- Dispatch: load the decoded SPIR-V directly, no WGSL involved ------
    let instance = wgpu::Instance::default();
    let adapter = pollster::block_on(instance.request_adapter(&wgpu::RequestAdapterOptions::default()))
        .expect("no GPU adapter");
    println!("GPU adapter: {}", adapter.get_info().name);
    let (device, queue) = pollster::block_on(adapter.request_device(&wgpu::DeviceDescriptor::default(), None))
        .expect("request_device");

    // naga parses the decoded SPIR-V words directly into its IR and compiles
    // them for the native backend (Vulkan/Metal/DX12) — no WGSL text is ever
    // involved. This is the portable route; the unsafe raw
    // create_shader_module_spirv passthrough exists too but requires a
    // Vulkan feature (SPIRV_SHADER_PASSTHROUGH) this host's Intel Mesa
    // driver doesn't support (it segfaults inside wgpu-hal when requested).
    let shader = device.create_shader_module(wgpu::ShaderModuleDescriptor {
        label: Some("double_buffer (from pixels)"),
        source: wgpu::ShaderSource::SpirV(std::borrow::Cow::Owned(words)),
    });

    let input: [u32; 4] = [1, 2, 3, 4];
    let buffer = device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
        label: Some("data"),
        contents: bytemuck::cast_slice(&input),
        usage: wgpu::BufferUsages::STORAGE | wgpu::BufferUsages::COPY_SRC | wgpu::BufferUsages::COPY_DST,
    });
    let staging = device.create_buffer(&wgpu::BufferDescriptor {
        label: Some("staging"),
        size: std::mem::size_of_val(&input) as u64,
        usage: wgpu::BufferUsages::MAP_READ | wgpu::BufferUsages::COPY_DST,
        mapped_at_creation: false,
    });

    let pipeline = device.create_compute_pipeline(&wgpu::ComputePipelineDescriptor {
        label: Some("double_buffer pipeline"),
        layout: None,
        module: &shader,
        entry_point: "main",
        compilation_options: Default::default(),
    });
    let bind_group = device.create_bind_group(&wgpu::BindGroupDescriptor {
        label: Some("bind group"),
        layout: &pipeline.get_bind_group_layout(0),
        entries: &[wgpu::BindGroupEntry {
            binding: 0,
            resource: buffer.as_entire_binding(),
        }],
    });

    let mut encoder = device.create_command_encoder(&wgpu::CommandEncoderDescriptor::default());
    {
        let mut pass = encoder.begin_compute_pass(&wgpu::ComputePassDescriptor::default());
        pass.set_pipeline(&pipeline);
        pass.set_bind_group(0, &bind_group, &[]);
        pass.dispatch_workgroups(input.len() as u32, 1, 1);
    }
    encoder.copy_buffer_to_buffer(&buffer, 0, &staging, 0, std::mem::size_of_val(&input) as u64);
    queue.submit(Some(encoder.finish()));

    let slice = staging.slice(..);
    slice.map_async(wgpu::MapMode::Read, |r| r.unwrap());
    device.poll(wgpu::Maintain::Wait);
    let result: Vec<u32> = bytemuck::cast_slice(&slice.get_mapped_range()).to_vec();

    println!("Input:  {:?}", input);
    println!("Output: {:?}", result);
    let expected: Vec<u32> = input.iter().map(|x| x * 2).collect();
    assert_eq!(result, expected, "GPU output must match doubled input");
    println!("PASS: shader loaded from pixel-decoded SPIR-V produced the correct result");
}

#[cfg(not(feature = "gpu"))]
fn main() {
    eprintln!("This example requires the 'gpu' feature. Run with: --features gpu");
    std::process::exit(1);
}
