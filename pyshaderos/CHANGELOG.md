# Changelog

All notable changes to ShaderOS will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0-alpha] - 2025-11-24

### Changed

- **Major Refactor: Storage Pointer Elimination**
  - Refactored the entire WGSL codebase to remove all uses of `ptr<storage, ...>` in function parameters, ensuring full compliance with the WGSL 1.0 specification.
  - Replaced pointer-based access with an index-based pattern, where functions now accept `u32` indices or offsets to look up data in global storage buffers.
  - This affects `inter_shader_comms.wgsl`, `network_shader.wgsl`, and `filesystem_shader.wgsl`.

### Added

- **Pointer Migration Utilities (`pointer_utils.wgsl`)**:
  - Created a new utility file containing helper functions for accessing shared memory buffers (e.g., `os_payload_buffer`).
  - Implemented a mechanism to pass the size of runtime-sized buffers from the Python host to the shaders via the `os_system_flags` buffer.
- **Developer Documentation**:
  - Added documentation to all refactored functions, explaining the new index-based parameters and usage.
  - Temporarily created and then removed `POINTER_VIOLATIONS.md` which guided the refactoring process.

### Fixed

- **Shader Compilation**:
  - Fixed invalid `arrayLength()` calls on global storage buffers by using either compile-time constants or the new runtime size mechanism.
  - Corrected compute shader entry point naming conventions (`ai_service` -> `main`).
  - Resolved a `KeyError` in `ShaderOSRuntime.py` related to an incorrect buffer name (`os_system_flags` vs `system_flags`).
- **Validation**:
  - All shaders now compile successfully, and the main runtime script executes without errors, validating the architectural changes.

## [0.1.0-alpha] - 2025-11-23

### Added

**Core Runtime:**
- Initial ShaderOSRuntime implementation
- 40 GPU buffer bindings for complete OS services
- WebGPU-based shader compilation and dispatch
- Service request/response handling system
- Debug logging and trace collection

**Shader Components:**
- Substrate kernel (substrate.wgsl)
- Complete OS ABI definitions (os_abi.wgsl)
- Buffer bindings for all services
- Debug helper functions

**Services:**
- Filesystem service framework (65K files, 256MB storage)
- Network service framework (1K sockets, 8K packets)
- Window system framework (256 windows, events, compositor)
- AI service framework (16 models, 128 layers, 4MB weights)
- Debug visualization system

**Documentation:**
- Comprehensive README.md
- Architecture documentation (ARCHITECTURE.md)
- Complete API reference (API.md)
- Quick start guide (QUICKSTART.md)
- Example code collection (EXAMPLES.md)
- Contributing guidelines (CONTRIBUTING.md)

**Infrastructure:**
- MIT License
- .gitignore for Python projects
- requirements.txt with dependencies
- Repository structure for distribution

### Fixed

**WGSL Compatibility:**
- Replaced all u64 types with u32 (SHADER_INT64 not available)
- Renamed `type` fields to avoid reserved keyword conflicts
- Removed pointer-returning functions (not allowed in WGSL)
- Commented out functions with atomic struct parameters
- Fixed all global variable declarations (commas → semicolons)

**Buffer Sizing:**
- Corrected debug_traces buffer size (2.1MB)
- Aligned all buffer sizes with shader expectations
- Added proper struct size calculations

### Known Issues

- Service handlers are stubs (not fully implemented)
- No persistent storage
- Limited error handling
- Single-threaded host runtime
- Requires modern GPU with WebGPU support

### Technical Details

**Memory Usage:**
- Total GPU allocation: ~450MB
- Largest buffer: fs_data_blocks (256MB)
- Framebuffers: 3× 8.3MB (25MB total)
- AI weights: 4MB

**Performance:**
- Default workgroup size: 64 threads
- Default dispatch: 1 workgroup
- Frame time: ~0.1ms (substrate kernel)

**Compatibility:**
- Python: 3.8+
- GPU: Vulkan 1.1+, Metal 2+, or DirectX 12+
- OS: Linux, macOS, Windows

## [Unreleased]

### Planned Features

- [ ] Persistent filesystem backend
- [ ] Real network integration
- [ ] Window compositor with rendering
- [ ] AI inference implementation
- [ ] Hot shader reloading
- [ ] Multi-shader orchestration
- [ ] Performance profiling tools
- [ ] Comprehensive test suite

### Under Consideration

- [ ] Multi-GPU support
- [ ] Shader debugging tools
- [ ] Visual debugger UI
- [ ] JIT shader compilation
- [ ] Distributed ShaderOS

---

## Version History

- **0.1.0-alpha** (2025-11-23) - Initial release

## Links

- [Repository](https://github.com/yourusername/shaderos) (TBD)
- [Issue Tracker](https://github.com/yourusername/shaderos/issues) (TBD)
- [Discussions](https://github.com/yourusername/shaderos/discussions) (TBD)
