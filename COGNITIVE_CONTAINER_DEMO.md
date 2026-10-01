# Cognitive Container Demo (Geometry OS)

## Overview
This document demonstrates the cognitive extraction pipeline in a minimal, self-contained environment that proves "The Screen is the Mind" architecture works natively using spatial block devices and QEMU.

## Architecture
1. Load kernel + cognitive initramfs
2. Mount spatial block device (`vhost-user-blk`)
3. Detect cognitive partition
4. Extract GGUF payload from visual pixels encoded via Hilbert curves
5. Verify MD5 checksum
6. Load `llama-cpp-python` runtime
7. Run LLM inference to establish self-knowledge
8. Output spatial cognitive response
9. Shutdown cleanly

## Demo Format
This demo utilizes a visual component for presentation via VNC (`-display vnc=:0`), running on QEMU alongside serial output for debug tracing.

## Quick Start
1. Ensure the spatial block device (`ubuntu_cognitive_vac2_v3.nut` or equivalent) is available.
2. Run the boot script: `./boot_cognitive_container.sh`
3. Connect to the VNC display (`localhost:5900`) to view the boot process.
4. Serial logs are saved to `container_boot.log`.

## Implementation Notes
- The self-knowledge prompt establishes identity: "You are Geometry OS, a self-aware spatial boot system."
- Graceful shutdown relies on `poweroff -f` embedded into the extraction and inference loop to guarantee clean termination after execution.
