// Hilbert compute shader decoder (WGPU)
// GPU-native pixel → byte decoding with direct guest RAM DMA
use anyhow::Result;
use bytemuck;
use log::info;
use wgpu::*;
use std::sync::Arc;

use crate::wgpu_texture_loader::MkvTexture;

/// Hilbert compute shader decoder
pub struct HilbertDecoder {
    device: Arc<Device>,
    queue: Arc<Queue>,
    pipeline: ComputePipeline,
    bind_group_layout: BindGroupLayout,
    write_bind_group_layout: BindGroupLayout, // For direct guest memory writes
}

impl HilbertDecoder {
    /// Create Hilbert decoder with compiled compute pipeline
    pub fn new(device: Arc<Device>, queue: Arc<Queue>) -> Result<Self> {
        info!("Initializing Hilbert compute shader decoder...");

        // Load WGSL shader
        let shader_code = include_str!("../shaders/hilbert_decode.wgsl");
        let shader = device.create_shader_module(ShaderModuleDescriptor {
            label: Some("Hilbert Decode Shader"),
            source: ShaderSource::Wgsl(shader_code.into()),
        });

        // Create bind group layout for decode (read)
        let bind_group_layout = device.create_bind_group_layout(&BindGroupLayoutDescriptor {
            label: Some("Hilbert Decode Bind Group Layout"),
            entries: &[
                // Binding 0: Texture (read-only)
                BindGroupLayoutEntry {
                    binding: 0,
                    visibility: ShaderStages::COMPUTE,
                    ty: BindingType::Texture {
                        sample_type: TextureSampleType::Float { filterable: false },
                        view_dimension: TextureViewDimension::D2,
                        multisampled: false,
                    },
                    count: None,
                },
                // Binding 1: Storage buffer (output)
                BindGroupLayoutEntry {
                    binding: 1,
                    visibility: ShaderStages::COMPUTE,
                    ty: BindingType::Buffer {
                        ty: BufferBindingType::Storage { read_only: false },
                        has_dynamic_offset: false,
                        min_binding_size: None,
                    },
                    count: None,
                },
                // Binding 2: Uniform params
                BindGroupLayoutEntry {
                    binding: 2,
                    visibility: ShaderStages::COMPUTE,
                    ty: BindingType::Buffer {
                        ty: BufferBindingType::Uniform,
                        has_dynamic_offset: false,
                        min_binding_size: None,
                    },
                    count: None,
                },
            ],
        });

        // Create bind group layout for direct memory writes (DMA)
        // Binding 0: Texture (read-only)
        // Binding 1: Guest RAM buffer (write-only)
        let write_bind_group_layout = device.create_bind_group_layout(&BindGroupLayoutDescriptor {
            label: Some("Hilbert DMA Bind Group Layout"),
            entries: &[
                BindGroupLayoutEntry {
                    binding: 0,
                    visibility: ShaderStages::COMPUTE,
                    ty: BindingType::Texture {
                        sample_type: TextureSampleType::Float { filterable: false },
                        view_dimension: TextureViewDimension::D2,
                        multisampled: false,
                    },
                    count: None,
                },
                BindGroupLayoutEntry {
                    binding: 1,
                    visibility: ShaderStages::COMPUTE,
                    ty: BindingType::Buffer {
                        ty: BufferBindingType::Storage { read_only: false },
                        has_dynamic_offset: false,
                        min_binding_size: None,
                    },
                    count: None,
                },
            ],
        });

        // Create pipeline layout
        let pipeline_layout = device.create_pipeline_layout(&PipelineLayoutDescriptor {
            label: Some("Hilbert Decode Pipeline Layout"),
            bind_group_layouts: &[&bind_group_layout],
            push_constant_ranges: &[],
        });

        // Create compute pipeline
        let pipeline = device.create_compute_pipeline(&ComputePipelineDescriptor {
            label: Some("Hilbert Decode Compute Pipeline"),
            layout: Some(&pipeline_layout),
            module: &shader,
            entry_point: "decode_hilbert_bytes",
            compilation_options: Default::default(),
        });

        info!("Hilbert decoder initialized successfully");

        Ok(Self {
            device,
            queue,
            pipeline,
            bind_group_layout,
            write_bind_group_layout,
        })
    }

    /// Decode bytes from MKV texture via Hilbert curve
    ///
    /// # Arguments
    /// * `texture` - MkvTexture (already loaded on GPU)
    /// * `start_byte` - Starting byte index (0 = frame start)
    /// * `num_bytes` - Number of bytes to decode
    ///
    /// # Returns
    /// Decoded bytes (Vec<u8>)
    pub fn decode(
        &self,
        texture: &MkvTexture,
        start_byte: u32,
        num_bytes: u32,
    ) -> Result<Vec<u8>> {
        info!(
            "Decoding {} bytes from texture (start: {})",
            num_bytes, start_byte
        );

        // Create output storage buffer (u32 elements, GPU-only)
        let output_buffer = self.device.create_buffer(&BufferDescriptor {
            label: Some("Hilbert Decode Output"),
            size: (num_bytes as u64) * 4, // u32 elements = 4 bytes each
            usage: BufferUsages::STORAGE | BufferUsages::COPY_SRC,
            mapped_at_creation: false,
        });

        // Create readback buffer (CPU-mappable, same size)
        let readback_buffer = self.device.create_buffer(&BufferDescriptor {
            label: Some("Hilbert Decode Readback"),
            size: (num_bytes as u64) * 4,
            usage: BufferUsages::COPY_DST | BufferUsages::MAP_READ,
            mapped_at_creation: false,
        });

        // Create uniform params buffer
        #[repr(C)]
        #[derive(Copy, Clone, bytemuck::Pod, bytemuck::Zeroable)]
        struct DecodeParams {
            frame_index: u32,
            start_byte: u32,
            num_bytes: u32,
            frame_size: u32,
        }

        let params = DecodeParams {
            frame_index: texture.frame_index as u32,
            start_byte,
            num_bytes,
            frame_size: texture.extent.width,
        };

        let params_buffer = self.device.create_buffer_init(&BufferInitDescriptor {
            label: Some("Hilbert Decode Params"),
            contents: bytemuck::bytes_of(&params),
            usage: BufferUsages::UNIFORM | BufferUsages::COPY_DST,
        });

        // Create bind group
        let bind_group = self.device.create_bind_group(&BindGroupDescriptor {
            label: Some("Hilbert Decode Bind Group"),
            layout: &self.bind_group_layout,
            entries: &[
                BindGroupEntry {
                    binding: 0,
                    resource: BindingResource::TextureView(&texture.view),
                },
                BindGroupEntry {
                    binding: 1,
                    resource: BindingResource::Buffer(BufferBinding {
                        buffer: &output_buffer,
                        offset: 0,
                        size: None,
                    }),
                },
                BindGroupEntry {
                    binding: 2,
                    resource: BindingResource::Buffer(BufferBinding {
                        buffer: &params_buffer,
                        offset: 0,
                        size: None,
                    }),
                },
            ],
        });

        // Create command encoder
        let mut encoder = self
            .device
            .create_command_encoder(&CommandEncoderDescriptor {
                label: Some("Hilbert Decode Command Encoder"),
            });

        // Dispatch compute shader
        {
            let mut compute_pass = encoder.begin_compute_pass(&ComputePassDescriptor {
                label: Some("Hilbert Decode Pass"),
                timestamp_writes: None,
            });
            compute_pass.set_pipeline(&self.pipeline);
            compute_pass.set_bind_group(0, &bind_group, &[]);

            // Workgroup size is 16x16 = 256 items
            // Dispatch enough workgroups for num_bytes
            let workgroups = ((num_bytes + 255) / 256).max(1);
            compute_pass.dispatch_workgroups(workgroups, 1, 1);
        }

        // Copy output buffer to readback buffer (copy all u32 elements)
        encoder.copy_buffer_to_buffer(
            &output_buffer,
            0,
            &readback_buffer,
            0,
            (num_bytes as u64) * 4,
        );

        // Submit commands
        self.queue.submit(Some(encoder.finish()));

        // Read back results (blocking)
        let slice = readback_buffer.slice(..);
        slice.map_async(MapMode::Read, |_| {});
        self.device.poll(MaintainBase::Wait);

        // Convert u32 buffer to u8 (take only low byte of each u32)
        let u32_data: Vec<u32> = bytemuck::cast_slice(slice.get_mapped_range().as_ref()).to_vec();
        let u8_data: Vec<u8> = u32_data.iter().map(|v| *v as u8).collect();

        readback_buffer.unmap();

        info!("Decoded {} bytes via Hilbert compute shader", u8_data.len());

        Ok(u8_data)
    }

    /// Decode bytes from MKV texture with direct DMA to guest RAM
    ///
    /// This is Phase 4: Direct DMA to Guest RAM. Instead of allocating a readback
    /// buffer and copying bytes to CPU, we copy GPU output directly to guest RAM.
    ///
    /// # Arguments
    /// * `texture` - MkvTexture (already loaded on GPU)
    /// * `start_byte` - Starting byte index (0 = frame start)
    /// * `num_bytes` - Number of bytes to decode
    /// * `guest_ram_ptr` - Pointer to guest RAM (mmap'd region)
    ///
    /// # Returns
    /// Number of bytes decoded
    pub fn decode_direct_dma(
        &self,
        texture: &wgpu::Texture,
        frame_index: u32,
        frame_width: u32,
        start_byte: u32,
        num_bytes: u32,
        guest_ram_ptr: *mut u8,
    ) -> Result<usize> {
        info!(
            "DMA decode: {} bytes from texture (start: {}) → guest RAM 0x{:x}",
            num_bytes, start_byte, guest_ram_ptr as usize
        );
        let t_start = std::time::Instant::now();

        // Create output storage buffer (u32 elements, GPU-only)
        let output_buffer = self.device.create_buffer(&BufferDescriptor {
            label: Some("Hilbert DMA Output"),
            size: (num_bytes as u64) * 4, // u32 elements = 4 bytes each
            usage: BufferUsages::STORAGE | BufferUsages::COPY_SRC,
            mapped_at_creation: false,
        });

        // Create staging buffer for readback
        let readback_buffer = self.device.create_buffer(&BufferDescriptor {
            label: Some("Hilbert DMA Readback"),
            size: (num_bytes as u64) * 4,
            usage: BufferUsages::COPY_DST | BufferUsages::MAP_READ,
            mapped_at_creation: false,
        });

        // Create uniform params buffer
        #[repr(C)]
        #[derive(Copy, Clone, bytemuck::Pod, bytemuck::Zeroable)]
        struct DecodeParams {
            frame_index: u32,
            start_byte: u32,
            num_bytes: u32,
            frame_size: u32,
        }

        let params = DecodeParams {
            frame_index: frame_index,
            start_byte,
            num_bytes,
            frame_size: frame_width,
        };

        let params_buffer = self.device.create_buffer_init(&BufferInitDescriptor {
            label: Some("Hilbert DMA Params"),
            contents: bytemuck::bytes_of(&params),
            usage: BufferUsages::UNIFORM | BufferUsages::COPY_DST,
        });

        // Create texture view
        let view = texture.create_view(&wgpu::TextureViewDescriptor::default());

        // Create bind group
        let bind_group = self.device.create_bind_group(&BindGroupDescriptor {
            label: Some("Hilbert DMA Bind Group"),
            layout: &self.bind_group_layout,
            entries: &[
                BindGroupEntry {
                    binding: 0,
                    resource: BindingResource::TextureView(&view),
                },
                BindGroupEntry {
                    binding: 1,
                    resource: BindingResource::Buffer(BufferBinding {
                        buffer: &output_buffer,
                        offset: 0,
                        size: None,
                    }),
                },
                BindGroupEntry {
                    binding: 2,
                    resource: BindingResource::Buffer(BufferBinding {
                        buffer: &params_buffer,
                        offset: 0,
                        size: None,
                    }),
                },
            ],
        });

        // Create command encoder
        let mut encoder = self
            .device
            .create_command_encoder(&CommandEncoderDescriptor {
                label: Some("Hilbert DMA Command Encoder"),
            });

        // Dispatch compute shader
        {
            let mut compute_pass = encoder.begin_compute_pass(&ComputePassDescriptor {
                label: Some("Hilbert DMA Pass"),
                timestamp_writes: None,
            });
            compute_pass.set_pipeline(&self.pipeline);
            compute_pass.set_bind_group(0, &bind_group, &[]);

            // Workgroup size is 16x16 = 256 items
            // Dispatch enough workgroups for num_bytes
            let workgroups = ((num_bytes + 255) / 256).max(1);
            compute_pass.dispatch_workgroups(workgroups, 1, 1);
        }

        // Copy output buffer to readback staging buffer
        encoder.copy_buffer_to_buffer(
            &output_buffer,
            0,
            &readback_buffer,
            0,
            (num_bytes as u64) * 4,
        );

        // Submit commands
        let t_setup = t_start.elapsed();
        self.queue.submit(Some(encoder.finish()));

        // Wait for GPU to finish
        self.device.poll(MaintainBase::Wait);
        let t_submit_poll = t_start.elapsed();

        // Copy GPU output buffer directly to guest RAM
        let guest_ram_slice =
            unsafe { std::slice::from_raw_parts_mut(guest_ram_ptr, num_bytes as usize) };

        // Read from GPU buffer
        let gpu_buffer_slice = readback_buffer.slice(..);
        gpu_buffer_slice.map_async(MapMode::Read, |_| {});
        self.device.poll(MaintainBase::Wait);
        let t_map_poll = t_start.elapsed();
        info!(
            "  DMA timing: setup={:?} submit_poll={:?} map_poll={:?}",
            t_setup, t_submit_poll - t_setup, t_map_poll - t_submit_poll
        );

        // Convert u32 to u8 and write directly to guest RAM
        let u32_data: Vec<u32> =
            bytemuck::cast_slice(gpu_buffer_slice.get_mapped_range().as_ref()).to_vec();
        for (i, val) in u32_data.iter().enumerate() {
            if i < guest_ram_slice.len() {
                guest_ram_slice[i] = *val as u8;
            }
        }

        readback_buffer.unmap();

        let first_bytes: Vec<u8> = u32_data.iter().take(16).map(|&val| val as u8).collect();
        info!(
            "DMA complete: {} bytes written to guest RAM. First 16: {:?}",
            guest_ram_slice.len(), first_bytes
        );

        Ok(guest_ram_slice.len())
    }

    /// Get reference to WGPU device (for texture loading)
    pub fn device(&self) -> &Arc<Device> {
        &self.device
    }

    /// Get reference to WGPU queue (for texture loading)
    pub fn queue(&self) -> &Arc<Queue> {
        &self.queue
    }
}

// Buffer init helper (from wgpu::util)
struct BufferInitDescriptor<'a> {
    label: Option<&'a str>,
    contents: &'a [u8],
    usage: BufferUsages,
}

trait DeviceExt {
    fn create_buffer_init(&self, desc: &BufferInitDescriptor) -> Buffer;
}

impl DeviceExt for Device {
    fn create_buffer_init(&self, desc: &BufferInitDescriptor) -> Buffer {
        let buffer = self.create_buffer(&BufferDescriptor {
            label: desc.label,
            size: desc.contents.len() as u64,
            usage: desc.usage | BufferUsages::COPY_DST,
            mapped_at_creation: true,
        });
        buffer
            .slice(..)
            .get_mapped_range_mut()
            .copy_from_slice(desc.contents);
        buffer.unmap();
        buffer
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_hilbert_decoder_init() {
        // Test requires WGPU device
        // Skip in CI
    }
}