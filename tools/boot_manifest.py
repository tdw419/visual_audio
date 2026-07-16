#!/usr/bin/env python3
"""
boot_manifest.py — Safe parsing and launching of ["boot", ...] ops.

A boot op is a small manifest that a *signed* utterance can carry to ask the
listener to emulate an OS with QEMU. The OS image itself never travels over the
audio channel (far too slow — see speak.py throughput); the manifest only names
a local image that the operator has already placed in a trusted directory.

Because a decoded audio frame that launches a process is exactly the "Eve"
threat the provenance system defends against, this module is deliberately
narrow and refuses anything it cannot prove safe:

  - the architecture must be on a fixed allowlist (maps to a known qemu binary);
  - the image must be a bare filename (no path separators, no "..") that
    resolves to an existing regular file *inside* the trusted image directory;
  - the qemu command is built as an argv list and never passed through a shell.

The caller (the listener) is responsible for the other half of the gate: it
must only invoke this after the frame's Ed25519 signature has been verified.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional


# arch -> qemu binary + argv template (the image path is appended after "-kernel")
ARCH_QEMU = {
    "riscv64": ("qemu-system-riscv64", ["-nographic", "-machine", "virt", "-kernel"]),
    "x86_64": ("qemu-system-x86_64", ["-nographic", "-kernel"]),
}

# Allowed values for the optional "bios" manifest field. Only these two symbolic
# values are accepted — never an arbitrary path — so the field can't smuggle a
# file into the qemu command line. "default" uses qemu's built-in firmware
# (OpenSBI on riscv virt); "none" passes `-bios none` for kernels that carry
# their own machine-mode boot code (e.g. xv6-riscv).
ALLOWED_BIOS = ("default", "none")


class BootManifestError(ValueError):
    """Raised when a boot op is malformed or fails a safety check."""


def _check_bare_filename(name: str, label: str) -> None:
    """Reject anything that is not a plain filename (no path structure)."""
    if not isinstance(name, str) or not name:
        raise BootManifestError(f"{label} must be a non-empty string")
    if os.path.basename(name) != name or name in (".", ".."):
        raise BootManifestError(f"{label} must be a bare filename, got {name!r}")


@dataclass(frozen=True)
class BootManifest:
    arch: str
    image: str  # bare filename, validated against the image directory later
    bios: str = "default"  # one of ALLOWED_BIOS
    drive: str = None  # optional bare filename attached as a virtio-blk disk


def parse_boot_op(op) -> BootManifest:
    """Parse and structurally validate a boot op.

    Accepts ["boot", arch, image] or, with an options dict,
    ["boot", arch, image, {"bios": "none", "drive": "fs.img"}]. Raises
    BootManifestError on anything that is not a boot op with an allowlisted
    architecture, syntactically safe image/drive names, and (if present) an
    allowlisted bios value.
    """
    if not isinstance(op, (list, tuple)) or len(op) not in (3, 4):
        raise BootManifestError(
            f"boot op must be [\"boot\", arch, image] or [..., opts], got {op!r}"
        )

    kind, arch, image = op[0], op[1], op[2]
    opts = op[3] if len(op) == 4 else {}
    if kind != "boot":
        raise BootManifestError(f"not a boot op: {kind!r}")
    if not isinstance(arch, str) or arch not in ARCH_QEMU:
        raise BootManifestError(
            f"unsupported arch {arch!r} (allowed: {sorted(ARCH_QEMU)})"
        )
    # image and (optional) drive may only name bare files inside the trusted
    # directory, so neither can traverse out or smuggle a path onto the argv.
    _check_bare_filename(image, "image")

    if not isinstance(opts, dict):
        raise BootManifestError(f"boot options must be an object, got {opts!r}")
    unknown = set(opts) - {"bios", "drive"}
    if unknown:
        raise BootManifestError(f"unknown boot options: {sorted(unknown)}")
    bios = opts.get("bios", "default")
    if bios not in ALLOWED_BIOS:
        raise BootManifestError(
            f"bios must be one of {list(ALLOWED_BIOS)}, got {bios!r}"
        )
    drive = opts.get("drive")
    if drive is not None:
        _check_bare_filename(drive, "drive")
        # virtio-mmio disk wiring below is riscv-virt specific.
        if arch != "riscv64":
            raise BootManifestError(f"drive option is only supported for riscv64, not {arch!r}")

    return BootManifest(arch=arch, image=image, bios=bios, drive=drive)


def _resolve_in_dir(name: str, base_dir: str, label: str) -> Path:
    """Resolve a bare filename to a real regular file inside base_dir.

    Defends against traversal even if parse_boot_op is bypassed: the resolved
    path must stay within the resolved base directory and be a regular file.
    """
    base = Path(base_dir).resolve()
    target = (base / name).resolve()
    if base not in target.parents and target != base:
        raise BootManifestError(f"{label} escapes {base}: {target}")
    if not target.is_file():
        raise BootManifestError(f"{label} not found in {base}: {name}")
    return target


def resolve_image(manifest: BootManifest, image_dir: str) -> Path:
    """Resolve the manifest's image to a real file inside image_dir."""
    return _resolve_in_dir(manifest.image, image_dir, "image")


def build_qemu_argv(manifest: BootManifest, image_path: Path,
                    drive_path: Optional[Path] = None) -> List[str]:
    """Build the qemu argv list for a validated manifest and resolved paths."""
    binary, template = ARCH_QEMU[manifest.arch]
    bios = ["-bios", "none"] if manifest.bios == "none" else []
    # template ends with "-kernel"; splice any disk wiring in before it.
    pre_kernel, kernel_flag = template[:-1], template[-1]
    disk = []
    if drive_path is not None:
        disk = [
            "-global", "virtio-mmio.force-legacy=false",
            "-drive", f"file={drive_path},if=none,format=raw,id=x0",
            "-device", "virtio-blk-device,drive=x0,bus=virtio-mmio-bus.0",
        ]
    return [binary, *bios, *pre_kernel, *disk, kernel_flag, str(image_path)]


def launch_boot(
    op,
    image_dir: str,
    dry_run: bool = False,
    runner: Callable[[List[str]], object] = None,
) -> List[str]:
    """Validate a boot op and (optionally) launch qemu.

    Returns the qemu argv that was (or would be) executed. Raises
    BootManifestError if the op fails any safety check. When dry_run is True the
    process is not started — useful for tests and for auditing what a signed
    utterance would do. `runner` defaults to subprocess.Popen and is injectable
    for testing.
    """
    manifest = parse_boot_op(op)
    image_path = resolve_image(manifest, image_dir)
    drive_path = (_resolve_in_dir(manifest.drive, image_dir, "drive")
                  if manifest.drive is not None else None)
    argv = build_qemu_argv(manifest, image_path, drive_path)

    if not dry_run:
        (runner or subprocess.Popen)(argv)

    return argv
