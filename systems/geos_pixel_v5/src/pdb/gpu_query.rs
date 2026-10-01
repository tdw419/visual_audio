/// GPU-Accelerated Query Engine for PDB
///
/// Uses WGSL compute shaders to scan spatially-encoded table data in parallel.
/// Operates on PDB frames loaded as textures and returns matching row indices.

#[cfg(feature = "gpu")]
use crate::pdb::{BoundingBox, PdbError, PdbResult};
use std::sync::Arc;

/// GPU query engine
#[cfg(feature = "gpu")]
pub struct GpuQueryEngine {
    device: Arc<wgpu::Device>,
    queue: Arc<wgpu::Queue>,
}

/// GPU query configuration
#[cfg(feature = "gpu")]
#[derive(Debug, Clone)]
pub struct GpuQueryConfig {
    /// Maximum matches to return per query
    pub max_matches: usize,
    /// Workgroup size for compute shader (X dimension)
    pub workgroup_size_x: u32,
}

impl Default for GpuQueryConfig {
    fn default() -> Self {
        Self {
            max_matches: 1000,
            workgroup_size_x: 64,
        }
    }
}

/// Query result containing matching Hilbert distances
#[cfg(feature = "gpu")]
#[derive(Debug, Clone)]
pub struct QueryResult {
    /// Hilbert distances of matching positions
    pub matches: Vec<u32>,
    /// Total workgroups dispatched
    pub workgroups_dispatched: u32,
}

#[cfg(feature = "gpu")]
impl GpuQueryEngine {
    /// Create new GPU query engine (blocking version)
    ///
    /// # Errors
    /// Returns error if no suitable GPU adapter is found
    pub fn new() -> PdbResult<Self> {
        let instance = wgpu::Instance::new(wgpu::InstanceDescriptor {
            backends: wgpu::Backends::all(),
            ..Default::default()
        });

        let adapter = pollster::block_on(instance.request_adapter(&wgpu::RequestAdapterOptions {
            power_preference: wgpu::PowerPreference::HighPerformance,
            compatible_surface: None,
            force_fallback_adapter: false,
        }))
        .ok_or(PdbError::DecodingFailed)?;

        let (device, queue) = pollster::block_on(adapter.request_device(
            &wgpu::DeviceDescriptor {
                label: Some("PDB GPU Query Engine"),
                required_features: wgpu::Features::empty(),
                required_limits: wgpu::Limits {
                    max_storage_buffers_per_shader_stage: 2,
                    max_uniform_buffers_per_shader_stage: 2,
                    ..Default::default()
                },
            },
            None,
        ))
        .map_err(|e| PdbError::IoError(e.to_string()))?;

        Ok(Self {
            device: Arc::new(device),
            queue: Arc::new(queue),
        })
    }

    /// Create a wgpu::Texture from an image::RgbaImage
    pub fn create_texture_from_image(&self, img: &image::RgbaImage) -> wgpu::Texture {
        let size = wgpu::Extent3d {
            width: img.width(),
            height: img.height(),
            depth_or_array_layers: 1,
        };

        let texture = self.device.create_texture(&wgpu::TextureDescriptor {
            label: Some("PDB Texture"),
            size,
            mip_level_count: 1,
            sample_count: 1,
            dimension: wgpu::TextureDimension::D2,
            format: wgpu::TextureFormat::Rgba8Unorm,
            usage: wgpu::TextureUsages::TEXTURE_BINDING | wgpu::TextureUsages::COPY_DST,
            view_formats: &[],
        });

        self.queue.write_texture(
            wgpu::ImageCopyTexture {
                texture: &texture,
                mip_level: 0,
                origin: wgpu::Origin3d::ZERO,
                aspect: wgpu::TextureAspect::All,
            },
            img,
            wgpu::ImageDataLayout {
                offset: 0,
                bytes_per_row: Some(4 * img.width()),
                rows_per_image: Some(img.height()),
            },
            size,
        );

        texture
    }

    /// Scan a table for a byte pattern using GPU compute shader
    ///
    /// # Arguments
    /// * `texture` - PDB frame as RGBA8 texture
    /// * `table_bbox` - Bounding box of table to scan
    /// * `pattern` - Byte pattern to search for
    /// * `config` - Query configuration
    ///
    /// # Returns
    /// Query result with matching Hilbert distances
    pub fn scan_table_for_pattern(
        &self,
        texture: &wgpu::Texture,
        table_bbox: &BoundingBox,
        pattern: &[u8],
        config: &GpuQueryConfig,
    ) -> PdbResult<QueryResult> {
        // Calculate grid size for Hilbert curve (power of 2)
        let bbox_width = table_bbox.x_max - table_bbox.x_min + 1;
        let bbox_height = table_bbox.y_max - table_bbox.y_min + 1;
        let grid_size = bbox_width.max(bbox_height).next_power_of_two();

        // Create uniform buffer
        let mut pattern_u32 = [0u32; 4];
        for (i, &b) in pattern.iter().take(16).enumerate() {
            let word = i / 4;
            let byte = i % 4;
            pattern_u32[word] |= (b as u32) << (byte * 8);
        }

        let uniforms: [u32; 12] = [
            table_bbox.x_min,
            table_bbox.y_min,
            table_bbox.x_max,
            table_bbox.y_max,
            grid_size,
            pattern.len() as u32,
            0, // padding1
            0, // padding2
            pattern_u32[0],
            pattern_u32[1],
            pattern_u32[2],
            pattern_u32[3],
        ];
        
        let mut uniforms_bytes = [0u8; 48];
        for (i, &val) in uniforms.iter().enumerate() {
            uniforms_bytes[i*4..i*4+4].copy_from_slice(&val.to_le_bytes());
        }

        use wgpu::util::DeviceExt;
        let uniform_buffer = self.device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
            label: Some("Query Uniforms"),
            contents: &uniforms_bytes,
            usage: wgpu::BufferUsages::UNIFORM | wgpu::BufferUsages::COPY_DST,
        });

        // Create compute pipeline for pattern matching
        let shader = self.device.create_shader_module(wgpu::ShaderModuleDescriptor {
            label: Some("Hilbert Pattern Scanner"),
            source: wgpu::ShaderSource::Wgsl(Self::get_pattern_scan_shader().into()),
        });

        let compute_pipeline = self
            .device
            .create_compute_pipeline(&wgpu::ComputePipelineDescriptor {
                label: Some("Pattern Scan Pipeline"),
                layout: None,
                module: &shader,
                entry_point: "main",
                compilation_options: Default::default(),
            });

        // Create result buffer (atomic counter + matches array)
        let buffer_size = std::mem::size_of::<u32>() * (config.max_matches + 1);
        let result_buffer = self.device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("Result Buffer"),
            size: buffer_size as u64,
            usage: wgpu::BufferUsages::STORAGE | wgpu::BufferUsages::COPY_SRC | wgpu::BufferUsages::COPY_DST,
            mapped_at_creation: false,
        });

        // Create readback buffer for CPU access
        let readback_buffer = self.device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("Readback Buffer"),
            size: buffer_size as u64,
            usage: wgpu::BufferUsages::MAP_READ | wgpu::BufferUsages::COPY_DST,
            mapped_at_creation: false,
        });

        // Create bind group
        let bind_group = self.device.create_bind_group(&wgpu::BindGroupDescriptor {
            label: Some("Pattern Scan Bind Group"),
            layout: &compute_pipeline.get_bind_group_layout(0),
            entries: &[
                // Binding 0: Input texture
                wgpu::BindGroupEntry {
                    binding: 0,
                    resource: wgpu::BindingResource::TextureView(
                        &texture.create_view(&wgpu::TextureViewDescriptor::default()),
                    ),
                },
                // Binding 1: Result buffer
                wgpu::BindGroupEntry {
                    binding: 1,
                    resource: result_buffer.as_entire_binding(),
                },
                // Binding 2: Uniform buffer
                wgpu::BindGroupEntry {
                    binding: 2,
                    resource: uniform_buffer.as_entire_binding(),
                },
            ],
        });

        // Initialize result buffer counter to 0
        self.queue.write_buffer(&result_buffer, 0, &[0u8; 4]);

        // Calculate grid size for Hilbert curve (power of 2)
        let bbox_width = table_bbox.x_max - table_bbox.x_min + 1;
        let bbox_height = table_bbox.y_max - table_bbox.y_min + 1;
        let grid_size = bbox_width.max(bbox_height).next_power_of_two();

        // Calculate total workgroups needed
        let total_positions = grid_size * grid_size;
        let workgroups_needed = (total_positions + config.workgroup_size_x - 1) / config.workgroup_size_x;

        // Create command encoder
        let mut encoder = self
            .device
            .create_command_encoder(&wgpu::CommandEncoderDescriptor {
                label: Some("Pattern Scan Encoder"),
            });

        {
            let mut cpass = encoder.begin_compute_pass(&wgpu::ComputePassDescriptor {
                label: Some("Pattern Scan Pass"),
                timestamp_writes: None,
            });

            cpass.set_pipeline(&compute_pipeline);
            cpass.set_bind_group(0, &bind_group, &[]);
            cpass.dispatch_workgroups(workgroups_needed, 1, 1);
        }

        // Copy result to readback buffer
        encoder.copy_buffer_to_buffer(&result_buffer, 0, &readback_buffer, 0, buffer_size as u64);

        // Submit commands
        self.queue.submit(Some(encoder.finish()));

        // Read back results
        let result_slice = readback_buffer.slice(..);

        // Buffer slice API returns a future
        let (tx, rx) = std::sync::mpsc::channel();
        result_slice.map_async(wgpu::MapMode::Read, move |result| {
            tx.send(result).unwrap();
        });

        // Poll device until mapping completes
        loop {
            self.device.poll(wgpu::Maintain::Wait);
            if let Ok(Ok(())) = rx.try_recv() {
                break;
            }
        }

        let result_data = result_slice.get_mapped_range();

        // Parse results: first u32 is match count, rest are matches
        let match_count = u32::from_le_bytes([
            result_data[0], result_data[1], result_data[2], result_data[3],
        ]) as usize;
        let matches: Vec<u32> = (1..=match_count)
            .map(|i| {
                let start = i * 4;
                u32::from_le_bytes([
                    result_data[start],
                    result_data[start + 1],
                    result_data[start + 2],
                    result_data[start + 3],
                ])
            })
            .collect();

        Ok(QueryResult {
            matches,
            workgroups_dispatched: workgroups_needed,
        })
    }

    /// Get WGSL shader source for pattern scanning
    fn get_pattern_scan_shader() -> &'static str {
        r#"
// Hilbert Pattern Scanner Compute Shader
// Scans spatial data for byte patterns along Hilbert curve

struct QueryUniforms {
    bbox_x_min: u32,
    bbox_y_min: u32,
    bbox_x_max: u32,
    bbox_y_max: u32,
    grid_size: u32,
    pattern_len: u32,
    padding1: u32,
    padding2: u32,
    pattern: vec4<u32>,
}

@group(0) @binding(0)
var input_texture: texture_2d<f32>;

@group(0) @binding(1)
var<storage, read_write> result_buffer: array<atomic<u32>>;

@group(0) @binding(2)
var<uniform> uniforms: QueryUniforms;

fn hilbert_d2xy(n: u32, d: u32) -> vec2<u32> {
    var x = 0u;
    var y = 0u;
    var s = 1u;
    var dd = d;

    for (var i = 0u; i < 16u; i++) {
        if (s >= n) { break; }

        let rx = 1u & (dd / 2u);
        let ry = 1u & (dd ^ rx);

        if (ry == 0u) {
            if (rx == 1u) {
                x = s - 1u - x;
                y = s - 1u - y;
            }
            let tmp = x;
            x = y;
            y = tmp;
        }

        x = x + s * rx;
        y = y + s * ry;
        dd = dd / 4u;
        s = s * 2u;
    }

    return vec2<u32>(x, y);
}

fn get_pattern_byte(idx: u32) -> u32 {
    let word = idx / 4u;
    let byte = idx % 4u;
    let w = uniforms.pattern[word];
    return (w >> (byte * 8u)) & 0xFFu;
}

fn check_match(global_idx: u32, start_channel: u32) -> bool {
    var current_i = global_idx;
    var current_channel = start_channel;
    
    var hpos = hilbert_d2xy(uniforms.grid_size, current_i);
    var abs_x = uniforms.bbox_x_min + hpos.x;
    var abs_y = uniforms.bbox_y_min + hpos.y;
    var pixel = textureLoad(input_texture, vec2<i32>(i32(abs_x), i32(abs_y)), 0);
    var bytes = vec3<u32>(
        u32(pixel.r * 255.0 + 0.5),
        u32(pixel.g * 255.0 + 0.5),
        u32(pixel.b * 255.0 + 0.5)
    );

    for (var p = 0u; p < uniforms.pattern_len; p++) {
        let expected = get_pattern_byte(p);
        let actual = bytes[current_channel];
        if (expected != actual) {
            return false;
        }

        current_channel += 1u;
        if (current_channel > 2u) {
            current_channel = 0u;
            // Advance to next valid pixel
            current_i += 1u;
            var found = false;
            while (current_i < uniforms.grid_size * uniforms.grid_size) {
                hpos = hilbert_d2xy(uniforms.grid_size, current_i);
                abs_x = uniforms.bbox_x_min + hpos.x;
                abs_y = uniforms.bbox_y_min + hpos.y;
                if (abs_x <= uniforms.bbox_x_max && abs_y <= uniforms.bbox_y_max) {
                    pixel = textureLoad(input_texture, vec2<i32>(i32(abs_x), i32(abs_y)), 0);
                    bytes = vec3<u32>(
                        u32(pixel.r * 255.0 + 0.5),
                        u32(pixel.g * 255.0 + 0.5),
                        u32(pixel.b * 255.0 + 0.5)
                    );
                    found = true;
                    break;
                }
                current_i += 1u;
            }
            if (!found && p + 1u < uniforms.pattern_len) {
                return false; // Reached end of bbox before pattern finished
            }
        }
    }
    return true;
}

@compute @workgroup_size(64, 1, 1)
fn main(@builtin(global_invocation_id) global_id: vec3<u32>) {
    let global_idx = global_id.x;

    let hilbert_pos = hilbert_d2xy(uniforms.grid_size, global_idx);
    let abs_x = uniforms.bbox_x_min + hilbert_pos.x;
    let abs_y = uniforms.bbox_y_min + hilbert_pos.y;

    if (abs_x > uniforms.bbox_x_max || abs_y > uniforms.bbox_y_max) {
        return;
    }

    // Try matching starting at R, G, and B channels
    for (var start_channel = 0u; start_channel < 3u; start_channel++) {
        if (check_match(global_idx, start_channel)) {
            // Found a match!
            let old_count = atomicAdd(&result_buffer[0], 1u);
            if (old_count < 1000u) {
                // Store match info (e.g. Hilbert distance * 3 + channel offset)
                // This represents the byte offset in the linear data
                let byte_offset = global_idx * 3u + start_channel;
                atomicStore(&result_buffer[old_count + 1u], byte_offset);
            }
        }
    }
}
"#
    }
}

#[cfg(feature = "gpu")]
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_gpu_query_engine_creation() {
        let engine = GpuQueryEngine::new();
        assert!(engine.is_ok());
    }

    #[test]
    fn test_pattern_scan_basic() {
        // Requires test PDB frame - will implement with fixtures
    }
}

// Stub implementation when GPU feature is disabled
#[cfg(not(feature = "gpu"))]
pub struct GpuQueryEngine;

#[cfg(not(feature = "gpu"))]
pub struct GpuQueryConfig;

#[cfg(not(feature = "gpu"))]
pub struct QueryResult;

#[cfg(not(feature = "gpu"))]
impl GpuQueryEngine {
    pub fn new() -> PdbResult<Self> {
        Err(PdbError::IoError("GPU feature not enabled".to_string()))
    }
}