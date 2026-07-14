# Sandboxed Executor Architecture

## TASK_X001: Secure Cartridge Execution

### Problem

Visual Audio allows software to be spoken into existence through audio. Without sandboxing, any speaker in microphone range can execute arbitrary code — a severe security vulnerability.

### Solution: Defense-in-Depth Security

The sandboxed executor implements multiple security layers:

#### 1. Import Allowlisting

**Allowed modules** (safe, read-only):
- `math`, `random`, `statistics`, `datetime`, `collections`
- `itertools`, `functools`, `re`, `string`, `hashlib`
- `array`, `bisect`, `heapq`, `queue`
- `unicodedata`, `textwrap`, `difflib`

**Blocked modules** (dangerous):
- `os`, `sys`, `subprocess`, `shutil`, `pathlib`, `io`
- `socket`, `urllib`, `http`, `ftplib`, `smtplib`
- `pickle`, `shelve`, `marshal`, `eval`, `exec`, `compile`
- `importlib`, `ctypes`, `multiprocessing`, `threading`
- `signal`, `resource`, `pty`, `fcntl`, `termios`

Additional modules can be allowed via `--allowlist` flag.

#### 2. Resource Limits

| Limit | Value | Enforcement |
|-------|-------|-------------|
| CPU time | 5 seconds | `RLIMIT_CPU` |
| Wall time | 10 seconds | `subprocess.communicate(timeout)` |
| Memory | 64 MB | `RLIMIT_AS` |
| Disk writes | 10 MB | Post-execution check |
| stdout/stderr | 512 KB each | Truncation |
| File descriptors | 16 | `RLIMIT_NOFILE` |
| Processes | 1 (no forking) | `RLIMIT_NPROC` |

#### 3. Environment Isolation

- **PYTHONPATH stripped**: No access to site-packages
- **PYTHONNOUSERSITE=1**: Disables user site-packages
- **PATH cleared**: Cannot execute external commands
- **TMPDIR set**: Temporary directory only
- **Stdin closed**: DEVNULL (no interactive input)

#### 4. Signal Handling

Blocked signals to prevent signal-based escapes:
- `SIGINT`, `SIGQUIT`, `SIGTSTP` (terminal control)
- `SIGTTIN`, `SIGTTOU` (background job control)
- `SIGHUP` (terminal disconnect)

#### 5. Disk Usage Monitoring

Temporary directory usage checked after execution:
- Exceeds 10 MB → execution failed
- Temp dir auto-cleaned on exit

### Usage

#### Basic Execution

```bash
# Encode a file as dense cartridge
python3 tools/dense_encoder_sandbox.py encode script.py -o cartridge.png

# Execute in sandbox
python3 tools/dense_encoder_sandbox.py run cartridge.png
```

#### With Custom Limits

```bash
# Longer timeout
python3 tools/dense_encoder_sandbox.py run cartridge.png --timeout 30

# Allow additional modules
python3 tools/dense_encoder_sandbox.py run cartridge.png --allowlist statistics numpy

# Verbose output
python3 tools/dense_encoder_sandbox.py run cartridge.png -v
```

### Programmatic API

```python
from src.executor.sandbox import SandboxedExecutor, ExecutionResult

executor = SandboxedExecutor()

# Execute untrusted code
result = executor.execute(
    code="print('Hello')",
    timeout=10.0,
    allowlist=['math', 'statistics']
)

if result.success:
    print("Output:", result.stdout)
else:
    print("Error:", result.error_message)
```

### Test Coverage

The sandbox has 15 comprehensive tests:

1. **Safe execution** - Math operations work
2. **Timeout enforcement** - Infinite loops terminated
3. **Import blocking** - Dangerous imports rejected
4. **Memory limit** - Excessive allocation blocked
5. **Additional allowlist** - Allowlisted modules work
6. **Filesystem isolation** - `tempfile` blocked
7. **Network isolation** - `socket` blocked
8. **Subprocess blocking** - `subprocess` blocked
9. **Output truncation** - Large output limited
10. **Safe eval** - `eval()` allowed for literals
11. **Math module** - Allowlisted modules work
12. **Simple code** - Basic execution works
13. **Syntax error** - Syntax errors caught
14. **Multiple imports** - All blocked modules detected
15. **'from import'** - Import-from blocked

**All tests pass**: 15/15

### Example: Safe vs Malicious

#### Safe Cartridge

```python
# fibonacci.py
def fibonacci(n):
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a

print(f"Fibonacci(10) = {fibonacci(10)}")
```

```bash
$ python3 tools/dense_encoder_sandbox.py run fibonacci.png
✓ Execution completed successfully
[STDOUT]
Fibonacci(10) = 55
```

#### Malicious Cartridge (blocked)

```python
# malicious.py
import os
print("Host files:", list(os.listdir('/')))
```

```bash
$ python3 tools/dense_encoder_sandbox.py run malicious.png
✗ Execution failed
  Reason: Blocked import(s): os
  ⚠ Killed by system (security limit)
```

### Security Properties

✓ **No filesystem access**: `os`, `pathlib`, `tempfile` blocked
✓ **No network access**: `socket`, `urllib`, `http` blocked
✓ **No process forking**: `subprocess`, `multiprocessing` blocked
✓ **No code injection**: `eval`, `exec`, `compile` blocked
✓ **No persistent state**: Temp dir auto-cleaned
✓ **Resource limits enforced**: CPU, memory, wall time
✓ **Output bounded**: stdout/stderr truncated
✓ **No side channels**: Signals blocked, fd limit

### Integration Points

The sandbox integrates with:

1. **Dense encoder** (`tools/dense_encoder_sandbox.py`)
   - Replaces unsafe `exec()` with `SandboxedExecutor`
   - Same interface, transparent integration

2. **Future: Audio decoder**
   - Cartridges from spectral codec use same sandbox
   - Unified security for all visual audio sources

3. **Future: Geometry OS**
   - Cartridge execution through hypervisor syscall
   - Sandboxed by default, allowlist configurable

### Limitations and Trade-offs

1. **No persistent state**: Each execution is fresh
   - Acceptable for functional cartridges
   - Not suitable for stateful services

2. **Small memory limit**: 64 MB
   - Sufficient for data processing, algorithms
   - Insufficient for large ML models, heavy computation

3. **Limited I/O**: No network, no files
   - Cartridges must be self-contained
   - No external dependencies

4. **CPU timeout**: 5 seconds
   - Prevents infinite loops
   - Limits algorithmic complexity

### Future Enhancements

1. **Signed cartridges** - Ed25519 signatures for provenance
2. **Seccomp-bpf** - System call filtering (Linux only)
3. **User namespaces** - Process-level isolation
4. **cgroups** - Fine-grained resource control
5. **Whitelisted filesystem paths** - Configurable read-only dirs

### Conclusion

The sandboxed executor provides robust security for visual audio cartridges, enabling safe execution of untrusted code received over open acoustic channels. The defense-in-depth approach ensures that even if one layer fails, multiple additional protections remain.

**Status**: ✅ TASK_X001 COMPLETE

All 15 tests pass. Ready for integration with boot-from-audio systems.