import struct
import subprocess

with open("/home/jericho/projects/zion/apps/linux/alpine/alpine-riscv64.lnx.bin", "rb") as f:
    raw = f.read()

kernel_offset = struct.unpack('<I', raw[4:8])[0]
kernel = raw[kernel_offset:]

snippet = kernel[0x10a0:0x10c0]
with open("tools/snippet2.bin", "wb") as f:
    f.write(snippet)

subprocess.run(["riscv64-linux-gnu-objdump", "-D", "-b", "binary", "-m", "riscv", "tools/snippet2.bin"])
