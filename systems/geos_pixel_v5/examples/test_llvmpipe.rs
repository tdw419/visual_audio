// Test WindowSystem::render() with forced software adapter (llvmpipe)
#[cfg(feature = "gpu")]
fn main() {
    let instance = wgpu::Instance::new(wgpu::InstanceDescriptor {
        backends: wgpu::Backends::all(),
        ..Default::default()
    });

    let adapter = pollster::block_on(instance.request_adapter(&wgpu::RequestAdapterOptions {
        power_preference: wgpu::PowerPreference::HighPerformance,
        compatible_surface: None,
        force_fallback_adapter: true,  // Force software fallback (llvmpipe)
    }))
    .expect("forced fallback adapter not found");

    println!("Forced adapter: {}", adapter.get_info().name);
    println!("Forced adapter features: {:?}", adapter.features());

    let (device, queue) = pollster::block_on(adapter.request_device(
        &wgpu::DeviceDescriptor {
            label: Some("geos_pixel_v5 test (forced software)"),
            required_features: wgpu::Features::empty(),
            required_limits: wgpu::Limits {
                max_storage_buffers_per_shader_stage: 2,
                max_uniform_buffers_per_shader_stage: 2,
                ..Default::default()
            },
        },
        None,
    )).expect("device request failed");

    println!("Device created with forced adapter");
}

#[cfg(not(feature = "gpu"))]
fn main() {
    eprintln!("This example requires the 'gpu' feature. Run with: --features gpu");
    std::process::exit(1);
}
