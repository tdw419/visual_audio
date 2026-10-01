# Glyph Dispatch Request Structure Constants
# Used by both RISC-V guest assembly and Host Python dispatcher

# Memory regions
REQUEST_STRUCT_BASE = 0x8100_1000
REQUEST_STRUCT_SIZE = 60  # 48 + reserved[4] * 4 bytes = 60

MMIO_DISPATCH_TRIGGER = 0x8800_0000

# Field offsets (relative to REQUEST_STRUCT_BASE)
OFFSET_FLAGS = 0x00
OFFSET_GLYPH_ID = 0x04
OFFSET_INPUT_BUF_PTR = 0x08
OFFSET_INPUT_BUF_LEN = 0x10
OFFSET_OUTPUT_BUF_PTR = 0x18
OFFSET_OUTPUT_BUF_LEN = 0x20
OFFSET_RESULT_STATUS = 0x28
OFFSET_RESERVED = 0x2C

# Flag bits
FLAG_BUSY = 0x00000001    # Bit 0: 1 = glyph executing, 0 = done
FLAG_ERROR = 0x00000002   # Bit 1: 1 = error occurred
FLAG_RESERVED = 0xFFFFFFF0  # Bits 2-31: reserved

# Result status values
RESULT_SUCCESS = 0
RESULT_ERROR = -1
RESULT_OUTPUT_TOO_SMALL = -2
RESULT_GLYPH_FAILED = -3

# Glyph kernel IDs (registry)
# Phase 1: Test kernels
GLYPH_ID_TEST_COUNTER = 0
GLYPH_ID_TEST_BUFFER_COPY = 1

# Phase 2: Crypto kernels
GLYPH_ID_SHA256 = 10

# Phase 3: eBPF-transpiled kernels (reserved range 0x100-0xFFF)
GLYPH_ID_EBPF_BASE = 0x100

# CPU state struct offsets (for glyph_busy detection)
# These must match the RiscvCPU struct in RISCV_CPU_MMU_dispatch.wgsl
# After existing fields, we add:
#   glyph_busy: u32 at offset ...
#   glyph_last_trigger: u32 at offset ...
#
# Actual offsets will be determined after inspecting the WGSL struct

# Alignment helpers
def is_aligned(addr: int, alignment: int) -> bool:
    """Check if address is aligned to given boundary."""
    return addr % alignment == 0

def assert_aligned(addr: int, alignment: int, name: str):
    """Assert address is aligned, raise ValueError if not."""
    if not is_aligned(addr, alignment):
        raise ValueError(f"{name} (0x{addr:x}) not aligned to {alignment} bytes")

# Validate structure layout
assert_aligned(OFFSET_FLAGS, 4, "FLAGS")
assert_aligned(OFFSET_GLYPH_ID, 4, "GLYPH_ID")
assert_aligned(OFFSET_INPUT_BUF_PTR, 8, "INPUT_BUF_PTR")
assert_aligned(OFFSET_INPUT_BUF_LEN, 8, "INPUT_BUF_LEN")
assert_aligned(OFFSET_OUTPUT_BUF_PTR, 8, "OUTPUT_BUF_PTR")
assert_aligned(OFFSET_OUTPUT_BUF_LEN, 8, "OUTPUT_BUF_LEN")
assert_aligned(OFFSET_RESULT_STATUS, 4, "RESULT_STATUS")
assert_aligned(OFFSET_RESERVED, 4, "RESERVED")

# Validate field sizes
assert (OFFSET_GLYPH_ID - OFFSET_FLAGS) == 4, "GAP between FLAGS and GLYPH_ID"
assert (OFFSET_INPUT_BUF_PTR - OFFSET_GLYPH_ID) == 4, "GAP between GLYPH_ID and INPUT_BUF_PTR"
assert (OFFSET_INPUT_BUF_LEN - OFFSET_INPUT_BUF_PTR) == 8, "GAP between INPUT_BUF_PTR and INPUT_BUF_LEN"
assert (OFFSET_OUTPUT_BUF_PTR - OFFSET_INPUT_BUF_LEN) == 8, "GAP between INPUT_BUF_LEN and OUTPUT_BUF_PTR"
assert (OFFSET_OUTPUT_BUF_LEN - OFFSET_OUTPUT_BUF_PTR) == 8, "GAP between OUTPUT_BUF_PTR and OUTPUT_BUF_LEN"
assert (OFFSET_RESULT_STATUS - OFFSET_OUTPUT_BUF_LEN) == 8, "GAP between OUTPUT_BUF_LEN and RESULT_STATUS"
assert (OFFSET_RESERVED - OFFSET_RESULT_STATUS) == 4, "GAP between RESULT_STATUS and RESERVED"
assert (REQUEST_STRUCT_SIZE - OFFSET_RESERVED) == 16, "GAP after RESERVED"

# Field access helpers for RISC-V guest assembly generation
def generate_guest_request_code(glyph_id: int, input_ptr: int, input_len: int,
                                 output_ptr: int, output_len: int,
                                 req_base: int = REQUEST_STRUCT_BASE,
                                 trigger_base: int = MMIO_DISPATCH_TRIGGER) -> str:
    """Generate RISC-V assembly code to submit a glyph dispatch request.

    Args:
        glyph_id: Glyph kernel identifier
        input_ptr: Guest physical address of input buffer
        input_len: Length of input buffer in bytes
        output_ptr: Guest physical address of output buffer
        output_len: Length of output buffer in bytes
        req_base: Base address of request structure (default: 0x8100_1000)
        trigger_base: MMIO trigger address (default: 0x8800_0000)

    Returns:
        Assembly code as string
    """
    code = f"""# Submit glyph dispatch request for glyph_id={glyph_id}
li a0, 0x{req_base:x}      # a0 = request base

# Set BUSY flag
li t0, 1
sw t0, 0(a0)              # Set BIT0 (BUSY)

# Set glyph_id
li t0, {glyph_id}
sw t0, 4(a0)              # glyph_id at offset 4

# Set input buffer
li t0, 0x{input_ptr:x}
sd t0, 8(a0)              # input_buf_ptr at offset 8
li t0, {input_len}
sd t0, 16(a0)             # input_buf_len at offset 16

# Set output buffer
li t0, 0x{output_ptr:x}
sd t0, 24(a0)             # output_buf_ptr at offset 24
li t0, {output_len}
sd t0, 32(a0)             # output_buf_len at offset 32

# Trigger dispatch
li t0, 0x{trigger_base:x}
sw zero, 0(t0)            # Write any value (zero)

"""
    return code

def generate_guest_poll_code(req_base: int = REQUEST_STRUCT_BASE) -> str:
    """Generate RISC-V assembly code to poll for glyph completion.

    Args:
        req_base: Base address of request structure

    Returns:
        Assembly code as string
    """
    code = f"""# Poll for glyph completion
1:
  lw t1, 0(a0)            # Read flags
  andi t1, t1, 1          # Extract BUSY bit
  bnez t1, 1b             # Loop if BUSY still set

# Check result status
lw t1, 0x28(a0)           # Read result_status
bnez t1, glyph_error     # Non-zero = error

# Output buffer now has result!
# Continue execution...

glyph_error:
  # Handle error (t1 contains result_status)
  # ...

"""
    return code

if __name__ == "__main__":
    # Self-test: generate example code
    print("=== Example: Guest Dispatch Code ===")
    print(generate_guest_request_code(
        glyph_id=GLYPH_ID_SHA256,
        input_ptr=0x8100_2000,
        input_len=10485760,  # 10MB
        output_ptr=0x8100_3000,
        output_len=32
    ))

    print("=== Example: Guest Poll Code ===")
    print(generate_guest_poll_code())