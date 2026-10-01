#!/usr/bin/env python3
r"""BM903 step 3, L4: the ONLY normalizations a transcript may undergo.

The brief says "byte-identical modulo timestamps". Measured on three real boots
of one medium (/tmp/bm903_{time_run0,time_run1,ctrl}.log), here is the complete
list of what varies and what does not. Every rule is counted and printed, so a
leg that needs more normalisation than this cannot quietly slide past; the gate
itself stays a single strict `cmp` of the .norm files.

  T1  a bracketed kernel timestamp   `[    0.123456]`      (fires 0 times here --
                                                           TinyCore's init strips
                                                           them; kept because the
                                                           brief names timestamps)
  T2  a busybox login line's pid     `login[499]`          varies per boot
  T3  spinner cycles while a script  `/\|-` + BACKSPACE    varies per boot
      waits

  T4  THE CUT. Everything from the first RACE-ONSET line onward is two autologin
      getties (tty1 and ttyS0) racing for /dev/console, and the VM is stopped the
      instant the anchor appears. The onset is the EARLIEST of a `login[PID]`
      console record and the /etc/issue banner, because MEASURED (gate run 4)
      both orders occur: one boot printed `root login on 'tty1'` before the
      banner and another printed the banner first, so cutting at "the first login
      record" alone moves the cut by 129 bytes between two legitimate boots and
      makes the same boot pair look non-deterministic. The tail's CONTENT, not
      just its order, is not reproducible, and no pattern-matching makes it so.
      Transcripts are therefore compared strictly up to that onset -- which is
      still the entire stage2 trace, the whole kernel boot and all of init's
      bootcode -- and the discarded tail is reported (length + sha256) instead of
      being hidden.

  usage: bm903_norm_transcript.py <log> [<log2> ...]     writes <log>.norm
"""
import hashlib
import re
import sys
from pathlib import Path

RULES = [
    ('T1 kernel timestamp', re.compile(rb'\[[ 0-9]{1,10}\.[0-9]{1,10}\]'), b'[TS]'),
    ('T2 login pid',        re.compile(rb'login\[[0-9]+\]'),               b'login[PID]'),
    ('T3 spinner cycles',   re.compile(rb'(?:[/\\|\-]\x08)+'),             b'[SPIN]'),
]
# The two lines that can only exist because the autologin race resolved.
ONSETS = [('login record', re.compile(rb'login\[PID\]')),
          ('issue banner', re.compile(rb"\( '>'\)\r?\n"))]

for arg in sys.argv[1:]:
    if arg.startswith('-'):
        continue
    p = Path(arg)
    raw = p.read_bytes()
    data = raw
    hits = []
    for name, pat, rep in RULES:
        data, n = pat.subn(rep, data)
        hits.append((name, n))
    cut, where = len(data), None
    for name, pat in ONSETS:
        m = pat.search(data)
        if m:
            # snap back to the start of the line: the banner is indented, so an
            # onset measured mid-line would move the cut by its own whitespace.
            at = data.rfind(b'\n', 0, m.start()) + 1
            if where is None or at < cut:
                cut, where = at, name
    tail = b'' if where is None else data[cut:]
    hits.append(('T4 cut', 'no race line' if where is None
                 else f'{cut} B, at the first {where}'))
    p.with_suffix(p.suffix + '.norm').write_bytes(data[:cut])
    fired = ', '.join(f'{n}={c}' for n, c in hits if c)
    print(f'  {p.name}: {len(raw)} B -> {cut} B compared   fired: {fired}')
    if tail:
        print(f'      tail not compared: {len(tail)} B '
              f'sha256 {hashlib.sha256(tail).hexdigest()[:16]}…')
