struct CameraUniform {
    pan: vec2<f32>,
    zoom: f32,
    aspect_ratio: f32,
};

struct NodeUniform {
    position: vec2<f32>,
    size: vec2<f32>,
    is_focused: u32,
};

@group(0) @binding(0) var<uniform> camera: CameraUniform;
@group(1) @binding(0) var<uniform> node: NodeUniform;
@group(2) @binding(0) var t_diffuse: texture_2d<f32>;
@group(2) @binding(1) var s_diffuse: sampler;

struct VertexInput {
    @location(0) position: vec3<f32>,
    @location(1) tex_coords: vec2<f32>,
};

struct VertexOutput {
    @builtin(position) clip_position: vec4<f32>,
    @location(0) tex_coords: vec2<f32>,
};

@vertex
fn vs_main(model: VertexInput) -> VertexOutput {
    var out: VertexOutput;
    
    // Scale quad by node size, place at node.position, transform by camera
    let local_pos = model.position.xy * node.size;
    let world_pos = local_pos + node.position + camera.pan;
    
    let screen_x = (world_pos.x * camera.zoom) / camera.aspect_ratio;
    let screen_y = world_pos.y * camera.zoom;

    out.clip_position = vec4<f32>(screen_x, screen_y, 0.0, 1.0);
    out.tex_coords = model.tex_coords;
    return out;
}

@fragment
fn fs_main(in: VertexOutput) -> @location(0) vec4<f32> {
    let color = textureSample(t_diffuse, s_diffuse, in.tex_coords);
    
    // Border highlighting based on focus
    let uv = in.tex_coords;
    let border = step(0.99, uv.x) + step(uv.x, 0.01) + step(0.99, uv.y) + step(uv.y, 0.01);
    
    if (border > 0.0) {
        if (node.is_focused == 1u) {
            return vec4<f32>(0.0, 0.95, 0.8, 1.0); // Bright Cyan (Active)
        } else {
            return vec4<f32>(0.2, 0.25, 0.3, 0.8); // Dim Slate (Background)
        }
    }
    
    return color;
}
