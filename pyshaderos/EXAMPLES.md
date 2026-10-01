# ShaderOS Examples

Practical examples demonstrating ShaderOS capabilities.

## Table of Contents

- [Example 1: Hello World Shader](#example-1-hello-world-shader)
- [Example 2: Parallel Computation](#example-2-parallel-computation)
- [Example 3: Service Communication](#example-3-service-communication)
- [Example 4: Debug Visualization](#example-4-debug-visualization)
- [Example 5: Multi-Shader System](#example-5-multi-shader-system)

## Example 1: Hello World Shader

The simplest possible shader that logs a message.

### Shader Code: `examples/hello.wgsl`

```wgsl
#include "../runtime/core/os_abi.wgsl"

@compute @workgroup_size(1)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
    // Log "Hello" message
    os_trace_debug_log(
        gid.x,          // Thread 0
        0u,             // PC
        0x48454C4Cu,    // "HELL" in ASCII
        0x4F000000u,    // "O" in ASCII
        0u,
        0u,
        0u
    );
}
```

### Python Runner

```python
from ShaderOSRuntime import ShaderOSRuntime
import time

runtime = ShaderOSRuntime()
runtime.register_shader(1, "hello", "examples/hello.wgsl", "main")

print("Running hello shader...")
runtime.dispatch_shader(1)
time.sleep(0.1)

runtime.read_debug_log()
```

**Expected Output:**
```
--- SHADER DEBUG LOG ---
  [000] Code: 0x48454c4c, Args: (0x4f000000, 0x00000000, 0x00000000)
------------------------
```

---

## Example 2: Parallel Computation

Compute the sum of numbers 0-63 in parallel.

### Shader Code: `examples/parallel_sum.wgsl`

```wgsl
#include "../runtime/core/os_abi.wgsl"

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
    let thread_id = gid.x;

    // Each thread computes its contribution
    let value = thread_id;

    // Store in payload buffer
    os_payload_buffer[thread_id] = value;

    // Thread 0 sums all values
    if (thread_id == 0u) {
        var sum: u32 = 0u;
        for (var i: u32 = 0u; i < 64u; i = i + 1u) {
            sum = sum + os_payload_buffer[i];
        }

        // Log result: sum(0..63) = 2016
        os_trace_debug_log(
            0u,
            0u,
            0xSUMu,
            sum,
            0u,
            0u,
            0u
        );
    }
}
```

### Python Runner

```python
runtime = ShaderOSRuntime()
runtime.register_shader(2, "parallel_sum", "examples/parallel_sum.wgsl", "main")

runtime.dispatch_shader(2)
time.sleep(0.1)

runtime.read_debug_log()  # Should show sum = 2016
```

---

## Example 3: Service Communication

Request a service and wait for response.

### Shader Code: `examples/service_test.wgsl`

```wgsl
#include "../runtime/core/os_abi.wgsl"

@compute @workgroup_size(1)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
    // Submit a service request
    os_service_requests[0].opcode = 1u;     // Custom opcode
    os_service_requests[0].arg0 = 42u;      // First arg
    os_service_requests[0].arg1 = 100u;     // Second arg
    os_service_requests[0].arg2 = 0u;
    os_service_requests[0].arg3 = 0u;

    // Log that we made a request
    os_trace_debug_log(
        gid.x,
        0u,
        0xREQUu,        // "REQU"
        1u,             // Opcode
        42u,            // Arg0
        100u,           // Arg1
        0u
    );
}
```

### Python Handler

```python
def custom_handler(request_id, opcode, args):
    """Add two numbers"""
    arg0, arg1, arg2 = args[0], args[1], args[2]

    if opcode == 1:
        result = arg0 + arg1
        print(f"Computing {arg0} + {arg1} = {result}")

        runtime.write_service_response(
            request_id=request_id,
            status=1,       # Success
            value0=result,  # 142
            value1=0,
            value2=0
        )

# Main
runtime = ShaderOSRuntime()

# Register custom service
SERVICE_CALCULATOR = 6
runtime.service_handlers[SERVICE_CALCULATOR] = custom_handler

runtime.register_shader(3, "service_test", "examples/service_test.wgsl", "main")

# Run
runtime.dispatch_shader(3)
runtime.tick()  # Process the request
```

**Expected Output:**
```
Computing 42 + 100 = 142
```

---

## Example 4: Debug Visualization

Create a visual pattern in the debug framebuffer.

### Shader Code: `examples/visual_debug.wgsl`

```wgsl
#include "../runtime/core/os_abi.wgsl"

@compute @workgroup_size(256)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
    let idx = gid.x;

    // Create a simple pattern in visual debug buffer
    // Each thread writes a color value
    let color = (idx * 255u) / 1920u;  // Gradient
    os_visual_debug_data[idx] = color;

    // Log every 64th pixel
    if (idx % 64u == 0u) {
        os_trace_debug_log(
            idx,
            0u,
            0xPIXLu,
            color,
            0u,
            0u,
            0u
        );
    }
}
```

### Python Visualizer

```python
import numpy as np

runtime = ShaderOSRuntime()
runtime.register_shader(4, "visual", "examples/visual_debug.wgsl", "main")

# Dispatch with enough threads to cover the buffer
runtime.dispatch_shader(4, workgroups_x=8)  # 8 * 256 = 2048 threads
time.sleep(0.1)

# Read visual debug buffer
buffer_data = runtime.queue.read_buffer(
    runtime.shared_buffers['visual_debug_data'],
    0,
    1920 * 4  # First row of pixels
)

pixels = np.frombuffer(buffer_data, dtype=np.uint32)
print(f"First 10 pixels: {pixels[:10]}")
print(f"Pixel values range: {pixels.min()} to {pixels.max()}")
```

---

## Example 5: Multi-Shader System

Run multiple shaders in sequence.

### Shader 1: `examples/producer.wgsl`

```wgsl
#include "../runtime/core/os_abi.wgsl"

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
    // Producer: generate data
    let idx = gid.x;
    os_payload_buffer[idx] = idx * idx;  // Squares

    if (idx == 0u) {
        os_trace_debug_log(idx, 0u, 0xPRODu, 64u, 0u, 0u, 0u);
    }
}
```

### Shader 2: `examples/consumer.wgsl`

```wgsl
#include "../runtime/core/os_abi.wgsl"

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
    // Consumer: read and process data
    let idx = gid.x;
    let value = os_payload_buffer[idx];

    // Compute sum of squares
    if (idx == 0u) {
        var sum: u32 = 0u;
        for (var i: u32 = 0u; i < 64u; i = i + 1u) {
            sum = sum + os_payload_buffer[i];
        }

        os_trace_debug_log(0u, 0u, 0xCONSu, sum, 0u, 0u, 0u);
    }
}
```

### Python Orchestrator

```python
runtime = ShaderOSRuntime()

# Register both shaders
runtime.register_shader(10, "producer", "examples/producer.wgsl", "main")
runtime.register_shader(11, "consumer", "examples/consumer.wgsl", "main")

# Run in sequence
print("Running producer...")
runtime.dispatch_shader(10)

print("Running consumer...")
runtime.dispatch_shader(11)

time.sleep(0.1)
runtime.read_debug_log()

# Should show:
# [0] PROD (64 values produced)
# [1] CONS (sum of squares: 85344)
```

---

## Example 6: Frame Animation

Animate a value over time using the frame counter.

### Shader Code: `examples/animator.wgsl`

```wgsl
#include "../runtime/core/os_abi.wgsl"

@compute @workgroup_size(1)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
    let frame = atomicLoad(&os_frame_counter);

    // Compute animated value (sine wave approximation)
    let phase = frame % 60u;
    let value = phase;  // Simple linear animation

    // Store in payload
    os_payload_buffer[0] = value;

    // Log every 10 frames
    if (frame % 10u == 0u) {
        os_trace_debug_log(
            0u,
            0u,
            0xANIMu,
            frame,
            value,
            0u,
            0u
        );
    }
}
```

### Python Runner

```python
runtime = ShaderOSRuntime()
runtime.register_shader(6, "animator", "examples/animator.wgsl", "main")

print("Running animation for 60 frames...")
for i in range(60):
    runtime.dispatch_shader(6)

    if i % 10 == 0:
        runtime.read_debug_log()

    time.sleep(1/30)  # 30 FPS

print("Animation complete!")
```

---

## Example 7: Atomic Counters

Multiple threads incrementing a shared counter.

### Shader Code: `examples/atomic_test.wgsl`

```wgsl
#include "../runtime/core/os_abi.wgsl"

@compute @workgroup_size(256)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
    let tid = gid.x;

    // Each thread increments the counter
    let old_value = atomicAdd(&os_debug_index, 1u);

    // Thread 0 reports final count
    if (tid == 0u) {
        // Wait a bit for all threads (simplified)
        for (var i: u32 = 0u; i < 1000u; i = i + 1u) {
            // Busy wait
        }

        let final_count = atomicLoad(&os_debug_index);

        os_trace_debug_log(
            0u,
            0u,
            0xCNTRu,
            final_count,  // Should be ~256
            0u,
            0u,
            0u
        );
    }
}
```

### Python Runner

```python
runtime = ShaderOSRuntime()

# Reset counter
runtime.queue.write_buffer(
    runtime.shared_buffers['debug_index'],
    0,
    np.array([0], dtype=np.uint32).tobytes()
)

runtime.register_shader(7, "atomic", "examples/atomic_test.wgsl", "main")
runtime.dispatch_shader(7)
time.sleep(0.1)

runtime.read_debug_log()  # Should show count ~256
```

---

## Example 8: Data Processing Pipeline

Chain multiple operations on data.

### Shader: `examples/pipeline.wgsl`

```wgsl
#include "../runtime/core/os_abi.wgsl"

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
    let tid = gid.x;

    // Stage 1: Generate data
    let input = tid;

    // Stage 2: Transform (multiply by 2)
    let transformed = input * 2u;

    // Stage 3: Filter (keep only evens)
    let filtered = select(0u, transformed, transformed % 4u == 0u);

    // Stage 4: Store result
    os_payload_buffer[tid] = filtered;

    // Thread 0 counts non-zero results
    if (tid == 0u) {
        var count: u32 = 0u;
        for (var i: u32 = 0u; i < 64u; i = i + 1u) {
            if (os_payload_buffer[i] != 0u) {
                count = count + 1u;
            }
        }

        os_trace_debug_log(0u, 0u, 0xPIPEu, count, 0u, 0u, 0u);
    }
}
```

---

## Example 9: Memory Bandwidth Test

Measure memory bandwidth.

### Shader: `examples/bandwidth.wgsl`

```wgsl
#include "../runtime/core/os_abi.wgsl"

@compute @workgroup_size(256)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
    let tid = gid.x;
    let iterations = 1000u;

    // Write test
    for (var i: u32 = 0u; i < iterations; i = i + 1u) {
        os_payload_buffer[tid] = i;
    }

    // Read test
    var sum: u32 = 0u;
    for (var i: u32 = 0u; i < iterations; i = i + 1u) {
        sum = sum + os_payload_buffer[tid];
    }

    // Report result (prevents optimization)
    if (tid == 0u) {
        os_trace_debug_log(0u, 0u, 0xBWTHu, sum, 0u, 0u, 0u);
    }
}
```

### Python Benchmark

```python
import time

runtime = ShaderOSRuntime()
runtime.register_shader(9, "bandwidth", "examples/bandwidth.wgsl", "main")

# Benchmark
start = time.perf_counter()

for _ in range(100):
    runtime.dispatch_shader(9)

elapsed = time.perf_counter() - start

iterations = 100 * 256 * 1000 * 2  # dispatches × threads × iterations × ops
bandwidth_gbps = (iterations * 4) / elapsed / 1e9  # 4 bytes per u32

print(f"Elapsed: {elapsed:.3f}s")
print(f"Bandwidth: {bandwidth_gbps:.2f} GB/s")
```

---

## Example 10: Simple AI Inference

Basic neural network forward pass.

### Shader: `examples/simple_nn.wgsl`

```wgsl
#include "../runtime/core/os_abi.wgsl"

@compute @workgroup_size(1)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
    // Simple 2-input, 1-output network
    let input0 = 1.0;
    let input1 = 2.0;

    // Weights (stored in first 2 positions)
    let w0 = 0.5;
    let w1 = 0.3;
    let bias = 0.1;

    // Forward pass: output = relu(w0*x0 + w1*x1 + bias)
    let weighted_sum = w0 * input0 + w1 * input1 + bias;
    let output = relu(weighted_sum);

    // Store result in ai_weights buffer (as u32)
    let output_u32 = bitcast<u32>(output);
    os_payload_buffer[0] = output_u32;

    os_trace_debug_log(
        0u,
        0u,
        0xINFRu,
        output_u32,
        0u,
        0u,
        0u
    );
}
```

---

## Tips for Writing Examples

1. **Keep shaders simple** - One concept per example
2. **Use debug logging** - Show what's happening
3. **Comment generously** - Explain the logic
4. **Test edge cases** - What if thread_id is 0? 64? 256?
5. **Measure performance** - Use timing in Python

## Common Patterns

### Pattern 1: Thread 0 Coordination

```wgsl
if (gid.x == 0u) {
    // Only one thread does this
    atomicAdd(&os_frame_counter, 1u);
}
```

### Pattern 2: Parallel Reduction

```wgsl
// Each thread computes partial result
let partial = compute_something(gid.x);
os_payload_buffer[gid.x] = partial;

// Thread 0 combines results
if (gid.x == 0u) {
    var total: u32 = 0u;
    for (var i: u32 = 0u; i < 64u; i = i + 1u) {
        total = total + os_payload_buffer[i];
    }
}
```

### Pattern 3: Atomic Operations

```wgsl
// Safe concurrent increment
let old = atomicAdd(&counter, 1u);

// Safe concurrent maximum
atomicMax(&max_value, my_value);
```

---

**Ready to experiment?** Copy these examples and modify them to learn ShaderOS!
