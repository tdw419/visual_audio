import re

with open("tools/spatial_rv64i_cpu.py", "r") as f:
    content = f.read()

content = content.replace(
    "def load_program(self, binary_data: bytes, entry_point: int = 0, ram_base: int = 0):",
    "def load_program(self, binary_data: bytes, entry_point: int = 0, ram_base: int = 0, offset: int = 0):"
)
content = content.replace(
    "for d in range(len(linear_arr)):",
    "for i in range(len(linear_arr)):\n            d = i + (offset // 4)"
)
content = content.replace(
    "spatial_arr[idx] = linear_arr[d]",
    "spatial_arr[idx] = linear_arr[i]"
)
content = content.replace(
    "self.queue.write_buffer(self.memory.buffer, 0, spatial_arr.tobytes())",
    "if offset == 0:\n            self.queue.write_buffer(self.memory.buffer, 0, spatial_arr.tobytes())\n        else:\n            # Write element by element is too slow, we must merge! Wait, no, we just merge all segments into one python bytearray first!"
)

# Actually, the best way to load the whole memory is to build a single bytearray first, then call load_program!
