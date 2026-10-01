# UART Ops Support — pixel_os_listener.py

## Overview

The pixel_os_listener daemon now supports executing shell commands inside a persistent Linux guest booted on SpatialRV32ICore (the GPU-resident RISC-V core). This enables pixels to trigger computational operations that run "inside the pixels" — a true spatial computing primitive.

## Architecture

```
Signed Audio Frame → Provenance Validation → UART Op → RV32Guest → Linux Shell → Output File
```

### Components

1. **RV32Guest** (`tools/rv32_guest.py`) — Persistent handle to a Linux guest
   - Boots once (~30-45s) and stays alive across commands
   - Provides `exec()` method to run shell commands
   - Auto-recovers from crashes (new guest on next op)

2. **ListenerDaemon** (`tools/pixel_os_listener.py`) — Main daemon with UART support
   - `_handle_uart_op()` — Validates and executes `["uart", command]` operations
   - Guest lifecycle management (boot, reuse, recover)
   - Output file persistence (timestamped `.txt` files)

3. **SpatialRV32ICore** (`tools/spatial_rv32i_cpu.py`) — GPU-native RISC-V execution
   - Real WGSL compute (not CPU simulation)
   - UART input/output via memory-mapped registers
   - 64MB RAM, Linux 6.1.14 RV32IMA-NOMMU kernel

## Usage

### Starting the Daemon

```bash
python3 tools/pixel_os_listener.py \
    --fb /tmp/framebuffer.png \
    --provenance \
    --public-key keys/pixel_os_public.pem \
    --enable-uart-ops \
    --uart-output-dir /tmp/uart_output \
    --queue \
    --watch-dir ./
```

### UART Op Format

Signed frame with operations:
```python
[
    ["uart", "echo hello world"],
    ["set_pixel", 100, 100, (255, 0, 0)],
    ["uart", "uname -a"],
    ["clear"]
]
```

### Execution Flow

1. **First UART op**: Guest boots (30-45s), logs in as root, runs command
2. **Subsequent UART ops**: Same guest reused (instant)
3. **Guest crash**: Detected, marked dead, new guest boots on next op
4. **Output**: Written to timestamped file (e.g., `/tmp/uart_output/uart_1723456789000.txt`)

## Security Features

### Required Flags
- `--provenance`: Only signed frames may execute UART ops
- `--enable-uart-ops`: Opt-in flag (disabled by default)
- `--uart-output-dir`: Trusted directory for output files

### Validation Rules
1. **Provenance required**: Unsigned frames rejected
2. **Opt-in only**: UART ops disabled unless `--enable-uart-ops` passed
3. **Sandboxed execution**: Commands run inside isolated Linux guest
4. **Output isolation**: Results written to trusted directory only
5. **Guest recovery**: Crashes don't compromise host

## Testing

### Unit Tests (No GPU Required)

```bash
# Run UART validation tests
python3 -m pytest tests/test_pixel_os_listener_uart.py -v

# Test coverage: 8 tests covering
# - Import validation
# - Security validation (provenance, enable flag, output dir)
# - Op structure validation
# - UART op classification
```

### Integration Tests (GPU Required)

```bash
# Real guest boot and execution (~35s for first boot)
python3 tools/pixel_os_listener.py \
    --fb /tmp/fb.png \
    --provenance \
    --enable-uart-ops \
    --uart-output-dir /tmp/uart \
    --queue &

# Create signed frame with UART op
python3 tools/speak.py encode '[["uart", "echo inside_the_pixels"]]' \
    -o test_uart.wav \
    --provenance

# Place in watch directory, verify output
ls /tmp/uart/uart_*.txt
cat /tmp/uart/uart_*.txt  # Should contain "inside_the_pixels"
```

## Performance

| Metric | Value | Notes |
|--------|-------|-------|
| First boot time | 30-45s | Linux kernel + login, one-time cost |
| Subsequent commands | <1s | Guest already running |
| Command overhead | Minimal | Just exec() in already-booted guest |
| Memory usage | ~64MB | Guest RAM allocation |
| GPU impact | One SpatialRV32ICore instance | Shared across all UART ops |

## Examples

### Example 1: Simple Shell Command

Operations:
```python
[["uart", "echo 'Hello from inside the pixels!'"]]
```

Output file (`uart_1723456789000.txt`):
```
$ echo 'Hello from inside the pixels!'
Hello from inside the pixels!
```

### Example 2: System Information

Operations:
```python
[
    ["uart", "uname -a"],
    ["uart", "free -h"],
    ["uart", "cat /proc/cpuinfo | grep 'processor'"]
]
```

Output files (3 timestamped files with system info)

### Example 3: File Operations

Operations:
```python
[
    ["uart", "mkdir -p /tmp/test"],
    ["uart", "echo 'pixel data' > /tmp/test/data.txt"],
    ["uart", "cat /tmp/test/data.txt"]
]
```

### Example 4: Mixed Pixel and UART Operations

Operations:
```python
[
    ["set_pixel", 10, 10, (255, 0, 0)],           # Draw red pixel
    ["uart", "echo 'pixel drawn'"],              # Log command
    ["draw_rect", 50, 50, 100, 50, (0, 255, 0)], # Draw green rectangle
    ["uart", "echo 'rectangle drawn'"],          # Log command
    ["clear"]                                     # Clear screen
]
```

## Troubleshooting

### Guest Never Reaches Login Prompt

**Symptom**: Logs show "Failed to boot uart guest: Linux never reached the login prompt"

**Causes**:
- Missing or corrupted kernel/DTB files
- GPU initialization failure
- Timeout too short (default 4000 blocks)

**Solutions**:
1. Verify boot images exist: `ls -la boot_images/rv32ima_nommu/`
2. Check GPU support: `python3 -c "import wgpu; print(wgpu.__version__)"`
3. Increase timeout in `rv32_guest.py` (line 56)

### Guest Crashes on Every Command

**Symptom**: Every UART op returns False with "guest crashed" error

**Causes**:
- Guest memory corruption
- Command causing kernel panic
- UART input buffer overflow

**Solutions**:
1. Check guest logs in `/tmp/uart/uart_*.txt`
2. Try simple commands first (`echo hello`, `uname -a`)
3. Verify guest not hung: `ps aux | grep python3 | grep pixel_os_listener`

### Output Files Not Created

**Symptom**: UART ops return True but no output files

**Causes**:
- Missing `--uart-output-dir` flag
- Permission denied on output directory
- Disk full

**Solutions**:
1. Check directory exists: `ls -la /tmp/uart_output`
2. Verify permissions: `chmod 755 /tmp/uart_output`
3. Check disk space: `df -h`

## Implementation Details

### Guest Lifecycle

```python
class RV32Guest:
    def __init__(self):
        # 1. Load kernel + DTB into memory
        # 2. Boot and wait for login prompt
        # 3. Login as root
        # 4. Ready for commands

    def exec(self, command: str) -> str:
        # 1. Type command into UART (byte-by-byte with stepping)
        # 2. Wait for sentinel output
        # 3. Extract and return stdout
```

### ListenerDaemon Integration

```python
class ListenerDaemon:
    def __init__(self, ..., enable_uart_ops=False, uart_output_dir=None):
        self.enable_uart_ops = enable_uart_ops
        self.uart_output_dir = uart_output_dir
        self.guest = None  # Lazy-initialized

    def _dispatch_ops(self, ops: list) -> bool:
        # Classify ops
        uart_ops = [op for op in ops if op[0] == 'uart']
        draw_ops = [op for op in ops if op[0] not in ('boot', 'write', 'run', 'uart')]

        # Execute in order
        for op in uart_ops:
            self._handle_uart_op(op)
        self._apply_ops_to_framebuffer(draw_ops)

    def _handle_uart_op(self, op) -> bool:
        # 1. Validate provenance, enable flag, output dir
        # 2. Boot guest if needed (lazy, one-time)
        # 3. Execute command
        # 4. Write output to timestamped file
```

## Future Enhancements

### Planned Features
- [ ] Command timeout enforcement (prevent infinite hangs)
- [ ] Output size limits (prevent disk exhaustion)
- [ ] Command whitelist/blacklist (sandbox tightening)
- [ ] Multi-guest support (parallel execution)
- [ ] Guest state persistence (files across commands)
- [ ] Network access (HTTP requests from inside pixels)

### Research Directions
- [ ] Persistent filesystem mounted from container
- [ ] AI agent execution inside guest (LLM booted from pixels)
- [ ] Distributed computing across multiple guests
- [ ] GPU-to-GPU communication (guest ↔ host graphics)

## Related Components

- **SpatialRV32ICore** (`tools/spatial_rv32i_cpu.py`) — GPU RISC-V core
- **inside_the_pixels_demo.py** — Original demo extracting guest output
- **pixel_os_listener.py** — Main daemon with UART support
- **rv32_guest.py** — Persistent guest abstraction layer

## References

- **Linux kernel**: `boot_images/rv32ima_nommu/Image` (6.1.14 RV32IMA-NOMMU)
- **Device tree**: `boot_images/rv32ima_nommu/sixtyfourmb.dtb` (64MB RAM config)
- **WGSL compute shader**: `tools/SPATIAL_RV64I.wgsl` (GPU execution engine)

---

**Status**: ✅ IMPLEMENTED — UART op support complete with validation, testing, and documentation

**Last Updated**: 2026-08-12

**Compatibility**: Requires wgpu backend, Linux 6.1.14 RV32IMA-NOMMU kernel, SpatialRV32ICore implementation