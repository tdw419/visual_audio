import numpy as np
import pytest
from tools.glyph_isa_v2 import OpcodeMapV2, GlyphCPUv2, GlyphAssemblerV2
import os

def test_syscall_audio_io(tmp_path):
    wav_path = tmp_path / "test_out.wav"
    path_bytes = str(wav_path).encode('utf-8') + b'\x00'
    
    # 4 bytes of data to encode
    data_bytes = b'\xDE\xAD\xBE\xEF'
    
    op_map = OpcodeMapV2()
    assembler = GlyphAssemblerV2(op_map)
    cpu = GlyphCPUv2(op_map, cols_instrs=32)

    path_addr = 128
    data_addr = 256
    
    program = [
        f"LDI r1 {path_addr}",  # Address of path
        f"LDI r2 {data_addr}",  # Address of data
        f"LDI r3 {len(data_bytes)}", # Length of data
        "LDI r7 8",             # SYSCALL_AUDIO_OUT (8)
        "SYSCALL r0 8",         # Emit audio
        "HALT"
    ]
    
    while len(program) < 32:
        program.append("HALT")
        
    image = assembler.assemble(program, width_instrs=32)
    
    # Pad image for data
    if image.shape[0] < 3:
        pad = np.zeros((3 - image.shape[0], 32 * 4, 3), dtype=np.uint8)
        image = np.vstack([image, pad])
        
    # PATH is data: seed the RAM view (DEFECT-23-ROOT convention). Image-side
    # seeding relied on _read_path's view-merge, retired 2026-09-22
    # (claim-queue item 2 step 2).
    for i, b in enumerate(path_bytes):
        cpu.memory[path_addr + i] = b
        
    # backlog(d)/DEFECT-D handler 4/5 (2026-09-16): AUDIO_OUT (0x08) reads
    # its data arg from RAM (self.memory), not image pixels - file/audio
    # payloads are DATA per the DEFECT-23-ROOT convention. Seed the payload
    # via direct RAM writes (same fix shape handler 3/5 applied to
    # test_glyph_file_io.py). The path stays image-seeded: _read_path's
    # view is untouched by this migration.
    for i, b in enumerate(data_bytes):
        cpu.memory[data_addr + i] = b
        
    cpu.run(image)
    assert not cpu.running
    assert wav_path.exists()
    
    # Now test reading it back
    cpu2 = GlyphCPUv2(op_map, cols_instrs=32)
    program2 = [
        f"LDI r1 {path_addr}",  # Address of path
        f"LDI r2 {data_addr}",  # Address of data
        f"LDI r3 16",           # Max length to read
        "LDI r7 9",             # SYSCALL_AUDIO_IN (9)
        "SYSCALL r0 9",         # Read audio
        "HALT"
    ]
    
    while len(program2) < 32:
        program2.append("HALT")
        
    image2 = assembler.assemble(program2, width_instrs=32)
    
    if image2.shape[0] < 3:
        pad = np.zeros((3 - image2.shape[0], 32 * 4, 3), dtype=np.uint8)
        image2 = np.vstack([image2, pad])
        
    # PATH is data: seed the RAM view for the readback program too
    # (view-merge retired 2026-09-22, claim-queue item 2 step 2).
    for i, b in enumerate(path_bytes):
        cpu2.memory[path_addr + i] = b
    cpu2.run(image2)
    
    # Check that data was read back correctly
    # backlog(d)/DEFECT-D handler 5/5 (2026-09-16): AUDIO_IN (0x09) writes
    # its dest to RAM (self.memory), not image pixels - decoded bytes are
    # DATA per the DEFECT-23-ROOT convention. Read back via direct RAM
    # indexing (same dest-side fix shape handler 2/5 applied to FILE_READ's
    # tests).
    read_bytes = bytearray()
    for i in range(len(data_bytes)):
        read_bytes.append(cpu2.memory[data_addr + i] & 0xFF)
        
    assert bytes(read_bytes) == data_bytes
    op_map.close()
