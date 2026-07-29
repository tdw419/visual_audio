import struct
import subprocess

with open("/home/jericho/projects/zion/apps/linux/alpine/alpine-riscv64.lnx.bin", "rb") as f:
    raw = f.read()

kernel_offset = struct.unpack('<I', raw[4:8])[0]
kernel = raw[kernel_offset:]

snippet = kernel[0x1000:0x1060]
with open("tools/snippet3.bin", "wb") as f:
    f.write(snippet)

subprocess.run(["riscv64-linux-gnu-objdump", "-D", "-b", "binary", "-m", "riscv", "tools/snippet3.bin"])
