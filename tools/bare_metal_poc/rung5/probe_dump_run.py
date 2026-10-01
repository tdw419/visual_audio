#!/usr/bin/env python3
"""Brute-force the scatter fault: compare what the guest DECODED (the dump)
against the medium planes. Guest decoded a payload whose CRC is F8180F11.
The dump printout was suppressed by the CRC refusal (stage1 refuses before
transferring control) - so this run only tells us the CRC. The dump probe
needs a medium whose stage1 EXPECTED_CRC matches the dump image, which
rung4_consts.py already generated (it reads stage2.bin in CWD). So: copy
probe_dump.bin over stage2.bin temporarily? NO - instead generate consts
from probe_dump.bin directly: rung4_consts.py reads stage2.bin, so feed
it via a symlink-free copy and re-run, keeping probe artifacts separate.
"""
import shutil
import subprocess
import sys

shutil.copy("probe_dump.bin", "stage2.bin")
subprocess.run([sys.executable, "rung4_consts.py"], check=True)
subprocess.run(["nasm", "-f", "bin", "stage1.asm", "-o", "stage1.bin"], check=True)
subprocess.run([sys.executable, "rung5_codec.py", "encode", "stage1.bin",
                "probe_dump.bin", "img2.bin", "rung5_probe.png",
                "rung5_probe.raw", "rung5_probe_meta.json"],
               check=True, stdout=subprocess.DEVNULL)
subprocess.run(["timeout", "25", "qemu-system-x86_64",
                "-drive", "file=rung5_probe.raw,format=raw,if=ide",
                "-display", "none", "-no-reboot",
                "-serial", "file:serial_probe_dump.log"], check=False)
print(open("serial_probe_dump.log", "rb").read().decode(errors="replace"))
print("host want: FC FA 31 C0 8E D8 8E C0 8E D0 BC 00 7C FB BA F9 03 30 C0 "
      "EE BA FB 03 B0 80 EE BA F8 03 B0 01 EE BA F9 03 30 C0 EE BA FB 03 B0 "
      "03 EE 8C C8 8E D8 31 F6 B9 40 00 AC 51 88 C4 D0 E8 D0 E8 D0 E8 D0")
