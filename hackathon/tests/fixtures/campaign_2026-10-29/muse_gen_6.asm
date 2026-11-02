LDI r7 0
LDI r6 0
LDI r3 8
LDI r4 1024
LDI r2 1
LDI r10 0
 :fill
ST r6 r3
ADD r6 r2
SUB r4 r2
CMP r4 r7
JNZ fill
LDI r1 0
LDI r2 4
LDI r3 15
LDI r4 32
LDI r5 0
 :row
LDI r6 0
 :col
ADD r8 r1
MUL r8 r4
ADD r8 r6
ADD r8 r5
ST r8 r3
LDI r9 1
ADD r6 r9
CMP r6 r2
JLT col
LDI r9 1
ADD r1 r9
CMP r1 r2
JLT row
LDI r10 1
HALT
