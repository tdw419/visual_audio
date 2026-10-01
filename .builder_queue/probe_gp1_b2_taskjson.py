#!/usr/bin/env python3
"""Write task.json for each GP-1 batch-2 capture (schema: va-syscall-corpus/1)."""
import json
from pathlib import Path

CAPS = {
    'b2cap1b': {
        'slug': 'denied_access_probe',
        'task_prompt': 'Run exactly: bash /var/tmp/run_cap1b.sh',
        'workload': '64KB urandom copy + head of mode-600 file + ls of missing dir (ENOENT/ENOTTY/permission error surface)',
    },
    'b2cap2': {
        'slug': 'af_unix_socketpair_echo',
        'task_prompt': 'Run exactly: bash /var/tmp/run_cap2.sh',
        'workload': 'AF_UNIX socketpair DGRAM ping + SOCK_STREAM bind/listen/connect/accept4 echo server',
    },
    'b2cap3': {
        'slug': 'mmap_rw_page',
        'task_prompt': 'Run exactly: bash /var/tmp/run_cap3.sh',
        'workload': '4KB file mmap: slice write, flush, seek+read back',
    },
    'b2cap4': {
        'slug': 'tar_gz_roundtrip',
        'task_prompt': 'Run exactly: bash /var/tmp/run_cap4.sh',
        'workload': 'tar czf of a nested dir tree + listing + extract to new dir (archive/recursive-getdents surface)',
    },
    'b2cap5': {
        'slug': 'dd_blockio_eacces',
        'task_prompt': 'Run exactly: bash /var/tmp/run_cap5.sh',
        'workload': 'dd 64KB bs=512 conv=notrunc,sync + cat of mode-000 file (EACCES) + sync',
    },
}

for d, meta in CAPS.items():
    p = Path('corpus_build') / d
    t = {
        'schema': 'va-syscall-corpus/1',
        'captured_utc': '2026-09-17T04:32:00Z',
        'slug': meta['slug'],
        'task_prompt': meta['task_prompt'],
        'dispatch': 'guest_bridge.py hermes_run',
        'guest': {'kernel': '6.8.0-136-generic', 'strace': '6.8'},
        'workload': meta['workload'],
        'hermes_reply': 'script executed via guest channel; see trace.log for ground truth',
    }
    (p / 'task.json').write_text(json.dumps(t, indent=2) + '\n')
    print('WROTE', p / 'task.json')
