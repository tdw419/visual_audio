use crate::pty::TerminalSession;
use glyphon::{Buffer, Metrics};

pub struct SpatialNode {
    pub id: String,
    pub world_x: f32,
    pub world_y: f32,
    pub target_x: Option<f32>,
    pub target_y: Option<f32>,
    pub width: f32,
    pub height: f32,

    pub content: Box<dyn crate::content::NodeContent>,

    // The Shell (WGPU Pixels)
    pub offscreen_texture: wgpu::Texture,
    pub offscreen_view: wgpu::TextureView,
    pub bind_group: wgpu::BindGroup,
    pub text_buffer: Buffer,
    pub is_focused: bool,
}

impl SpatialNode {
    pub fn new(
        id: &str,
        world_x: f32,
        world_y: f32,
        width: f32,
        height: f32,
        content: Box<dyn crate::content::NodeContent>,
        device: &wgpu::Device,
        bind_group_layout: &wgpu::BindGroupLayout,
        sampler: &wgpu::Sampler,
        font_system: &mut glyphon::FontSystem,
        texture_width: u32,
        texture_height: u32,
    ) -> Self {
        let texture_desc = wgpu::TextureDescriptor {
            label: Some(&format!("Node Texture: {}", id)),
            size: wgpu::Extent3d {
                width: texture_width,
                height: texture_height,
                depth_or_array_layers: 1,
            },
            mip_level_count: 1,
            sample_count: 1,
            dimension: wgpu::TextureDimension::D2,
            format: wgpu::TextureFormat::Rgba8UnormSrgb,
            usage: wgpu::TextureUsages::RENDER_ATTACHMENT | wgpu::TextureUsages::TEXTURE_BINDING | wgpu::TextureUsages::COPY_DST,
            view_formats: &[],
        };

        let texture = device.create_texture(&texture_desc);
        let view = texture.create_view(&Default::default());

        let bind_group = device.create_bind_group(&wgpu::BindGroupDescriptor {
            layout: bind_group_layout,
            entries: &[
                wgpu::BindGroupEntry {
                    binding: 0,
                    resource: wgpu::BindingResource::TextureView(&view),
                },
                wgpu::BindGroupEntry {
                    binding: 1,
                    resource: wgpu::BindingResource::Sampler(sampler),
                },
            ],
            label: Some(&format!("BindGroup: {}", id)),
        });

        let mut buffer = Buffer::new(font_system, Metrics::new(14.0, 18.0));
        buffer.set_size(font_system, 1024.0, 1024.0);

        Self {
            id: id.to_string(),
            world_x,
            world_y,
            target_x: None,
            target_y: None,
            width,
            height,
            content,
            offscreen_texture: texture,
            offscreen_view: view,
            bind_group,
            text_buffer: buffer,
            is_focused: false,
        }
    }

    pub fn contains_point(&self, wx: f32, wy: f32) -> bool {
        let half_w = self.width * 0.5;
        let half_h = self.height * 0.5;
        wx >= self.world_x - half_w
            && wx <= self.world_x + half_w
            && wy >= self.world_y - half_h
            && wy <= self.world_y + half_h
    }

    pub fn set_target(&mut self, x: f32, y: f32) {
        self.target_x = Some(x);
        self.target_y = Some(y);
    }

    pub fn update(&mut self, dt: f32) -> bool {
        let mut is_animating = false;
        let ease = 6.0; // snappy layout
        let t = (ease * dt).min(1.0);

        if let Some(tx) = self.target_x {
            self.world_x += (tx - self.world_x) * t;
            is_animating = true;
            if (tx - self.world_x).abs() < 0.001 {
                self.world_x = tx;
                self.target_x = None;
            }
        }
        if let Some(ty) = self.target_y {
            self.world_y += (ty - self.world_y) * t;
            is_animating = true;
            if (ty - self.world_y).abs() < 0.001 {
                self.world_y = ty;
                self.target_y = None;
            }
        }
        is_animating
    }
}
