import json
d = json.load(open('/home/jericho/projects/zion/projects/visual_audio/.builder_queue/DEFECT-22_arc_legA_instability.json'))
ks = [k for k in d if k.startswith('ledger')]
print(ks[-2:])
print(d[ks[-1]][:500])
