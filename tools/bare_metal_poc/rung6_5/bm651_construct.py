#!/usr/bin/env python3
"""BM651: construct Rung 6.5's loader by DELTA, not by re-typing.

`rung5/stage2.asm` is a read-only, gated artifact (GATE5 PASS x2, rung-5
receipt). Rung 6.5's claim is narrower than a rewrite: the already-verified
image becomes executable, and every byte that is not the new leg must stay
the byte rung 5 measured. So this script reads that file, applies a named
list of textual deltas, asserts each matched EXACTLY ONCE, and writes
`bm651_stage2.asm`; then it UNDOES them newest-first and asserts the result
is byte-identical to the proven source. Anything outside a named block is
therefore the gated text, which is what lets the gate's WRITE=OK / IMG2 CRC /
STAGE2 CKSUM anchors keep meaning "rung 5 still works" instead of "we hope
the fork did not break it".

Two deltas add runtime witness words (`execcbline`, `execnidline`). They are
stored only by the exec leg, which runs strictly AFTER the BM-502 write, so
the marker the guest puts on the medium is unchanged by this fork -- the
rung-5 `expected_marker.py` semantics carry over untouched.

Same discipline for the consts emitter: three deltas add the image path as
argv and emit EXPECTED_EXEC_NID beside the already-proven EXPECTED_IMG2_CRC,
both from the same bytes, so no run can pair one variant's image with
another variant's expectation.

  usage: python3 bm651_construct.py    # writes 2 files, no boots
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNG5 = HERE.parent / 'rung5'

# --------------------------------------------------------------------------
# stage2 deltas
# --------------------------------------------------------------------------
D2 = []

D2.append(('header: name the fork at the top of the proven text',
           '; stage2.asm -- RUNG5 payload: BM-501 second-image read + BM-502 write leg.',
           '; stage2.asm -- RUNG5 payload: BM-501 second-image read + BM-502 write leg.\n'
           ';\n'
           '; RUNG6.5 fork (bm651_construct.py): BM-651 exec-from-data added after\n'
           '; BM-502. Outside the named delta blocks this file is byte-identical to\n'
           '; rung5/stage2.asm.'))

D2.append(('contract: the arg-block table, shared by name with bm651_img2.asm',
           'COM1 equ 0x3F8',
           'COM1 equ 0x3F8\n'
           '\n'
           '; ---- BM-651 exec-from-data contract ---------------------------\n'
           '; The offsets below are the wire format between this loader and the\n'
           '; image it jumps into. bm651_img2.py parses the same table out of\n'
           '; bm651_img2.asm and refuses the build if the two texts disagree --\n'
           '; the contract is checked as text, not assumed as a comment.\n'
           'EXEC_MAILBOX equ 0x4B4F          ; "I finished", in the image\'s words\n'
           'ARG_LEN  equ 0                   ; image length in bytes\n'
           'ARG_LBA  equ 2                   ; where those bytes came from\n'
           'ARG_COM  equ 4                   ; the only I/O port promised\n'
           'ARG_CS   equ 6                   ; segment the image executes in\n'
           'ARG_NID  equ 8                   ; 16-bit identity of this image\n'
           'ARG_MBOX equ 10                  ; image writes EXEC_MAILBOX here\n'
           'ARG_ECHO equ 12                  ; image writes ARG_NID back here\n'
           'EXEC_ARGS equ IMG2_LEN * 2       ; first offset above BOTH image\n'
           '                                 ; windows: neither the copy-down\n'
           '                                 ; nor the image can reach it'))

D2.append(('BM-651 leg: jump into the verified image, between the write and the halt',
           """    mov si, msg3
    call puts
.halt:""",
           """    mov si, msg3
    call puts

    ; =============== BM-651: exec-from-data (RUNG6.5) =====================
    ; The image that the CRC gate just accepted is DATA until this line
    ; jumps into it. Ordering is load-bearing three times over:
    ;   * strictly after .img2_ok -- a corrupt image can never be reached.
    ;     The gate's RED-CRC leg proves that by name rather than trusting
    ;     the order.
    ;   * strictly after the BM-502 write, because the copy-down below
    ;     overwrites IMG2_SEG:[0,IMG2_LEN), which is the write leg's bounce
    ;     buffer. By then the medium already holds those bytes.
    ;   * after the self receipt, so CKSUM is computed over the same payload
    ;     rung 5 measured and the EXEC verdict is the last thing the loader
    ;     says.
    ; Copy-down: src [IMG2_LEN,2*IMG2_LEN) -> dst [0,IMG2_LEN). R-SCOPE-5:
    ; the design review's "full overlap, copy backward" hazard assumed an
    ; in-place move. The windows are DISJOINT, so a forward rep movsw is
    ; correct, and DF is already 0 (the write leg's own forward rep movsw
    ; above is the measured proof). cld anyway: this leg must not inherit
    ; a flag from a neighbour.
    ; IF=0 across the handover (R-SCOPE-3): the image owns no IDT
    ; discipline, and a timer tick landing inside it would be blamed on the
    ; claim under test. Nothing re-enables interrupts; the loader halts on
    ; every path from here.
    cli
    push ds
    push es
    mov ax, IMG2_SEG
    mov ds, ax
    mov es, ax
    mov word [es:EXEC_ARGS + ARG_LEN], IMG2_LEN
    mov word [es:EXEC_ARGS + ARG_LBA], IMG2_BASE_LBA
    mov word [es:EXEC_ARGS + ARG_COM], COM1
    mov word [es:EXEC_ARGS + ARG_CS], IMG2_SEG
    mov word [es:EXEC_ARGS + ARG_NID], EXPECTED_EXEC_NID
    mov word [es:EXEC_ARGS + ARG_MBOX], 0
    mov word [es:EXEC_ARGS + ARG_ECHO], 0
    mov si, IMG2_LEN
    xor di, di
    mov cx, IMG2_LEN/2
    cld
    rep movsw
    mov si, EXEC_ARGS              ; the image finds its args in ES:SI
    call IMG2_SEG:0                ; FAR call (9A): pushes DST_SEG:.back for
                                   ; the image's retf to pop. R-SCOPE-6: the
                                   ; first build copied stage1's
                                   ; push-seg/push-off/retf idiom here, but
                                   ; that idiom is a far JUMP with no return
                                   ; -- so the retf came back to
                                   ; IMG2_SEG:.back, inside the image's own
                                   ; bytes (measured 2026-09-20: two banners
                                   ; and serial garbage where EXEC=OK belongs)
.back:
    ; ONE store per witness, both paths read it back (DEFECT-R5WITNESS:
    ; push/pop pairing across branches let a witness pop consume the value
    ; and print stack garbage). ES is still IMG2_SEG -- retf restores only
    ; CS:IP -- so the reads come first and the segment restores after.
    mov ax, [es:EXEC_ARGS + ARG_MBOX]
    mov dx, [es:EXEC_ARGS + ARG_ECHO]
    pop es
    pop ds
    mov [execcbline], ax
    mov [execnidline], dx
    cmp ax, EXEC_MAILBOX
    jne .exec_badmbx               ; did it finish, per the contract?
    cmp dx, EXPECTED_EXEC_NID
    jne .exec_nobanner             ; did it run, and run as THIS image?
    mov si, msg_execok
    call puts
    jmp halt                       ; the refusals below are fall-through
                                   ; neighbours, so green needs its own exit
.exec_badmbx:
    mov si, msg_badmbx             ; computed first, then expected:
    call puts                      ; rung-4 DEFECT-R4PRINT
    mov ax, [execcbline]
    call puthex4
    mov si, msg_img2exp
    call puts
    mov ax, EXEC_MAILBOX
    call puthex4
    mov si, msg_crlf
    call puts
    jmp halt
.exec_nobanner:
    mov si, msg_nobanner
    call puts
    mov ax, [execnidline]
    call puthex4
    mov si, msg_img2exp
    call puts
    mov ax, EXPECTED_EXEC_NID
    call puthex4
    mov si, msg_crlf
    call puts
    jmp halt
.halt:"""))

D2.append(('strings: the two refusal labels and the verdict',
           'msg_crlf        db 13, 10, 0',
           'msg_crlf        db 13, 10, 0\n'
           'msg_execok      db \'EXEC=OK\', 13, 10, 0\n'
           'msg_badmbx      db \'EXEC=BAD-MAILBOX \', 0\n'
           'msg_nobanner    db \'EXEC=NO-BANNER \', 0'))

D2.append(('witness words: stored only by the exec leg, after the write',
           """img2crcline: dd 0
img2sumline: dw 0""",
           """img2crcline: dd 0
img2sumline: dw 0
execcbline:  dw 0                  ; BM-651: mailbox word the image left
execnidline: dw 0                  ; BM-651: NID word the image echoed"""))

# --------------------------------------------------------------------------
# consts deltas
# --------------------------------------------------------------------------
DC = []

DC.append(('docstring: which rung this emitter feeds',
           'Reads rung5_layout.inc (from rung5_layout.py) + img2.bin (the second\n'
           'image, whose CRC the guest must reproduce) and prints a single\n'
           '-D flag string. Keep IMG2_LEN in sync with rung5_codec.py.',
           'Reads rung5_layout.inc (from rung5_layout.py) + the second image\n'
           '(argv[2], default img2.bin), whose CRC the guest must reproduce, and\n'
           'prints a single -D flag string. Keep IMG2_LEN in sync with\n'
           'rung5_codec.py.\n\n'
           'BM651 addition: EXPECTED_EXEC_NID, a 16-bit fold of the SAME CRC the\n'
           'CRC gate checks, handed to the image and required back. One source of\n'
           'truth for both defines, so a variant image and a mismatching NID\n'
           'expectation cannot be paired by accident.'))

DC.append(('image path: argv, so one emitter builds every variant',
           'img2 = open("img2.bin", "rb").read()',
           'IMG2 = sys.argv[2] if len(sys.argv) > 2 else "img2.bin"\n'
           'img2 = open(IMG2, "rb").read()'))

DC.append(('emit EXPECTED_EXEC_NID beside EXPECTED_IMG2_CRC',
           '         f"-DEXPECTED_IMG2_CRC=0x{zlib.crc32(img2) & 0xFFFFFFFF:08X} "\n',
           '         f"-DEXPECTED_IMG2_CRC=0x{crc:08X} "\n'
           '         f"-DEXPECTED_EXEC_NID=0x{nid:04X} "\n'))

DC.append(('derive crc/nid once',
           'flags = (f"-DRUNG4_SCALE={int(sys.argv[1])} "',
           'crc = zlib.crc32(img2) & 0xFFFFFFFF\n'
           'nid = ((crc & 0xFFFF) ^ (crc >> 16)) & 0xFFFF\n'
           'flags = (f"-DRUNG4_SCALE={int(sys.argv[1])} "'))

# --------------------------------------------------------------------------
def apply(text, deltas, what):
    for name, old, new in deltas:
        n = text.count(old)
        assert n == 1, f'{what}: delta "{name}" matched {n} times, want exactly 1'
        text = text.replace(old, new, 1)
    return text


def round_trip(text, deltas, what):
    for name, old, new in reversed(deltas):
        n = text.count(new)
        assert n == 1, f'{what}: undo "{name}" found {n} copies of its own text'
        text = text.replace(new, old, 1)
    return text


def main() -> int:
    s2src = (RUNG5 / 'stage2.asm').read_text()
    s2 = apply(s2src, D2, 'stage2')
    assert round_trip(s2, D2, 'stage2') == s2src, 'stage2 deltas are not invertible'

    csrc = (RUNG5 / 'rung5_consts.py').read_text()
    con = apply(csrc, DC, 'consts')
    assert round_trip(con, DC, 'consts') == csrc, 'consts deltas are not invertible'

    (HERE / 'bm651_stage2.asm').write_text(s2)
    (HERE / 'bm651_consts.py').write_text(con)

    print(f'stage2: {len(D2)} deltas, {len(s2src):,} B proven text -> '
          f'{len(s2):,} B ({len(s2) - len(s2src):+,} B)')
    for name, old, new in D2:
        print(f'  +{len(new) - len(old):>5} B  {name}')
    print(f'consts: {len(DC)} deltas, {len(csrc):,} B -> {len(con):,} B')
    for name, old, new in DC:
        print(f'  +{len(new) - len(old):>5} B  {name}')
    print('round-trip: undoing every delta newest-first reproduces '
          'rung5/stage2.asm and rung5/rung5_consts.py byte-for-byte')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
