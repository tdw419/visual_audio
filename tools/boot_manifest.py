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


@dataclass(frozen=True)
class BootManifest:
    arch: str
    image: str  # bare filename, validated against the image directory later
    bios: str = "default"  # one of ALLOWED_BIOS


def parse_boot_op(op) -> BootManifest:
    """Parse and structurally validate a boot op.

    Accepts either ["boot", arch, image] or, with an options dict,
    ["boot", arch, image, {"bios": "none"}]. Raises BootManifestError on
    anything that is not a boot op with an allowlisted architecture, a
    syntactically safe image name, and (if present) an allowlisted bios value.
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
    if not isinstance(image, str) or not image:
        raise BootManifestError("image must be a non-empty string")
    # A manifest may only name a bare file; reject any path structure outright so
    # traversal can't reach outside the trusted image directory.
    if os.path.basename(image) != image or image in (".", ".."):
        raise BootManifestError(f"image must be a bare filename, got {image!r}")

    if not isinstance(opts, dict):
        raise BootManifestError(f"boot options must be an object, got {opts!r}")
    unknown = set(opts) - {"bios"}
    if unknown:
        raise BootManifestError(f"unknown boot options: {sorted(unknown)}")
    bios = opts.get("bios", "default")
    if bios not in ALLOWED_BIOS:
        raise BootManifestError(
            f"bios must be one of {list(ALLOWED_BIOS)}, got {bios!r}"
        )

    return BootManifest(arch=arch, image=image, bios=bios)


def resolve_image(manifest: BootManifest, image_dir: str) -> Path:
    """Resolve the manifest's image to a real file inside image_dir.

    Defends against traversal even if parse_boot_op is bypassed: the resolved
    path must stay within the resolved image directory and be a regular file.
    """
    base = Path(image_dir).resolve()
    target = (base / manifest.image).resolve()
    if base not in target.parents and target != base:
        raise BootManifestError(f"image escapes {base}: {target}")
    if not target.is_file():
        raise BootManifestError(f"image not found in {base}: {manifest.image}")
    return target


def build_qemu_argv(manifest: BootManifest, image_path: Path) -> List[str]:
    """Build the qemu argv list for a validated manifest and resolved image."""
    binary, template = ARCH_QEMU[manifest.arch]
    bios = ["-bios", "none"] if manifest.bios == "none" else []
    return [binary, *bios, *template, str(image_path)]


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
    argv = build_qemu_argv(manifest, image_path)

    if not dry_run:
        (runner or subprocess.Popen)(argv)

    return argv
