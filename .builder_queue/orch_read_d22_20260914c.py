import json
d = json.load(open('.builder_queue/DEFECT-22_arc_legA_instability.json'))
keys = [k for k in d if '2026_09_14' in k or '2026_09_13_1' in k or '2026_09_13_2' in k]
for k in sorted(keys):
    v = str(d[k])
    print(f"=== {k} ===")
    print(v[:1500])
    print()
print("STATUS:", d.get('status'))
print("NEXT_STEP:", d.get('next_step'))
