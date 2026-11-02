# Indirect memory load and store demonstration with LD and ST
LDI r1 100
LDI r2 42
ST r1 r2
LD r3 r1
PRT r3
HALT
