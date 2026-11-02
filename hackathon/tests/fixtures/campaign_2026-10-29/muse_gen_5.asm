LDI r1 0
LDI r2 16
LDI r3 7
LDI r4 64
LDI r5 1024
LDI r7 1
LDI r10 0
ADD r10 r4
 :loop
CMP r1 r4
JZ :done
LDI r6 0
ADD r6 r2
MUL r6 r4
ADD r6 r1
ADD r6 r5
ST r6 r3
ADD r1 r7
JMP :loop
 :done
HALT
