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
