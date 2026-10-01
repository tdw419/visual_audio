use crate::pty::TerminalSession;
use glyphon::{
    Attrs, Color, Family, FontSystem, Resolution, Shaping, SwashCache, TextArea, TextBounds,
    TextRenderer, TextAtlas, Weight, Style, Metrics
};
use wgpu;
use pulldown_cmark::{Parser, Event, Tag, TagEnd, HeadingLevel};

pub enum NodeEvent<'a> {
    Keyboard(&'a str),
    Resize(u32, u32),
}

pub trait NodeContent {
    /// Update the internal state (e.g., read PTY)
    fn update(&mut self);
    
    /// Write the content into the WGPU ecosystem.
    /// Note: This signature forces all implementors to accept `glyphon` and `wgpu`
    /// parameters even if they don't use them (e.g. an ImageContent wouldn't use glyphon). 
    /// This is an intentional simplicity/generality trade-off to keep `main.rs` uninvolved 
    /// in per-type branching for now.
    #[allow(clippy::too_many_arguments)]
    fn render(
        &mut self,
        device: &wgpu::Device,
        queue: &wgpu::Queue,
        offscreen_view: &wgpu::TextureView,
        text_buffer: &mut glyphon::Buffer,
        font_system: &mut FontSystem,
        text_renderer: &mut TextRenderer,
        text_atlas: &mut TextAtlas,
        swash_cache: &mut SwashCache,
        is_focused: bool,
    );

    /// Handle user input routed from the compositor
    fn handle_event(&mut self, event: NodeEvent);

    /// Extract text representation (used by agents to read the screen)
    fn get_lines(&self) -> Option<Vec<String>> {
        None
    }

    /// Extract raw pixel data for texture upload (used by image nodes)
    fn pixel_data(&mut self) -> Option<(&[u8], u32, u32)> {
        None
    }
}

pub struct TerminalContent {
    pub pty: TerminalSession,
}

impl TerminalContent {
    pub fn new(cols: u16, rows: u16, shell_cmd: Option<String>) -> Self {
        let pty = if let Some(cmd) = shell_cmd {
            TerminalSession::new_with_command(cols, rows, &cmd)
        } else {
            TerminalSession::new(cols, rows)
        };
        Self { pty }
    }
}

impl NodeContent for TerminalContent {
    fn update(&mut self) {}

    fn render(
        &mut self,
        device: &wgpu::Device,
        queue: &wgpu::Queue,
        offscreen_view: &wgpu::TextureView,
        text_buffer: &mut glyphon::Buffer,
        font_system: &mut FontSystem,
        text_renderer: &mut TextRenderer,
        text_atlas: &mut TextAtlas,
        swash_cache: &mut SwashCache,
        is_focused: bool,
    ) {
        let screen_text = {
            let p = self.pty.parser.lock().unwrap();
            let mut txt = String::new();
            for row in p.screen().rows_formatted(0, p.screen().size().0) {
                let row_str = String::from_utf8_lossy(&row).to_string();
                let clean = strip_ansi_escapes::strip(&row_str);
                txt.push_str(&String::from_utf8_lossy(&clean));
                txt.push('\n');
            }
            txt
        };

        text_buffer.set_text(
            font_system,
            &screen_text,
            Attrs::new().family(Family::Monospace),
            Shaping::Advanced,
        );

        let _ = text_renderer.prepare(
            device,
            queue,
            font_system,
            text_atlas,
            Resolution { width: 1024, height: 1024 },
            [TextArea {
                buffer: text_buffer,
                left: 20.0,
                top: 20.0,
                scale: 1.0,
                bounds: TextBounds { left: 0, top: 0, right: 1024, bottom: 1024 },
                default_color: if is_focused { Color::rgb(0, 255, 204) } else { Color::rgb(180, 190, 200) },
            }],
            swash_cache,
        ).unwrap();

        let mut encoder = device.create_command_encoder(&wgpu::CommandEncoderDescriptor {
            label: Some("Encoder Pass1 Terminal"),
        });

        {
            let mut pass = encoder.begin_render_pass(&wgpu::RenderPassDescriptor {
                label: Some("Pass1 Text Terminal"),
                color_attachments: &[Some(wgpu::RenderPassColorAttachment {
                    view: offscreen_view,
                    resolve_target: None,
                    ops: wgpu::Operations {
                        load: wgpu::LoadOp::Clear(wgpu::Color { r: 0.05, g: 0.06, b: 0.08, a: 1.0 }),
                        store: wgpu::StoreOp::Store,
                    },
                })],
                depth_stencil_attachment: None,
                timestamp_writes: None,
                occlusion_query_set: None,
            });

            text_renderer.render(text_atlas, &mut pass).unwrap();
        }
        queue.submit(std::iter::once(encoder.finish()));
    }

    fn handle_event(&mut self, event: NodeEvent) {
        match event {
            NodeEvent::Keyboard(s) => {
                use std::io::Write;
                let _ = self.pty.writer.write_all(s.as_bytes());
            }
            NodeEvent::Resize(_w, _h) => {}
        }
    }

    fn get_lines(&self) -> Option<Vec<String>> {
        let p = self.pty.parser.lock().unwrap();
        let mut lines = Vec::new();
        for row in p.screen().rows_formatted(0, p.screen().size().0) {
            let row_str = String::from_utf8_lossy(&row).to_string();
            let clean = strip_ansi_escapes::strip(&row_str);
            lines.push(String::from_utf8_lossy(&clean).to_string());
        }
        Some(lines)
    }
}

pub struct MarkdownContent {
    pub source: String,
}

fn markdown_to_spans(source: &str) -> Vec<(String, Attrs<'static>)> {
    let mut spans = Vec::new();
    let mut bold = false;
    let mut italic = false;
    let mut heading: Option<HeadingLevel> = None;

    let base_attrs = Attrs::new().family(Family::SansSerif).color(Color::rgb(240, 240, 240));

    for event in Parser::new(source) {
        match event {
            Event::Start(Tag::Strong) => bold = true,
            Event::End(TagEnd::Strong) => bold = false,
            Event::Start(Tag::Emphasis) => italic = true,
            Event::End(TagEnd::Emphasis) => italic = false,
            Event::Start(Tag::Heading { level, .. }) => heading = Some(level),
            Event::End(TagEnd::Heading(_)) => heading = None,
            Event::Start(Tag::Item) => spans.push(("• ".to_string(), base_attrs)),
            Event::Code(text) => {
                let mut attrs = Attrs::new().family(Family::Monospace).color(Color::rgb(200, 240, 200));
                if bold { attrs = attrs.weight(Weight::BOLD); }
                if italic { attrs = attrs.style(Style::Italic); }
                if heading.is_some() {
                    attrs = attrs.weight(Weight::BOLD).color(Color::rgb(255, 204, 100));
                }
                spans.push((text.into_string(), attrs));
            }
            Event::Text(text) => {
                let mut attrs = base_attrs;
                if bold { attrs = attrs.weight(Weight::BOLD); }
                if italic { attrs = attrs.style(Style::Italic); }
                if heading.is_some() {
                    attrs = attrs.weight(Weight::BOLD).color(Color::rgb(255, 204, 100));
                }
                spans.push((text.into_string(), attrs));
            }
            Event::End(TagEnd::Paragraph) | Event::HardBreak | Event::SoftBreak | Event::End(TagEnd::Item) => {
                spans.push(("\n".to_string(), base_attrs));
            }
            _ => {}
        }
    }
    spans
}

impl NodeContent for MarkdownContent {
    fn update(&mut self) {}

    fn render(
        &mut self,
        device: &wgpu::Device,
        queue: &wgpu::Queue,
        offscreen_view: &wgpu::TextureView,
        text_buffer: &mut glyphon::Buffer,
        font_system: &mut FontSystem,
        text_renderer: &mut TextRenderer,
        text_atlas: &mut TextAtlas,
        swash_cache: &mut SwashCache,
        _is_focused: bool,
    ) {
        let spans = markdown_to_spans(&self.source);
        let span_refs = spans.iter().map(|(s, a)| (s.as_str(), *a));

        text_buffer.set_rich_text(
            font_system,
            span_refs,
            Shaping::Advanced,
        );

        let _ = text_renderer.prepare(
            device,
            queue,
            font_system,
            text_atlas,
            Resolution { width: 1024, height: 1024 },
            [TextArea {
                buffer: text_buffer,
                left: 40.0,
                top: 40.0,
                scale: 1.0,
                bounds: TextBounds { left: 0, top: 0, right: 1024, bottom: 1024 },
                default_color: Color::rgb(240, 240, 240),
            }],
            swash_cache,
        ).unwrap();

        let mut encoder = device.create_command_encoder(&wgpu::CommandEncoderDescriptor {
            label: Some("Encoder Pass1 Markdown"),
        });

        {
            let mut pass = encoder.begin_render_pass(&wgpu::RenderPassDescriptor {
                label: Some("Pass1 Text Markdown"),
                color_attachments: &[Some(wgpu::RenderPassColorAttachment {
                    view: offscreen_view,
                    resolve_target: None,
                    ops: wgpu::Operations {
                        load: wgpu::LoadOp::Clear(wgpu::Color { r: 0.1, g: 0.1, b: 0.12, a: 1.0 }),
                        store: wgpu::StoreOp::Store,
                    },
                })],
                depth_stencil_attachment: None,
                timestamp_writes: None,
                occlusion_query_set: None,
            });

            text_renderer.render(text_atlas, &mut pass).unwrap();
        }
        queue.submit(std::iter::once(encoder.finish()));
    }

    fn handle_event(&mut self, _event: NodeEvent) {}

    fn get_lines(&self) -> Option<Vec<String>> {
        Some(self.source.lines().map(|s| s.to_string()).collect())
    }
}

pub struct ImageContent {
    pub rgba_data: Vec<u8>,
    pub width: u32,
    pub height: u32,
    pub path: String,
    pub needs_upload: bool,
}

impl NodeContent for ImageContent {
    fn update(&mut self) {}

    fn render(
        &mut self,
        _device: &wgpu::Device,
        _queue: &wgpu::Queue,
        _offscreen_view: &wgpu::TextureView,
        _text_buffer: &mut glyphon::Buffer,
        _font_system: &mut FontSystem,
        _text_renderer: &mut TextRenderer,
        _text_atlas: &mut TextAtlas,
        _swash_cache: &mut SwashCache,
        _is_focused: bool,
    ) {
        // No-op: texture is uploaded directly to the SpatialNode
    }

    fn handle_event(&mut self, _event: NodeEvent) {}

    fn pixel_data(&mut self) -> Option<(&[u8], u32, u32)> {
        if self.needs_upload {
            self.needs_upload = false;
            Some((&self.rgba_data, self.width, self.height))
        } else {
            None
        }
    }
}
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
