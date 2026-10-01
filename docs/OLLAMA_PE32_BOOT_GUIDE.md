# Using Ollama for PE32+ GPU Boot Stepladder

## Available Models

```
ollama list

qwen2.5-coder:14b        - 9.0 GB   - 4 days ago   - BEST for code generation
llava:latest             - 4.7 GB   - 6 days ago   - Vision + code (debug screenshots)
nomadic-embed-text      - 274 MB   - 4 weeks ago  - Embeddings (semantic search)
phi3:latest             - 2.2 GB   - 5 weeks ago  - Fast, smaller model
qwen2.5-coder:latest    - 4.7 GB   - 3 months ago - Older qwen version
```

**Recommended: qwen2.5-coder:14b** (9GB, best for code generation)

---

## Use Case 1: Generate WGSL UEFI Services

**Problem:** Need to write UEFI runtime services in WGSL shader language.

**Ollama can:** Generate UEFI service implementations in WGSL format.

### Example: Generate AllocatePool

```bash
cat <<'EOF' | ollama run qwen2.5-coder:14b
You are a WebGPU/WGSL shader expert. I need to implement UEFI AllocatePool
service in a RISC-V GPU emulator shader.

Context:
- GPU memory is in a storage buffer (read_write)
- Need to allocate memory from a heap
- Return EFI_SUCCESS (0) on success, EFI_OUT_OF_RESOURCES otherwise

WGSL code snippet (RiscvCPU struct):
struct RiscvCPU {
    pc: vec2<u32>,
    regs: array<vec2<u32>, 32>,
    running: u32,
    uefi_heap_ptr: u32,        // Current heap pointer
    uefi_heap_end: u32,        // End of heap
}

Function signature:
fn uefi_allocate_pool(size: u32, pool_ptr: ptr<u32>) -> u32

Requirements:
1. Check if size fits in remaining heap
2. If yes, allocate from heap_ptr and update it
3. Write address to pool_ptr
4. Return EFI_SUCCESS (0) or EFI_OUT_OF_RESOURCES (0x80000009)
5. Use atomic operations if needed

Write the complete WGSL function with comments explaining each step.
EOF
```

**Expected Output:**
```wgsl
fn uefi_allocate_pool(size: u32, pool_ptr: ptr<u32>) -> u32 {
    // Check if requested size fits in remaining heap
    let remaining = cpu.uefi_heap_end - cpu.uefi_heap_ptr;
    if (size > remaining) {
        return 0x80000009u;  // EFI_OUT_OF_RESOURCES
    }

    // Allocate from heap
    let addr = cpu.uefi_heap_ptr;
    cpu.uefi_heap_ptr = cpu.uefi_heap_ptr + size;

    // Return allocated address to caller
    *pool_ptr = addr;

    return 0u;  // EFI_SUCCESS
}
```

### Batch Generate Multiple Services

```bash
#!/bin/bash
# generate_uefi_services.sh

SERVICES=(
    "AllocatePool(size: u32, pool_ptr: ptr<u32>) -> u32"
    "FreePool(pool: u32) -> u32"
    "GetVariable(name: ptr<u8>, guid: ptr<u8>, attrs: ptr<u32>, data: ptr<u8>, size: ptr<u32>) -> u32"
    "SetVariable(name: ptr<u8>, guid: ptr<u8>, attrs: u32, data: ptr<u8>, size: u32) -> u32"
    "GetTime(time: ptr<u32>) -> u32"
    "ResetSystem(reset_type: u32, status: u32, data_size: u32, data: ptr<u8>) -> u32"
)

for service in "${SERVICES[@]}"; do
    echo "Generating: $service"
    cat <<EOF | ollama run qwen2.5-coder:14b > "uefi_${service%%(*}.wgsl"
You are a WebGPU/WGSL shader expert. Implement this UEFI service:
$service

Context: RISC-V GPU emulator, UEFI runtime services.
Requirements: Return EFI_SUCCESS (0) on success, error codes on failure.

Write complete WGSL function with comments.
EOF
done
```

---

## Use Case 2: Code Review Hybrid Loader

**Problem:** Hybrid loader is complex, need to catch bugs before GPU testing.

**Ollama can:** Review code for bugs, security issues, and performance problems.

### Example: Review hybrid_kernel_loader.py

```bash
cat <<'EOF' | ollama run qwen2.5-coder:14b
You are a senior Python code reviewer. Review this kernel loader for bugs,
security issues, and performance problems.

Review the file: tools/hybrid_kernel_loader.py

Focus on:
1. Buffer overflow vulnerabilities
2. Integer overflow in size calculations
3. Missing error handling
4. Performance issues (unnecessary copies)
5. Edge cases (empty files, corrupted headers)

Provide:
- Bug reports with line numbers
- Security vulnerabilities (if any)
- Performance suggestions
- Code quality issues

Be thorough but concise. Use this format:
[BUG] Line 123: Potential buffer overflow
[SEC] Line 456: Missing input validation
[PERF] Line 789: Unnecessary copy of 21MB data
[QUAL] Line 100: Magic numbers, should use constants
EOF
```

**Expected Output:**
```
[BUG] Line 195: pe_offset can be negative if header[0x3C:0x40] is corrupted
[SEC] Line 171: No file size validation before reading 256 bytes (DoS risk)
[PERF] Line 280: Loop recalculates total_size in every iteration, move outside
[QUAL] Line 198: Magic number 0x3C should be named PE_HEADER_OFFSET
```

### Interactive Review Loop

```bash
# Step 1: Ask Ollama to review
ollama run qwen2.5-coder:14b "Review tools/hybrid_kernel_loader.py for bugs" > review_1.txt

# Step 2: Fix the bugs (manually or with Ollama's help)

# Step 3: Ask Ollama to re-review
ollama run qwen2.5-coder:14b "Review tools/hybrid_kernel_loader.py again, focusing on PE32+ section parsing" > review_2.txt

# Step 4: Compare reviews
diff review_1.txt review_2.txt
```

---

## Use Case 3: Debug Boot Failures

**Problem:** Alpine kernel loads but doesn't boot. Need to diagnose why.

**Ollama can:** Analyze boot logs and suggest fixes.

### Example: Analyze Alpine Boot Output

```bash
# Capture boot output
python3 tools/boot_xv6_gpu.py boot_images/alpine_Image 2>&1 > alpine_boot_log.txt

# Ask Ollama to analyze
cat <<'EOF' | ollama run qwen2.5-coder:14b
You are a Linux kernel boot debugging expert. Analyze this boot log
from a RISC-V GPU emulator booting Alpine Linux.

Boot log:
$(cat alpine_boot_log.txt)

Context:
- Emulator: GPU-based RISC-V emulator (WGSL compute shader)
- Kernel: Alpine Linux PE32+ kernel
- UEFI support: Minimal (AllocatePool, FreePool, ConsoleOutput only)

Questions:
1. Why did the kernel fail to boot?
2. Which UEFI service is missing or failing?
3. What error code is returned?
4. Suggest 3 specific fixes to try

Be specific with line numbers and error codes.
EOF
```

**Expected Output:**
```
Analysis:
1. Kernel loaded successfully (entry point 0x0000100000a3b6d8)
2. Called UEFI service 0x15 (OutputString) - success
3. Called UEFI service 0x10 (AllocatePool, size=0x1000) - returned EFI_OUT_OF_RESOURCES (0x80000009)
4. Kernel panicked: "EFI memory allocation failed"

Missing services:
- GetVariable (needed for kernel config)
- GetTime (needed for boot timing)

Suggested fixes:
1. Increase UEFI heap size (currently 8MB, try 16MB)
2. Implement GetVariable service (kernel reads config variables)
3. Add memory pool tracking (prevent fragmentation)
```

### Use llava for Visual Debugging

```bash
# Take screenshot of VNC console
vncdotool -s localhost:1 capture boot_screenshot.png

# Ask llava to analyze
ollama run llava "Analyze this boot screenshot. Is there an error message? What does the console say?" boot_screenshot.png
```

---

## Use Case 4: Generate Test Cases

**Problem:** Each phase needs verification tests. Writing tests manually is slow.

**Ollama can:** Generate comprehensive test cases for each phase.

### Example: Generate Phase 1 Tests

```bash
cat <<'EOF' | ollama run qwen2.5-coder:14b
You are a Python test engineer. Write pytest test cases for Phase 1 of the
PE32+ GPU boot stepladder.

Context:
- Phase 1 integrates HybridKernelLoader into boot_xv6_gpu.py
- Must test: xv6 (ELF64), hello (ELF64), Alpine (PE32+)
- Must verify: Format detection, segment loading, entry point

Write 10 test cases covering:
1. ELF64 format detection
2. PE32+ format detection
3. Invalid format rejection
4. ELF64 segment loading
5. PE32+ section loading
6. Entry point correctness (ELF64)
7. Entry point correctness (PE32+)
8. Memory boundary checks
9. Shared code path (no regressions)
10. Performance (xv6 still boots in <0.5s)

Use pytest format with fixtures and assertions. Include docstrings explaining each test.
EOF
```

**Expected Output:**
```python
import pytest
from hybrid_kernel_loader import HybridKernelLoader, ELF64Loader, PE32Loader

@pytest.fixture
def xv6_path():
    return "boot_images/xv6.img"

@pytest.fixture
def alpine_path():
    return "boot_images/alpine_Image"

def test_elf64_format_detection(xv6_path):
    """Test ELF64 format is correctly detected."""
    loader, fmt = HybridKernelLoader.load(xv6_path)
    assert fmt == "ELF64"
    assert isinstance(loader, ELF64Loader)

def test_pe32_format_detection(alpine_path):
    """Test PE32+ format is correctly detected."""
    loader, fmt = HybridKernelLoader.load(alpine_path)
    assert fmt == "PE32+"
    assert isinstance(loader, PE32Loader)

def test_invalid_format_rejection():
    """Test invalid format raises ValueError."""
    with pytest.raises(ValueError, match="Unknown kernel format"):
        HybridKernelLoader.load("nonexistent_file.bin")

# ... more tests
```

### Batch Generate Tests for All Phases

```bash
#!/bin/bash
# generate_tests.sh

PHASES=(
    "Phase 1: Hybrid Loader Integration"
    "Phase 2: UEFI Runtime Services"
    "Phase 3: UEFI Boot Services"
    "Phase 4: Alpine Boot"
    "Phase 5: Ubuntu Boot"
    "Phase 6: Regression Testing"
)

for phase in "${PHASES[@]}"; do
    echo "Generating tests for: $phase"
    cat <<EOF | ollama run qwen2.5-coder:14b > "tests/test_${phase// /_}.py"
You are a Python test engineer. Write pytest test cases for: $phase

Read the stepladder: docs/PE32_GPU_BOOT_STEPLADER.md

Write 10 comprehensive test cases covering:
1. Happy path (success case)
2. Error cases (invalid inputs, failures)
3. Edge cases (boundary conditions)
4. Integration with other phases
5. Performance benchmarks

Use pytest format with fixtures and assertions.
EOF
done
```

---

## Use Case 5: Code Completion in IDE

**Problem:** Writing WGSL shader code is tedious without IDE support.

**Ollama can:** Provide IDE-style code completion via integration.

### Example: Neovim Integration

```lua
-- ~/.config/nvim/lua/ollama-completion.lua
local M = {}

function M.complete()
    local line = vim.api.nvim_get_current_line()
    local col = vim.api.nvim_win_get_cursor(0)[2]

    local context = table.concat(vim.api.nvim_buf_get_lines(0, 0, -1, false), "\n")

    local prompt = string.format(
        "Complete this WGSL code at cursor position (line %d, col %d):\n%s\n\nComplete only the next 10 tokens, no explanation.",
        line_num, col, context
    )

    local handle = io.popen("ollama run qwen2.5-coder:14b '" .. prompt .. "'", "r")
    local completion = handle:read("*a")
    handle:close()

    -- Insert completion at cursor
    vim.api.nvim_put({completion}, "", true, true)
end

return M

-- Map to <Tab>
vim.api.nvim_set_keymap("i", "<Tab>", "<cmd>lua require('ollama-completion').complete()<CR>", {noremap = true})
```

### Example: VS Code Integration

```json
// .vscode/settings.json
{
    "python.languageServer": "Pylance",
    "editor.inlineSuggest.enabled": true,
    "github.copilot.enable": {
        "*": false,  // Disable Copilot
        "wgsl": true,  // Use Ollama instead
    }
}
```

```typescript
// Extension: Ollama Code Completion (pseudo-code)
import * as vscode from 'vscode';
import { exec } from 'child_process';

function provideCompletion(
    document: vscode.TextDocument,
    position: vscode.Position
): vscode.CompletionItem[] {
    const linePrefix = document.lineAt(position).text.substr(0, position.character);

    exec(`ollama run qwen2.5-coder:14b "Complete this WGSL: ${linePrefix}"`,
        (error, stdout) => {
            if (!error) {
                return [
                    new vscode.CompletionItem(stdout.trim(), vscode.CompletionItemKind.Function)
                ];
            }
        }
    );

    return [];
}
```

---

## Use Case 6: Parallel Code Generation

**Problem:** Multiple phases need code simultaneously (WGSL services, Python tests, docs).

**Ollama can:** Generate code in parallel using multiple model instances.

### Example: Generate 3 Phases in Parallel

```bash
#!/bin/bash
# parallel_codegen.sh

# Phase 2: UEFI WGSL services
(
    cat <<EOF | ollama run qwen2.5-coder:14b > phase2_uefi.wgsl
Generate UEFI runtime services in WGSL for RISC-V GPU emulator.
Services: AllocatePool, FreePool, GetVariable, SetVariable.
EOF
) &

# Phase 3: Boot services Python
(
    cat <<EOF | ollama run qwen2.5-coder:14b > phase3_boot_services.py
Generate UEFIBootServices class in Python for GPU emulator.
Methods: load_image(), start_image(), get_handle().
EOF
) &

# Phase 4: Device tree generator
(
    cat <<EOF | ollama run qwen2.5-coder:14b > phase4_dtb_generator.py
Generate minimal device tree blob generator for RISC-V.
CPU, memory, UART, VirtIO devices.
EOF
) &

# Wait for all to complete
wait

echo "All phases generated in parallel:"
ls -lh phase*.wgsl phase*.py
```

### Monitor Progress

```bash
# Run in background
parallel_codegen.sh > parallel.log 2>&1 &

# Watch progress
watch -n 1 'tail -20 parallel.log; echo "---"; ls -lh phase* 2>/dev/null'

# When done:
cat parallel.log
```

---

## Use Case 7: Documentation Generation

**Problem:** Writing documentation is tedious and often incomplete.

**Ollama can:** Generate comprehensive documentation from code.

### Example: Generate API Docs for Hybrid Loader

```bash
cat <<'EOF' | ollama run qwen2.5-coder:14b > docs/HYBRID_LOADER_API.md
Generate comprehensive API documentation for the hybrid kernel loader.

Read the source: tools/hybrid_kernel_loader.py

Generate:
1. Module overview
2. Class documentation (ELF64Loader, PE32Loader, HybridKernelLoader)
3. Method documentation (all public methods)
4. Usage examples
5. Error handling guide
6. Performance characteristics

Format as Markdown with code examples.
EOF
```

**Expected Output:**
```markdown
# Hybrid Kernel Loader API

## Overview

The hybrid kernel loader provides unified loading for both ELF64 and PE32+ RISC-V kernels.

## Classes

### ELF64Loader

Loads RISC-V ELF64 executables.

```python
from hybrid_kernel_loader import ELF64Loader

elf = ELF64Loader("boot_images/xv6.img")
print(f"Entry point: 0x{elf.entry_point:016x}")

for segment in elf.get_loadable_segments():
    data = elf.get_segment_data(segment)
    # Upload to GPU...
```

#### Methods

- `__init__(path: str)`: Parse ELF64 file
- `get_loadable_segments()`: Return PT_LOAD segments
- `get_segment_data(segment)`: Get raw segment data
- `print_info()`: Print ELF information

... more documentation
```

---

## Best Practices

### 1. Prompt Engineering

**Good prompt:**
```
You are a WGSL shader expert. Implement UEFI AllocatePool service.

Context:
- RISC-V GPU emulator
- GPU memory is in storage buffer
- Need to allocate from heap

Requirements:
1. Check heap bounds
2. Allocate memory
3. Return EFI_SUCCESS (0) or error code

Write complete WGSL function with comments.
```

**Bad prompt:**
```
Write AllocatePool in WGSL.
```

### 2. Iterate on Results

```bash
# First attempt
ollama run qwen2.5-coder:14b "Write AllocatePool in WGSL" > alloc1.wgsl

# Review and refine
ollama run qwen2.5-coder:14b "Improve this WGSL code, add atomic operations for thread safety" alloc1.wgsl > alloc2.wgsl

# Test and debug
ollama run qwen2.5-coder:14b "This WGSL code has compilation errors, fix them: $(cat alloc2.wgsl)" > alloc3.wgsl
```

### 3. Use Smaller Models for Quick Tasks

```bash
# Fast: Use phi3 for quick code snippets
ollama run phi3 "What's the magic number for ELF64?"  # 2s response

# Accurate: Use qwen2.5-coder:14b for complex tasks
ollama run qwen2.5-coder:14b "Implement full UEFI AllocatePool in WGSL"  # 10s response
```

### 4. Batch Process Large Tasks

```bash
# Don't: Ask for all UEFI services at once (slow, incomplete)
ollama run qwen2.5-coder:14b "Implement all 20 UEFI services in WGSL" > all_services.wgsl

# Do: Ask for services one at a time (fast, detailed)
for service in AllocatePool FreePool GetVariable SetVariable; do
    ollama run qwen2.5-coder:14b "Implement $service in WGSL" > "${service}.wgsl"
done
```

### 5. Save Context for Continuity

```bash
# Create context file
cat > context.md <<EOF
Project: PE32+ GPU Boot Stepladder
Goal: Enable Ubuntu/Alpine RISC-V kernels on GPU
Current phase: Phase 2 (UEFI Runtime Services)
WGSL shader: RISCV_CPU_MMU.wgsl (3411 lines)
Python loader: tools/hybrid_kernel_loader.py
EOF

# Use context in all prompts
ollama run qwen2.5-coder:14b -f context.md "Implement AllocatePool in WGSL"
```

---

## Performance Tips

### 1. Use Local Models

```bash
# Slow: Online API (latency, cost)
curl https://api.openai.com/...  # 2-5s per request

# Fast: Local Ollama (no latency, free)
ollama run qwen2.5-coder:14b  # 0.5s per request
```

### 2. Cache Common Prompts

```bash
# Save frequently-used prompts
mkdir -p ~/.ollama/prompts

cat > ~/.ollama/prompts/wgsl_template.txt <<EOF
You are a WGSL shader expert. Implement this function:
FUNCTION_SIGNATURE

Context: RISC-V GPU emulator, UEFI runtime services.
Requirements:
1. Return EFI_SUCCESS (0) on success
2. Return error codes on failure
3. Use atomic operations if needed

Write complete WGSL function with comments.
EOF

# Use template
ollama run qwen2.5-coder:14b -f ~/.ollama/prompts/wgsl_template.txt "AllocatePool(size: u32, pool: ptr<u32>) -> u32"
```

### 3. Limit Output Size

```bash
# Too much output (slow)
ollama run qwen2.5-coder:14b "Explain PE32+ format in detail"  # 500 words

# Just enough (fast)
ollama run qwen2.5-coder:14b "Explain PE32+ format in 3 sentences"  # 50 words
```

---

## Common Pitfalls

### 1. Hallucination

```
User: What's the magic number for ELF64?
Ollama: 0x7F (wrong, it's 0x7fELF)

Fix: Always verify with actual file
```

### 2. Incomplete Code

```
User: Implement all UEFI services
Ollama: (writes 5 services, stops halfway through)

Fix: Ask for one service at a time
```

### 3. Wrong Language/Format

```
User: Write AllocatePool in WGSL
Ollama: (writes in GLSL instead of WGSL)

Fix: Be explicit about WGSL syntax
```

---

## Summary

**How to use Ollama:**

| Use Case | Model | Command |
|----------|-------|---------|
| **Generate WGSL code** | qwen2.5-coder:14b | `ollama run qwen2.5-coder:14b "Write AllocatePool in WGSL"` |
| **Code review** | qwen2.5-coder:14b | `ollama run qwen2.5-coder:14b "Review tools/hybrid_kernel_loader.py"` |
| **Debug boot logs** | qwen2.5-coder:14b | `ollama run qwen2.5-coder:14b -f boot.log.txt "Analyze boot failure"` |
| **Generate tests** | qwen2.5-coder:14b | `ollama run qwen2.5-coder:14b "Write pytest tests for Phase 1"` |
| **Visual debugging** | llava | `ollama run llava "Analyze screenshot" screenshot.png` |
| **Quick questions** | phi3 | `ollama run phi3 "What's ELF64 magic?"` |
| **Documentation** | qwen2.5-coder:14b | `ollama run qwen2.5-coder:14b "Generate API docs"` |
| **Parallel generation** | Multiple | `parallel ollama run ...` |

**Recommended workflow:**

1. **Phase 1 (Integration):** Use Ollama for code review
2. **Phase 2 (UEFI):** Use Ollama to generate WGSL services
3. **Phase 3 (Boot Services):** Use Ollama to write Python classes
4. **Phase 4-5 (Boot):** Use Ollama to analyze boot logs
5. **Phase 6 (Testing):** Use Ollama to generate test cases
6. **Phase 8 (Docs):** Use Ollama to write documentation

**Start now:**

```bash
# Generate UEFI AllocatePool service
ollama run qwen2.5-coder:14b "Implement UEFI AllocatePool in WGSL for RISC-V GPU emulator" > uefi_allocate_pool.wgsl

# Review the result
cat uefi_allocate_pool.wgsl
```