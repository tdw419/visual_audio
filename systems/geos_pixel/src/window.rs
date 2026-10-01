//! GPU windowing system for geos_pixel — spatial window coordinator render
//! and interaction, ported from the Python/WGSL incubator (WC005-WC007).
//!
//! The WCB (Window Control Block) array lives in a `data_memory` storage
//! buffer as 64-byte spatial rows (stride 16 i32 words), base address 100:
//!
//! | off | field     | meaning                                   |
//! |-----|-----------|--------------------------------------------|
//! | 0   | STATE     | 0 = empty, 1 = active                      |
//! | 1   | X         | window origin column                      |
//! | 2   | Y         | window origin row                         |
//! | 3   | W         | width                                      |
//! | 4   | H         | height                                     |
//! | 5   | Z         | z-order (higher = closer to viewer)       |
//! | 6   | TICK_ADDR | coordinator dispatch target (WC004/005)   |
//! | 7   | counter   | persistent per-window tick state          |
//! | 8   | VISIBLE   | 0 = hidden, 1 = visible                   |
//! | 9-15| reserved  | future window state fields                |
//!
//! Two shaders operate on the same `data_memory` buffer, so a mutation by
//! one is automatically visible to the next dispatch of the other:
//!
//! - `glyph_render.wgsl` — composites the WCB rows into an RGBA image,
//!   Z-order aware (WC006).
//! - `glyph_interact.wgsl` — mutates the rows from mouse events: click
//!   raises the hit window to max_z + 1, drag adds a delta to the hit
//!   window's X/Y (WC007).
//!
//! Both shaders are byte-identical to the files verified in the Python
//! incubator on the RTX 5090 (Vulkan). [`interact_model`] is a pure-Rust
//! semantic mirror of the interact shader, used to diff GPU state against
//! host-computed expectations after every event.

use std::sync::Arc;

/// Base address of the WCB array in `data_memory` (words).
pub const WCB_BASE: usize = 100;
/// Stride between WCB rows in words (16 words = 64 bytes).
pub const WCB_STRIDE: usize = 16;
/// Maximum number of windows the coordinator supervises.
pub const MAX_WINDOWS: usize = 4;
/// Size of the spatial memory buffer in i32 words.
pub const MEM_WORDS: usize = 2048;
/// Render target width in pixels.
pub const SCREEN_W: u32 = 800;
/// Render target height in pixels.
pub const SCREEN_H: u32 = 600;
/// Size of the event buffer in i32 words.
pub const EV_WORDS: usize = 8;

/// Event type: no-op.
pub const EV_NONE: u32 = 0;
/// Event type: click — raise the topmost window at (x, y).
pub const EV_CLICK: u32 = 1;
/// Event type: drag — move the topmost window at (x, y) by (dx, dy).
pub const EV_DRAG: u32 = 2;

/// A single mouse event delivered to the GPU interaction shader.
///
/// Layout matches the shader's `events` buffer:
/// `[type, x, y, dx, dy, reserved, reserved, reserved]`.
#[derive(Debug, Clone, Copy)]
pub struct WindowEvent {
    /// One of [`EV_NONE`], [`EV_CLICK`], [`EV_DRAG`].
    pub event_type: u32,
    /// Pointer X (click anchor / drag grab anchor).
    pub x: i32,
    /// Pointer Y.
    pub y: i32,
    /// Drag delta X (drag events only).
    pub dx: i32,
    /// Drag delta Y (drag events only).
    pub dy: i32,
}

impl WindowEvent {
    /// Click at `(x, y)` — bring-to-front on the topmost window there.
    pub fn click(x: i32, y: i32) -> Self {
        Self { event_type: EV_CLICK, x, y, dx: 0, dy: 0 }
    }

    /// Drag by `(dx, dy)` grabbing the topmost window at `(x, y)`.
    pub fn drag(x: i32, y: i32, dx: i32, dy: i32) -> Self {
        Self { event_type: EV_DRAG, x, y, dx, dy }
    }

    fn pack(&self) -> [u8; EV_WORDS * 4] {
        let words = [self.event_type as i32, self.x, self.y, self.dx, self.dy, 0, 0, 0];
        let mut out = [0u8; EV_WORDS * 4];
        for (i, w) in words.iter().enumerate() {
            out[i * 4..i * 4 + 4].copy_from_slice(&w.to_le_bytes());
        }
        out
    }
}

/// Seed `mem` with the canonical 3-window test layout used by the Python
/// incubator (WC006/WC007): RED Z=1 at (50,50), GREEN Z=2 at (100,100),
/// BLUE Z=0 at (20,20), WCB3 empty.
pub fn seed_wcb_state(mem: &mut [i32]) {
    mem.fill(0);
    // WCB0: RED
    mem[WCB_BASE + 0] = 1;
    mem[WCB_BASE + 1] = 50;
    mem[WCB_BASE + 2] = 50;
    mem[WCB_BASE + 3] = 200;
    mem[WCB_BASE + 4] = 150;
    mem[WCB_BASE + 5] = 1;
    mem[WCB_BASE + 8] = 1;
    // WCB1: GREEN
    let b1 = WCB_BASE + WCB_STRIDE;
    mem[b1 + 0] = 1;
    mem[b1 + 1] = 100;
    mem[b1 + 2] = 100;
    mem[b1 + 3] = 200;
    mem[b1 + 4] = 150;
    mem[b1 + 5] = 2;
    mem[b1 + 8] = 1;
    // WCB2: BLUE
    let b2 = WCB_BASE + 2 * WCB_STRIDE;
    mem[b2 + 0] = 1;
    mem[b2 + 1] = 20;
    mem[b2 + 2] = 20;
    mem[b2 + 3] = 400;
    mem[b2 + 4] = 300;
    mem[b2 + 5] = 0;
    mem[b2 + 8] = 1;
    // WCB3: empty (STATE stays 0)
}

/// Pure-Rust semantic mirror of `glyph_interact.wgsl` `main()`.
///
/// Applies `ev` to `mem` in place using the same hit-test rule (topmost
/// visible active Z wins). Used to diff GPU state against host-computed
/// expectations byte-for-byte after every event.
pub fn interact_model(mem: &mut [i32], ev: &WindowEvent) {
    match ev.event_type {
        EV_CLICK => {
            let (mx, my) = (ev.x, ev.y);
            let mut hit: i32 = -1;
            let mut hit_z: i32 = -1;
            for i in 0..MAX_WINDOWS {
                let base = WCB_BASE + i * WCB_STRIDE;
                if mem[base] == 0 || mem[base + 8] == 0 {
                    continue;
                }
                let (wx, wy, ww, wh, wz) =
                    (mem[base + 1], mem[base + 2], mem[base + 3], mem[base + 4], mem[base + 5]);
                if mx >= wx && mx < wx + ww && my >= wy && my < wy + wh && wz > hit_z {
                    hit_z = wz;
                    hit = i as i32;
                }
            }
            if hit >= 0 {
                let mut max_z = 0;
                for j in 0..MAX_WINDOWS {
                    let b = WCB_BASE + j * WCB_STRIDE;
                    if mem[b] != 0 {
                        max_z = max_z.max(mem[b + 5]);
                    }
                }
                mem[WCB_BASE + hit as usize * WCB_STRIDE + 5] = max_z + 1;
            }
        }
        EV_DRAG => {
            let (ax, ay, ddx, ddy) = (ev.x, ev.y, ev.dx, ev.dy);
            let mut hit: i32 = -1;
            let mut hit_z: i32 = -1;
            for i in 0..MAX_WINDOWS {
                let base = WCB_BASE + i * WCB_STRIDE;
                if mem[base] == 0 || mem[base + 8] == 0 {
                    continue;
                }
                let (wx, wy, ww, wh, wz) =
                    (mem[base + 1], mem[base + 2], mem[base + 3], mem[base + 4], mem[base + 5]);
                if ax >= wx && ax < wx + ww && ay >= wy && ay < wy + wh && wz > hit_z {
                    hit_z = wz;
                    hit = i as i32;
                }
            }
            if hit >= 0 {
                let hb = WCB_BASE + hit as usize * WCB_STRIDE;
                mem[hb + 1] += ddx;
                mem[hb + 2] += ddy;
            }
        }
        _ => {}
    }
}

/// GPU windowing system: owns the WCB memory buffer, the event buffer, the
/// render/interact pipelines, and the readback plumbing.
pub struct WindowSystem {
    device: Arc<wgpu::Device>,
    queue: Arc<wgpu::Queue>,
    adapter_name: String,
    mem_buf: wgpu::Buffer,
    ev_buf: wgpu::Buffer,
    out_buf: wgpu::Buffer,
    out_ro: wgpu::Buffer,
    mem_ro: wgpu::Buffer,
    render_pipeline: wgpu::ComputePipeline,
    interact_pipeline: wgpu::ComputePipeline,
    render_bg: wgpu::BindGroup,
    interact_bg: wgpu::BindGroup,
}

impl WindowSystem {
    /// Create the window system on the high-performance GPU adapter.
    ///
    /// # Errors
    /// Returns an error string if no suitable adapter is found or device
    /// creation fails.
    pub fn new() -> Result<Self, String> {
        let instance = wgpu::Instance::new(wgpu::InstanceDescriptor {
            backends: wgpu::Backends::all(),
            ..Default::default()
        });

        let adapter = pollster::block_on(instance.request_adapter(&wgpu::RequestAdapterOptions {
            power_preference: wgpu::PowerPreference::HighPerformance,
            compatible_surface: None,
            force_fallback_adapter: false,
        }))
        .ok_or_else(|| "no suitable GPU adapter found".to_string())?;

        let adapter_name = adapter.get_info().name.clone();

        let (device, queue) = pollster::block_on(adapter.request_device(
            &wgpu::DeviceDescriptor {
                label: Some("geos_pixel window system"),
                required_features: wgpu::Features::empty(),
                required_limits: wgpu::Limits {
                    max_storage_buffers_per_shader_stage: 2,
                    max_uniform_buffers_per_shader_stage: 2,
                    ..Default::default()
                },
            },
            None,
        ))
        .map_err(|e| format!("request_device: {e}"))?;

        let device = Arc::new(device);
        let queue = Arc::new(queue);

        let render_shader = device.create_shader_module(wgpu::ShaderModuleDescriptor {
            label: Some("glyph_render"),
            source: wgpu::ShaderSource::Wgsl(include_str!("../shaders/glyph_render.wgsl").into()),
        });
        let interact_shader = device.create_shader_module(wgpu::ShaderModuleDescriptor {
            label: Some("glyph_interact"),
            source: wgpu::ShaderSource::Wgsl(include_str!("../shaders/glyph_interact.wgsl").into()),
        });

        let mem_buf = device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("wcb data_memory"),
            size: (MEM_WORDS * 4) as u64,
            usage: wgpu::BufferUsages::STORAGE
                | wgpu::BufferUsages::COPY_DST
                | wgpu::BufferUsages::COPY_SRC,
            mapped_at_creation: false,
        });
        let ev_buf = device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("window events"),
            size: (EV_WORDS * 4) as u64,
            usage: wgpu::BufferUsages::STORAGE | wgpu::BufferUsages::COPY_DST,
            mapped_at_creation: false,
        });
        let out_size = (SCREEN_W * SCREEN_H * 4) as u64;
        let out_buf = device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("render out_image"),
            size: out_size,
            usage: wgpu::BufferUsages::STORAGE | wgpu::BufferUsages::COPY_SRC,
            mapped_at_creation: false,
        });
        let out_ro = device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("render readback"),
            size: out_size,
            usage: wgpu::BufferUsages::MAP_READ | wgpu::BufferUsages::COPY_DST,
            mapped_at_creation: false,
        });
        let mem_ro = device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("memory readback"),
            size: (MEM_WORDS * 4) as u64,
            usage: wgpu::BufferUsages::MAP_READ | wgpu::BufferUsages::COPY_DST,
            mapped_at_creation: false,
        });

        let render_pipeline = device.create_compute_pipeline(&wgpu::ComputePipelineDescriptor {
            label: Some("render pipeline"),
            layout: None,
            module: &render_shader,
            entry_point: "main",
            compilation_options: Default::default(),
        });
        let interact_pipeline = device.create_compute_pipeline(&wgpu::ComputePipelineDescriptor {
            label: Some("interact pipeline"),
            layout: None,
            module: &interact_shader,
            entry_point: "main",
            compilation_options: Default::default(),
        });

        let render_bg = device.create_bind_group(&wgpu::BindGroupDescriptor {
            label: Some("render bind group"),
            layout: &render_pipeline.get_bind_group_layout(0),
            entries: &[
                wgpu::BindGroupEntry { binding: 0, resource: mem_buf.as_entire_binding() },
                wgpu::BindGroupEntry { binding: 1, resource: out_buf.as_entire_binding() },
            ],
        });
        let interact_bg = device.create_bind_group(&wgpu::BindGroupDescriptor {
            label: Some("interact bind group"),
            layout: &interact_pipeline.get_bind_group_layout(0),
            entries: &[
                wgpu::BindGroupEntry { binding: 0, resource: mem_buf.as_entire_binding() },
                wgpu::BindGroupEntry { binding: 1, resource: ev_buf.as_entire_binding() },
            ],
        });

        Ok(Self {
            device,
            queue,
            adapter_name,
            mem_buf,
            ev_buf,
            out_buf,
            out_ro,
            mem_ro,
            render_pipeline,
            interact_pipeline,
            render_bg,
            interact_bg,
        })
    }

    /// Adapter name, for verification output (e.g. "NVIDIA GeForce RTX 5090").
    pub fn adapter_name(&self) -> &str {
        &self.adapter_name
    }

    /// Write a full `MEM_WORDS`-length memory image (e.g. from
    /// [`seed_wcb_state`]) into the GPU WCB buffer.
    pub fn write_memory(&self, mem: &[i32]) {
        debug_assert_eq!(mem.len(), MEM_WORDS);
        let bytes: Vec<u8> = mem.iter().flat_map(|w| w.to_le_bytes()).collect();
        self.queue.write_buffer(&self.mem_buf, 0, &bytes);
    }

    /// Read the WCB buffer back to the host.
    pub fn read_memory(&self) -> Vec<i32> {
        let mut encoder = self
            .device
            .create_command_encoder(&wgpu::CommandEncoderDescriptor {
                label: Some("mem readback encoder"),
            });
        encoder.copy_buffer_to_buffer(
            &self.mem_buf,
            0,
            &self.mem_ro,
            0,
            (MEM_WORDS * 4) as u64,
        );
        self.queue.submit(Some(encoder.finish()));

        let slice = self.mem_ro.slice(..);
        let (tx, rx) = std::sync::mpsc::channel();
        slice.map_async(wgpu::MapMode::Read, move |r| {
            let _ = tx.send(r);
        });
        loop {
            self.device.poll(wgpu::Maintain::Wait);
            if let Ok(Ok(())) = rx.try_recv() {
                break;
            }
        }
        let data = slice.get_mapped_range();
        let mut out = Vec::with_capacity(MEM_WORDS);
        for i in 0..MEM_WORDS {
            out.push(i32::from_le_bytes([
                data[i * 4],
                data[i * 4 + 1],
                data[i * 4 + 2],
                data[i * 4 + 3],
            ]));
        }
        drop(data);
        self.mem_ro.unmap();
        out
    }

    /// Deliver one mouse event to the GPU interaction shader.
    pub fn send_event(&self, ev: &WindowEvent) {
        self.queue.write_buffer(&self.ev_buf, 0, &ev.pack());
        let mut encoder = self
            .device
            .create_command_encoder(&wgpu::CommandEncoderDescriptor {
                label: Some("interact encoder"),
            });
        {
            let mut cpass = encoder.begin_compute_pass(&wgpu::ComputePassDescriptor {
                label: Some("interact pass"),
                timestamp_writes: None,
            });
            cpass.set_pipeline(&self.interact_pipeline);
            cpass.set_bind_group(0, &self.interact_bg, &[]);
            cpass.dispatch_workgroups(1, 1, 1);
        }
        self.queue.submit(Some(encoder.finish()));
    }

    /// Composite the current WCB state into an RGBA image
    /// (`SCREEN_W * SCREEN_H * 4` bytes, row-major, R/G/B/A order).
    pub fn render(&self) -> Vec<u8> {
        let mut encoder = self
            .device
            .create_command_encoder(&wgpu::CommandEncoderDescriptor {
                label: Some("render encoder"),
            });
        {
            let mut cpass = encoder.begin_compute_pass(&wgpu::ComputePassDescriptor {
                label: Some("render pass"),
                timestamp_writes: None,
            });
            cpass.set_pipeline(&self.render_pipeline);
            cpass.set_bind_group(0, &self.render_bg, &[]);
            cpass.dispatch_workgroups((SCREEN_W + 15) / 16, (SCREEN_H + 15) / 16, 1);
        }
        encoder.copy_buffer_to_buffer(
            &self.out_buf,
            0,
            &self.out_ro,
            0,
            (SCREEN_W * SCREEN_H * 4) as u64,
        );
        self.queue.submit(Some(encoder.finish()));

        let slice = self.out_ro.slice(..);
        let (tx, rx) = std::sync::mpsc::channel();
        slice.map_async(wgpu::MapMode::Read, move |r| {
            let _ = tx.send(r);
        });
        loop {
            self.device.poll(wgpu::Maintain::Wait);
            if let Ok(Ok(())) = rx.try_recv() {
                break;
            }
        }
        let data = slice.get_mapped_range();
        let out = data.to_vec();
        drop(data);
        self.out_ro.unmap();
        out
    }

    /// Convenience pixel probe on a render result.
    pub fn pixel(&self, img: &[u8], x: u32, y: u32) -> [u8; 4] {
        let idx = ((y * SCREEN_W + x) * 4) as usize;
        [img[idx], img[idx + 1], img[idx + 2], img[idx + 3]]
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_seed_layout() {
        let mut mem = vec![0i32; MEM_WORDS];
        seed_wcb_state(&mut mem);
        assert_eq!(mem[WCB_BASE + 0], 1);
        assert_eq!(mem[WCB_BASE + 5], 1); // RED Z
        let b1 = WCB_BASE + WCB_STRIDE;
        assert_eq!(mem[b1 + 5], 2); // GREEN Z
        let b2 = WCB_BASE + 2 * WCB_STRIDE;
        assert_eq!(mem[b2 + 5], 0); // BLUE Z
        let b3 = WCB_BASE + 3 * WCB_STRIDE;
        assert_eq!(mem[b3 + 0], 0); // WCB3 empty
    }

    #[test]
    fn test_interact_click_raise() {
        let mut mem = vec![0i32; MEM_WORDS];
        seed_wcb_state(&mut mem);
        // Click inside RED (60,60): RED is topmost there (Z=1 > BLUE Z=0).
        interact_model(&mut mem, &WindowEvent::click(60, 60));
        assert_eq!(mem[WCB_BASE + 5], 3, "RED raised to max_z+1 = 3");
        // GREEN exclusive region untouched
        let b1 = WCB_BASE + WCB_STRIDE;
        assert_eq!(mem[b1 + 5], 2);
    }

    #[test]
    fn test_interact_drag_move() {
        let mut mem = vec![0i32; MEM_WORDS];
        seed_wcb_state(&mut mem);
        // Drag RED (topmost at 60,60) by (+100,+50).
        interact_model(&mut mem, &WindowEvent::drag(60, 60, 100, 50));
        assert_eq!(mem[WCB_BASE + 1], 150, "X 50 + 100");
        assert_eq!(mem[WCB_BASE + 2], 100, "Y 50 + 50");
        // Only X/Y of the hit window changed; Z untouched by drag.
        assert_eq!(mem[WCB_BASE + 5], 1);
    }

    #[test]
    fn test_interact_empty_and_miss() {
        let mut mem = vec![0i32; MEM_WORDS];
        seed_wcb_state(&mut mem);
        // Click on background: no hit, nothing changes.
        let before = mem.clone();
        interact_model(&mut mem, &WindowEvent::click(700, 500));
        assert_eq!(mem, before);
        // Click must not dispatch empty WCB3.
        let b3 = WCB_BASE + 3 * WCB_STRIDE;
        assert_eq!(mem[b3 + 5], 0);
    }
}
