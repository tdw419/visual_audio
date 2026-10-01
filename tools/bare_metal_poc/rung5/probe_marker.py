med = open('rung5_medium.raw','rb').read()
s2 = open('stage2.bin','rb').read()
off = 68096
got = med[off:off+2048]
want = s2[:2048]
diffs = [i for i in range(2048) if got[i] != want[i]]
print("first diff:", diffs[0] if diffs else None, "count:", len(diffs))
if diffs:
    i = diffs[0]
    print(f"medium[{off}+{i}] = {got[i]:02X}  stage2.bin[{i}] = {want[i]:02X}")
    # context
    print("medium ctx:", ' '.join('%02X'%b for b in got[max(0,i-8):i+8]))
    print("want   ctx:", ' '.join('%02X'%b for b in want[max(0,i-8):i+8]))
    # are the diffs 512-periodic (a sector boundary issue)?
    print("diff offsets (first 30):", diffs[:30])
    print("all diffs mod 512:", sorted(set(d % 512 for d in diffs))[:20])
