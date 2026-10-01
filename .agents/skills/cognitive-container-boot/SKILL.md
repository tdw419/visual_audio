---
name: cognitive-container-boot
description: >-
  Use this skill when you need to boot the Geometry OS cognitive container,
  verify spatial logic extraction, or test the "Screen is the Mind" architecture.
---

# Cognitive Container Boot Skill

This skill provides the runbook for booting the Geometry OS cognitive container and verifying the successful extraction of neural weights from a spatial block device.

## Context
Geometry OS uses a visual bootstrap process ("The Screen is the Mind") where LLM neural weights (GGUF) are extracted from a visual pixel substrate (Hilbert curve encoded) during the initramfs phase.

## Steps to Boot and Verify

1. **Verify Prerequisites**:
   Ensure the spatial block device container (`ubuntu_cognitive_vac2_v3.nut` or equivalent) and the `boot_cognitive_container.sh` script exist in the workspace root.

2. **Execute the Boot Sequence**:
   Run the boot script in the background or monitor it directly.
   ```bash
   ./boot_cognitive_container.sh
   ```
   *Note: The script uses QEMU with VNC enabled (`-display vnc=:0`). The VirtIO-Pixel backend is started automatically to serve the `.nut` container.*

3. **Wait for Extraction**:
   The extraction process (parsing pixels to bytes and calculating the MD5 hash) and the subsequent `llama-cpp-python` inference typically takes around 30 to 60 seconds depending on the system load.

4. **Verify the Results**:
   Read the `container_boot.log` output. You MUST ensure the following verification gates pass:
   
   - **MD5 Hash Verification**: 
     Look for `✓ MD5 verification passed` in the log.
   - **Inference Verification**:
     Look for the `=== COGNITIVE OUTPUT ===` JSON block. The `status` must be `"success"` and the `boot_type` must be `"spatial_cognitive"`.
   - **Graceful Shutdown**:
     Look for `Shutting down container gracefully...` followed by `=== Container Shutdown ===`.

## Troubleshooting

- **Timeout Error**: If the `VirtIO-Pixel` backend times out, check `/tmp/virtio_cognitive_backend.log` for errors related to the `.nut` file parsing.
- **Kernel Panic**: If QEMU panics with `Unable to mount root fs`, the `initramfs-cognitive.gz` is likely missing or corrupted. You may need to rebuild it using `initramfs-cognitive/build.sh`.
