A = region(shape=(8,), initial=1)
B = region(shape=(8,), initial=2)
C = A + B
total = reduce(C, sum)
print(total)
