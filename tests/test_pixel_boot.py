#!/usr/bin/env python3
"""Boot-on-pixels verification: a kernel stored AS a PNG boots in QEMU.

Uses the committed boot_images/hello.img (S-mode kernel that prints via SBI and
boots under default OpenSBI) so the test always has its fixture and actually runs
in CI — no ephemeral /tmp payload, and the asserted banner matches the kernel.
Chain: hello.img -> dense PNG -> decode -> qemu -kernel -> assert banner.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
KERNEL = ROOT / "boot_images" / "hello.img"
BANNER = "*** HELLO FROM THE SPOKEN KERNEL ***"


def test_pixel_boot_pipeline(tmp_path):
    if shutil.which("qemu-system-riscv64") is None:
        pytest.skip("qemu-system-riscv64 not installed")
    assert KERNEL.exists(), f"committed kernel fixture missing: {KERNEL}"

    png_path = tmp_path / "kernel.png"
    recovered = tmp_path / "recovered.img"

    # Kernel -> PNG -> kernel (the PNG *is* the storage medium).
    subprocess.run(["python3", "tools/dense_encoder.py", "encode", str(KERNEL),
                    "-o", str(png_path)], check=True, cwd=ROOT)
    subprocess.run(["python3", "tools/dense_encoder.py", "decode", str(png_path),
                    "-o", str(recovered)], check=True, cwd=ROOT)
    assert recovered.read_bytes() == KERNEL.read_bytes(), \
        "pixel round-trip is not bit-identical"

    # Boot the pixel-recovered kernel and confirm it actually runs.
    try:
        result = subprocess.run(
            ["qemu-system-riscv64", "-nographic", "-machine", "virt",
             "-kernel", str(recovered)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=6,
        )
        out = result.stdout
    except subprocess.TimeoutExpired as e:
        # The kernel wfi-loops after printing, so a timeout is the normal path.
        out = e.stdout.decode("utf-8", "ignore") if isinstance(e.stdout, bytes) else (e.stdout or "")

    assert BANNER in out, f"kernel did not boot from pixel-recovered ELF; got:\n{out[-500:]}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
