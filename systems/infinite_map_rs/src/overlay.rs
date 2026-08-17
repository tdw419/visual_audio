use bytemuck::{Pod, Zeroable};
use serde::{Deserialize, Serialize};
use crate::node::SpatialNode;

#[repr(C)]
#[derive(Copy, Clone, Debug, Pod, Zeroable)]
pub struct OverlayVertex {
    pub position: [f32; 2],
    pub color: [f32; 4],
}

#[derive(Serialize, Deserialize, Debug, Clone)]
#[serde(tag = "type")]
pub enum Annotation {
    #[serde(rename = "box")]
    BoundingBox {
        node_id: Option<String>,
        #[serde(default)] line_start: usize,
        #[serde(default = "default_one")] line_count: usize,
        #[serde(default)] world_bounds: Option<[f32; 4]>,
        color: [f32; 4],
        #[serde(default = "default_thickness")] thickness: f32,
    },
    #[serde(rename = "span")]
    Span {
        node_id: String,
        row: usize,
        col_start: usize,
        col_end: usize,
        color: [f32; 4],
        #[serde(default)] underline: bool,
    },
    #[serde(rename = "arrow")]
    Arrow {
        from: [f32; 2],
        to: [f32; 2],
        color: [f32; 4],
        #[serde(default = "default_thickness")] thickness: f32,
    },
    #[serde(rename = "callout")]
    Callout {
        #[serde(default)] node_id: Option<String>,
        #[serde(default)] anchor: [f32; 2], // World-space [x, y] if node_id is None
        #[serde(default)] row: usize,       // Node grid row if node_id is Some
        #[serde(default)] col: usize,       // Node grid col if node_id is Some
        text: String,
        badge_color: [f32; 4],
        border_color: [f32; 4],
    },
    #[serde(rename = "clear")]
    Clear,
}

fn default_one() -> usize { 1 }
fn default_thickness() -> f32 { 0.005 }

pub struct CalloutTextItem {
    pub world_pos: [f32; 2],
    pub text: String,
}

pub struct OverlayManager {
    pub annotations: Vec<Annotation>,
    pub vertex_buffer: Option<wgpu::Buffer>,
    pub vertex_count: u32,
    pub callout_texts: Vec<CalloutTextItem>,
}

impl OverlayManager {
    pub fn new() -> Self {
        Self {
            annotations: Vec::new(),
            vertex_buffer: None,
            vertex_count: 0,
            callout_texts: Vec::new(),
        }
    }

    pub fn build_mesh(&mut self, device: &wgpu::Device, nodes: &[SpatialNode]) {
        let mut vertices: Vec<OverlayVertex> = Vec::new();
        self.callout_texts.clear();

        for ann in &self.annotations {
            match ann {
                Annotation::Span { node_id, row, col_start, col_end, color, underline } => {
                    if let Some(node) = nodes.iter().find(|n| &n.id == node_id) {
                        let cols = 120.0;
                        let rows = 40.0;
                        let cell_w = node.width / cols;
                        let cell_h = node.height / rows;

                        let left_x = (node.world_x - node.width * 0.5) + (*col_start as f32 * cell_w);
                        let span_w = ((*col_end - *col_start) as f32 * cell_w).max(cell_w);
                        let top_y = (node.world_y + node.height * 0.5) - (*row as f32 * cell_h);
                        let center_x = left_x + span_w * 0.5;

                        if *underline {
                            // Underline strip along cell baseline
                            let underline_h = cell_h * 0.15;
                            let center_y = top_y - cell_h + underline_h * 0.5;
                            append_quad(&mut vertices, center_x, center_y, span_w, underline_h, *color);
                        } else {
                            // Full-cell background highlight
                            let center_y = top_y - cell_h * 0.5;
                            append_quad(&mut vertices, center_x, center_y, span_w, cell_h, *color);
                        }
                    }
                }

                Annotation::Callout { node_id, anchor, row, col, text, badge_color, border_color } => {
                    let anchor_pos = if let Some(id) = node_id {
                        if let Some(node) = nodes.iter().find(|n| &n.id == id) {
                            let cell_w = node.width / 120.0;
                            let cell_h = node.height / 40.0;
                            let x = (node.world_x - node.width * 0.5) + (*col as f32 * cell_w);
                            let y = (node.world_y + node.height * 0.5) - (*row as f32 * cell_h);
                            [x, y]
                        } else {
                            *anchor
                        }
                    } else {
                        *anchor
                    };

                    // Compute badge dimensions based on text length (estimated width)
                    let char_w = 0.018;
                    let badge_w = (text.len() as f32 * char_w) + 0.08;
                    let badge_h = 0.08;
                    let badge_cx = anchor_pos[0] + badge_w * 0.5 + 0.04;
                    let badge_cy = anchor_pos[1] + badge_h * 0.5 + 0.04;

                    // 1. Badge background quad
                    append_quad(&mut vertices, badge_cx, badge_cy, badge_w, badge_h, *badge_color);

                    // 2. Badge border outline
                    append_rect_outline(&mut vertices, badge_cx, badge_cy, badge_w, badge_h, 0.004, *border_color);

                    // 3. Anchor pointer line from target point to badge
                    append_arrow(&mut vertices, [anchor_pos[0], anchor_pos[1]], [badge_cx - badge_w * 0.5, badge_cy], 0.003, *border_color);

                    // Queue text for Glyphon render pass
                    self.callout_texts.push(CalloutTextItem {
                        world_pos: [badge_cx - badge_w * 0.5 + 0.03, badge_cy + badge_h * 0.25],
                        text: text.clone(),
                    });
                }

                Annotation::BoundingBox { node_id, line_start, line_count, world_bounds, color, thickness } => {
                    let rect = if let Some(id) = node_id {
                        if let Some(node) = nodes.iter().find(|n| &n.id == id) {
                            let line_h = node.height / 40.0;
                            let top_y = (node.world_y + node.height * 0.5) - (*line_start as f32 * line_h);
                            let box_h = *line_count as f32 * line_h;
                            [node.world_x, top_y - box_h * 0.5, node.width * 0.98, box_h]
                        } else {
                            continue;
                        }
                    } else if let Some(bounds) = world_bounds {
                        *bounds
                    } else {
                        continue;
                    };
                    append_rect_outline(&mut vertices, rect[0], rect[1], rect[2], rect[3], *thickness, *color);
                }

                Annotation::Arrow { from, to, color, thickness } => {
                    append_arrow(&mut vertices, *from, *to, *thickness, *color);
                }

                Annotation::Clear => {}
            }
        }

        self.vertex_count = vertices.len() as u32;
        if !vertices.is_empty() {
            use wgpu::util::DeviceExt;
            self.vertex_buffer = Some(device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
                label: Some("Overlay Vertex Buffer"),
                contents: bytemuck::cast_slice(&vertices),
                usage: wgpu::BufferUsages::VERTEX,
            }));
        } else {
            self.vertex_buffer = None;
        }
    }
}

fn append_rect_outline(v: &mut Vec<OverlayVertex>, cx: f32, cy: f32, w: f32, h: f32, t: f32, col: [f32; 4]) {
    let hw = w * 0.5;
    let hh = h * 0.5;
    append_quad(v, cx, cy + hh, w + t, t, col);
    append_quad(v, cx, cy - hh, w + t, t, col);
    append_quad(v, cx - hw, cy, t, h - t, col);
    append_quad(v, cx + hw, cy, t, h - t, col);
}

fn append_quad(v: &mut Vec<OverlayVertex>, cx: f32, cy: f32, w: f32, h: f32, col: [f32; 4]) {
    let hw = w * 0.5;
    let hh = h * 0.5;
    let p0 = [cx - hw, cy - hh];
    let p1 = [cx + hw, cy - hh];
    let p2 = [cx + hw, cy + hh];
    let p3 = [cx - hw, cy + hh];

    v.extend_from_slice(&[
        OverlayVertex { position: p0, color: col },
        OverlayVertex { position: p1, color: col },
        OverlayVertex { position: p2, color: col },
        OverlayVertex { position: p0, color: col },
        OverlayVertex { position: p2, color: col },
        OverlayVertex { position: p3, color: col },
    ]);
}

fn append_arrow(v: &mut Vec<OverlayVertex>, from: [f32; 2], to: [f32; 2], t: f32, col: [f32; 4]) {
    let dx = to[0] - from[0];
    let dy = to[1] - from[1];
    let len = (dx * dx + dy * dy).sqrt();
    if len < 0.001 { return; }

    let nx = -dy / len;
    let ny = dx / len;

    let stem_end = [to[0] - (dx / len) * (t * 4.0), to[1] - (dy / len) * (t * 4.0)];
    let p0 = [from[0] + nx * (t * 0.5), from[1] + ny * (t * 0.5)];
    let p1 = [from[0] - nx * (t * 0.5), from[1] - ny * (t * 0.5)];
    let p2 = [stem_end[0] - nx * (t * 0.5), stem_end[1] - ny * (t * 0.5)];
    let p3 = [stem_end[0] + nx * (t * 0.5), stem_end[1] + ny * (t * 0.5)];

    v.extend_from_slice(&[
        OverlayVertex { position: p0, color: col },
        OverlayVertex { position: p1, color: col },
        OverlayVertex { position: p2, color: col },
        OverlayVertex { position: p0, color: col },
        OverlayVertex { position: p2, color: col },
        OverlayVertex { position: p3, color: col },
    ]);

    let head_left = [stem_end[0] + nx * (t * 2.5), stem_end[1] + ny * (t * 2.5)];
    let head_right = [stem_end[0] - nx * (t * 2.5), stem_end[1] - ny * (t * 2.5)];
    v.extend_from_slice(&[
        OverlayVertex { position: to, color: col },
        OverlayVertex { position: head_left, color: col },
        OverlayVertex { position: head_right, color: col },
    ]);
}
