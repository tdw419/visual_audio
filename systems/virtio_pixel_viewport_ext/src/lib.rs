//! Virtual Viewpoint Extension for VirtIO Pixel Backend
//! Enables infinite 65536×65536 virtual coordinate space with multiple viewports

use std::collections::HashMap;
use std::sync::{Arc, Mutex};

pub const VIRTUAL_SIZE: (u32, u32) = (65536, 65536);
pub const DEFAULT_VIEWPORT_SIZE: (u32, u32) = (4096, 4096);

/// Virtual coordinate system for infinite desktop
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct VirtualCoord {
    pub x: u32,
    pub y: u32,
}

impl VirtualCoord {
    pub fn new(x: u32, y: u32) -> Self {
        VirtualCoord { x, y }
    }

    /// Clamp to virtual space boundaries
    pub fn clamp(&self) -> Self {
        VirtualCoord {
            x: self.x.min(VIRTUAL_SIZE.0 - 1),
            y: self.y.min(VIRTUAL_SIZE.1 - 1),
        }
    }
}

/// Viewport into virtual space
#[derive(Debug, Clone)]
pub struct Viewport {
    pub id: u32,
    pub origin: VirtualCoord,
    pub size: (u32, u32),
    pub container_id: Option<u32>,
}

impl Viewport {
    pub fn new(id: u32, origin: VirtualCoord) -> Self {
        Viewport {
            id,
            origin: origin.clamp(),
            size: DEFAULT_VIEWPORT_SIZE,
            container_id: None,
        }
    }

    /// Check if local coordinate is within viewport
    pub fn contains_local(&self, local_x: u32, local_y: u32) -> bool {
        local_x < self.size.0 && local_y < self.size.1
    }

    /// Convert local to virtual coordinate
    pub fn to_virtual(&self, local_x: u32, local_y: u32) -> Option<VirtualCoord> {
        if self.contains_local(local_x, local_y) {
            Some(VirtualCoord::new(
                self.origin.x + local_x,
                self.origin.y + local_y,
            ))
        } else {
            None
        }
    }

    /// Convert virtual to local coordinate (if within viewport)
    pub fn to_local(&self, virtual_coord: VirtualCoord) -> Option<(u32, u32)> {
        if virtual_coord.x >= self.origin.x
            && virtual_coord.x < self.origin.x + self.size.0
            && virtual_coord.y >= self.origin.y
            && virtual_coord.y < self.origin.y + self.size.1
        {
            Some((
                virtual_coord.x - self.origin.x,
                virtual_coord.y - self.origin.y,
            ))
        } else {
            None
        }
    }
}

/// Virtual Viewpoint Manager
pub struct VirtualViewportManager {
    viewports: Arc<Mutex<HashMap<u32, Viewport>>>,
    next_viewport_id: Arc<Mutex<u32>>,
    active_viewport: Arc<Mutex<u32>>,
}

impl VirtualViewportManager {
    pub fn new() -> Self {
        VirtualViewportManager {
            viewports: Arc::new(Mutex::new(HashMap::new())),
            next_viewport_id: Arc::new(Mutex::new(0)),
            active_viewport: Arc::new(Mutex::new(0)),
        }
    }

    /// Create new viewport at virtual origin
    pub fn create_viewport(&self, origin: VirtualCoord) -> u32 {
        let mut next_id = self.next_viewport_id.lock().unwrap();
        let id = *next_id;
        *next_id += 1;

        let viewport = Viewport::new(id, origin);

        let mut viewports = self.viewports.lock().unwrap();
        viewports.insert(id, viewport.clone());
        drop(viewports);

        id
    }

    /// Switch to viewport by ID
    pub fn switch_viewport(&self, id: u32) -> Result<Viewport, String> {
        let viewports = self.viewports.lock().unwrap();
        match viewports.get(&id).cloned() {
            Some(viewport) => {
                drop(viewports);
                let mut active = self.active_viewport.lock().unwrap();
                *active = id;
                Ok(viewport)
            }
            None => Err(format!("Viewport {} not found", id)),
        }
    }

    /// Get active viewport
    pub fn get_active(&self) -> Viewport {
        let active_id = self.active_viewport.lock().unwrap();
        let viewports = self.viewports.lock().unwrap();
        viewports.get(&*active_id)
            .cloned()
            .unwrap_or_else(|| Viewport::new(0, VirtualCoord::new(0, 0)))
    }

    /// Pan active viewport
    pub fn pan(&self, dx: i32, dy: i32) -> Result<Viewport, String> {
        let mut viewports = self.viewports.lock().unwrap();
        let active_id = *self.active_viewport.lock().unwrap();

        if let Some(viewport) = viewports.get_mut(&active_id) {
            // Handle underflow/overflow safely
            let new_x = if dx >= 0 {
                viewport.origin.x + dx as u32
            } else {
                viewport.origin.x.saturating_sub((-dx) as u32)
            };

            let new_y = if dy >= 0 {
                viewport.origin.y + dy as u32
            } else {
                viewport.origin.y.saturating_sub((-dy) as u32)
            };

            viewport.origin = VirtualCoord::new(new_x, new_y).clamp();
            Ok(viewport.clone())
        } else {
            Err(format!("Active viewport {} not found", active_id))
        }
    }

    /// Map container to viewport
    pub fn map_container(&self, viewport_id: u32, container_id: u32) -> Result<(), String> {
        let mut viewports = self.viewports.lock().unwrap();
        if let Some(viewport) = viewports.get_mut(&viewport_id) {
            viewport.container_id = Some(container_id);
            Ok(())
        } else {
            Err(format!("Viewport {} not found", viewport_id))
        }
    }

    /// List all viewports
    pub fn list_viewports(&self) -> Vec<Viewport> {
        let viewports = self.viewports.lock().unwrap();
        viewports.values().cloned().collect()
    }
}

impl Default for VirtualViewportManager {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_viewport_coordinates() {
        let viewport = Viewport::new(0, VirtualCoord::new(0, 0));

        // Local to virtual
        assert_eq!(
            viewport.to_virtual(100, 200),
            Some(VirtualCoord::new(100, 200))
        );

        // Virtual to local
        assert_eq!(
            viewport.to_local(VirtualCoord::new(100, 200)),
            Some((100, 200))
        );

        // Out of bounds
        assert!(viewport.to_virtual(5000, 200).is_none());
        assert!(viewport.to_local(VirtualCoord::new(5000, 200)).is_none());
    }

    #[test]
    fn test_viewport_offset() {
        let viewport = Viewport::new(0, VirtualCoord::new(4096, 0));

        // Offset local to virtual
        assert_eq!(
            viewport.to_virtual(100, 200),
            Some(VirtualCoord::new(4196, 200))
        );

        // Offset virtual to local
        assert_eq!(
            viewport.to_local(VirtualCoord::new(4196, 200)),
            Some((100, 200))
        );
    }

    #[test]
    fn test_viewport_manager() {
        let manager = VirtualViewportManager::new();

        // Create viewport
        let id1 = manager.create_viewport(VirtualCoord::new(0, 0));
        assert_eq!(id1, 0);

        // Create second viewport at offset
        let id2 = manager.create_viewport(VirtualCoord::new(4096, 0));
        assert_eq!(id2, 1);

        // Switch viewport
        manager.switch_viewport(id2).unwrap();
        let active = manager.get_active();
        assert_eq!(active.id, id2);
        assert_eq!(active.origin.x, 4096);

        // Pan viewport
        manager.pan(100, 0).unwrap();
        let active = manager.get_active();
        assert_eq!(active.origin.x, 4196);

        // List viewports
        let viewports = manager.list_viewports();
        assert_eq!(viewports.len(), 2);
    }
}
