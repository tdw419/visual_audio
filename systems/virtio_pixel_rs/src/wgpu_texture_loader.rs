// WGPU texture loader for MKV frames
// Phase 1 of WGPU_INTEGRATION_GUIDE.md

use anyhow::{Context, Result};
use log::info;
use std::path::Path;
use wgpu::*;

/// MKV frame loaded as WGPU texture for O(1) sampling
pub struct MkvTexture {
    pub texture: Texture,
    pub view: TextureView,
    pub sampler: Sampler,
    pub frame_index: usize,
    pub extent: Extent3d,
    pub frame_capacity: usize,  // How many bytes fit in this frame
}

impl MkvTexture {
    /// Load a single MKV frame as WGPU texture (blocking)
    pub fn load_frame(
        device: &Device,
        queue: &Queue,
        mkv_path: &Path,
        frame_index: usize,
    ) -> Result<Self> {
        info!("Loading frame {} from MKV: {:?}", frame_index, mkv_path);

        // Step 1: Extract frame via ffmpeg (one-time cost)
        let frame_pixels = extract_frame_pixels(mkv_path, frame_index)
            .context("Failed to extract MKV frame")?;

        // Step 2: Convert to RGBA8 for WGPU
        let rgba_data = convert_to_rgba8(&frame_pixels);

        // Step 3: Infer frame size from data (RGB24 → pixels)
        // frame_pixels.len() = width * height * 3
        let rgb_pixels = frame_pixels.len() / 3;
        let width = (rgb_pixels as f32).sqrt() as u32;
        let height = width;  // Square frames

        info!(
            "Frame {}: inferred size {}×{} ({} RGB pixels)",
            frame_index, width, height, rgb_pixels
        );

        let extent = Extent3d {
            width,
            height,
            depth_or_array_layers: 1,
        };

        let texture = device.create_texture(&TextureDescriptor {
            label: Some(&format!("MKV Frame {}", frame_index)),
            size: extent,
            mip_level_count: 1,
            sample_count: 1,
            dimension: TextureDimension::D2,
            format: TextureFormat::Rgba8Unorm, // Linear, NOT sRGB, for exact byte extraction
            usage: TextureUsages::TEXTURE_BINDING | TextureUsages::COPY_DST,
            view_formats: &[],
        });

        // Step 4: Upload pixels to GPU
        queue.write_texture(
            ImageCopyTexture {
                texture: &texture,
                mip_level: 0,
                origin: Origin3d::ZERO,
                aspect: TextureAspect::All,
            },
            &rgba_data,
            ImageDataLayout {
                offset: 0,
                bytes_per_row: Some(width * 4),
                rows_per_image: Some(height),
            },
            extent,
        );

        // Step 5: Create texture view
        let view = texture.create_view(&TextureViewDescriptor::default());

        // Step 6: Create sampler
        let sampler = device.create_sampler(&SamplerDescriptor {
            address_mode_u: AddressMode::ClampToEdge,
            address_mode_v: AddressMode::ClampToEdge,
            address_mode_w: AddressMode::ClampToEdge,
            mag_filter: FilterMode::Nearest,
            min_filter: FilterMode::Nearest,
            mipmap_filter: FilterMode::Nearest,
            ..Default::default()
        });

        info!("Frame {} uploaded to GPU: {}x{} pixels", frame_index, extent.width, extent.height);

        let frame_capacity = (width * height) as usize;

        Ok(Self {
            texture,
            view,
            sampler,
            frame_index,
            extent,
            frame_capacity,
        })
    }
}

/// Extract a single frame from MKV using ffmpeg
fn extract_frame_pixels(mkv_path: &Path, frame_index: usize) -> Result<Vec<u8>> {
    use std::process::Command;

    let mkv_str = mkv_path.to_str().context("Invalid MKV path")?;

    let output = Command::new("ffmpeg")
        .args([
            "-i", mkv_str,
            "-vf", &format!("select=eq(n\\,{frame_index})"),
            "-vframes", "1",
            "-f", "rawvideo",
            "-pix_fmt", "rgb24",
            "pipe:",
        ])
        .output()
        .context("ffmpeg extraction failed")?;

    if output.status.success() {
        log::info!(
            "Extracted frame {} ({} bytes)",
            frame_index,
            output.stdout.len()
        );
        Ok(output.stdout)
    } else {
        Err(anyhow::anyhow!(
            "ffmpeg failed with status {}: {}",
            output.status,
            String::from_utf8_lossy(&output.stderr)
        ))
    }
}

/// Convert RGB24 to RGBA8 (add alpha channel)
fn convert_to_rgba8(rgb_data: &[u8]) -> Vec<u8> {
    let mut rgba_data = Vec::with_capacity(rgb_data.len() / 3 * 4);

    for chunk in rgb_data.chunks_exact(3) {
        rgba_data.push(chunk[0]); // R
        rgba_data.push(chunk[1]); // G
        rgba_data.push(chunk[2]); // B
        rgba_data.push(255);      // A (fully opaque)
    }

    rgba_data
}

/// Initialize WGPU instance, adapter, and device (blocking)
pub fn init_wgpu() -> Result<(Instance, Adapter, Device, Queue)> {
    info!("Initializing WGPU...");

    let instance = Instance::new(InstanceDescriptor {
        backends: Backends::all(),
        dx12_shader_compiler: Default::default(),
        ..Default::default()
    });

    let adapter = pollster::block_on(instance.request_adapter(&RequestAdapterOptions {
        power_preference: PowerPreference::HighPerformance,
        compatible_surface: None,
        force_fallback_adapter: false,
    }))
    .context("No WGPU adapter found")?;

    info!("WGPU adapter: {:?}", adapter.get_info());

    let (device, queue) = pollster::block_on(adapter.request_device(
        &DeviceDescriptor {
            label: Some("WGPU Device"),
            required_features: Features::empty(),
            required_limits: Limits::default(),
        },
        None,
    ))
    .context("Failed to create WGPU device")?;

    info!("WGPU initialized successfully");

    Ok((instance, adapter, device, queue))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;

    #[test]
    #[ignore] // Requires visual_audio.mkv
    fn test_load_mkv_texture() {
        let (_instance, _adapter, device, queue) = init_wgpu().unwrap();

        let mkv_path = PathBuf::from("../../visual_audio.mkv");
        let texture = MkvTexture::load_frame(&device, &queue, &mkv_path, 0).unwrap();

        assert_eq!(texture.extent.width, 4096);
        assert_eq!(texture.extent.height, 4096);
    }

    #[test]
    fn test_wgpu_init() {
        let (_instance, _adapter, _device, _queue) = init_wgpu().unwrap();
    }
}