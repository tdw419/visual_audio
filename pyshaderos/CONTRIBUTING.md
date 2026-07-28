# Contributing to ShaderOS

Thank you for your interest in contributing to ShaderOS! This experimental project welcomes contributions of all kinds.

## Ways to Contribute

### 1. Bug Reports

Found a bug? Please open an issue with:
- **Description**: What went wrong?
- **Environment**: OS, GPU, Python version
- **Steps to reproduce**: How can we see the bug?
- **Expected vs Actual**: What should happen vs what does happen?

**Example:**
```
Title: Shader compilation fails on AMD GPUs

Environment:
- OS: Ubuntu 22.04
- GPU: AMD RX 6700 XT
- Python: 3.10.6
- wgpu: 0.9.5

Steps:
1. Run `python3 ShaderOSRuntime.py`
2. Observe shader compilation error

Expected: Shader compiles successfully
Actual: GPUValidationError with message "..."
```

### 2. Feature Requests

Have an idea? Open an issue describing:
- **Use case**: Why is this needed?
- **Proposed solution**: How should it work?
- **Alternatives**: What other approaches exist?

### 3. Documentation Improvements

- Fix typos
- Clarify confusing sections
- Add examples
- Improve diagrams

### 4. Code Contributions

#### Small Changes

For typos, small fixes, or clarifications:
1. Fork the repository
2. Make your changes
3. Submit a pull request

#### Larger Changes

For new features or significant refactoring:
1. Open an issue first to discuss
2. Wait for feedback/approval
3. Fork and implement
4. Submit a pull request

## Development Setup

### Prerequisites

```bash
# Clone the repository
git clone <repo-url>
cd shaderos

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install development dependencies
pip install pytest black mypy
```

### Running Tests

```bash
# Run basic functionality test
python3 ShaderOSRuntime.py

# Run with different configurations
python3 -c "
from ShaderOSRuntime import ShaderOSRuntime
runtime = ShaderOSRuntime()
print('✅ Runtime initialized successfully')
"
```

### Code Style

**Python:**
- Follow PEP 8
- Use `black` for formatting: `black ShaderOSRuntime.py`
- Add type hints where reasonable
- Keep functions focused and documented

**WGSL:**
- 4-space indentation
- Descriptive variable names
- Comment non-obvious logic
- Use constants for magic numbers

### Commit Messages

Use clear, descriptive commit messages:

```
✅ Good:
- Fix buffer size calculation for debug_traces
- Add filesystem service documentation
- Optimize atomic operations in substrate kernel

❌ Bad:
- fix bug
- update
- changes
```

Format:
```
<type>: <subject>

<body>

<footer>
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `style`: Formatting, no code change
- `refactor`: Code restructuring
- `test`: Add/modify tests
- `chore`: Maintenance tasks

Example:
```
feat: Add window system service handler

Implements basic window creation and management in the host runtime.
Adds support for:
- Window allocation from ws_windows buffer
- Event queue processing
- Z-order management

Closes #42
```

## Pull Request Process

### Before Submitting

- [ ] Code follows style guidelines
- [ ] Comments explain complex logic
- [ ] Documentation updated if needed
- [ ] Testing completed on your system
- [ ] No merge conflicts with main branch

### PR Description Template

```markdown
## Description
Brief description of changes

## Motivation
Why is this change needed?

## Changes
- Change 1
- Change 2
- Change 3

## Testing
How was this tested?

## Screenshots (if applicable)
Add screenshots for visual changes

## Checklist
- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] Documentation updated
- [ ] No breaking changes (or clearly documented)
```

### Review Process

1. Maintainers will review your PR
2. Address any feedback
3. Once approved, PR will be merged
4. Celebrate! 🎉

## Project Structure

```
shaderos/
├── ShaderOSRuntime.py          # Main runtime
├── runtime/
│   └── core/
│       ├── substrate.wgsl      # Substrate kernel
│       └── os_abi.wgsl         # OS ABI definitions
├── docs/                       # Documentation
│   ├── README.md
│   ├── ARCHITECTURE.md
│   ├── API.md
│   ├── QUICKSTART.md
│   └── EXAMPLES.md
├── requirements.txt
├── LICENSE
└── CONTRIBUTING.md
```

## Areas for Contribution

### High Priority

1. **Service Implementations**
   - Filesystem operations (read/write/delete)
   - Network stack (TCP/UDP)
   - Window system compositor
   - AI inference engine

2. **Testing**
   - Unit tests for runtime
   - Shader validation tests
   - Integration tests

3. **Documentation**
   - More examples
   - Architecture diagrams
   - Video tutorials

### Medium Priority

4. **Performance**
   - Buffer access optimization
   - Shader compilation caching
   - Async buffer operations

5. **Developer Experience**
   - Hot shader reloading improvements
   - Better error messages
   - Debugging tools

### Research Projects

6. **Advanced Features**
   - Multi-GPU support
   - Persistent storage backend
   - Real network integration
   - JIT shader compilation

## Coding Guidelines

### Python

```python
# Good
def dispatch_shader(
    self,
    shader_id: int,
    workgroups_x: int = 1,
    workgroups_y: int = 1,
    workgroups_z: int = 1
) -> None:
    """
    Dispatches a compute shader.

    Args:
        shader_id: Unique shader identifier
        workgroups_x: Workgroups in X dimension
        workgroups_y: Workgroups in Y dimension
        workgroups_z: Workgroups in Z dimension
    """
    if shader_id not in self.shader_registry:
        raise ValueError(f"Shader {shader_id} not registered")

    # Implementation...
```

### WGSL

```wgsl
// Good
fn process_request(request_id: u32) {
    // Read request from buffer
    let opcode = os_service_requests[request_id].opcode;

    // Process based on opcode
    if (opcode == 1u) {
        handle_read_operation(request_id);
    } else if (opcode == 2u) {
        handle_write_operation(request_id);
    }

    // Log completion
    os_trace_debug_log(
        0u,
        request_id,
        0xDONEu,
        opcode,
        0u,
        0u,
        0u
    );
}
```

## Documentation Guidelines

### Code Comments

```python
# Good: Explain WHY, not WHAT
# Allocate buffer with padding for alignment requirements
buffer_size = (requested_size + 255) & ~255

# Bad: Restates the code
# Add 255 and bitwise AND with ~255
buffer_size = (requested_size + 255) & ~255
```

### Docstrings

Use Google-style docstrings:

```python
def register_shader(self, shader_id: int, name: str, path: str) -> None:
    """
    Registers a compute shader for execution.

    Compiles the WGSL shader at the given path and creates a compute
    pipeline. The shader can then be dispatched using dispatch_shader().

    Args:
        shader_id: Unique integer identifier (0-255)
        name: Human-readable shader name
        path: Path to .wgsl shader file

    Raises:
        FileNotFoundError: If shader file doesn't exist
        GPUValidationError: If shader compilation fails

    Example:
        >>> runtime.register_shader(0, "substrate", "runtime/core/substrate.wgsl")
    """
```

## Testing

### Manual Testing Checklist

Before submitting:

- [ ] Runs without errors on your system
- [ ] All buffers initialize correctly
- [ ] Shaders compile successfully
- [ ] Debug output is readable
- [ ] No memory leaks (run for extended period)
- [ ] Works with different GPU vendors (if possible)

### Example Test Cases

```python
# Test 1: Basic initialization
def test_runtime_init():
    runtime = ShaderOSRuntime()
    assert len(runtime.shared_buffers) == 40
    print("✅ Runtime initialization test passed")

# Test 2: Shader registration
def test_shader_registration():
    runtime = ShaderOSRuntime()
    runtime.register_shader(0, "test", "runtime/core/substrate.wgsl", "main")
    assert 0 in runtime.shader_registry
    print("✅ Shader registration test passed")

# Test 3: Shader dispatch
def test_shader_dispatch():
    runtime = ShaderOSRuntime()
    runtime.register_shader(0, "test", "runtime/core/substrate.wgsl", "main")
    runtime.dispatch_shader(0)  # Should not raise
    print("✅ Shader dispatch test passed")

# Run tests
if __name__ == "__main__":
    test_runtime_init()
    test_shader_registration()
    test_shader_dispatch()
    print("\n✅ All tests passed!")
```

## Getting Help

- **Questions?** Open a discussion or issue
- **Stuck?** Check existing issues and documentation
- **Chat?** Join our community (TBD)

## Recognition

Contributors will be:
- Listed in CONTRIBUTORS.md
- Credited in release notes
- Thanked profusely! 🙏

## Code of Conduct

### Our Standards

- Be respectful and inclusive
- Focus on what's best for the project
- Accept constructive criticism gracefully
- Show empathy towards other contributors

### Unacceptable Behavior

- Harassment or discrimination
- Trolling or inflammatory comments
- Personal attacks
- Publishing others' private information

### Enforcement

Maintainers may remove, edit, or reject contributions that don't align with these standards.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

## Quick Reference

### First Time Contributing?

1. Fork the repository
2. Create a branch: `git checkout -b feature/my-feature`
3. Make changes
4. Test locally
5. Commit: `git commit -m "feat: add my feature"`
6. Push: `git push origin feature/my-feature`
7. Open a Pull Request

### Need Ideas?

Check the issue tracker for:
- `good first issue` - Beginner-friendly tasks
- `help wanted` - Need contributions
- `enhancement` - Feature requests

### Questions?

Don't hesitate to ask! Open an issue with the `question` label.

---

**Thank you for contributing to ShaderOS!** 🚀
