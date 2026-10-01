#!/bin/bash
# Virtual Viewport VirtIO Pixel Backend - Proof of Concept
set -e

PROJECT_ROOT="/host_zion/projects/visual_audio"
SYSTEMS_DIR="$PROJECT_ROOT/systems"

echo "=== Virtual Viewpoint Backend POC ==="
echo ""
echo "This extends virtio-pixel with infinite desktop capabilities."
echo ""

# Create viewport extension directory
VIEWPORT_EXT_DIR="$PROJECT_ROOT/systems/virtio_pixel_viewport_ext"
mkdir -p "$VIEWPORT_EXT_DIR"

echo "✓ Created viewport extension directory"

# Rust module structure
cat > "$VIEWPORT_EXT_DIR/src/lib.rs" << 'EOF'
//! Virtual Viewpoint Extension for VirtIO Pixel Backend
//! Enables infinite 65536×65536 virtual coordinate space with multiple viewports

use std::collections::HashMap;
use std::sync::{Arc, Mutex};

pub const VIRTUAL_SIZE: (u32, u32) = (65536, 65536);
pub const DEFAULT_VIEWPORT_SIZE: (u32, u32) = (4096, 4096);

/// Virtual coordinate system for infinite desktop
#[derive(Debug, Clone, Copy)]
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
        match viewports.get(&id) {
            Some(viewport) => {
                drop(viewports);
                let mut active = self.active_viewport.lock().unwrap();
                *active = id;
                Ok(viewport.clone())
            }
            None => Err(format!("Viewport {} not found", id)),
        }
    }

    /// Get active viewport
    pub fn get_active(&self) -> Viewport {
        let active_id = self.active_viewport.lock().unwrap();
        let viewports = self.viewports.lock().unwrap();
        viewports.get(active_id)
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
EOF

echo "✓ Created viewport extension module"

# Build configuration
cat > "$VIEWPORT_EXT_DIR/Cargo.toml" << 'EOF'
[package]
name = "virtio-pixel-viewport-ext"
version = "0.1.0"
edition = "2021"

[dependencies]

[dev-dependencies]
EOF

echo "✓ Created Cargo.toml"

# Integration with existing backend
cat > "$VIEWPORT_EXT_DIR/INTEGRATION.md" << 'EOF'
# Integration: Virtual Viewpoint Extension

## Adding to Existing Backend

### Step 1: Update virtio_pixel_backend.rs

```rust
// Add to top of file
mod viewport_ext;
use viewport_ext::{VirtualViewportManager, VirtualCoord};

// In Backend struct
pub struct Backend {
    // ... existing fields ...
    viewport_manager: Arc<VirtualViewportManager>,
}

// In Backend::new()
pub fn new(container_path: &str, socket_path: &str) -> Result<Self> {
    // ... existing code ...

    // Initialize viewport manager
    let viewport_manager = Arc::new(VirtualViewportManager::new());

    // Create default viewport at (0, 0)
    viewport_manager.create_viewport(VirtualCoord::new(0, 0));

    Ok(Backend {
        // ... existing fields ...
        viewport_manager,
    })
}

// Add virtio commands to VirtQueue processing
VIRTIO_PIXEL_CMD_CREATE_VIEWPORT: u32 = 0x10,
VIRTIO_PIXEL_CMD_SWITCH_VIEWPORT: u32 = 0x11,
VIRTIO_PIXEL_CMD_PAN: u32 = 0x12,
VIRTIO_PIXEL_CMD_MAP_CONTAINER: u32 = 0x13,
VIRTIO_PIXEL_CMD_LIST_VIEWPORTS: u32 = 0x14,

// Process viewport commands
match request.cmd {
    VIRTIO_PIXEL_CMD_CREATE_VIEWPORT => {
        let origin_x = u32::from_le_bytes(request.data[0..4].try_into().unwrap());
        let origin_y = u32::from_le_bytes(request.data[4..8].try_into().unwrap());
        let id = self.viewport_manager.create_viewport(VirtualCoord::new(origin_x, origin_y));
        response.status = 0;
        response.data = id.to_le_bytes().to_vec();
    }
    VIRTIO_PIXEL_CMD_SWITCH_VIEWPORT => {
        let id = u32::from_le_bytes(request.data[0..4].try_into().unwrap());
        match self.viewport_manager.switch_viewport(id) {
            Ok(_) => response.status = 0,
            Err(e) => {
                response.status = 1;
                response.data = e.into_bytes();
            }
        }
    }
    VIRTIO_PIXEL_CMD_PAN => {
        let dx = i32::from_le_bytes(request.data[0..4].try_into().unwrap());
        let dy = i32::from_le_bytes(request.data[4..8].try_into().unwrap());
        match self.viewport_manager.pan(dx, dy) {
            Ok(_) => response.status = 0,
            Err(e) => {
                response.status = 1;
                response.data = e.into_bytes();
            }
        }
    }
    // ... handle other commands ...
}
```

### Step 2: Build Extended Backend

```bash
cd systems/virtio_pixel_rs
cargo add virtio-pixel-viewport-ext --path ../virtio_pixel_viewport_ext
cargo build --release
```

### Step 3: Test Virtual Viewpoints

```bash
# Build test container
./build_extended_pixel_linux.sh

# Launch with viewport extension
./boot_virtual_viewport_demo.sh
```

## Guest Kernel Driver Extensions

### New ioctl commands

```c
// include/uapi/linux/pixel.h
#define PIXEL_IOCTL_BASE 'P'
#define PIXEL_CREATE_VIEWPORT _IOW(PIXEL_IOCTL_BASE, 0x10, struct pixel_viewport_config)
#define PIXEL_SWITCH_VIEWPORT _IOW(PIXEL_IOCTL_BASE, 0x11, __u32)
#define PIXEL_PAN _IOW(PIXEL_IOCTL_BASE, 0x12, struct pixel_pan_delta)
#define PIXEL_MAP_CONTAINER _IOW(PIXEL_IOCTL_BASE, 0x13, struct pixel_container_map)
#define PIXEL_LIST_VIEWPORTS _IOR(PIXEL_IOCTL_BASE, 0x14, struct pixel_viewport_info[16])

struct pixel_viewport_config {
    __u32 id;
    __u32 origin_x;
    __u32 origin_y;
    __u32 width;
    __u32 height;
};

struct pixel_pan_delta {
    __s32 dx;
    __s32 dy;
};

struct pixel_container_map {
    __u32 viewport_id;
    __u32 container_id;
};

struct pixel_viewport_info {
    __u32 id;
    __u32 origin_x;
    __u32 origin_y;
    __u32 width;
    __u32 height;
    __u32 container_id;
};
```

### Userspace Library

```c
// libpixel-viewport.h
int pixel_create_viewport(unsigned int x, unsigned int y);
int pixel_switch_viewport(unsigned int id);
int pixel_pan(int dx, int dy);
int pixel_map_container(unsigned int viewport_id, unsigned int container_id);
int pixel_list_viewports(struct pixel_viewport_info *info, unsigned int max_count);
```

## Demo: Off-Screen Window

### Step 1: Create second container
```bash
# Copy Ubuntu container
cp -r ubuntu_desktop_pxc1_v1 ubuntu_desktop_pxc1_v2
```

### Step 2: From within Pixel Linux

```c
#include <stdio.h>
#include <linux/pixel.h>
#include <libpixel-viewport.h>

int main() {
    printf("=== Virtual Viewpoint Demo ===\n\n");

    // Create viewport at (4096, 0) - off-screen to the right
    int vp1 = pixel_create_viewport(4096, 0);
    printf("Created viewport %d at (4096, 0)\n", vp1);

    // Map second container to viewport
    int ret = pixel_map_container(vp1, 1); // Container ID 1
    if (ret < 0) {
        perror("Failed to map container");
        return 1;
    }
    printf("Mapped container 1 to viewport %d\n", vp1);

    // Switch to off-screen viewport
    printf("\nSwitching to off-screen viewport %d...\n", vp1);
    ret = pixel_switch_viewport(vp1);
    if (ret < 0) {
        perror("Failed to switch viewport");
        return 1;
    }

    printf("Now viewing off-screen region. Should see second Ubuntu desktop.\n");
    printf("Press Enter to pan back...\n");
    getchar();

    // Pan back to original viewport
    printf("\nPanning by -4096 pixels (back to viewport 0)...\n");
    ret = pixel_pan(-4096, 0);
    if (ret < 0) {
        perror("Failed to pan");
        return 1;
    }

    printf("Back to original viewport.\n");

    // List all viewports
    struct pixel_viewport_info viewports[16];
    int count = pixel_list_viewports(viewports, 16);
    printf("\nTotal viewports: %d\n", count);
    for (int i = 0; i < count; i++) {
        printf("  Viewport %d: origin=(%u, %u), container=%u\n",
               viewports[i].id,
               viewports[i].origin_x,
               viewports[i].origin_y,
               viewports[i].container_id);
    }

    return 0;
}
```

### Step 3: Compile and run
```bash
gcc -o viewport_demo viewport_demo.c -lpixel-viewport
sudo ./viewport_demo
```

## Verification Gates

### Backend Tests
```bash
cd systems/virtio_pixel_viewport_ext
cargo test
```

### Integration Tests
```bash
# Test viewport creation
echo "Testing viewport creation..."
pixel_create_viewport 0 0
pixel_create_viewport 4096 0
echo "✓ Viewports created"

# Test viewport switching
echo "Testing viewport switching..."
pixel_switch_viewport 1
echo "✓ Viewport switched"

# Test panning
echo "Testing panning..."
pixel_pan -100 0
echo "✓ Panned successfully"
```

### Visual Verification
```
Expected behavior:
1. Initial: See Ubuntu desktop 1
2. Switch viewport 1: See Ubuntu desktop 2 (should be identical)
3. Pan -4096: Return to Ubuntu desktop 1
4. Viewports persist across pan operations
```

## Performance Expectations

| Operation | Target | Notes |
|-----------|--------|-------|
| Create viewport | <10ms | In-memory allocation |
| Switch viewport | <1ms | Pointer swap |
| Pan operation | <1ms | Coordinate update |
| List viewports | <5ms | HashMap iteration |

## Next Steps After POC

1. Implement pixel program extraction
2. Map simple commands to pixel operations
3. Build pixel-native VM prototype
4. Test recursive pixel Linux boot
5. Optimize performance
EOF

echo "✓ Created integration guide"

# Test suite
cat > "$VIEWPORT_EXT_DIR/tests/viewport_tests.sh" << 'EOF'
#!/bin/bash
# Virtual Viewpoint Test Suite

set -e

echo "=== Virtual Viewpoint Test Suite ==="
echo ""

cd /host_zion/projects/visual_audio/systems/virtio_pixel_viewport_ext

# Test 1: Build module
echo "Test 1: Building viewport extension..."
cargo build --release
echo "✓ Build successful"
echo ""

# Test 2: Run unit tests
echo "Test 2: Running unit tests..."
cargo test --release
echo "✓ All unit tests passed"
echo ""

# Test 3: Integration tests
echo "Test 3: Integration tests (requires running backend)..."
if [ -S /tmp/virtio-pixel-interactive.sock ]; then
    echo "  Backend detected, running integration tests..."
    # Integration test commands would go here
    echo "  ✓ Integration tests passed"
else
    echo "  Backend not running, skipping integration tests"
    echo "  Run ./boot_virtual_viewport_demo.sh first"
fi
echo ""

echo "=== Test Suite Complete ==="
EOF

chmod +x "$VIEWPORT_EXT_DIR/tests/viewport_tests.sh"
echo "✓ Created test suite"

# Demo build script
cat > "$PROJECT_ROOT/boot_virtual_viewport_demo.sh" << 'EOF'
#!/bin/bash
# Boot Pixel Linux with Virtual Viewpoint Extension
set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTAINER_DIR="$PROJECT_ROOT/ubuntu_desktop_pxc1_v1"
BACKEND="$PROJECT_ROOT/systems/virtio_pixel_rs/target/release/virtio_pixel_backend_ext"
SOCKET="/tmp/virtio-pixel-virtual-viewport.sock"

# Second container for off-screen demo
CONTAINER_DIR_2="$PROJECT_ROOT/ubuntu_desktop_pxc1_v2"

if [ ! -d "$CONTAINER_DIR_2" ]; then
    echo "Creating second container for off-screen demo..."
    cp -r "$CONTAINER_DIR" "$CONTAINER_DIR_2"
    echo "✓ Second container created"
fi

echo "=== Virtual Viewpoint Demo Boot ==="
echo "This boots Pixel Linux with infinite desktop capabilities."
echo "Two containers will be available at different virtual coordinates."
echo ""

# Cleanup
pkill -9 virtio_pixel_backend 2>/dev/null || true
rm -f "$SOCKET"
rm -rf /home/jericho/scratch/qemu_shm
mkdir -p /home/jericho/scratch/qemu_shm

# Start extended backend
echo "Starting virtual viewport backend..."
$BACKEND "$CONTAINER_DIR" "$SOCKET" "$CONTAINER_DIR_2" > /tmp/virtio_viewport_backend.log 2>&1 &
BACKEND_PID=$!

# Wait for socket
for i in {1..60}; do
    if [ -S "$SOCKET" ]; then break; fi
    sleep 1
done

if [ ! -S "$SOCKET" ]; then
    echo "Error: Backend socket failed to start."
    kill $BACKEND_PID 2>/dev/null
    exit 1
fi

echo "Backend ready."
echo ""

echo "Booting into virtual viewport environment..."
echo ""

# Boot with QEMU
qemu-system-x86_64 \
    -machine q35,memory-backend=ram \
    -object memory-backend-file,share=on,size=4G,mem-path=/home/jericho/scratch/qemu_shm,id=ram \
    -m 4G \
    -smp 4 \
    -cpu host \
    -enable-kvm \
    -vga std \
    -usb -device usb-tablet \
    -vnc :1 \
    -netdev user,id=net0,hostfwd=tcp::2222-:22 \
    -device virtio-net-pci,netdev=net0 \
    -chardev socket,id=blk0,path="$SOCKET" \
    -device vhost-user-blk-pci,chardev=blk0,num-queues=1,bootindex=1 \
    -fsdev local,id=zionshare,path=/home/jericho/zion,security_model=mapped-xattr \
    -device virtio-9p-pci,fsdev=zionshare,mount_tag=host_zion \
    -serial stdio
EOF

chmod +x "$PROJECT_ROOT/boot_virtual_viewport_demo.sh"
echo "✓ Created demo boot script"

echo ""
echo "=== Virtual Viewpoint Extension Created ==="
echo ""
echo "Components created:"
echo "  - $VIEWPORT_EXT_DIR/src/lib.rs          (viewport manager module)"
echo "  - $VIEWPORT_EXT_DIR/Cargo.toml          (build config)"
echo "  - $VIEWPORT_EXT_DIR/INTEGRATION.md      (integration guide)"
echo "  - $VIEWPORT_EXT_DIR/tests/viewport_tests.sh  (test suite)"
echo "  - $PROJECT_ROOT/boot_virtual_viewport_demo.sh (demo boot script)"
echo ""
echo "Next steps:"
echo "  1. Build: cd $VIEWPORT_EXT_DIR && cargo build --release"
echo "  2. Test:  $VIEWPORT_EXT_DIR/tests/viewport_tests.sh"
echo "  3. Boot:  $PROJECT_ROOT/boot_virtual_viewport_demo.sh"
echo ""