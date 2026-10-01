BITS 32
%include "bm602_px_layout.inc"
BEE_WORDS equ PX_GROUP_BYTES/4
; bee_correct -- BM602 pass 1 over one group's seven 4096-byte plane
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

bee_fixed:           dd 0     ; data symbols repaired this boot
bee_parity_faults:   dd 0     ; parity-plane-only faults: inert for the payload
