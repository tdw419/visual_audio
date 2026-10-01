#[cfg(test)]
mod tests {
    use super::*;
    use image::RgbaImage;
    use std::fs;

    #[test]
    fn test_image_node_upload() {
        pollster::block_on(async {
            let instance = wgpu::Instance::new(wgpu::InstanceDescriptor {
                backends: wgpu::Backends::all(),
                ..Default::default()
            });
            let adapter = instance.request_adapter(&wgpu::RequestAdapterOptions {
                power_preference: wgpu::PowerPreference::LowPower,
                force_fallback_adapter: false,
                compatible_surface: None,
            }).await.expect("Failed to find wgpu adapter");

            let (device, queue) = adapter.request_device(&wgpu::DeviceDescriptor {
                required_features: wgpu::Features::empty(),
                required_limits: wgpu::Limits::downlevel_defaults(),
                label: None,
            }, None).await.unwrap();

            let path = "../../systems/glyph_os/patch_and_copy_demo.rts.png".to_string();
            let img = image::open(&path).unwrap().to_rgba8();
            let width = img.width();
            let height = img.height();

            let mut content = ImageContent {
                rgba_data: img.into_raw(),
                width,
                height,
                path,
                needs_upload: true,
            };

            let texture = device.create_texture(&wgpu::TextureDescriptor {
                label: Some("test"),
                size: wgpu::Extent3d { width, height, depth_or_array_layers: 1 },
                mip_level_count: 1,
                sample_count: 1,
                dimension: wgpu::TextureDimension::D2,
                format: wgpu::TextureFormat::Rgba8UnormSrgb,
                usage: wgpu::TextureUsages::COPY_DST | wgpu::TextureUsages::COPY_SRC,
                view_formats: &[],
            });

            if let Some((data, w, h)) = content.pixel_data() {
                queue.write_texture(
                    wgpu::ImageCopyTexture { texture: &texture, mip_level: 0, origin: wgpu::Origin3d::ZERO, aspect: wgpu::TextureAspect::All },
                    data,
                    wgpu::ImageDataLayout { offset: 0, bytes_per_row: Some(4 * w), rows_per_image: Some(h) },
                    wgpu::Extent3d { width: w, height: h, depth_or_array_layers: 1 },
                );
            }

            let buffer_size = (4 * width * height) as wgpu::BufferAddress;
            let buffer = device.create_buffer(&wgpu::BufferDescriptor {
                label: None, size: buffer_size,
                usage: wgpu::BufferUsages::COPY_DST | wgpu::BufferUsages::MAP_READ,
                mapped_at_creation: false,
            });

            let mut encoder = device.create_command_encoder(&wgpu::CommandEncoderDescriptor { label: None });
            encoder.copy_texture_to_buffer(
                wgpu::ImageCopyTexture { texture: &texture, mip_level: 0, origin: wgpu::Origin3d::ZERO, aspect: wgpu::TextureAspect::All },
                wgpu::ImageCopyBuffer { buffer: &buffer, layout: wgpu::ImageDataLayout { offset: 0, bytes_per_row: Some(4 * width), rows_per_image: Some(height) } },
                wgpu::Extent3d { width, height, depth_or_array_layers: 1 }
            );
            queue.submit(Some(encoder.finish()));

            let buffer_slice = buffer.slice(..);
            let (tx, rx) = std::sync::mpsc::channel();
            buffer_slice.map_async(wgpu::MapMode::Read, move |v| tx.send(v).unwrap());
            device.poll(wgpu::Maintain::Wait);
            rx.recv().unwrap().unwrap();

            let data = buffer_slice.get_mapped_range();
            let out_img = RgbaImage::from_raw(width, height, data.to_vec()).unwrap();
            out_img.save("offscreen_receipt.png").unwrap();
        });
    }
}
