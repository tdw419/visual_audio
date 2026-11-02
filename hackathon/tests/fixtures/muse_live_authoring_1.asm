LDI r1 4
LDI r2 2
LDI r3 32
LDI r7 1
LDI r8 8
LDI r9 24
LDI r4 0
 :red_outer
LDI r5 0
 :red_inner
LDI r6 0
ADD r6 r4
MUL r6 r3
ADD r6 r5
ST r1 r6
ADD r5 r7
CMP r5 r8
JZ :red_row_end
JMP :red_inner
 :red_row_end
ADD r4 r7
CMP r4 r8
JZ :green_start
JMP :red_outer
 :green_start
LDI r4 0
 :green_outer
LDI r5 0
 :green_inner
LDI r6 0
ADD r6 r4
MUL r6 r3
ADD r6 r5
ADD r6 r9
ST r2 r6
ADD r5 r7
CMP r5 r8
JZ :green_row_end
JMP :green_inner
 :green_row_end
ADD r4 r7
CMP r4 r8
JZ :done
JMP :green_outer
 :done
LDI r10 1
HALT
