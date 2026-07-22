import pytest
import numpy as np
from tools.glyph_isa_v2 import OpcodeMapV2, SpatialMisalignmentFault, GlyphCPUv2, GlyphAssemblerV2

def test_opcode_map_collision_avoidance():
    # Create an OpcodeMapV2 and mock its _color_for_word to force collisions
    op_map = OpcodeMapV2()
    # Force 'HALT' to return a reserved color
    op_map._opcode_to_rgb.clear()
    op_map._rgb_to_opcode.clear()
    
    # Mocking
    original_color_for_word = op_map._color_for_word
    def mock_color_for_word(word, opcode):
        if opcode == 'HALT':
            return (0, 0, 0) # Reserved
        if opcode == 'LDI':
            return (0, 0, 1) # Reserved
        if opcode == 'ADD':
            return (5, 5, 5) # Valid
        if opcode == 'SUB':
            return (5, 5, 5) # Collision with ADD!
        return original_color_for_word(word, opcode)
    
    op_map._color_for_word = mock_color_for_word
    op_map._build_maps()
    
    # Assert HALT and LDI got shifted out of reserved space
    assert op_map.opcode_to_rgb('HALT') != (0, 0, 0)
    assert not op_map._is_reserved(op_map.opcode_to_rgb('HALT'))
    
    assert op_map.opcode_to_rgb('LDI') != (0, 0, 1)
    assert not op_map._is_reserved(op_map.opcode_to_rgb('LDI'))
    
    # Assert ADD is (5, 5, 5) and SUB got shifted
    assert op_map.opcode_to_rgb('ADD') == (5, 5, 5)
    assert op_map.opcode_to_rgb('SUB') != (5, 5, 5)
    
    # Assert no two opcodes share the same color
    colors = set(op_map._opcode_to_rgb.values())
    assert len(colors) == len(op_map.OPCODES)
    
    op_map.close()

def test_spatial_misalignment_fault():
    op_map = OpcodeMapV2()
    cpu = GlyphCPUv2(op_map, cols_instrs=8)
    image = np.zeros((1, 8, 3), dtype=np.uint8)
    
    # Valid alignment
    cpu.pc = (4, 0)
    # won't raise fault, but might halt on empty image
    cpu.step(image)
    
    # Invalid alignment
    cpu.pc = (3, 0)
    with pytest.raises(SpatialMisalignmentFault):
        cpu.step(image)
        
    op_map.close()

