# Bare-metal RV64 payload: submit a glyph SHA-256 dispatch and spin until done.
# Linked at 0x80000000. Assembled by tools/rv64i_asm.py (RV64I base + li/j).
#
# Request struct @ 0x81001000 (see glyph_dispatch/docs/ABI.md):
#   +0  flags (BUSY=bit0)   +4  glyph_id
#   +8  input_buf_ptr  (64) +16 input_buf_len  (64)
#   +24 output_buf_ptr (64) +32 output_buf_len (64)
# 64-bit fields written as two 32-bit stores (assembler has no sd); all our
# pointers fit in 32 bits so the high word is zero.
#
# input  buffer @ 0x81002000 : "abc"
# output buffer @ 0x81004000 : 32-byte digest written back by the host

_start:
    # input "abc" -> 0x81002000  (0x00636261 little-endian)
    li   t0, 0x81002000
    li   t1, 0x00636261
    sw   t1, 0(t0)

    li   a0, 0x81001000          # a0 = request struct base

    li   t1, 10                  # glyph_id = GLYPH_ID_SHA256
    sw   t1, 4(a0)

    li   t1, 0x81002000          # input_buf_ptr
    sw   t1, 8(a0)
    sw   zero, 12(a0)
    li   t1, 3                   # input_buf_len
    sw   t1, 16(a0)
    sw   zero, 20(a0)

    li   t1, 0x81004000          # output_buf_ptr
    sw   t1, 24(a0)
    sw   zero, 28(a0)
    li   t1, 32                  # output_buf_len
    sw   t1, 32(a0)
    sw   zero, 36(a0)

    li   t1, 1                   # FLAG_BUSY -- written last
    sw   t1, 0(a0)

    li   t2, 0x88000000          # GLYPH_DISPATCH_TRIGGER
    sw   zero, 0(t2)             # any value; host services the request struct

poll:
    lw   t1, 0(a0)
    andi t1, t1, 1               # BUSY still set?
    bne  t1, zero, poll

    li   t3, 0x11100000          # SYSCON: any write halts the core (halted=1)
    li   t4, 1
    sw   t4, 0(t3)

spin:
    j    spin
