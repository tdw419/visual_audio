use bytemuck::{Pod, Zeroable};

#[repr(C)]
#[derive(Copy, Clone, Debug, Pod, Zeroable)]
pub struct CameraUniform {
    pub pan: [f32; 2],
    pub zoom: f32,
    pub aspect_ratio: f32,
}

pub struct Camera {
    // Current interpolated state
    pub pan_x: f32,
    pub pan_y: f32,
    pub zoom: f32,
    pub aspect_ratio: f32,

    // Target state for smooth transitions
    pub target_pan_x: f32,
    pub target_pan_y: f32,
    pub target_zoom: f32,

    // Animation parameters
    pub smoothness: f32, // Decay lambda (e.g., 10.0)
}

impl Camera {
    pub fn new(aspect_ratio: f32) -> Self {
        Self {
            pan_x: 0.0,
            pan_y: 0.0,
            zoom: 1.0,
            aspect_ratio,
            target_pan_x: 0.0,
            target_pan_y: 0.0,
            target_zoom: 1.0,
            smoothness: 10.0,
        }
    }

    pub fn build_uniform(&self) -> CameraUniform {
        CameraUniform {
            pan: [self.pan_x, self.pan_y],
            zoom: self.zoom,
            aspect_ratio: self.aspect_ratio,
        }
    }

    /// Focus on a target node coordinate and optimal zoom level
    pub fn focus_on(&mut self, world_x: f32, world_y: f32, target_zoom: Option<f32>) {
        // Camera pan is the inverse translation of world coordinates
        self.target_pan_x = -world_x;
        self.target_pan_y = -world_y;
        if let Some(z) = target_zoom {
            self.target_zoom = z.clamp(0.05, 50.0);
        }
    }

    /// Direct manual pan (mouse drag) moves target immediately
    pub fn pan_manual(&mut self, dx: f32, dy: f32) {
        let speed = 2.0 / self.zoom;
        self.target_pan_x += dx * speed;
        self.target_pan_y -= dy * speed;
        
        // Snap current to target during manual drag for zero input lag
        self.pan_x = self.target_pan_x;
        self.pan_y = self.target_pan_y;
    }

    /// Direct manual zoom (scroll wheel)
    pub fn zoom_by(&mut self, factor: f32) {
        self.target_zoom = (self.target_zoom * factor).clamp(0.05, 50.0);
    }

    /// Frame-rate independent tick step
    pub fn update(&mut self, dt: f32) -> bool {
        let decay = (-self.smoothness * dt).exp();

        let prev_x = self.pan_x;
        let prev_y = self.pan_y;
        let prev_z = self.zoom;

        self.pan_x = self.target_pan_x + (self.pan_x - self.target_pan_x) * decay;
        self.pan_y = self.target_pan_y + (self.pan_y - self.target_pan_y) * decay;
        self.zoom = self.target_zoom + (self.zoom - self.target_zoom) * decay;

        // Returns true if camera is still actively animating
        (self.pan_x - prev_x).abs() > 0.0001
            || (self.pan_y - prev_y).abs() > 0.0001
            || (self.zoom - prev_z).abs() > 0.0001
    }
}
