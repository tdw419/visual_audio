"""Shared MockGpuRam for dispatch tests -- a flat little-endian byte array with
the same read/write surface GlyphDispatcher expects from the real GpuRam.
"""


class MockGpuRam:
    def __init__(self, size_mb: int = 32, ram_base: int = 0x80000000):
        self.ram_base = ram_base
        self.size = size_mb * 1024 * 1024
        self.memory = bytearray(self.size)

    def _off(self, gpa: int, length: int) -> int:
        if gpa < self.ram_base:
            raise IndexError(f"access below RAM base: 0x{gpa:x} < 0x{self.ram_base:x}")
        end = gpa + length
        if end > self.ram_base + self.size:
            raise IndexError(f"access beyond RAM: [0x{gpa:x}, 0x{end:x})")
        return gpa - self.ram_base

    def read_u32(self, gpa: int) -> int:
        o = self._off(gpa, 4)
        return int.from_bytes(self.memory[o:o + 4], "little")

    def write_u32(self, gpa: int, val: int):
        o = self._off(gpa, 4)
        self.memory[o:o + 4] = (val & 0xFFFFFFFF).to_bytes(4, "little")

    def read_u64(self, gpa: int) -> int:
        o = self._off(gpa, 8)
        return int.from_bytes(self.memory[o:o + 8], "little")

    def write_u64(self, gpa: int, val: int):
        o = self._off(gpa, 8)
        self.memory[o:o + 8] = (val & 0xFFFFFFFFFFFFFFFF).to_bytes(8, "little")

    def read_bytes(self, gpa: int, length: int) -> bytes:
        o = self._off(gpa, length)
        return bytes(self.memory[o:o + length])

    def write_bytes(self, gpa: int, data: bytes):
        o = self._off(gpa, len(data))
        self.memory[o:o + len(data)] = data
