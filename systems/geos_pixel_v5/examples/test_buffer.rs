// Test u32 storage buffer write/readback on llvmpipe vs hardware
#[cfg(feature = "gpu")]
fn main() {
    let instance = wgpu::Instance::new(wgpu::InstanceDescriptor {
        backends: wgpu::Backends::all(),
        ..Default::default()
    });

    let adapter = pollster::block_on(instance.request_adapter(&wgpu::RequestAdapterOptions {
        power_preference: wgpu::PowerPreference::HighPerformance,
        compatible_surface: None,
        force_fallback_adapter: true,  // Force llvmpipe
    }))
    .expect("adapter not found");

    println!("Using adapter: {}", adapter.get_info().name);

    let (device, queue) = pollster::block_on(adapter.request_device(
        &wgpu::DeviceDescriptor {
            label: Some("buffer test"),
            required_features: wgpu::Features::empty(),
            required_limits: wgpu::Limits::default(),
        },
        None,
    )).expect("device creation failed");

    // Create a simple compute shader that writes a constant u32 value
    let shader = device.create_shader_module(wgpu::ShaderModuleDescriptor {
        label: Some("test shader"),
        source: wgpu::ShaderSource::Wgsl(r#"
            @group(0) @binding(0) var<storage, read_write> out_buf: array<u32>;

            @compute @workgroup_size(1)
            fn main() {
                // Write RED as u32: 0xFF0000FF (little-endian: FF 00 00 FF)
                out_buf[0] = 0xFF0000FFu;
                out_buf[1] = 0xFF00FF00u; // GREEN
                out_buf[2] = 0xFFFF0000u; // BLUE
            }
        "#.into()),
    });

    let storage_buf = device.create_buffer(&wgpu::BufferDescriptor {
        label: Some("storage"),
        size: 3 * 4,
        usage: wgpu::BufferUsages::STORAGE | wgpu::BufferUsages::COPY_SRC,
        mapped_at_creation: false,
    });

    let readback_buf = device.create_buffer(&wgpu::BufferDescriptor {
        label: Some("readback"),
        size: 3 * 4,
        usage: wgpu::BufferUsages::MAP_READ | wgpu::BufferUsages::COPY_DST,
        mapped_at_creation: false,
    });

    let bind_group = device.create_bind_group(&wgpu::BindGroupDescriptor {
        label: Some("bind group"),
        layout: &shader.get_bind_group_layout(0),
        entries: &[
            wgpu::BindGroupEntry {
                binding: 0,
                resource: storage_buf.as_entire_binding(),
            },
        ],
    });

    let pipeline = device.create_compute_pipeline(&wgpu::ComputePipelineDescriptor {
        label: Some("pipeline"),
        layout: None,
        module: &shader,
        entry_point: "main",
        compilation_options: Default::default(),
    });

    let mut encoder = device.create_command_encoder(&wgpu::CommandEncoderDescriptor {
        label: Some("encoder"),
    });

    {
        let mut cpass = encoder.begin_compute_pass(&wgpu::ComputePassDescriptor {
            label: Some("pass"),
            timestamp_writes: None,
        });
        cpass.set_pipeline(&pipeline);
        cpass.set_bind_group(0, &bind_group, &[]);
        cpass.dispatch_workgroups(1, 1, 1);
    }

    encoder.copy_buffer_to_buffer(&storage_buf, 0, &readback_buf, 0, 3 * 4);
    queue.submit(Some(encoder.finish()));

    let slice = readback_buf.slice(..);
    let (tx, rx) = std::sync::mpsc::channel();
    slice.map_async(wgpu::MapMode::Read, move |r| {
        let _ = tx.send(r);
    });
    loop {
        device.poll(wgpu::Maintain::Wait);
        if let Ok(Ok(())) = rx.try_recv() {
            break;
        }
    }

    let data = slice.get_mapped_range();
    let bytes: Vec<u8> = data.to_vec();
    drop(data);
    readback_buf.unmap();

    println!("Readback bytes (12 total):");
    println!("  {:02x} {:02x} {:02x} {:02x} | {:02x} {:02x} {:02x} {:02x} | {:02x} {:02x} {:02x} {:02x}",
             bytes[0], bytes[1], bytes[2], bytes[3],
             bytes[4], bytes[5], bytes[6], bytes[7],
             bytes[8], bytes[9], bytes[10], bytes[11]);

    // Interpret as u32 little-endian
    let u32s: Vec<u32> = (0..3).map(|i| u32::from_le_bytes([
        bytes[i*4], bytes[i*4+1], bytes[i*4+2], bytes[i*4+3]
    ])).collect();
    println!("As u32s (little-endian): {:08x} {:08x} {:08x}", u32s[0], u32s[1], u32s[2]);
}

#[cfg(not(feature = "gpu"))]
fn main() {
    eprintln!("Requires 'gpu' feature");
    std::process::exit(1);
}
