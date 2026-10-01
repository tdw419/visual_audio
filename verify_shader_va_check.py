#!/usr/bin/env python3
"""
Check how the faulting VA is represented in the shader's vec2<u32> format
"""
fault_va = 0xffffffc4febfe000

# Represent as vec2<u32>
va_x = fault_va & 0xFFFFFFFF
va_y = (fault_va >> 32) & 0xFFFFFFFF

print(f"Full VA: 0x{fault_va:016x}")
print(f"va.x (low 32): 0x{va_x:08x}")
print(f"va.y (high 32): 0x{va_y:08x}")
print()

# The shader checks:
# bit38 = (va.y >> 6u) & 1u
bit38_shader = (va_y >> 6) & 1
print(f"Shader: bit38 = (va.y >> 6) & 1 = {bit38_shader}")

# expected_hi = select(0u, 0x03FFFFFFu, bit38 == 1u)
expected_hi_shader = 0x03FFFFFF if bit38_shader == 1 else 0
print(f"Shader: expected_hi = {expected_hi_shader:08x}")

# (va.y >> 6u) vs expected_hi
va_y_shifted = va_y >> 6
print(f"Shader: (va.y >> 6) = {va_y_shifted:08x}")
print(f"Shader: (va.y >> 6) != expected_hi ? {va_y_shifted != expected_hi_shader}")
print()

# Now check Python interpretation
# bit38 is bit 38 of full VA (bit 6 of va.y is correct)
bit38_full = (fault_va >> 38) & 1
print(f"Python: bit38 = (VA >> 38) & 1 = {bit38_full}")

# bits[39:63] should be all equal to bit38
bits_39_63 = fault_va >> 39
print(f"Python: bits[39:63] = {bits_39_63:08x}")
print(f"Python: bits[39:63] should be all {bit38_full}s")
print(f"Python: Is valid? {bits_39_63 == (0 if bit38_full == 0 else (1 << 25) - 1)}")
print()

# The correct check for Sv39 is: bits[38:63] must be sign-extended from bit 38
# This means bits[39:63] must all equal bit38
expected_bits_39_63 = (1 << 25) - 1 if bit38_full == 1 else 0
print(f"Correct: expected bits[39:63] = 0x{expected_bits_39_63:08x}")
print(f"Correct: actual bits[39:63] = 0x{bits_39_63:08x}")
print(f"Correct: Is valid? {bits_39_63 == expected_bits_39_63}")