mod pty;
mod camera;
mod node;
mod ipc;
mod overlay;
pub mod content;

use winit::{
    event::*,
    event_loop::EventLoop,
    window::WindowBuilder,
    keyboard::{Key, NamedKey},
};
use wgpu::util::DeviceExt;
use std::sync::Arc;
use std::borrow::Cow;
use glyphon::{
    Attrs, Color, Family, FontSystem, Resolution, Shaping, SwashCache, TextArea, TextAtlas, TextBounds,
    TextRenderer,
};
use camera::{Camera, CameraUniform};
use node::SpatialNode;
use ipc::{IpcServer, IpcMessage, IpcRequest, IpcResponse};
use overlay::{OverlayManager, OverlayVertex};

#[repr(C)]
#[derive(Copy, Clone, Debug, bytemuck::Pod, bytemuck::Zeroable)]
struct Vertex {
    position: [f32; 3],
    tex_coords: [f32; 2],
}

#[repr(C)]
#[derive(Copy, Clone, Debug, bytemuck::Pod, bytemuck::Zeroable)]
struct NodeUniform {
    position: [f32; 2],
    size: [f32; 2],
    is_focused: u32,
    _padding: [u32; 3],
}

const VERTICES: &[Vertex] = &[
    Vertex { position: [-0.5,  0.5, 0.0], tex_coords: [0.0, 0.0] }, // Top-Left
    Vertex { position: [-0.5, -0.5, 0.0], tex_coords: [0.0, 1.0] }, // Bottom-Left
    Vertex { position: [ 0.5, -0.5, 0.0], tex_coords: [1.0, 1.0] }, // Bottom-Right
    Vertex { position: [ 0.5,  0.5, 0.0], tex_coords: [1.0, 0.0] }, // Top-Right
];

const INDICES: &[u16] = &[
    0, 1, 2,
    0, 2, 3,
];

async fn run() {
    env_logger::init();
    
    let event_loop = EventLoop::new().unwrap();
    let window = Arc::new(WindowBuilder::new()
        .with_title("Geometry OS - Infinite Map Compositor")
        .with_inner_size(winit::dpi::LogicalSize::new(1024.0, 768.0))
        .build(&event_loop)
        .unwrap());

    let instance = wgpu::Instance::default();
    let surface = instance.create_surface(window.clone()).unwrap();

    let adapter = instance.request_adapter(&wgpu::RequestAdapterOptions {
        power_preference: wgpu::PowerPreference::HighPerformance,
        force_fallback_adapter: false,
        compatible_surface: Some(&surface),
    }).await.expect("Failed to find WGPU adapter");

    let (device, queue) = adapter.request_device(&Default::default(), None).await.unwrap();

    let size = window.inner_size();
    let surface_caps = surface.get_capabilities(&adapter);
    let surface_format = surface_caps.formats.iter()
        .copied()
        .find(|f| f.is_srgb())
        .unwrap_or(surface_caps.formats[0]);

    let mut config = wgpu::SurfaceConfiguration {
        usage: wgpu::TextureUsages::RENDER_ATTACHMENT,
        format: surface_format,
        width: size.width,
        height: size.height,
        present_mode: surface_caps.present_modes[0],
        alpha_mode: surface_caps.alpha_modes[0],
        view_formats: vec![],
        desired_maximum_frame_latency: 2,
    };
    surface.configure(&device, &config);

    // ==========================================
    // Camera Setup
    // ==========================================
    let mut camera = Camera::new(size.width as f32 / size.height as f32);
    let mut camera_uniform = camera.build_uniform();

    let camera_buffer = device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
        label: Some("Camera Buffer"),
        contents: bytemuck::cast_slice(&[camera_uniform]),
        usage: wgpu::BufferUsages::UNIFORM | wgpu::BufferUsages::COPY_DST,
    });

    let camera_bind_group_layout = device.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor {
        entries: &[wgpu::BindGroupLayoutEntry {
            binding: 0,
            visibility: wgpu::ShaderStages::VERTEX,
            ty: wgpu::BindingType::Buffer {
                ty: wgpu::BufferBindingType::Uniform,
                has_dynamic_offset: false,
                min_binding_size: None,
            },
            count: None,
        }],
        label: Some("camera_bind_group_layout"),
    });

    let camera_bind_group = device.create_bind_group(&wgpu::BindGroupDescriptor {
        layout: &camera_bind_group_layout,
        entries: &[wgpu::BindGroupEntry {
            binding: 0,
            resource: camera_buffer.as_entire_binding(),
        }],
        label: Some("camera_bind_group"),
    });

    // ==========================================
    // Node Uniform Setup
    // ==========================================
    let node_uniform_buf = device.create_buffer(&wgpu::BufferDescriptor {
        label: Some("Node Uniform Buffer"),
        size: std::mem::size_of::<NodeUniform>() as wgpu::BufferAddress,
        usage: wgpu::BufferUsages::UNIFORM | wgpu::BufferUsages::COPY_DST,
        mapped_at_creation: false,
    });

    let node_bind_group_layout = device.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor {
        entries: &[wgpu::BindGroupLayoutEntry {
            binding: 0,
            visibility: wgpu::ShaderStages::VERTEX | wgpu::ShaderStages::FRAGMENT,
            ty: wgpu::BindingType::Buffer {
                ty: wgpu::BufferBindingType::Uniform,
                has_dynamic_offset: false,
                min_binding_size: None,
            },
            count: None,
        }],
        label: Some("node_bind_group_layout"),
    });

    let node_bind_group = device.create_bind_group(&wgpu::BindGroupDescriptor {
        layout: &node_bind_group_layout,
        entries: &[wgpu::BindGroupEntry {
            binding: 0,
            resource: node_uniform_buf.as_entire_binding(),
        }],
        label: Some("node_bind_group"),
    });

    // ==========================================
    // Quad Pipeline Setup
    // ==========================================
    let terminal_bind_group_layout = device.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor {
        entries: &[
            wgpu::BindGroupLayoutEntry {
                binding: 0,
                visibility: wgpu::ShaderStages::FRAGMENT,
                ty: wgpu::BindingType::Texture {
                    multisampled: false,
                    view_dimension: wgpu::TextureViewDimension::D2,
                    sample_type: wgpu::TextureSampleType::Float { filterable: true },
                },
                count: None,
            },
            wgpu::BindGroupLayoutEntry {
                binding: 1,
                visibility: wgpu::ShaderStages::FRAGMENT,
                ty: wgpu::BindingType::Sampler(wgpu::SamplerBindingType::Filtering),
                count: None,
            },
        ],
        label: Some("terminal_bind_group_layout"),
    });

    let shader_src = include_str!("shaders/quad.wgsl");
    let shader = device.create_shader_module(wgpu::ShaderModuleDescriptor {
        label: Some("Quad Shader"),
        source: wgpu::ShaderSource::Wgsl(Cow::Borrowed(shader_src)),
    });

    let render_pipeline_layout = device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor {
        label: Some("Quad Pipeline Layout"),
        bind_group_layouts: &[&camera_bind_group_layout, &node_bind_group_layout, &terminal_bind_group_layout],
        push_constant_ranges: &[],
    });

    let quad_pipeline = device.create_render_pipeline(&wgpu::RenderPipelineDescriptor {
        label: Some("Quad Render Pipeline"),
        layout: Some(&render_pipeline_layout),
        vertex: wgpu::VertexState {
            module: &shader,
            entry_point: "vs_main",
            buffers: &[wgpu::VertexBufferLayout {
                array_stride: std::mem::size_of::<Vertex>() as wgpu::BufferAddress,
                step_mode: wgpu::VertexStepMode::Vertex,
                attributes: &wgpu::vertex_attr_array![0 => Float32x3, 1 => Float32x2],
            }],
        },
        fragment: Some(wgpu::FragmentState {
            module: &shader,
            entry_point: "fs_main",
            targets: &[Some(wgpu::ColorTargetState {
                format: config.format,
                blend: Some(wgpu::BlendState::ALPHA_BLENDING),
                write_mask: wgpu::ColorWrites::ALL,
            })],
        }),
        primitive: wgpu::PrimitiveState {
            topology: wgpu::PrimitiveTopology::TriangleList,
            strip_index_format: None,
            front_face: wgpu::FrontFace::Ccw,
            cull_mode: Some(wgpu::Face::Back),
            polygon_mode: wgpu::PolygonMode::Fill,
            unclipped_depth: false,
            conservative: false,
        },
        depth_stencil: None,
        multisample: wgpu::MultisampleState {
            count: 1,
            mask: !0,
            alpha_to_coverage_enabled: false,
        },
        multiview: None,
    });

    let vertex_buffer = device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
        label: Some("Quad Vertex Buffer"),
        contents: bytemuck::cast_slice(VERTICES),
        usage: wgpu::BufferUsages::VERTEX,
    });

    let index_buffer = device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
        label: Some("Quad Index Buffer"),
        contents: bytemuck::cast_slice(INDICES),
        usage: wgpu::BufferUsages::INDEX,
    });

    // ==========================================
    // Overlay Pipeline Setup
    // ==========================================
    let overlay_shader_src = include_str!("shaders/overlay.wgsl");
    let overlay_shader = device.create_shader_module(wgpu::ShaderModuleDescriptor {
        label: Some("Overlay Shader"),
        source: wgpu::ShaderSource::Wgsl(Cow::Borrowed(overlay_shader_src)),
    });

    let overlay_pipeline_layout = device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor {
        label: Some("Overlay Pipeline Layout"),
        bind_group_layouts: &[&camera_bind_group_layout],
        push_constant_ranges: &[],
    });

    let overlay_pipeline = device.create_render_pipeline(&wgpu::RenderPipelineDescriptor {
        label: Some("Overlay Render Pipeline"),
        layout: Some(&overlay_pipeline_layout),
        vertex: wgpu::VertexState {
            module: &overlay_shader,
            entry_point: "vs_main",
            buffers: &[wgpu::VertexBufferLayout {
                array_stride: std::mem::size_of::<OverlayVertex>() as wgpu::BufferAddress,
                step_mode: wgpu::VertexStepMode::Vertex,
                attributes: &wgpu::vertex_attr_array![0 => Float32x2, 1 => Float32x4],
            }],
        },
        fragment: Some(wgpu::FragmentState {
            module: &overlay_shader,
            entry_point: "fs_main",
            targets: &[Some(wgpu::ColorTargetState {
                format: config.format,
                blend: Some(wgpu::BlendState::ALPHA_BLENDING),
                write_mask: wgpu::ColorWrites::ALL,
            })],
        }),
        primitive: wgpu::PrimitiveState {
            topology: wgpu::PrimitiveTopology::TriangleList,
            strip_index_format: None,
            front_face: wgpu::FrontFace::Ccw,
            cull_mode: None,
            polygon_mode: wgpu::PolygonMode::Fill,
            unclipped_depth: false,
            conservative: false,
        },
        depth_stencil: None,
        multisample: wgpu::MultisampleState {
            count: 1,
            mask: !0,
            alpha_to_coverage_enabled: false,
        },
        multiview: None,
    });

    let mut overlay_manager = OverlayManager::new();

    // ==========================================
    // Glyphon & Nodes Setup
    // ==========================================
    let mut font_system = FontSystem::new();
    let mut swash_cache = SwashCache::new();
    let mut text_atlas = TextAtlas::new(&device, &queue, wgpu::TextureFormat::Rgba8UnormSrgb);
    let mut text_renderer = TextRenderer::new(&mut text_atlas, &device, wgpu::MultisampleState::default(), None);

    let sampler = device.create_sampler(&wgpu::SamplerDescriptor {
        address_mode_u: wgpu::AddressMode::ClampToEdge,
        address_mode_v: wgpu::AddressMode::ClampToEdge,
        mag_filter: wgpu::FilterMode::Linear,
        min_filter: wgpu::FilterMode::Linear,
        ..Default::default()
    });

    let mut nodes = vec![
        SpatialNode::new(
            "user_sh",
            0.0,
            0.0,
            1.2,
            1.2,
            Box::new(content::TerminalContent::new(120, 40, None)),
            &device,
            &terminal_bind_group_layout,
            &sampler,
            &mut font_system,
            1024,
            1024,
        ),
        SpatialNode::new(
            "htop",
            1.4,
            0.0,
            1.2,
            1.2,
            Box::new(content::TerminalContent::new(120, 40, Some("htop".to_string()))),
            &device,
            &terminal_bind_group_layout,
            &sampler,
            &mut font_system,
            1024,
            1024,
        ),
    ];
    nodes[0].is_focused = true;

    // ==========================================
    // IPC Server Setup
    // ==========================================
    let ipc_server = IpcServer::start().expect("Failed to start IPC Server");

    let mut last_mouse_pos = winit::dpi::PhysicalPosition::new(0.0, 0.0);
    let mut is_right_mouse_down = false;

    let mut last_frame_time = std::time::Instant::now();

    println!("[infinite_map_rs] Ready! Right-click to pan, scroll to zoom.");

    event_loop.run(move |event, target| {
        match event {
            Event::WindowEvent { ref event, window_id } if window_id == window.id() => {
                match event {
                    WindowEvent::CloseRequested => target.exit(),
                    WindowEvent::Resized(physical_size) => {
                        config.width = physical_size.width;
                        config.height = physical_size.height;
                        surface.configure(&device, &config);
                        
                        camera.aspect_ratio = config.width as f32 / config.height as f32;
                        window.request_redraw();
                    }
                    WindowEvent::MouseInput { state, button, .. } => {
                        if *button == MouseButton::Right {
                            is_right_mouse_down = *state == ElementState::Pressed;
                        } else if *button == MouseButton::Left && *state == ElementState::Pressed {
                            let norm_x = ((last_mouse_pos.x as f32 / config.width as f32) * 2.0 - 1.0) * camera.aspect_ratio;
                            let norm_y = -((last_mouse_pos.y as f32 / config.height as f32) * 2.0 - 1.0);
                            
                            let world_x = (norm_x / camera.zoom) - camera.pan_x;
                            let world_y = (norm_y / camera.zoom) - camera.pan_y;

                            let mut clicked_id = None;
                            for node in &mut nodes {
                                if node.contains_point(world_x, world_y) {
                                    clicked_id = Some(node.id.clone());
                                    break;
                                }
                            }

                            if let Some(ref clicked_id_str) = clicked_id {
                                if let Some(clicked_node) = nodes.iter().find(|n| n.id == *clicked_id_str) {
                                    camera.focus_on(clicked_node.world_x, clicked_node.world_y, Some(1.2));
                                }
                            }

                            for node in &mut nodes {
                                node.is_focused = Some(node.id.clone()) == clicked_id;
                            }
                        }
                    }
                    WindowEvent::MouseWheel { delta, .. } => {
                        match delta {
                            MouseScrollDelta::LineDelta(_, y) => {
                                let factor = if *y > 0.0 { 1.15 } else { 0.85 };
                                camera.zoom_by(factor);
                            }
                            MouseScrollDelta::PixelDelta(pos) => {
                                let factor = if pos.y > 0.0 { 1.15 } else { 0.85 };
                                camera.zoom_by(factor);
                            }
                        }
                        window.request_redraw();
                    }
                    WindowEvent::CursorMoved { position, .. } => {
                        if is_right_mouse_down {
                            let dx = (position.x - last_mouse_pos.x) as f32 / config.width as f32;
                            let dy = (position.y - last_mouse_pos.y) as f32 / config.height as f32;
                            camera.pan_manual(dx, dy);
                            window.request_redraw();
                        }
                        last_mouse_pos = *position;
                    }
                    WindowEvent::KeyboardInput { event: kb_event, .. } => {
                        if kb_event.state == winit::event::ElementState::Pressed {
                            if let Some(active_node) = nodes.iter_mut().find(|n| n.is_focused) {
                                if let Some(text) = &kb_event.text {
                                    active_node.content.handle_event(content::NodeEvent::Keyboard(text.as_str()));
                                } else {
                                    match kb_event.logical_key {
                                        Key::Named(NamedKey::Enter) => active_node.content.handle_event(content::NodeEvent::Keyboard("\r")),
                                        Key::Named(NamedKey::Backspace) => active_node.content.handle_event(content::NodeEvent::Keyboard("\x08")),
                                        Key::Named(NamedKey::Tab) => active_node.content.handle_event(content::NodeEvent::Keyboard("\t")),
                                        Key::Named(NamedKey::ArrowUp) => active_node.content.handle_event(content::NodeEvent::Keyboard("\x1b[A")),
                                        Key::Named(NamedKey::ArrowDown) => active_node.content.handle_event(content::NodeEvent::Keyboard("\x1b[B")),
                                        Key::Named(NamedKey::ArrowRight) => active_node.content.handle_event(content::NodeEvent::Keyboard("\x1b[C")),
                                        Key::Named(NamedKey::ArrowLeft) => active_node.content.handle_event(content::NodeEvent::Keyboard("\x1b[D")),
                                        Key::Named(NamedKey::Escape) => { },
                                        _ => {}
                                    }
                                }
                            } else {
                                if let Key::Named(NamedKey::Escape) = kb_event.logical_key {
                                    target.exit();
                                }
                            }
                        }
                    }
                    WindowEvent::RedrawRequested => {
                        // Poll IPC Commands
                        while let Ok(IpcMessage::Request(req, responder)) = ipc_server.rx.try_recv() {
                            match req {
                                IpcRequest::SpawnNode { id, x, y, cmd } => {
                                    let content = Box::new(content::TerminalContent::new(120, 40, cmd));
                                    nodes.push(SpatialNode::new(
                                        &id,
                                        x,
                                        y,
                                        1.2,
                                        1.2,
                                        content,
                                        &device,
                                        &terminal_bind_group_layout,
                                        &sampler,
                                        &mut font_system,
                                        1024,
                                        1024,
                                    ));
                                    let _ = responder.send(IpcResponse {
                                        status: "ok".into(),
                                        message: Some(format!("Spawned node {}", id)),
                                        lines: None,
                                        nodes: None,
                                    });
                                }
                                IpcRequest::SpawnImageNode { id, x, y, path } => {
                                    if let Ok(img) = image::open(&path) {
                                        let img_rgba = img.to_rgba8();
                                        let width = img_rgba.width();
                                        let height = img_rgba.height();
                                        let content = Box::new(content::ImageContent {
                                            rgba_data: img_rgba.into_raw(),
                                            width,
                                            height,
                                            path: path.clone(),
                                            needs_upload: true,
                                        });
                                        nodes.push(SpatialNode::new(
                                            &id, x, y, 1.2, 1.2, content,
                                            &device, &terminal_bind_group_layout, &sampler, &mut font_system,
                                            width, height
                                        ));
                                        let _ = responder.send(IpcResponse {
                                            status: "ok".into(),
                                            message: Some(format!("Spawned image node {}", id)),
                                            lines: None,
                                            nodes: None,
                                        });
                                    } else {
                                        let _ = responder.send(IpcResponse {
                                            status: "error".into(),
                                            message: Some(format!("Failed to load image from path {}", path)),
                                            lines: None,
                                            nodes: None,
                                        });
                                    }
                                }
                        
                                IpcRequest::ReadNode { id } => {
                                    if let Some(node) = nodes.iter().find(|n| n.id == id) {
                                        if let Some(lines) = node.content.get_lines() {
                                            let _ = responder.send(IpcResponse {
                                                status: "ok".into(),
                                                message: None,
                                                lines: Some(lines),
                                                nodes: None,
                                            });
                                        } else {
                                            let _ = responder.send(IpcResponse {
                                                status: "error".into(),
                                                message: Some("Node does not support get_lines".into()),
                                                lines: None,
                                                nodes: None,
                                            });
                                        }
                                    } else {
                                        let _ = responder.send(IpcResponse {
                                            status: "error".into(),
                                            message: Some("Node not found".into()),
                                            lines: None,
                                            nodes: None,
                                        });
                                    }
                                }
                        
                                IpcRequest::WriteNode { id, data } => {
                                    if let Some(node) = nodes.iter_mut().find(|n| n.id == id) {
                                        node.content.handle_event(content::NodeEvent::Keyboard(&data));
                                        let _ = responder.send(IpcResponse {
                                            status: "ok".into(),
                                            message: None,
                                            lines: None,
                                            nodes: None,
                                        });
                                    } else {
                                        let _ = responder.send(IpcResponse {
                                            status: "error".into(),
                                            message: Some("Node not found".into()),
                                            lines: None,
                                            nodes: None,
                                        });
                                    }
                                }
                                IpcRequest::UpdateMarkdownNode { id, x, y, source } => {
                                    if let Some(node) = nodes.iter_mut().find(|n| n.id == id) {
                                        node.content = Box::new(content::MarkdownContent { source });
                                        node.world_x = x;
                                        node.world_y = y;
                                    } else {
                                        let content = Box::new(content::MarkdownContent { source });
                                        nodes.push(SpatialNode::new(
                                            &id,
                                            x,
                                            y,
                                            1.2,
                                            1.2,
                                            content,
                                            &device,
                                            &terminal_bind_group_layout,
                                            &sampler,
                                            &mut font_system,
                                            1024,
                                            1024,
                                        ));
                                    }
                                    let _ = responder.send(IpcResponse {
                                        status: "ok".into(),
                                        message: Some(format!("Updated markdown node {}", id)),
                                        lines: None,
                                        nodes: None,
                                    });
                                }
                        
                                IpcRequest::ListNodes => {
                                    let ids: Vec<String> = nodes.iter().map(|n| n.id.clone()).collect();
                                    let _ = responder.send(IpcResponse {
                                        status: "ok".into(),
                                        message: None,
                                        lines: None,
                                        nodes: Some(ids),
                                    });
                                }
                        
                                IpcRequest::CloseNode { id } => {
                                    nodes.retain(|n| n.id != id);
                                    let _ = responder.send(IpcResponse {
                                        status: "ok".into(),
                                        message: Some(format!("Closed node {}", id)),
                                        lines: None,
                                        nodes: None,
                                    });
                                }
                                
                                IpcRequest::FocusNode { id, zoom } => {
                                    if let Some(node) = nodes.iter_mut().find(|n| n.id == id) {
                                        let wx = node.world_x;
                                        let wy = node.world_y;
                                        for n in &mut nodes {
                                            n.is_focused = n.id == id;
                                        }
                                        camera.focus_on(wx, wy, zoom.or(Some(1.2)));
                                        let _ = responder.send(IpcResponse {
                                            status: "ok".into(),
                                            message: Some(format!("Focused on node {}", id)),
                                            lines: None,
                                            nodes: None,
                                        });
                                    } else {
                                        let _ = responder.send(IpcResponse {
                                            status: "error".into(),
                                            message: Some("Node not found".into()),
                                            lines: None,
                                            nodes: None,
                                        });
                                    }
                                }
                                
                                IpcRequest::PanCamera { x, y, zoom } => {
                                    camera.focus_on(x, y, zoom);
                                    let _ = responder.send(IpcResponse {
                                        status: "ok".into(),
                                        message: Some(format!("Panned camera to {}, {}", x, y)),
                                        lines: None,
                                        nodes: None,
                                    });
                                }

                                IpcRequest::SetAnnotations { items } => {
                                    overlay_manager.annotations = items;
                                    overlay_manager.build_mesh(&device, &nodes);
                                    let _ = responder.send(IpcResponse {
                                        status: "ok".into(),
                                        message: Some("Updated annotations".into()),
                                        lines: None,
                                        nodes: None,
                                    });
                                }
                                IpcRequest::LayoutNodes { mode } => {
                                    if mode == "grid" {
                                        let columns = (nodes.len() as f32).sqrt().ceil() as usize;
                                        let spacing_x = 1.4;
                                        let spacing_y = 1.4;
                                        let start_x = -((columns as f32 - 1.0) * spacing_x) * 0.5;
                                        let start_y = (((nodes.len() as f32) / columns as f32).ceil() - 1.0) * spacing_y * 0.5;

                                        for (i, node) in nodes.iter_mut().enumerate() {
                                            let col = i % columns;
                                            let row = i / columns;
                                            let target_x = start_x + col as f32 * spacing_x;
                                            let target_y = start_y - row as f32 * spacing_y;
                                            node.set_target(target_x, target_y);
                                            println!("[LAYOUT] Node {} targeting ({:.2}, {:.2})", node.id, target_x, target_y);
                                        }

                                        let _ = responder.send(IpcResponse {
                                            status: "ok".into(),
                                            message: Some("Layout applied".into()),
                                            lines: None,
                                            nodes: None,
                                        });
                                    }
                                }
                            }
                        }

                        // Update camera timing
                        let now = std::time::Instant::now();
                        let dt = now.duration_since(last_frame_time).as_secs_f32();
                        last_frame_time = now;

                        let mut is_animating = camera.update(dt);
                        for node in &mut nodes {
                            if node.update(dt) {
                                is_animating = true;
                            }
                        }

                        camera_uniform = camera.build_uniform();
                        queue.write_buffer(&camera_buffer, 0, bytemuck::cast_slice(&[camera_uniform]));

                        // PASS 1: Offscreen Text Updates for ALL Nodes
                        for node in &mut nodes {
                            if let Some((data, width, height)) = node.content.pixel_data() {
                                queue.write_texture(
                                    wgpu::ImageCopyTexture {
                                        texture: &node.offscreen_texture,
                                        mip_level: 0,
                                        origin: wgpu::Origin3d::ZERO,
                                        aspect: wgpu::TextureAspect::All,
                                    },
                                    data,
                                    wgpu::ImageDataLayout {
                                        offset: 0,
                                        bytes_per_row: Some(4 * width),
                                        rows_per_image: Some(height),
                                    },
                                    wgpu::Extent3d {
                                        width,
                                        height,
                                        depth_or_array_layers: 1,
                                    },
                                );
                            }
                            node.content.render(
                                &device,
                                &queue,
                                &node.offscreen_view,
                                &mut node.text_buffer,
                                &mut font_system,
                                &mut text_renderer,
                                &mut text_atlas,
                                &mut swash_cache,
                                node.is_focused,
                            );
                        }

                        // PASS 2: Main Compositing Pass & PASS 3: Overlay Pass
                        let output = surface.get_current_texture().unwrap();
                        let main_view = output.texture.create_view(&wgpu::TextureViewDescriptor::default());

                        let mut encoder = device.create_command_encoder(&wgpu::CommandEncoderDescriptor {
                            label: Some("Encoder Pass2"),
                        });

                        {
                            let mut pass = encoder.begin_render_pass(&wgpu::RenderPassDescriptor {
                                label: Some("Pass2 Spatial Canvas"),
                                color_attachments: &[Some(wgpu::RenderPassColorAttachment {
                                    view: &main_view,
                                    resolve_target: None,
                                    ops: wgpu::Operations {
                                        load: wgpu::LoadOp::Clear(wgpu::Color { r: 0.02, g: 0.02, b: 0.03, a: 1.0 }),
                                        store: wgpu::StoreOp::Store,
                                    },
                                })],
                                depth_stencil_attachment: None,
                                timestamp_writes: None,
                                occlusion_query_set: None,
                            });

                            pass.set_pipeline(&quad_pipeline);
                            pass.set_bind_group(0, &camera_bind_group, &[]);
                            pass.set_vertex_buffer(0, vertex_buffer.slice(..));
                            pass.set_index_buffer(index_buffer.slice(..), wgpu::IndexFormat::Uint16);

                            for node in &nodes {
                                queue.write_buffer(&node_uniform_buf, 0, bytemuck::cast_slice(&[
                                    NodeUniform {
                                        position: [node.world_x, node.world_y],
                                        size: [node.width, node.height],
                                        is_focused: if node.is_focused { 1 } else { 0 },
                                        _padding: [0, 0, 0],
                                    }
                                ]));

                                pass.set_bind_group(1, &node_bind_group, &[]);
                                pass.set_bind_group(2, &node.bind_group, &[]);
                                pass.draw_indexed(0..6, 0, 0..1);
                            }

                            // PASS 3: Overlay Pass
                            if let Some(ref vbuf) = overlay_manager.vertex_buffer {
                                pass.set_pipeline(&overlay_pipeline);
                                pass.set_bind_group(0, &camera_bind_group, &[]);
                                pass.set_vertex_buffer(0, vbuf.slice(..));
                                pass.draw(0..overlay_manager.vertex_count, 0..1);
                            }
                        }

                        // Callout text render pass
                        let mut callout_text_areas = Vec::new();
                        let mut callout_buffers = Vec::new();

                        for item in &overlay_manager.callout_texts {
                            let world_x = item.world_pos[0] + camera.pan_x;
                            let world_y = item.world_pos[1] + camera.pan_y;
                            let ndc_x = (world_x * camera.zoom) / camera.aspect_ratio;
                            let ndc_y = world_y * camera.zoom;

                            let screen_px_x = (ndc_x * 0.5 + 0.5) * config.width as f32;
                            let screen_px_y = (-ndc_y * 0.5 + 0.5) * config.height as f32;

                            let mut buf = glyphon::Buffer::new(&mut font_system, glyphon::Metrics::new(16.0 * camera.zoom, 20.0 * camera.zoom));
                            buf.set_size(&mut font_system, 600.0, 100.0);
                            buf.set_text(&mut font_system, &item.text, glyphon::Attrs::new().family(glyphon::Family::Monospace), glyphon::Shaping::Advanced);
                            callout_buffers.push((buf, screen_px_x, screen_px_y));
                        }

                        for (buf, sx, sy) in &callout_buffers {
                            callout_text_areas.push(glyphon::TextArea {
                                buffer: buf,
                                left: *sx,
                                top: *sy,
                                scale: 1.0,
                                bounds: glyphon::TextBounds { left: 0, top: 0, right: config.width as i32, bottom: config.height as i32 },
                                default_color: glyphon::Color::rgb(255, 255, 255),
                            });
                        }

                        if !callout_text_areas.is_empty() {
                            let _ = text_renderer.prepare(
                                &device,
                                &queue,
                                &mut font_system,
                                &mut text_atlas,
                                glyphon::Resolution { width: config.width, height: config.height },
                                callout_text_areas,
                                &mut swash_cache,
                            ).unwrap();

                            let mut encoder = device.create_command_encoder(&wgpu::CommandEncoderDescriptor {
                                label: Some("Encoder Callout"),
                            });
                            {
                                let mut pass = encoder.begin_render_pass(&wgpu::RenderPassDescriptor {
                                    label: Some("Pass Callout Text"),
                                    color_attachments: &[Some(wgpu::RenderPassColorAttachment {
                                        view: &main_view,
                                        resolve_target: None,
                                        ops: wgpu::Operations {
                                            load: wgpu::LoadOp::Load,
                                            store: wgpu::StoreOp::Store,
                                        },
                                    })],
                                    depth_stencil_attachment: None,
                                    timestamp_writes: None,
                                    occlusion_query_set: None,
                                });
                                text_renderer.render(&text_atlas, &mut pass).unwrap();
                            }
                            queue.submit(std::iter::once(encoder.finish()));
                        }

                        queue.submit(std::iter::once(encoder.finish()));
                        output.present();
                        text_atlas.trim();

                        if is_animating {
                            window.request_redraw();
                        }
                    }
                    _ => {}
                }
            },
            Event::AboutToWait => {
                // We keep requesting redraw to process incoming IPC commands or animating camera
                window.request_redraw();
            }
            _ => {}
        }
    }).unwrap();
}

fn main() {
    pollster::block_on(run());
}
