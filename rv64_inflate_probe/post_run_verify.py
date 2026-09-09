#!/usr/bin/env python3
"""Post-run verification of the fixed full boot."""
import json
from pathlib import Path

base = Path('/home/jericho/projects/zion/projects/visual_audio/rv64_inflate_probe')
text = ''.join(
    json.loads(l)['uart']
    for l in (base / 'fixed_full_trace.jsonl').read_text().strip().split('\n')
    if '"uart"' in l
)
print('total uart bytes:', len(text))
for marker in ['broken padding', 'write error', 'Run /init', 'BAD_PAGE',
               'workqueue: Failed', 'Unpacking initramfs', 'Freeing initrd memory']:
    print(f'{marker!r}: {text.count(marker)}')

dump = (base / 'initrd_fixed_boot_dump.bin').read_bytes()
src = (base / 'initrd.gz.bin').read_bytes()
region = dump[0x2800000:0x2800000 + len(src)]
cc = sum(1 for b in region if b == 0xcc)
print(f'initrd region @0x82800000: 0xcc={cc}/{len(src)} ({100.0*cc/len(src):.1f}%) — 0xCC expected (freed initrd, POISON_FREE_INITMEM)')
print('DTB magic at 0x82600000:', dump[0x2600000:0x2600004].hex())
print('kernel first bytes at 0x80200000:', dump[0x200000:0x200010].hex())
