import struct, sys
from webgpu_compute import Device

# We just want to run the emulator for 50M instructions, but read the PC and RA
# However, boot_xv6_gpu does it well. I will just modify boot_xv6_gpu.py directly!
