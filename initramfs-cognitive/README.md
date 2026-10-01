# Cognitive Initramfs — "The Screen is the Mind"

A self-bootstrapping Neural OS initramfs that extracts LLM weights from a pixel container during boot and queries itself to determine the correct boot procedure.

## Architecture

The Cognitive Initramfs implements a novel boot architecture where:

1. **The OS knows its own structure** — It reads cognitive metadata from the pixel container
2. **The OS contains its own mind** — LLM weights are embedded in the spatial substrate
3. **The OS makes boot decisions** — It queries the LLM during init to determine mount commands

This is "The Screen is the Mind" architecture: the screen (pixel container) IS the hard drive, and it also IS the mind (LLM weights).

## Components

### Core Userland (Busybox)
- 272 applets providing a complete POSIX environment
- ~1MB footprint
- Essential utilities: sh, mount, cat, grep, sed, awk, etc.

### Python Runtime (3.12)
- Full Python 3.12 interpreter
- Required modules: `sys`, `json`, `hashlib`
- Used for pixel decoding and GGUF extraction

### LLM Inference (llama-cpp-python)
- llama.cpp Python bindings
- Supports GGUF quantized models (Q4_K_M, Q5_K_M, Q8_0)
- Minimal memory footprint: ~200MB for 7B Q4 model

### Cognitive Boot Logic (`init`)
1. Mount essential filesystems (proc, sys, devtmpfs)
2. Check for VAC2 pixel container at `/mnt/pixels`
3. Read cognitive metadata from `cognitive_boot.json`
4. Decode pixel-encoded GGUF weights using Python
5. Verify MD5 checksum
6. Load LLM model via llama-cpp-python
7. Query model: "How should I complete this boot?"
8. Execute suggested mount commands
9. Transition to real root via `switch_root`

## Building

```bash
cd initramfs-cognitive
./build.sh
```

This creates `output/initramfs-cognitive.gz` (~275MB).

### Prerequisites

- `/bin/busybox` (install with `sudo apt-get install busybox`)
- Python 3.12 development headers
- llama-cpp-python installed in user or system Python

## Validation

```bash
cd initramfs-cognitive
./test.sh
```

Validates:
- Required directory structure
- Init script cognitive boot logic
- Python import capability
- llama-cpp-python installation
- Busybox applet availability
- Shared library completeness

## Usage with QEMU

```bash
qemu-system-x86_64 \
  -kernel vmlinuz \
  -initrd initramfs-cognitive/output/initramfs-cognitive.gz \
  -drive file=disk.img,format=raw,if=virtio \
  -m 4096 -smp 4 \
  -nographic
```

The initramfs expects:
- `/mnt/pixels` mounted by a VAC2-compatible kernel module
- `llm_weights.pixel` file containing GGUF model data
- `cognitive_boot.json` file with boot metadata

## Boot Flow

```
1. Kernel loads initramfs
   ├─ mounts /proc, /sys, /dev
   ├─ creates 512MB tmpfs at /tmp/cognitive
   └─ checks for /mnt/pixels

2. Pixel extraction (Python)
   ├─ reads llm_weights.pixel
   ├─ reads cognitive_boot.json
   ├─ decodes RGB triplets back to bytes
   ├─ removes padding
   ├─ writes GGUF to /tmp/cognitive/llm_weights.gguf
   └─ verifies MD5 checksum

3. Cognitive inference (llama-cpp-python)
   ├─ loads GGUF model
   ├─ queries: "How should I complete this boot?"
   ├─ receives: mount /dev/vda1 /sysroot
   └─ saves to /tmp/cognitive/boot_commands.sh

4. Boot execution
   ├─ sources boot_commands.sh
   ├─ mounts root filesystem
   └─ exec switch_root /sysroot /sbin/init

5. Normal systemd boot
```

## Cognitive Boot Prompt

The LLM receives this prompt:

```
I am a Linux kernel booting from a read-only pixel container. I have already extracted my own neural weights from the spatial substrate. I need to complete the boot process by mounting the root filesystem at /dev/vda1 and switching to init. Provide the exact shell commands I should execute, one per line, with no explanations.
```

The model responds with executable shell commands:

```
mount /dev/vda1 /sysroot
exec switch_root /sysroot /sbin/init
```

## Model Recommendations

| Model | Size | Params | Boot Time | Reasoning |
|-------|------|--------|-----------|-----------|
| TinyLlama 1.1B | 700MB | 1.1B | ~3s | Fastest, adequate for simple mount logic |
| Llama-2 7B | 4.3GB | 7B | ~8s | Stronger reasoning, good for complex boot scenarios |
| Llama-3 8B | 4.9GB | 8B | ~10s | Best quality, latest architecture |

Use TinyLlama for development/testing. Use Llama-2/3 for production where boot time is less critical than reasoning quality.

## Memory Requirements

- Base initramfs: 275MB
- TinyLlama 1.1B: +200MB → ~475MB total
- Llama-2 7B: +3.5GB → ~3.8GB total
- Llama-3 8B: +4.0GB → ~4.3GB total

Recommended QEMU memory: 4GB (TinyLlama) to 8GB (Llama-3).

## Integration with VAC2

The `tools/cognitive_boot_injector.py` script automates the full pipeline:

1. Downloads GGUF model from HuggingFace
2. Encodes GGUF bytes to spatial pixels
3. Injects pixel data into VAC2 MKV as `llm_weights.pixel`
4. Injects this built initramfs as `initramfs-cognitive.gz`
5. Creates cognitive metadata as `cognitive_boot.json`

```bash
python3 tools/cognitive_boot_injector.py inject \
  --mkv ubuntu_uefi_vac2.mkv \
  --model tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf \
  --output ubuntu_cognitive_vac2.mkv
```

## Verification

Verify injected payload:

```bash
python3 tools/cognitive_boot_injector.py verify \
  --mkv ubuntu_cognitive_vac2.mkv
```

## Expected Boot Output

```
=== Cognitive Boot Initramfs ===
I am a Linux kernel booting from a read-only pixel container.
Extracting my mind from the spatial substrate...
✓ Pixel container found at /mnt/pixels
Reading cognitive boot configuration...
{"cognitive_boot": true, "llm_model": "tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf", ...}

=== Decoding LLM weights from pixel storage ===
Pixel-encoded LLM weights detected
Extracting to /tmp/cognitive/llm_weights.gguf...
✓ Extracted 734,003,200 bytes of LLM weights
  Model: tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf
  Parameters: 1.1B
  Original MD5: a3f5e8d9c2b1...
  ✓ MD5 verification passed

✓ LLM weights extracted and verified successfully

=== Self-Aware Boot Query ===
Querying my own cognitive model: 'How should I complete this boot?'
Loading neural model...
Generating boot command...
mount /dev/vda1 /sysroot
exec switch_root /sysroot /sbin/init

=== Executing Cognitive Boot Commands ===
[ ... mount output ... ]
[ ... switch_root output ... ]
[ ... systemd boot messages ... ]
```

## Troubleshooting

### "llama-cpp-python not installed"
Install llama-cpp-python:
```bash
pip install llama-cpp-python
```

### "Pixel container not found at /mnt/pixels"
Ensure VAC2 kernel module is loaded and mounted:
```bash
modprobe vac2
mount -t vac2 none /mnt/pixels
```

### "LLM extraction failed"
Check:
- `llm_weights.pixel` exists and is readable
- `cognitive_boot.json` exists and is valid JSON
- MD5 checksum matches (may indicate corruption)

### "Cognitive inference failed"
Check:
- llama-cpp-python shared library is accessible
- Model file is valid GGUF format
- Sufficient memory available

## Design Philosophy

This initramfs embodies three key principles:

1. **Spatial Self-Awareness** — The OS knows it's stored as pixels
2. **Embedded Cognition** — The OS carries its own neural weights
3. **Recursive Bootstrapping** — The OS asks itself how to boot

The ultimate goal: a system that can boot, reason, and modify its own boot process purely through operations on its pixel representation.

## Future Enhancements

- **Self-modifying boot logic** — LLM suggests and applies init script patches
- **Boot-time debugging** — LLM analyzes and fixes boot failures
- **Adaptive mount strategies** — LLM chooses optimal mount options based on hardware
- **Parallel boot optimization** — LLM suggests parallel service startup order
- **Security-aware boot** — LLM verifies signatures and detects tampering

## License

Part of the Visual Audio project.