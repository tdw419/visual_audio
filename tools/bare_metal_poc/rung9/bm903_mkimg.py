#!/usr/bin/env python3
"""BM903 step 1: build the raw boot medium.

Layout (from bm903_consts.py / bm903_layout.json):
  LBA 0                    stage1 (MBR, 512 B, 0xAA55 tail)
  LBA 1 .. 1+STAGE2-1      stage2 (padded to STAGE2_SECTORS)
  KERNEL_LBA ..            vmlinuz64.extracted, whole bzImage file
  INITRD_LBA ..            core.gz

Assembly order matters: stage2 must exist before stage1 (both %include the
generated layout header, and stage1's size is fixed at 512 B).
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "bm903_medium.raw"


def nasm(src: str, dst: str) -> bytes:
    r = subprocess.run(["nasm", "-f", "bin", "-o", dst, "-I", str(HERE) + "/",
                        str(HERE / src)], capture_output=True, text=True)
    if r.returncode:
        sys.stderr.write(f"nasm {src} FAILED:\n{r.stderr}{r.stdout}\n")
        raise SystemExit(2)
    if r.stderr.strip():
        sys.stderr.write(f"nasm {src} warnings:\n{r.stderr}\n")
    return Path(dst).read_bytes()


def main() -> int:
    lay = json.loads((HERE / "bm903_layout.json").read_text())
    s2 = nasm("bm903_stage2.asm", "bm903_stage2.bin")
    s1 = nasm("bm903_stage1.asm", "bm903_stage1.bin")
    assert len(s1) == 512, f"stage1 is {len(s1)} B, must be exactly 512"
    assert s1[-2:] == b"\x55\xaa", "stage1 missing 0xAA55 boot signature"
    st2 = lay["stage2_sectors"] * 512
    assert len(s2) == st2, f"stage2 is {len(s2)} B, must be {st2}"
    kern = (HERE / "vmlinuz64.extracted").read_bytes()
    initrd = (HERE.parent / "rung7" / "core.gz").read_bytes()
    assert len(kern) == lay["kernel_bytes"], "kernel size drift vs layout"
    assert len(initrd) == lay["initrd_bytes"], "initrd size drift vs layout"

    img = bytearray((lay["medium_sectors"]) * 512)
    img[0:512] = s1
    img[512:512 + st2] = s2

    def put(lba: int, blob: bytes) -> None:
        off = lba * 512
        img[off:off + len(blob)] = blob
        pad = -len(blob) % 512
        if pad:
            img[off + len(blob):off + len(blob) + pad] = b"\0" * pad

    put(lay["kernel_lba"], kern)
    put(lay["initrd_lba"], initrd)
    OUT.write_bytes(bytes(img))
    print(f"wrote {OUT.name}: {len(img)} B = {len(img)//512} sectors "
          f"(kernel@{lay['kernel_lba']} {len(kern)} B, "
          f"initrd@{lay['initrd_lba']} {len(initrd)} B)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
