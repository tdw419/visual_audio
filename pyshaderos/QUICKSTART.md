# ShaderOS Quick Start Guide

Get ShaderOS running in 5 minutes!

## Prerequisites

### System Requirements

- **OS**: Linux, macOS, or Windows
- **Python**: 3.8 or higher
- **GPU**: Any GPU with Vulkan, Metal, or DirectX 12 support
- **Memory**: At least 512MB available GPU memory

### Check Your GPU

```bash
# Linux
lspci | grep -i vga

# macOS
system_profiler SPDisplaysDataType

# Windows
dxdiag
```

Most modern GPUs (2016+) will work. Integrated graphics are supported.

## Installation

### Step 1: Clone or Download

If you're reading this, you probably already have the files!

```bash
cd shaderos
ls
# You should see:
# - ShaderOSRuntime.py
# - requirements.txt
# - runtime/core/substrate.wgsl
# - runtime/core/os_abi.wgsl
```

### Step 2: Install Dependencies

```bash
pip install -r requirements.txt
```

This installs:
- `wgpu` - Python WebGPU implementation
- `numpy` - For buffer operations

**Troubleshooting:**

If you get errors, try:
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 3: Verify Installation

```bash
python3 -c "import wgpu; print('WebGPU:', wgpu.__version__)"
python3 -c "import numpy; print('NumPy:', numpy.__version__)"
```

Expected output:
```
WebGPU: 0.9.5 (or higher)
NumPy: 1.24.0 (or higher)
```

## Running ShaderOS

### Basic Execution

```bash
python3 ShaderOSRuntime.py
```

**Expected Output:**

```
🚀 ShaderOSRuntime - The Layer Above Shaders
Created buffer 'service_requests' (binding 0) with size 9216 bytes and usage 140
Created buffer 'service_responses' (binding 1) with size 6144 bytes and usage 140
...
Created buffer 'ai_weights' (binding 39) with size 4194304 bytes and usage 140

✅ ShaderOSRuntime ready - shaders can now request privileged operations

=== HOST TICK 0 ===
HOST: Processing request ID 0 for service 0, opcode 0
HOST: No handler for service 0
=== HOST TICK 1 ===
...
=== HOST TICK 9 ===

🏁 ShaderOSRuntime demo ended.
```

**What Just Happened?**

1. ✅ Created 40 GPU buffers (~450MB total)
2. ✅ Compiled substrate.wgsl shader
3. ✅ Ran 10 frames of computation
4. ✅ Processed service requests
5. ✅ Cleanly shut down

## Your First Modification

Let's make the substrate kernel do something visible!

### Step 1: Add Custom Debug Output

Edit `runtime/core/substrate.wgsl`:

```wgsl
@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
    // Original frame counter
    if (gid.x == 0u) {
        let frame = atomicAdd(&os_frame_counter, 1u);
        os_trace_debug_log(gid.x, 0u, 0xDEADu, frame, 0u, 0u, 0u);
    }

    // NEW: Log from every 4th thread
    if (gid.x % 4u == 0u) {
        os_trace_debug_log(
            gid.x,              // Thread ID
            0u,                 // PC
            0xCAFEu,            // Custom code
            gid.x * 100u,       // Some data
            gid.x * gid.x,      // More data
            0u,
            0u
        );
    }
}
```

### Step 2: Read Debug Output

Edit `ShaderOSRuntime.py`, change the main loop:

```python
def main():
    runtime = ShaderOSRuntime()
    runtime.register_shader(0, "substrate_kernel", "runtime/core/substrate.wgsl", "main")

    print("\n✅ ShaderOSRuntime ready")

    for i in range(10):
        print(f"\n=== HOST TICK {i} ===")
        runtime.tick()

        # NEW: Read debug log every tick
        if i % 2 == 0:  # Every other frame
            runtime.read_debug_log()

        time.sleep(0.1)

    print("\n🏁 ShaderOSRuntime demo ended.")
```

### Step 3: Run and See the Output

```bash
python3 ShaderOSRuntime.py
```

You should see debug traces from multiple threads!

## Common Workflows

### Running Continuously

Change the loop to run indefinitely:

```python
def main():
    runtime = ShaderOSRuntime()
    runtime.register_shader(0, "substrate_kernel", "runtime/core/substrate.wgsl", "main")

    print("\n✅ ShaderOSRuntime ready - Press Ctrl+C to stop")

    try:
        frame = 0
        while True:
            if frame % 60 == 0:  # Every second at 60 FPS
                print(f"Frame {frame}")

            runtime.tick()
            time.sleep(1/60)  # 60 FPS
            frame += 1

    except KeyboardInterrupt:
        print("\n\n🏁 Stopped by user")
```

### Monitoring GPU Memory

```python
import psutil

def main():
    runtime = ShaderOSRuntime()

    # Calculate total buffer size
    total_size = sum(buf.size for buf in runtime.shared_buffers.values())
    print(f"Total GPU buffers: {total_size / 1024 / 1024:.2f} MB")

    runtime.register_shader(0, "substrate_kernel", "runtime/core/substrate.wgsl", "main")

    for i in range(10):
        runtime.tick()
        time.sleep(0.1)
```

### Creating a New Service Handler

```python
def my_custom_handler(request_id, opcode, args):
    """Handle custom service requests"""
    print(f"Custom handler: req={request_id}, op={opcode}, args={args}")

    if opcode == 1:
        # Do something
        result = args[0] + args[1]

        runtime.write_service_response(
            request_id=request_id,
            status=1,  # Success
            value0=result
        )
    else:
        # Unknown opcode
        runtime.write_service_response(
            request_id=request_id,
            status=2,  # Error
            value0=1   # INVALID_PARAM
        )

# Register your handler
SERVICE_CUSTOM = 6
runtime.service_handlers[SERVICE_CUSTOM] = my_custom_handler
```

## Troubleshooting

### "Unable to find extension: VK_EXT_physical_device_drm"

**Issue:** Non-critical warning on some Linux systems.

**Fix:** Ignore it - ShaderOS will work fine.

### "Shader validation error"

**Issue:** WGSL shader compilation failed.

**Causes:**
- Syntax error in shader code
- Missing #include file
- Reserved keyword used

**Fix:** Check the error message for line number and fix the shader.

### "Buffer is bound with size X where shader expects Y"

**Issue:** Buffer size mismatch.

**Fix:** Update buffer size in `DEFAULT_BUFFER_SIZES` dictionary in `ShaderOSRuntime.py`.

### "Out of GPU memory"

**Issue:** Your GPU doesn't have enough free memory.

**Fix:** Reduce buffer sizes in `DEFAULT_BUFFER_SIZES`:

```python
DEFAULT_BUFFER_SIZES = {
    # Reduce these large buffers:
    'fs_data_blocks': 64 * 1024 * 1024,     # Was 256MB, now 64MB
    'compositor_framebuffer': 1280 * 720 * 4,  # Was 1920x1080, now 720p
    'display_framebuffer': 1280 * 720 * 4,
    # ... keep others the same
}
```

### Python Import Errors

**Issue:** `ModuleNotFoundError: No module named 'wgpu'`

**Fix:**
```bash
pip install wgpu numpy
# or
pip install --user wgpu numpy
```

## Next Steps

### 1. Explore the Examples

Check out the shader code:
- `runtime/core/substrate.wgsl` - Basic kernel
- `runtime/core/os_abi.wgsl` - All OS services

### 2. Read the Documentation

- **README.md** - Project overview
- **ARCHITECTURE.md** - System design details
- **API.md** - Complete API reference

### 3. Implement a Service

Try implementing one of these:
- **File write** - Store data in fs_data_blocks
- **Window creation** - Allocate a window entry
- **Simple AI inference** - Matrix multiplication

### 4. Join the Community

Share your ShaderOS experiments!

## Example Projects

### Project 1: Frame Rate Counter

Display FPS in the console:

```python
import time

def main():
    runtime = ShaderOSRuntime()
    runtime.register_shader(0, "substrate_kernel", "runtime/core/substrate.wgsl", "main")

    frame_times = []
    last_time = time.time()

    for i in range(300):  # 5 seconds at 60fps
        runtime.tick()

        current_time = time.time()
        frame_times.append(current_time - last_time)
        last_time = current_time

        if i % 60 == 0:  # Every second
            avg_frame_time = sum(frame_times[-60:]) / 60
            fps = 1 / avg_frame_time if avg_frame_time > 0 else 0
            print(f"FPS: {fps:.1f}")

        time.sleep(1/60)
```

### Project 2: Service Request Logger

Log all service requests:

```python
def main():
    runtime = ShaderOSRuntime()
    runtime.register_shader(0, "substrate_kernel", "runtime/core/substrate.wgsl", "main")

    service_names = {
        1: "Filesystem",
        2: "Reload",
        3: "Network",
        4: "ServiceManager",
        5: "Control"
    }

    for i in range(10):
        print(f"\n=== TICK {i} ===")
        runtime.tick()

        # Check for service requests
        requests = runtime.read_service_requests()
        for req_id, svc_id, opcode, arg0, arg1, arg2 in requests:
            svc_name = service_names.get(svc_id, f"Unknown({svc_id})")
            print(f"  [{req_id}] {svc_name}.{opcode}({arg0}, {arg1}, {arg2})")

        time.sleep(0.1)
```

### Project 3: Memory Monitor

Track GPU buffer usage:

```python
def main():
    runtime = ShaderOSRuntime()

    print("GPU Buffer Allocation:")
    print("-" * 60)

    total_size = 0
    for name, buffer in sorted(runtime.shared_buffers.items()):
        size_mb = buffer.size / 1024 / 1024
        total_size += buffer.size
        print(f"{name:30s} {size_mb:8.2f} MB")

    print("-" * 60)
    print(f"{'TOTAL':30s} {total_size/1024/1024:8.2f} MB")
    print()

    runtime.register_shader(0, "substrate_kernel", "runtime/core/substrate.wgsl", "main")

    for i in range(10):
        runtime.tick()
        time.sleep(0.1)
```

## Performance Tips

1. **Reduce tick rate** for slower systems:
   ```python
   time.sleep(1/30)  # 30 FPS instead of 60
   ```

2. **Batch debug reads** instead of every frame:
   ```python
   if frame % 10 == 0:  # Every 10 frames
       runtime.read_debug_log()
   ```

3. **Use smaller workgroups** for simple shaders:
   ```wgsl
   @compute @workgroup_size(16)  // Instead of 64
   ```

4. **Profile with timestamps**:
   ```python
   start = time.perf_counter()
   runtime.tick()
   elapsed = time.perf_counter() - start
   print(f"Tick took {elapsed*1000:.2f}ms")
   ```

## Getting Help

### Check the Logs

Enable verbose output:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Verify GPU Support

```python
import wgpu
adapter = wgpu.gpu.request_adapter_sync(power_preference="high-performance")
print(f"GPU: {adapter.request_adapter_info()}")
```

### Test Minimal Shader

Create `test.wgsl`:
```wgsl
@compute @workgroup_size(1)
fn main() {
    // Empty shader to test compilation
}
```

Try running it:
```python
runtime = ShaderOSRuntime()
runtime.register_shader(99, "test", "test.wgsl", "main")
runtime.dispatch_shader(99)
print("✅ Basic shader works!")
```

## What's Next?

You're now ready to:
- ✅ Run ShaderOS
- ✅ Modify shaders
- ✅ Add debug output
- ✅ Create service handlers
- ✅ Monitor performance

**Ready to go deeper?** Read the [ARCHITECTURE.md](ARCHITECTURE.md) document to understand the full system design.

**Want to build features?** Check [API.md](API.md) for the complete service API reference.

---

**Happy Hacking!**

Questions? Check the main [README.md](README.md) or explore the source code.
