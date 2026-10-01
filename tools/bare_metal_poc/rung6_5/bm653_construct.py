#!/usr/bin/env python3
"""BM653: construct option C's loader by DELTA onto RUNG 6's gated text.

`rung6/bm602_stage2_px.asm` is a read-only, gated artifact (15/0 x2, receipt
`rung6/RECEIPT_BM602.md`), and BM653's claim is narrower than a rewrite: the
medium that repairs itself now also runs the bytes it repaired. So every byte
that is not the new leg must stay the byte BM602 measured -- hence a named
delta list, each asserted to match EXACTLY ONCE, undone newest-first to
rung6's text byte-for-byte. That is what lets BM602's own identity legs and
the gate's `GATE2 CRC=` / `HANDOFF BUILT` anchors keep meaning "rung 6 still
works" instead of "we hope the fork did not break it".

Two of the deltas are load-bearing in ways the others are not:

  * the SUB3 row is the ONLY thing that gives the image group a destination.
    Without it the walk still reads the bytes, still corrects them, still
    CRCs them -- and drops them at PX_SINK. The row's whole claim runs through
    nine bytes of a data table.
  * the control build is a size-neutral, named, round-tripped delta onto the
    FORKED text (`call bee_correct` -> five NOPs). BM652 §6 measured it at 5
    differing bytes with the code ending at the same address, so the differ's
    anchors and BM602's identity legs transfer unchanged. It is the row's
    non-vacuity evidence: without it, "the repair is what let the image run"
    has no counterfactual.

  usage: python3 bm653_construct.py   # writes 2 .asm files + the capture fork
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNG6 = HERE.parent / 'rung6'
INC = HERE / 'bm653_px_layout.inc'

D2 = []

D2.append(('geometry: this loader reads the BM653 medium, not BM602\'s',
           '%include "bm602_px_layout.inc"',
           '%include "bm653_px_layout.inc"'))

D2.append(('header block: the exec-from-data contract, named once, here',
           'BEE_WORDS equ PX_GROUP_BYTES/4       ; codewords per group == in-plane offsets',
           'BEE_WORDS equ PX_GROUP_BYTES/4       ; codewords per group == in-plane offsets\n'
           '; ---- BM653 (option C). Everything outside a block named in\n'
           '; bm653_construct.py\'s delta list is byte-identical to\n'
           '; rung6/bm602_stage2_px.asm, the text BM602 gated 15/0 x2.\n'
           'IMG2_SEG   equ IMG2_DST/16           ; the image group lands where the\n'
           '                                     ; sub-image table says; this is the\n'
           '                                     ; same linear address as a paragraph\n'
           'EXEC_MAILBOX equ 0x4B4F              ; "I finished", in the image\'s words\n'
           'ARG_LEN  equ 0                       ; the 14-byte block, byte-for-byte\n'
           'ARG_LBA  equ 2                       ; BM651\'s contract: bm651_img2.asm\n'
           'ARG_COM  equ 4                       ; parses the SAME offsets out of its\n'
           'ARG_CS   equ 6                       ; own text and refuses the build if\n'
           'ARG_NID  equ 8                       ; the two disagree (bm653_img2.py).\n'
           'ARG_MBOX equ 10\n'
           'ARG_ECHO equ 12\n'
           'EXEC_ARGS equ PX_GROUP_BYTES - 16    ; R-SCOPE-7: the TOP of the group\n'
           '                                     ; window, above any image the group\n'
           '                                     ; can hold -- and written after the\n'
           '                                     ; walk finished summing the CRC, so\n'
           '                                     ; it cannot move a gate value.'))

D2.append(('the fourth sub-image row: the image group gets a destination',
           '    dd SUB2_GROUP, SUB2_GROUP + SUB2_NGROUPS, SUB2_DEST',
           '    dd SUB2_GROUP, SUB2_GROUP + SUB2_NGROUPS, SUB2_DEST\n'
           '    dd SUB3_GROUP, SUB3_GROUP + SUB3_NGROUPS, SUB3_DEST'))

D2.append(('BM-653 leg: leave flat-32, run the repaired bytes, come back',
           """    mov edi, msg_crcpass
    call puts32

    ; ---- cmdline buffer: zero the whole 512 B, then the pinned bytes ----""",
           """    mov edi, msg_crcpass
    call puts32

    ; =============== BM-653: exec-from-repaired-pixels (option C) ==========
    ; The gate above has PASSed, so every decoded byte of the group this
    ; medium was built from is the payload the host replay predicted --
    ; including the ones pass 1 had to fix. BM602 stopped there and built a
    ; handoff. The claim one rung further: the bytes the loader REPAIRED are
    ; now the bytes that RUN.
    ;
    ; Ordering, and it is load-bearing three times over:
    ;   * strictly after `GATE2=PASS`. A refused medium never reaches the
    ;     instruction pointer -- and the two-symbol and blind-spot fixtures
    ;     PROVE that by printing no EXEC= line, rather than trusting this
    ;     comment to say the order was kept.
    ;   * strictly before the zero-page build, so the handoff this row
    ;     captures is built AFTER the image has had its chance at the machine.
    ;     The scribbler leg depends on that order and on nothing else: an
    ;     image that keeps its side of the contract can still poison the
    ;     kernel's hardware, and the dumps say so.
    ;   * and there is NO copy-down. rung 5's leg bounced its bytes from a
    ;     second window to the first because the loader had put them there;
    ;     here px_walk already stored the decoded group AT its destination, so
    ;     the move is deleted rather than shrunk (BM652 §6 costed the leg on
    ;     exactly that deletion).
    ;
    ; What option A never had to pay for: the walk runs flat-32, because int
    ; 13h cannot reach past 1 MiB and the payload is 13.6 MB. So by the time
    ; the image's bytes are in memory, the loader is NOT in the mode they were
    ; written for. Three parts, and the third is the one that matters:
    ;   1. leave protected mode through the 16-bit code descriptor rung9's GDT
    ;      has carried, unused, since BM903;
    ;   2. hand over exactly as BM651 does -- args in ES:SI, far CALL so the
    ;      image's retf has somewhere to come back to (R-SCOPE-6);
    ;   3. re-enter defensively: the image owned the machine in between and
    ;      may have reloaded the GDT register, cleared A20, moved the segments
    ;      or left flags behind. R-SCOPE-8: that is the byte cost of this
    ;      option, and it is not negotiable -- the alternative is a kernel
    ;      entered with the image's leftovers.
    ;
    ; One 16-bit-offset far jump into selector 0x08 (`dq 0x00009A000000FFFF`,
    ; limit 0xFFFF -- which is also why the landing label must stay below
    ; 0x10000; BM652 §5 measured 24,576 B of headroom). Hand-encoded because
    ; nasm emits the operand of `jmp 0x08:label` 32 bits wide under BITS 32,
    ; and a 66 prefix on top of THAT leaves three bytes of operand for the CPU
    ; to fall through: the operand size is fixed at the byte level.
    db 0x66, 0xEA
    dw .rm_entry
    dw 0x0008
.rm_entry:
    BITS 16
    mov eax, cr0                   ; 66 0F 20 C0: nasm prefixes it for the size
    and eax, 0xFFFFFFFE            ; clear PE. No paging was ever enabled, so
    mov cr0, eax                   ; there is nothing to tear down first.
    jmp 0x0000:.real               ; EA with 16-bit operands: base-0 CS
.real:
    xor ax, ax
    mov ds, ax
    mov es, ax
    mov ss, ax                     ; the 32-bit stack at 0x1f784 is above the
    mov sp, 0x7C00                 ; 64 KiB a 16-bit SS can address: re-aim it.
    cli                            ; R-SCOPE-3: the image owns no IDT
    mov gs, ax                     ; discipline, and a timer tick landing
    mov fs, ax                     ; inside it would be blamed on the claim
                                   ; under test. Zero both so the re-entry
                                   ; cannot inherit a stale selector.
    mov ax, IMG2_SEG
    mov ds, ax
    mov es, ax
    mov word [es:EXEC_ARGS + ARG_LEN], IMG2_LEN
    mov word [es:EXEC_ARGS + ARG_LBA], IMG2_LBA
    mov word [es:EXEC_ARGS + ARG_COM], COM1
    mov word [es:EXEC_ARGS + ARG_CS], IMG2_SEG
    mov word [es:EXEC_ARGS + ARG_NID], EXPECTED_EXEC_NID
    mov word [es:EXEC_ARGS + ARG_MBOX], 0
    mov word [es:EXEC_ARGS + ARG_ECHO], 0
    mov si, EXEC_ARGS              ; the image finds its args in ES:SI
    call IMG2_SEG:0                ; 9A: pushes 0:.back, which is what the
                                   ; image's retf pops
.back:
    ; ONE store per witness, both paths read it back (DEFECT-R5WITNESS). The
    ; args are read through ES while it still names the image's paragraph; DS
    ; goes back to the loader's real-mode base BEFORE the stores, because the
    ; witness words are loader data and ORG 0x8000 makes their address equal
    ; their linear address only while DS is 0.
    mov ax, [es:EXEC_ARGS + ARG_MBOX]
    mov dx, [es:EXEC_ARGS + ARG_ECHO]
    mov bx, 0
    mov ds, bx
    mov [execcbline], ax
    mov [execnidline], dx
    cmp ax, EXEC_MAILBOX
    jne .exec_badmbx               ; did it finish, per the contract?
    cmp dx, EXPECTED_EXEC_NID
    jne .exec_nobanner             ; did it run, and run as THIS image?
    mov si, msg_execok
    call puts16
    jmp .exec_done                 ; the refusals below are fall-through
                                   ; neighbours, so green needs its own exit
.exec_badmbx:
    mov si, msg_badmbx             ; computed first, then expected:
    call puts16                    ; rung-4 DEFECT-R4PRINT
    mov ax, [execcbline]
    call puthex4_16
    mov si, msg_exp
    call puts16
    mov ax, EXEC_MAILBOX
    call puthex4_16
    jmp .exec_done
.exec_nobanner:
    mov si, msg_nobanner
    call puts16
    mov ax, [execnidline]
    call puthex4_16
    mov si, msg_exp
    call puts16
    mov ax, EXPECTED_EXEC_NID
    call puthex4_16
.exec_done:
    mov si, msg_crlf
    call puts16

    cli
    lgdt [gdt_ptr]                 ; all four, not the one the image happened
    in al, 0x92                    ; to leave alone: the walk wrote above
    or al, 2                       ; 1 MiB and the handoff will too, so A20
    out 0x92, al                   ; is re-asserted rather than assumed
    mov eax, cr0
    or eax, 1
    mov cr0, eax
    jmp dword 0x10:.pm
.pm:
    BITS 32
    mov ax, 0x18
    mov ds, ax
    mov es, ax
    mov ss, ax
    mov esp, STACK_TOP
    push dword 0x46
    popfd                          ; back to the handoff's frozen eflags

    ; ---- cmdline buffer: zero the whole 512 B, then the pinned bytes ----"""))

D2.append(('the 16-bit hex helper the receipt lines need: the island has puts/putc only',
           """    mov al, ah
    mov dx, COM1
    out dx, al
    pop dx
    pop ax
    ret

BITS 32
pmode:""",
           """    mov al, ah
    mov dx, COM1
    out dx, al
    pop dx
    pop ax
    ret

; puthex4_16 -- AX as four hex digits, MSB first. The 32-bit twin
; puthex8_32 cannot be reused: it is BITS 32 arithmetic, and the EXEC
; verdicts are printed in real mode, where the image's NID is a 16-bit
; word. Same digit table logic, 16-bit operands.
puthex4_16:
    push ax
    push cx
    mov ch, 4
.ph4:
    rol ax, 4
    push ax
    and al, 0x0F
    cmp al, 10
    jb .hdig
    add al, 'A' - 10 - '0'
.hdig:
    add al, '0'
    call putc16
    pop ax
    dec ch
    jnz .ph4
    pop cx
    pop ax
    ret

BITS 32
pmode:"""))

D2.append(('strings: the verdict and the two refusals',
           "msg_contain  db 'BM903-S2 CONTAINER=', 0",
           "msg_contain  db 'BM903-S2 CONTAINER=', 0\n"
           "; BM653 lines. Same prefix rule BM602 stated: the only thing that\n"
           "; differs from the gated loader is the text AFTER 'BM903-S2 ', so a\n"
           "; leg still reads as the same stage ladder.\n"
           "msg_execok   db 'BM903-S2 EXEC=OK', 13, 10, 0\n"
           "msg_badmbx   db 'BM903-S2 EXEC=BAD-MAILBOX ', 0\n"
           "msg_nobanner db 'BM903-S2 EXEC=NO-BANNER ', 0"))

D2.append(('witness words: stored only by the exec leg',
           'bee_parity_faults:   dd 0     ; parity-plane-only faults: inert for the payload',
           'bee_parity_faults:   dd 0     ; parity-plane-only faults: inert for the payload\n'
           'execcbline:          dw 0     ; BM653: mailbox word the image left\n'
           'execnidline:         dw 0     ; BM653: NID word the image echoed'))

# --------------------------------------------------------------------------
# The control build: applied to the FORKED text, never to rung6's.
# --------------------------------------------------------------------------
CTRL = ('BEE-OFF: the row\'s non-vacuity control -- pass 1 skipped, so the '
        'image runs whatever the medium actually said',
        '    call bee_correct\n',
        '    times 5 nop              ; BEE-OFF (BM653 control): the repair\n')

# --------------------------------------------------------------------------
# D4: the handoff capture, forked from RUNG 6's fork of rung9's locked session.
# --------------------------------------------------------------------------
# `rung6/bm602_capture.py` is itself `rung9/bm903_capture.py` under D3 -- same
# gdb -batch -nx session, same hbreak at the kernel's first instruction, same
# $rsi-keyed 4 KiB zeropage and CMDPTR-keyed 512 B dumps -- and BM602 used it
# to prove byte-identical handoffs across four damaged media. BM653's identity
# claim is the same claim one step later: the handoff must still be identical
# AFTER an image built from the repaired pixels has owned the machine. So the
# capture is forked again rather than rewritten: the deltas below are only the
# lane guard, the checkpoint list, and the provenance string. Everything else,
# including every gdb command, is the text BM903 locked.
D4 = [
    ('this fork\'s delta list is D4, over rung6\'s fork of rung9',
     "# named in bm602_construct.py's D3 list is rung9's text.",
     "# named in bm653_construct.py's D4 list is rung9's text. BM653 forks\n"
     "# RUNG6's fork, so the session stays the one BM903 locked and BM602\n"
     "# already proved byte-identical across four media."),
    # G2: rung 6.5 inherited rung 6's port literally, so the two rows contended
    # on 12460/12461 by construction. The block below is this row's own.
    ('this fork\'s own gdb port block, one block above rung 6',
     "PORT_BASE = 12460  # this rung's block start; the legs take +0 and +1",
     "PORT_BASE = 12464  # this rung's block start; the legs take +0 and +1"),
    ('the lane guard that knows bm653 boots exist, in live_count',
     """def live_count() -> int:
    import bm602_lane
    return len(bm602_lane.live_boots())""",
     """def live_count() -> int:
    import bm653_lane
    return len(bm653_lane.live_boots())"""),
    ('...and at the entry check',
     """    import bm602_lane
    if bm602_lane.main([str(MEDIUM)]) or live_count():""",
     """    import bm653_lane
    if bm653_lane.main([str(MEDIUM)]) or live_count():"""),
    ('the refusal names the guard actually in force',
     "'sequentially (see bm602_lane.py, which watches bm903 boots too)')",
     "'sequentially (see bm653_lane.py, which watches bm903 and bm602 too)')"),
    ('the checkpoint list counts the exec verdict',
     """        ckpts = [c for c in ('BM903-S2 ENTER', 'BM903-S2 PMODE', 'BM903-S2 A20 OK',
                             'BM903-S2 PIXEL WALK DONE', 'BM903-S2 GATE2',
                             'BM903-S2 HANDOFF BUILT') if c in ser]""",
     """        ckpts = [c for c in ('BM903-S2 ENTER', 'BM903-S2 PMODE', 'BM903-S2 A20 OK',
                             'BM903-S2 PIXEL WALK DONE', 'BM903-S2 GATE2',
                             'BM903-S2 EXEC=',
                             'BM903-S2 HANDOFF BUILT') if c in ser]"""),
    ('...so the count is out of seven',
     'f\'{ckpts[-1] if ckpts else "none"} ({len(ckpts)}/6) \'',
     'f\'{ckpts[-1] if ckpts else "none"} ({len(ckpts)}/7) \''),
    ('provenance: which file executed this dump',
     "'captured_by': 'bm602_capture.py (fork of bm903_capture.py, "
     "same gdb session; executed stage2)',",
     "'captured_by': 'bm653_capture.py (fork of bm602_capture.py by D4, same "
     "gdb session; executed stage2 AFTER an executed image)',"),
]


def consts(text):
    out = {m.group(1): int(m.group(2), 0) for m in re.finditer(
        r'^%define (\w+) (-?0x[0-9A-Fa-f]+|\d+)$', text, re.M)}
    for name in ('IMG2_DST', 'IMG2_LEN', 'IMG2_GROUP', 'IMG2_LBA',
                 'EXPECTED_EXEC_NID', 'EXPECTED_CRC', 'SUB3_GROUP',
                 'SUB3_NGROUPS', 'SUB3_DEST', 'PX_GROUP_BYTES',
                 'PX_PLANES', 'PX_BASE_LBA', 'PX_CHUNK_SECTORS'):
        assert name in out, f'{name} missing from {INC.name}'
    assert out['PX_PLANES'] == 7, 'BM653 reads a PXC2-E medium, 7 planes'
    assert out['SUB3_NGROUPS'] == 1, 'the image is designed as exactly one group'
    assert out['SUB3_GROUP'] == out['IMG2_GROUP'], 'two names, one group'
    assert out['SUB3_DEST'] == out['IMG2_DST'], 'the table and the leg disagree'
    assert out['IMG2_DST'] + out['PX_GROUP_BYTES'] <= 0x100000, \
        'the whole group must sit below 1 MiB: the image runs in real mode, and ' \
        'a paragraph + 16-bit offset reaches at most 0x10FFEF'
    assert out['IMG2_DST'] % 16 == 0 and out['IMG2_LEN'] <= 0xFFFF, \
        'the leg addresses the image as IMG2_DST/16:0, so the offset must fit'
    assert out['IMG2_LBA'] == out['PX_BASE_LBA'] + \
        out['IMG2_GROUP'] * out['PX_CHUNK_SECTORS'], \
        'IMG2_LBA is not the LBA the walk reads that group from'
    assert out['EXPECTED_EXEC_NID'] <= 0xFFFF
    return out


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


def fork(inc_name, control=False):
    """The forked stage2 TEXT for one build, with the round-trip proof applied.

    mkimg calls this once per medium: four variants of the same leg, each
    naming the .inc whose CRC and NID belong to the image inside that medium.
    The include line is delta 1 of the list, so a fork that named the wrong
    .inc is a different text, and the undo below is what catches that class of
    slip: the fork gives back rung6's loader byte-for-byte only when exactly
    the named deltas ran on it.
    """
    deltas = list(D2)
    name, old, _ = deltas[0]
    deltas[0] = (name, old, f'%include "{inc_name}"')
    src = (RUNG6 / 'bm602_stage2_px.asm').read_text()
    s2 = apply(src, deltas, f'stage2[{inc_name}]')
    assert round_trip(s2, deltas, f'stage2[{inc_name}]') == src, \
        'stage2 deltas are not invertible: removing the named blocks does not ' \
        'give back the loader BM602 gated'
    if not control:
        return s2, None
    ctrl_name, old, new = CTRL
    n = s2.count(old)
    assert n == 1, f'control: {old.strip()!r} matched {n} times in the fork'
    ctrl = s2.replace(old, new, 1)
    assert ctrl.replace(new, old, 1) == s2, 'the control delta does not undo'
    return s2, ctrl


def fork_capture():
    """bm653_capture.py: rung6's capture under D4, with the round-trip proof.

    `python3 -c "import ast; ast.parse(open(...).read())"` at the end is not
    decoration -- a delta list can produce text that is a faithful fork of the
    proven file and still not valid python, and the place that would be found
    is a boot leg, 45 seconds at a time, with the medium half-written.
    """
    src = (RUNG6 / 'bm602_capture.py').read_text()
    cap = apply(src, D4, 'capture')
    assert round_trip(cap, D4, 'capture') == src, \
        'capture deltas are not invertible: removing the named blocks does not ' \
        'give back bm602_capture.py'
    compile(cap, 'bm653_capture.py', 'exec')
    return src, cap


def main() -> int:
    c = consts(INC.read_text())
    src = (RUNG6 / 'bm602_stage2_px.asm').read_text()
    s2, ctrl = fork(INC.name, control=True)
    (HERE / 'bm653_stage2_px.asm').write_text(s2)
    (HERE / 'bm653_stage2_px_beeoff.asm').write_text(ctrl)
    ctrl_name, old, new = CTRL
    capsrc, cap = fork_capture()
    (HERE / 'bm653_capture.py').write_text(cap)

    # R-SCOPE-12: nothing in the fork may still name BM602's gate constant.
    assert '0x393950AA' not in s2, 'a BM602 CRC literal survived in the fork text'
    # The leg's landing label must fit the 16-bit code descriptor's limit.
    assert s2.count('.rm_entry:') == 1
    print(f'stage2: {len(D2)} deltas, {len(src):,} B gated text -> {len(s2):,} B '
          f'({len(s2) - len(src):+,} B); round-tripped to rung6 byte-for-byte, '
          'so the unnamed text is identical by check, not by claim')
    for name, old_, new_ in D2:
        print(f'  {len(new_) - len(old_):>+5} B  {name}')
    print(f'control: 1 delta "{ctrl_name}" -- {len(old)} B -> {len(new)} B, '
          'undoes cleanly to the fork (BM652 §6: 5 bytes differ, same code end)')
    print(f'capture: {len(D4)} deltas on rung6\'s fork of rung9\'s locked gdb '
          f'session, {len(capsrc):,} B -> {len(cap):,} B, round-tripped and '
          're-parsed (bm653_capture.py)')
    print(f'geometry read back from {INC.name}: image group {c["IMG2_GROUP"]} '
          f'-> {c["IMG2_DST"]:#x} ({c["IMG2_LEN"]} B), plane-0 chunk at LBA '
          f'{c["IMG2_LBA"]}, GATE CRC={c["EXPECTED_CRC"]:08X}, '
          f'EXEC NID={c["EXPECTED_EXEC_NID"]:04X}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
