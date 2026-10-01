# BRIEF — R7-TC-1: Tiny Core from a pixel medium (shim-allowed evidence probe)

**Authority:** roadmap row R7-TC-1 (systems/GLYPH_SELF_HOSTING_ROADMAP.md, census table). Queued under POLICY_decision_delegation_20260918.md (D-2). Origin: Jericho 2026-09-18 asked "would it help if we tried to boot xv6, alpine, or tiny core bare metal first?" — measured triage: xv6 = wrong ISA (the ladder is x86/SeaBIOS; the RISC-V xv6 lives on the GPU-emulator side where it already boots to shell), Alpine = requires the deferred protected-mode/long-mode stack, Tiny Core = feasible AT THE SHIM BOUNDARY and therefore valuable as evidence, not as a ladder rung.

**What this is:** boot Tiny Core Linux where the DISK bytes are served by the measured rung-1 pixel machinery (pxc1_nbd_plugin.py + nbdkit over NBD) — SeaBIOS/iPXE fetches the kernel from a medium whose bytes are a pixel stream. The shim is the point: this is the fastest real-OS receipt the existing measured tools can produce, and it must be LABELED as evidence (shim-allowed), never as advancing the loader-side-decode thesis.

**What this is NOT:** no loader-side decode of a 16 MB payload (that is the deferred Path-A-at-scale work); no new primitives in rung1-5 trees (read-only); no ECC; no hardware.

**Steps:**
1. Acquire TinyCore-current.iso (or CorePlus if TinyCore lacks serial console defaults — check; console=ttyS0 is required for the receipt). Record sha256. If no network access, STOP and file a blocker — never substitute or synthesize an image.
2. Medium math (in the receipt): ISO bytes -> raw RGBA medium size at 3 bytes/pixel; whether the rung-1 PNG-wrapper pattern applies or raw is required; measured nbdkit read throughput at ISO scale (dd the kernel+initrd through the NBD path and time it).
3. Boot: QEMU 8.2.2, the pixel-NBD disk, `-serial` captured; kernel args `console=ttyS0`. Success token: the `tc@box` prompt (or `loading extensions...` + userspace reachability if the prompt needs console fiddling).
4. x2 consecutive boots from the same medium byte-identical (rung-2 re-green pattern).
5. Receipt `tools/bare_metal_poc/rung7/RECEIPT_TC_PROBE.md`: console log paths, sha256 pins, medium math table, throughput numbers, and an HONEST BOUNDARY section naming exactly which bytes flowed from pixels (disk reads over NBD) vs host RAM (kernel/initrd already loaded by the bootloader at the moment of boot — say which path the ISO boot actually exercises: if iPXE/SeaBIOS reads the kernel from the NBD disk, disk = pixels; any initrd from host = label it).

**Gate:** the roadmap row's gate cell is authoritative. A measured NO (e.g. TC's loader cannot read from the NBD disk for a named cause) is an acceptable closed outcome with the failure log as the receipt; a silent or partial run is not.

**Escalation:** any blocker that needs a host shim BEYOND nbdkit+plugin, or a non-serial receipt channel, stop and file — do not improvise infrastructure.
