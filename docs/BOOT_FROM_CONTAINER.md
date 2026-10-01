# Boot from visual_audio.mkv

**Status**: Concept ready, Alpine Docker image available locally

## Concept

The `visual_audio.mkv` container can store bootable OS images. A single file can:
1. Store multiple qcow2/boot images
2. Verify them with CRC32 + sha256
3. Extract on demand to `boot_images/`
4. Boot via the existing `tools/boot_manifest.py` safety gates

## Workflow

### 1. Add a bootable image to container

```bash
# Create/download an Alpine qcow2 image (example using virt-manager)
# Then add it to the container:
python3 tools/va_container.py add visual_audio.mkv alpine.qcow2 \
  --role content --name alpine_desktop --note "Alpine Linux with desktop"
```

### 2. Extract and boot

```bash
# Extract to boot_images/
python3 tools/va_container.py cat visual_audio.mkv alpine_desktop \
  -o boot_images/alpine.qcow2

# Verify extraction
ls -lh boot_images/alpine.qcow2

# Boot via boot_manifest
python3 tools/boot_manifest.py launch_boot \
  ["boot", "x86_64", "alpine.qcow2", {"gui": true}] \
  --image-dir boot_images
```

### 3. Connect to VNC (if GUI mode)

```bash
# Connect to VNC display
vncviewer localhost:1

# Or capture screenshot
vncdotool -s localhost:1 capture screenshot.png
```

## Existing Boot Infrastructure

- `tools/boot_manifest.py` — Safe boot manifest parser (TASK_C033)
  - Validates architecture (riscv64, x86_64)
  - Allows drive/initrd/mem/smp options (TASK_C040)
  - GUI mode with VNC (TASK_C041)
- `boot_images/` — Trusted directory for boot images
  - Currently has: `arch_desktop.qcow2` (2.4GB, desktop Linux)
  - README documents usage and safety rules

## Next Steps

To make this work end-to-end:

1. **Create Alpine qcow2**:
   ```bash
   # Using Docker export + qemu-img convert
   docker run -d alpine tail -f /dev/null
   docker ps  # get container ID
   docker export <container_id> > alpine.tar
   tar -xf alpine.tar
   qemu-img convert -f raw filesystem.raw -O qcow2 alpine.qcow2
   ```

2. **Add to container**:
   ```bash
   python3 tools/va_container.py add visual_audio.mkv alpine.qcow2 \
     --role content --name alpine_boot
   ```

3. **Create helper script** (boot_from_container.py) to automate extract+boot

4. **Boot on demand**:
   ```bash
   python3 tools/boot_from_container.py alpine_boot --gui
   ```

## Security Model

- Container entries are CRC32 + sha256 verified
- Extracted files go to trusted `boot_images/` directory
- `boot_manifest.py` validates:
  - Architecture allowlist
  - No path traversal (bare filenames only)
  - Safe QEMU argv construction (no shell)
- GUI mode forces `snapshot=on` (no persistent disk changes)

## Status

- **Container**: Ready (157 frames, 133 entries, all verified)
- **Boot infrastructure**: Complete (TASK_C033, TASK_C040, TASK_C041)
- **Alpine image**: Docker image downloaded, needs qcow2 conversion
- **Automation**: boot_from_container.py draft exists

---

**Generated**: 2026-07-24