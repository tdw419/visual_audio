#!/usr/bin/env python3
"""BM602: construct Rung 6's loader by DELTA, not by re-typing.

`rung9/bm903_stage2_px.asm` is a read-only, gated artifact (42 legs green), and
Rung 6's whole claim is "the same loader text, a medium that can repair itself".
So this script reads that file, applies a named list of textual deltas, asserts
each one matched EXACTLY ONCE, and writes rung6/bm602_stage2_px.asm. Anything it
did not name is byte-identical to the proven loader, which is what lets the
differ's L1/L4 identity legs keep meaning "different medium" rather than
"somebody rewrote the loader". The delta list and the resulting byte counts are
printed, so the receipt can cite them.

Same for stage1: one delta, the container tag in the medium's own first sector,
which is what tells a PXC1 medium from a PXC2-E medium before 30 seconds of
walk produce an unexplained CRC mismatch.

  usage: python3 bm602_construct.py      # writes the two .asm files, no boots
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNG9 = HERE.parent / 'rung9'

# --------------------------------------------------------------------------
# stage2 deltas
# --------------------------------------------------------------------------
D2 = []

D2.append(('include: the PXC2-E geometry, not PXC1',
           '%include "bm903_px_layout.inc"',
           '%include "bm602_px_layout.inc"'))

D2.append(('header block: MBR slot + tag geometry named once, here',
           'STACK_TOP equ 0x1f784',
           'STACK_TOP equ 0x1f784\n'
           '; ---- BM602 additions. Everything outside a block named in\n'
           '; bm602_construct.py\'s delta list is byte-identical to\n'
           '; rung9/bm903_stage2_px.asm, which is what the L1/L4 identity legs read.\n'
           'MBR_ADDR equ 0x7C00                  ; the BIOS copy of stage1 is still there\n'
           'BEE_WORDS equ PX_GROUP_BYTES/4       ; codewords per group == in-plane offsets'))

D2.append(('container check before the walk',
           """    call px_walk
    mov edi, msg_kload             ; the walk completed; now the gate decides""",
           """    ; ---- BM602: this loader reads a PXC2-E medium (PX_PLANES planes). The
    ; ---- tag is read out of the stage1 bytes the BIOS left at 0x7C00, i.e.
    ; ---- out of the MEDIUM, so reusing an old 4-plane medium is refused by
    ; ---- name here rather than as an unexplained CRC mismatch one walk later.
    mov eax, [MBR_ADDR + PX_TAG_OFF]
    cmp eax, PX_CONTAINER
    jne fail_container
    call px_walk
    mov edi, msg_kload             ; the walk completed; now the gate decides"""))

D2.append(('plane buffer selection: 7 buffers, and 0x34000 is the sink',
           """    ; edi = PBp
    mov edi, PB0
    mov eax, ebx
    shl eax, 12
    add edi, eax""",
           """    ; edi = this plane's buffer. NOT PB0 + p*0x1000 past p=3: 0x34000 is
    ; PX_SINK, so the parity planes live above it, at PP1/PP2/PP4, and the
    ; mapping is a table the host proof reads too rather than arithmetic the
    ; reader has to re-derive.
    mov edi, [px_pb + ebx*4]"""))

D2.append(('read all planes, not four',
           """    mov eax, [px_plane]
    inc eax
    mov dword [px_plane], eax
    cmp eax, 4
    jb .pw_plane""",
           """    mov eax, [px_plane]
    inc eax
    mov dword [px_plane], eax
    cmp eax, PX_PLANES
    jb .pw_plane"""))

D2.append(('pass 1 before the de-interleave',
           """    ; ---- decode this group: EAX=dst, ESI = CRC, EBP = dst, ECX = j ----
    call px_dst                     ; reads [px_group]; clobbers ecx,edx only""",
           """    ; ---- BM602 PASS 1: repair the plane chunks in place. The decode and
    ; CRC loop below is then untouched, so the gate checksums corrected bytes
    ; in decoded order exactly as BM903 does. ----
    call bee_correct
    ; ---- decode this group: EAX=dst, ESI = CRC, EBP = dst, ECX = j ----
    call px_dst                     ; reads [px_group]; clobbers ecx,edx only"""))

D2.append(('ECC=/PAR= printed before the gate verdict, never after',
           """    mov edi, msg_crc
    call puts32
    mov eax, [px_crc]""",
           """    ; ---- BM602 non-vacuity anchor. Printed after the whole walk (nothing
    ; here can still change: DEFECT-R4PRINT) and BEFORE the CRC verdict, so a
    ; run that "passed" by correcting nothing cannot be read as a recovery.
    ; ECC=0 PAR=0 on a KNOWN-CORRUPT medium is a FAIL leg. ----
    mov edi, msg_ecc
    call puts32
    mov eax, [bee_fixed]
    call puthex8_32
    mov edi, msg_par
    call puts32
    mov eax, [bee_parity_faults]
    call puthex8_32
    mov edi, msg_crlf
    call puts32
    mov edi, msg_crc
    call puts32
    mov eax, [px_crc]"""))

D2.append(('the corrector itself, before ata_read',
           '; ata_read: esi = LBA, ebx = sector count (<=128), edi = dst',
           """; bee_correct -- BM602 pass 1 over one group's seven 4096-byte plane
; buffers. Hamming(7,4) over BYTE symbols, so the codeword is (PB0[x],PB1[x],
; PB2[x],PB3[x]) with parity planes p1=d0^d1^d3, p2=d0^d2^d3, p4=d1^d2^d3, and
; the three syndromes are bytes. Linear over GF(2): no multiply, no table, no
; solver. The nonzero pattern names the symbol and the syndrome VALUE is the
; fault, so fixing is one XOR. Clobbers eax,ebx,ecx,edx only (the walk holds
; the group counter in memory and re-derives everything else).
;
; There is deliberately no "uncorrectable" branch: with a 3-bit pattern over a
; byte symbol, two faults still name some symbol and get confidently mis-fixed.
; That is BM601 scoping leg G, and the CRC32 gate downstream is what catches
; it. The corrector never sits in front of the gate.
bee_correct:
    xor  ecx, ecx
.bee_loop:
    mov  al, [PP1 + ecx]
    xor  al, [PB0 + ecx]
    xor  al, [PB1 + ecx]
    xor  al, [PB3 + ecx]             ; al = s1
    mov  ah, [PP2 + ecx]
    xor  ah, [PB0 + ecx]
    xor  ah, [PB2 + ecx]
    xor  ah, [PB3 + ecx]             ; ah = s2
    mov  bl, [PP4 + ecx]
    xor  bl, [PB1 + ecx]
    xor  bl, [PB2 + ecx]
    xor  bl, [PB3 + ecx]             ; bl = s4
    mov  bh, ah
    or   bh, bl
    cmp  al, 0
    jne  .bee_synd
    test bh, bh
    jne  .bee_synd
.bee_next:
    inc  ecx
    cmp  ecx, BEE_WORDS
    jb   .bee_loop
    ret

.bee_synd:
    ; pattern (s1,s2,s4) -> symbol: 011 d0, 101 d1, 110 d2, 111 d3 (data, fix
    ; with the covering syndrome); 001/010/100 are a parity plane (the payload
    ; is untouched, counted separately); anything else is two faults and is
    ; mis-fixed by design.
    cmp  al, 0
    je   .bee_s1zero
    cmp  ah, 0
    jne  .bee_s12
    cmp  bl, 0
    je   .bee_parity                 ; s1 alone
    jmp  .bee_d1                     ; s1, s4
.bee_s12:
    cmp  bl, 0
    je   .bee_d0                     ; s1, s2
    jmp  .bee_d3                     ; s1, s2, s4
.bee_s1zero:
    cmp  ah, 0
    je   .bee_parity                 ; s4 alone (or nothing)
    cmp  bl, 0
    jne  .bee_d2                     ; s2, s4 -> fix with s2
.bee_parity:                         ; s2 alone
    inc  dword [bee_parity_faults]
    jmp  .bee_next
.bee_d0:
    mov  dl, [PB0 + ecx]
    xor  dl, al
    mov  [PB0 + ecx], dl
    inc  dword [bee_fixed]
    jmp  .bee_next
.bee_d1:
    mov  dl, [PB1 + ecx]
    xor  dl, al
    mov  [PB1 + ecx], dl
    inc  dword [bee_fixed]
    jmp  .bee_next
.bee_d2:
    mov  dl, [PB2 + ecx]
    xor  dl, ah
    mov  [PB2 + ecx], dl
    inc  dword [bee_fixed]
    jmp  .bee_next
.bee_d3:
    mov  dl, [PB3 + ecx]
    xor  dl, al
    mov  [PB3 + ecx], dl
    inc  dword [bee_fixed]
    jmp  .bee_next

; ata_read: esi = LBA, ebx = sector count (<=128), edi = dst"""))

D2.append(('refuse a medium this loader was not built for',
           """fail_hdrs:
    mov edi, msg_hdrfail
    call puts32
    jmp hang32""",
           """fail_hdrs:
    mov edi, msg_hdrfail
    call puts32
    jmp hang32
fail_container:
    ; computed-then-compared, same discipline as the CRC line: name what the
    ; medium says before the verdict, so a refusal can be read off serial.
    mov edi, msg_contain
    call puts32
    mov eax, [MBR_ADDR + PX_TAG_OFF]
    call puthex8_32
    mov edi, msg_exp
    call puts32
    mov eax, PX_CONTAINER
    call puthex8_32
    mov edi, msg_crlf
    call puts32
    jmp hang32"""))

D2.append(('the new strings and counters',
           """msg_crcfail  db 'BM903-S2 GATE2=FAIL -- NO HANDOFF JUMP', 13, 10, 0""",
           """msg_crcfail  db 'BM903-S2 GATE2=FAIL -- NO HANDOFF JUMP', 13, 10, 0
; BM602 lines. The ENTER/verdict strings keep the BM903-S2 prefix on purpose:
; a leg that differs from the proven loader only in these lines still shares
; every stage of BM903's stage ladder, which is what the classifier reads.
msg_ecc      db 'BM903-S2 ECC=', 0
msg_par      db ' PAR=', 0
msg_contain  db 'BM903-S2 CONTAINER=', 0"""))

D2.append(('plane buffer table + the two counters',
           """align 4
px_group:   dd 0
px_plane:   dd 0
px_crc:     dd 0""",
           """align 4
px_group:   dd 0
px_plane:   dd 0
px_crc:     dd 0
; plane p of the group in flight lands where this table says. The host proof
; (bm602_mkimg.py) reads THESE SEVEN DEFINES out of this file, so a buffer
; that moved here and not there is caught before anything boots.
px_pb:      dd PB0, PB1, PB2, PB3, PP1, PP2, PP4
bee_fixed:           dd 0     ; data symbols repaired this boot
bee_parity_faults:   dd 0     ; parity-plane-only faults: inert for the payload"""))

# --------------------------------------------------------------------------
# stage1: one delta -- the container tag, in the medium's own first sector
# --------------------------------------------------------------------------
D1 = [
    ('include the generated PXC2-E defines',
     '%include "bm903_layout.inc"',
     '%include "bm903_layout.inc"\n%include "bm602_px_layout.inc"'),
    ('the tag slot the guest reads at 0x7C00+PX_TAG_OFF',
     """    times 510-($-$$) db 0
    dw 0xAA55""",
     """; BM602: a four-byte container tag at a fixed offset, padded to from the
; current end of code so the slot cannot drift with the text above it. The
; guest reads it back out of the BIOS copy of this sector: an old medium's
; stage1 has 0 here, and the new loader refuses by name instead of misreading
; four planes as seven. The offset is the MBR's reserved band -- clear of
; this file's code+data, and clear of the partition table at 0x1BE.
    times PX_TAG_OFF-($-$$) db 0
    dd PX_CONTAINER
    times 510-($-$$) db 0
    dw 0xAA55"""),
]


# --------------------------------------------------------------------------
# capture: the same fork discipline applied to the handoff dump
# --------------------------------------------------------------------------
# rung9/bm903_capture.py is the LOCKED capture structure: same gdb -batch -nx
# session, same hbreak at the kernel's first instruction, same $rsi-keyed 4 KiB
# zeropage and CMDPTR-keyed 512 B cmdline dumps. BM601 scoping leg 1 asks for
# handoff dumps to be byte-identical across media, so rung6 needs that capture
# -- and rung9 is a read-only tree this row must not write into. Hence a fork
# whose ONLY named changes are where evidence lands, where geometry is read
# from, and which lane guard runs. Round-tripping them must give rung9 back.
D3 = [
    ('a run6 output root, next to the proven constants',
     'HERE = Path(__file__).resolve().parent',
     """HERE = Path(__file__).resolve().parent
RUNG9 = HERE.parent / 'rung9'
# BM602: rung9 is a gated, read-only tree, so this fork keeps rung9's capture
# SEMANTICS and redirects only its file system side effects. Everything not
# named in bm602_construct.py's D3 list is rung9's text.
OUT = HERE / 'captures'
OUT.mkdir(exist_ok=True)"""),
    # G2: rung 9's capture is the ancestor, so the port it names is rung 9's.
    # A fork that copied it verbatim would boot a second gdbstub on the same
    # port as its parent rung, and the collision would be silent until G1's
    # stderr fix made it loud. One block per rung, disjoint by the map.
    ('this fork\'s own gdb port block, so rung 6 shares no port with rung 9',
     "PORT_BASE = 12468  # this rung's block start; the legs take +0 and +1",
     "PORT_BASE = 12460  # this rung's block start; the legs take +0 and +1"),
    ('gdb dumps by absolute path',
     """    zpf = f'{PREFIX}_zp_leg{leg}.bin'
    cmdf = f'{PREFIX}_cmdline_leg{leg}.bin'""",
     """    # Absolute, because gdb resolves a relative dump name against ITS cwd,
    # which need not be this directory. rung9 happened to be invoked from its
    # own tree; a fork that inherited the relative names would write evidence
    # somewhere else and then compare files that never changed.
    zpf = str(OUT / f'{PREFIX}_zp_leg{leg}.bin')
    cmdf = str(OUT / f'{PREFIX}_cmdline_leg{leg}.bin')"""),
    ('the bidirectional lane guard, in live_count',
     """def live_count() -> int:
    import bm903_lane
    return len(bm903_lane.live_boots())""",
     """def live_count() -> int:
    import bm602_lane
    return len(bm602_lane.live_boots())"""),
    ('the bidirectional lane guard, at the entry check',
     """    import bm903_lane
    if bm903_lane.main([str(MEDIUM)]) or live_count():""",
     """    import bm602_lane
    if bm602_lane.main([str(MEDIUM)]) or live_count():"""),
    ('the refusal names the guard actually in force',
     "'sequentially (see bm903_lane.py)')",
     "'sequentially (see bm602_lane.py, which watches bm903 boots too)')"),
    ('geometry read from the gated tree, not copied into this one',
     '    lay = json.loads((HERE / "bm903_layout.json").read_text())',
     '    lay = json.loads((RUNG9 / "bm903_layout.json").read_text())'),
    ('the three per-leg logs land under captures/',
     """        logf = HERE / f'{PREFIX}_capture_leg{leg}.log'
        serf = HERE / f'{PREFIX}_serial_leg{leg}.log'
        qerrf = HERE / f'{PREFIX}_qemu_stderr_leg{leg}.log'""",
     """        logf = OUT / f'{PREFIX}_capture_leg{leg}.log'
        serf = OUT / f'{PREFIX}_serial_leg{leg}.log'
        qerrf = OUT / f'{PREFIX}_qemu_stderr_leg{leg}.log'"""),
    ('the two dumps land under captures/',
     """        zp = HERE / f'{PREFIX}_zp_leg{leg}.bin'
        cmd = HERE / f'{PREFIX}_cmdline_leg{leg}.bin'""",
     """        zp = OUT / f'{PREFIX}_zp_leg{leg}.bin'
        cmd = OUT / f'{PREFIX}_cmdline_leg{leg}.bin'"""),
    ('the register set lands under captures/',
     "        (HERE / f'{PREFIX}_regs_leg{leg}.json').write_text(",
     "        (OUT / f'{PREFIX}_regs_leg{leg}.json').write_text("),
    ('provenance: which file executed this dump',
     "            'captured_by': 'bm903_capture.py (executed stage2)',",
     "            'captured_by': 'bm602_capture.py (fork of bm903_capture.py, "\
     "same gdb session; executed stage2)',"),
]


def consts(inc_text):
    import re
    out = {m.group(1): int(m.group(2), 0) for m in re.finditer(
        r'^%define (\w+) (-?0x[0-9A-Fa-f]+|\d+)$', inc_text, re.M)}
    for name in ('PX_TAG_OFF', 'PX_CONTAINER', 'PX_PLANES', 'PB0', 'PP1',
                 'PP2', 'PP4', 'PX_SINK', 'PX_GROUP_BYTES'):
        assert name in out, f'{name} missing from bm602_px_layout.inc'
    assert out['PX_PLANES'] == 7 and 4 <= out['PX_TAG_OFF'] <= 506, \
        f'unusable geometry: {out["PX_PLANES"]} planes, tag at {out["PX_TAG_OFF"]:#x}'
    assert out['PX_TAG_OFF'] not in range(0x1BE, 0x1FE), 'tag would sit in the DPT'
    for name in ('PB0', 'PB1', 'PB2', 'PB3', 'PP1', 'PP2', 'PP4'):
        assert name in out, f'{name} missing from bm602_px_layout.inc'
    bufs = [out['PB0'] + i * 0x1000 for i in range(4)] + \
           [out['PP1'], out['PP2'], out['PP4']]
    assert len(set(bufs)) == 7 and all(b < b + 0x1000 for b in bufs)
    for i in range(7):
        for j in range(i + 1, 7):
            assert bufs[i] + 0x1000 <= bufs[j] or bufs[j] + 0x1000 <= bufs[i], \
                f'plane buffers {i} and {j} overlap at {bufs[i]:#x}/{bufs[j]:#x}'
    assert out['PP1'] >= out['PX_SINK'] + out['PX_GROUP_BYTES'], \
        'the parity buffers walk on top of the filler sink'
    assert out['PP4'] + 0x1000 <= 0x3C000, 'plane buffers run past the low map'
    return out


def apply(text, deltas, what):
    for name, old, new in deltas:
        n = text.count(old)
        assert n == 1, f'{what}: delta "{name}" matched {n} times, want exactly 1'
        text = text.replace(old, new, 1)
    return text


def round_trip(text, deltas, what):
    """Undo every delta, newest first, and require the proven file back byte
    for byte. This is the check behind the receipt's claim: not "we believe the
    unnamed bytes were left alone" but "removing exactly the named blocks
    reproduces rung9 exactly". A delta that duplicated text rather than
    replacing it fails here, not in a boot log."""
    for name, old, new in reversed(deltas):
        n = text.count(new)
        assert n == 1, f'{what}: undo "{name}" found {n} copies of its own text'
        text = text.replace(new, old, 1)
    return text


def main() -> int:
    c = consts((HERE / 'bm602_px_layout.inc').read_text())
    s2src = (RUNG9 / 'bm903_stage2_px.asm').read_text()
    s1src = (RUNG9 / 'bm903_stage1.asm').read_text()
    s2 = apply(s2src, D2, 'stage2')
    s1 = apply(s1src, D1, 'stage1')
    capsrc = (RUNG9 / 'bm903_capture.py').read_text()
    cap = apply(capsrc, D3, 'capture')
    assert round_trip(s2, D2, 'stage2') == s2src, 'stage2 deltas are not invertible'
    assert round_trip(s1, D1, 'stage1') == s1src, 'stage1 deltas are not invertible'
    assert round_trip(cap, D3, 'capture') == capsrc, \
        'capture deltas are not invertible'
    (HERE / 'bm602_stage2_px.asm').write_text(s2)
    (HERE / 'bm602_stage1.asm').write_text(s1)
    (HERE / 'bm602_capture.py').write_text(cap)
    print(f'stage2: {len(D2)} deltas applied, {len(s2src):,} B proven text -> '
          f'{len(s2):,} B ({len(s2) - len(s2src):+,} B); round-tripped to rung9 '
          'byte-for-byte, so the unnamed text is identical by check, not by claim')
    print(f'stage1: {len(D1)} deltas applied: tag {c["PX_CONTAINER"]:#x} '
          f'({"".join(chr(c["PX_CONTAINER"] >> 8 * i & 0xFF) for i in range(4))}) '
          f'at {c["PX_TAG_OFF"]:#x} of the MBR')
    print(f'capture: {len(D3)} deltas applied, {len(capsrc):,} B proven text -> '
          f'{len(cap):,} B ({len(cap) - len(capsrc):+,} B); the gdb session, the '
          'stop, and both dump widths are untouched -- only the output root, the '
          'geometry source and the lane guard moved, and they round-trip')
    print('wrote bm602_stage2_px.asm, bm602_stage1.asm, bm602_capture.py')
    return 0


if __name__ == '__main__':
    sys.exit(main())
