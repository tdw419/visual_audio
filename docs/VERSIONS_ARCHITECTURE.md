# Geometry OS: The Four Spatial Architectures (V1–V4)

**Last Updated:** 2026-08-24
**Topic:** Evolution of the Spatial Boot and Execution Environment

This document traces the evolution of the Geometry OS architecture from its conceptual origins as a visual block device (V1) to a fully self-hosted, GPU-native windowing system booting full desktop operating systems (V4).

---

## 🟢 V1: The MKV Video Block Device (Hyper-Dimensional Storage)
**Theme: "The Screen is the Hard Drive" (Concept Phase)**

V1 proved the foundational concept: software and operating systems could be stored entirely as pixels in a video file without data loss.

*   **Format:** `MKV` container with `FFV1` mathematically lossless video codec.
*   **Architecture:** A host-side daemon (Python/Rust) presented the MKV video as a block device to a QEMU guest over `vhost-user-blk`.
*   **Mechanism:** When the guest kernel requested a disk sector, the host daemon seeked to a specific video frame, decoded the RGB pixels, and applied the inverse Hilbert curve mapping to extract the raw bytes.
*   **Limitations:** Entirely reliant on a host-side daemon. Software decoding was too slow for high-performance interactive workloads.

---

## 🟡 V2: GPU-Accelerated VirtIO Backend (`virtio_pixel_rs_v2`)
**Theme: Performance and Write Persistence**

V2 professionalized the host-to-guest bridge, proving that pixel-based storage could hit near-native speeds.

*   **Format:** MKV/FFV1 and `PXC1` (Pixel Container v1 - PNG sequence).
*   **Architecture:** A native Rust `vhost-user-blk` server running on the host, communicating with QEMU.
*   **Mechanism:** 
    *   **GPU Acceleration:** Shifted the Hilbert curve coordinate calculations and byte-packing to WGSL compute shaders via `wgpu`. Resulted in a 10,000× speedup (121.91ms → 0.08ms per block).
    *   **COW Journaling:** Introduced a Copy-On-Write delta journal to support persistent, high-speed disk writes from the guest back to the visual container.
*   **Limitations:** Still required a host OS (Zion/Linux) to run the backend daemon and translate for QEMU.

---

## 🟠 V3: Native UEFI Spatial Bootloader (`virtio_pixel_rs_v3`)
**Theme: Cutting the Host Cord**

V3 moved the pixel decoding logic directly into the guest VM's boot sequence, eliminating the need for a host-side translation daemon for the boot phase.

*   **Format:** Single PNG Spatial Container (carrying kernel and initramfs).
*   **Architecture:** A native UEFI bootloader (`.efi`) written in Rust, running directly in the guest BIOS/firmware.
*   **Mechanism:**
    *   The UEFI firmware launches the V3 bootloader.
    *   The bootloader locates the PNG container on a standard block device.
    *   It parses the PNG chunks, executes the Hilbert mapping in CPU memory, extracts the ELF64 Linux kernel and initramfs into RAM, constructs the `boot_params`, and hands off execution to the kernel.
*   **Limitations:** The root filesystem still required a traditional block device or network mount to fit larger operating systems.

---

## 🔴 V4: Pixel Database (PDB) & GPU-First Windowing (`v4_bootloader_x86` & `geos_pixel`)
**Theme: Scale, GUI, and Geometric Intelligence**

V4 is the production standard, capable of booting a full 15GB Ubuntu 24.04 Desktop and running native spatial logic on the GPU.

*   **Format:** V4 Pixel Database (PDB). A multi-tile spatial storage architecture (32 massive 4096×4096 PNG tiles acting as a contiguous blob).
*   **Architecture:** 
    *   **V4 Bootloader:** An evolved UEFI bootloader that handles multi-tile PDB sequences, scaling up to extract massive multi-gigabyte root filesystems.
    *   **Spatial Program Coordinator (`geos_pixel`):** A GPU-first windowing system baked directly into the boot crate. 
*   **Mechanism:**
    *   **Boot:** Ubuntu boots to the graphical target entirely from the pixel-encoded V4 container without host passthrough (zero-trust architecture).
    *   **Windowing:** Once booted, the Spatial Desktop runs as a userspace application. Windows are governed by 64-byte Window Control Block (WCB) spatial rows in GPU memory.
    *   **Execution:** Native Glyph Assembly (`.glyph`) instructions are compiled to WGSL and executed by the GPU (Patch-and-Copy execution). Rendering respects Z-order natively from spatial memory, and interactions (click/drag) directly mutate the spatial buffer.

---

### The Future: V5 and Beyond
The current V4 implementation relies on "Visual Bootstrapping" — incubating the Geometry OS GPU-First windowing system on top of a traditional Ubuntu desktop. The next architectural leap will strip away the Ubuntu host OS entirely, running the Spatial Program Coordinator bare-metal on the GPU hardware immediately after the UEFI handoff.
