# ShaderOS - A GPU-Based Operating System Runtime

ShaderOS is an experimental operating system that runs entirely on the GPU using WebGPU compute shaders. It provides OS-level services (filesystem, networking, windowing, AI) directly in shader code, with privileged operations mediated by a minimal host runtime.

## 🎯 Overview

Traditional operating systems run on the CPU and use the GPU as a peripheral for graphics. ShaderOS inverts this model: the "kernel" runs as GPU compute shaders, and the CPU acts as a privileged host for hardware access.

**Key Features:**
- 🔧 **Filesystem Service** - Virtual filesystem with 65K files, 256MB storage
- 🌐 **Network Stack** - TCP/UDP/ICMP implementation in shaders
- 🪟 **Window System** - GPU-native compositor with 256 concurrent windows
- 🤖 **AI Service** - Neural network inference directly in compute shaders
- 🎨 **Framebuffer** - Direct 1920x1080 RGBA rendering
- 🐛 **Debug Traces** - Real-time shader debugging with 65K trace entries

## 📋 Requirements

- Python 3.8+
- GPU with WebGPU support (Vulkan, Metal, or DX12 backend)
- ~450MB GPU memory for all services

## 🚀 Quick Start

### Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Run the ShaderOS
python3 ShaderOSRuntime.py
```

### First Run

```bash
$ python3 ShaderOSRuntime.py

🚀 ShaderOSRuntime - The Layer Above Shaders
Created buffer 'service_requests' (binding 0) with size 9216 bytes
Created buffer 'service_responses' (binding 1) with size 6144 bytes
...
Created buffer 'ai_weights' (binding 39) with size 4194304 bytes

✅ ShaderOSRuntime ready - shaders can now request privileged operations

=== HOST TICK 0 ===
```

## 🏗️ Architecture

### System Components

```
┌─────────────────────────────────────────┐
│          Host Runtime (CPU)             │
│  ┌───────────────────────────────────┐  │
│  │   ShaderOSRuntime.py              │  │
│  │   - Service Handlers              │  │
│  │   - Buffer Management             │  │
│  │   - Shader Dispatch               │  │
│  └───────────────────────────────────┘  │
└─────────────────┬───────────────────────┘
                  │ WebGPU API
┌─────────────────▼───────────────────────┐
│          GPU Compute Shaders            │
│  ┌───────────────────────────────────┐  │
│  │  Substrate Kernel (substrate.wgsl)│  │
│  │  - Frame Counter                  │  │
│  │  - Debug Logging                  │  │
│  └───────────────────────────────────┘  │
│  ┌───────────────────────────────────┐  │
│  │  OS ABI (os_abi.wgsl)             │  │
│  │  - 40 Global Buffers              │  │
│  │  - Service Definitions            │  │
│  │  - Helper Functions               │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

### Service Architecture

ShaderOS provides 5 core services:

1. **Filesystem (Service ID: 1)**
   - 65,536 file entries
   - 256MB data storage
   - Directory hierarchy support
   - Atomic file operations

2. **Reload (Service ID: 2)**
   - Hot shader reloading
   - Runtime code updates

3. **Network (Service ID: 3)**
   - 1,024 concurrent sockets
   - TCP/UDP/ICMP protocols
   - Packet routing and DNS cache

4. **Service Manager (Service ID: 4)**
   - Service registration
   - Inter-service communication

5. **Control (Service ID: 5)**
   - System shutdown
   - Runtime control

### Memory Layout

Total GPU Memory: ~450MB

| Service               | Size      | Bindings |
|-----------------------|-----------|----------|
| Core System           | ~17MB     | 0-9      |
| Framebuffers          | ~33MB     | 10-13    |
| Filesystem            | ~340MB    | 14-20    |
| Window System         | ~250KB    | 21-26    |
| Networking            | ~14MB     | 27-34    |
| AI Services           | ~4.2MB    | 35-39    |

## 📖 Documentation

- **[ARCHITECTURE.md](ARCHITECTURE.md)** - Detailed system architecture
- **[API.md](API.md)** - Service API reference
- **[QUICKSTART.md](QUICKSTART.md)** - Getting started guide

## 🔧 Development

### Project Structure

```
shaderos/
├── ShaderOSRuntime.py      # Main runtime (host-side)
├── runtime/
│   └── core/
│       ├── substrate.wgsl  # Substrate kernel
│       └── os_abi.wgsl     # OS ABI definitions
├── requirements.txt        # Python dependencies
└── docs/                   # Documentation
```

### Adding New Services

1. Define service ID in `ShaderOSRuntime.py`
2. Add buffer bindings to `BUFFER_BINDINGS`
3. Implement handler in `ShaderOSRuntime` class
4. Define structs and bindings in `os_abi.wgsl`

### Debugging

Enable debug output:

```python
runtime.read_debug_log()  # Read shader debug traces
```

## 🎓 Technical Details

### WGSL Limitations Addressed

- **No u64 support**: All 64-bit types replaced with u32
- **No pointer returns**: Direct buffer access instead of helper functions
- **No atomic structs**: Structs with atomic fields cannot be passed as parameters
- **Reserved keywords**: `type` renamed to `event_type`/`socket_type`

### Buffer Bindings

All 40 buffer bindings follow WebGPU storage buffer conventions:
- `@group(0)` for all buffers
- `@binding(N)` from 0-39
- `var<storage, read_write>` for mutable buffers
- `var<storage, read>` for read-only buffers

## 🤝 Contributing

This is an experimental research project. Contributions welcome!

## 📜 License

MIT License - See LICENSE file for details

## 🙏 Acknowledgments

Built with:
- [wgpu-py](https://github.com/pygfx/wgpu-py) - Python WebGPU implementation
- WebGPU Shading Language (WGSL)
- NumPy for buffer operations

## ⚠️ Current Limitations

- Single-threaded host runtime
- No persistent storage
- Limited error handling
- Experimental shader implementations
- Requires modern GPU with WebGPU support

## 🔮 Future Directions

- [ ] Multi-shader orchestration
- [ ] Persistent filesystem
- [ ] Real network integration
- [ ] Window system with actual rendering
- [ ] Performance optimizations
- [ ] More comprehensive error handling

---

**Status**: Experimental Research Project
**Version**: 0.1.0-alpha
**Last Updated**: November 2025
