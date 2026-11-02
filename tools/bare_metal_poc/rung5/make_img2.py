import random

# SEED=20260918 (determinism clause): a build-time random image with
# os.urandom made every rebuild a different CRC target, so RED/GREEN
# tails were not comparable across runs AND the gate's DEFS ordering
# bug baked the PREVIOUS run's CRC into stage2. Seeded PRNG pins the
# image; the CRC is stable across rebuilds and runs.
head = b"RUNG5-MARKER-IMAGE-2.0\x00"
img = bytearray(random.Random(20260918).randbytes(2048))
img[:len(head)] = head
open("img2.bin", "wb").write(bytes(img))
print("img2.bin", len(img), "bytes, head:", head)
