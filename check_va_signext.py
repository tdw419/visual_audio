#!/usr/bin/env python3
"""
Check the exact VA representation stored in the shader
"""
fault_va = 0xffffffc4febfe000
print(f"Fault VA: 0x{fault_va:016x}")
print(f"Fault VA (64-bit): {fault_va:064b}")

# Decode as vec2<u32> (low, high)
va_x = fault_va & 0xFFFFFFFF
va_y = (fault_va >> 32) & 0xFFFFFFFF

print(f"\nAs vec2<u32>:")
print(f"  va.x (low):  0x{va_x:08x} = {va_x:032b}")
print(f"  va.y (high): 0x{va_y:08x} = {va_y:032b}")

# Calculate bit 38 (bit 6 of va.y)
bit38 = (va_y >> 6) & 1
print(f"\nbit38 = (va.y >> 6) & 1 = {bit38}")

# Calculate expected high (bits 6-31 of va.y)
expected_hi = 0x03FFFFFF if bit38 == 1 else 0
print(f"expected_hi = 0x{expected_hi:08x} = {expected_hi:032b}")

# Calculate actual high (va.y >> 6)
actual_hi = va_y >> 6
print(f"actual_hi   = va.y >> 6 = 0x{actual_hi:08x} = {actual_hi:032b}")

# Check if they match
if actual_hi == expected_hi:
    print("\n✓ Sign-extension check passes")
else:
    print(f"\n✗ Sign-extension check FAILS")
    print(f"  Expected 0x{expected_hi:08x}, got 0x{actual_hi:08x}")

# Now show what the GPU shader does
print(f"\nShader computation:")
print(f"  bit38 = (va.y >> 6u) & 1u = {bit38}")
print(f"  expected_hi = select(0u, 0x03FFFFFFu, bit38 == 1u) = 0x{expected_hi:08x}")
print(f"  (va.y >> 6u) = 0x{actual_hi:08x}")
print(f"  (va.y >> 6u) != expected_hi? {actual_hi != expected_hi}")