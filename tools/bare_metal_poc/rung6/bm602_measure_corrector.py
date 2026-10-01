#!/usr/bin/env python3
"""BM602: how many bytes of executed 16-bit code is the corrector?

BM601_ECC_SCOPING.md sized this from a standalone probe (`probe_bee_inner_loop
.asm`, never wired into anything, ~244 B) and said so. Rung 6 now has the real
thing inside the loader, so the estimate can be replaced by a measurement of the
bytes that actually assemble -- with no boot and no gate: cut `bee_correct` out
of the generated bm602_stage2_px.asm, keep its text verbatim, and give it the
same three things the real file gives it at that point: BITS 32, the generated
geometry .inc, and the two counters it increments.

The labels are local (`.bee_loop`, `.bee_synd`, ...) and nasm resolves them
within the block, so the extract assembles standalone. If it ever stops
assembling standalone, that is a fact about the block (it grew a dependency on
context) and this file says so loudly rather than reporting a size.

  usage: python3 bm602_measure_corrector.py
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / 'bm602_stage2_px.asm'
TMP = HERE / 'bm602_corrector_only.asm'


def main() -> int:
    text = SRC.read_text()
    start = text.index('; bee_correct -- BM602 pass 1')
    end = text.index('; ata_read: esi = LBA', start)
    block = text[start:end]
    words = re.search(r'^BEE_WORDS\s+equ\s+(\S+)', text, re.M).group(1)
    counters = re.search(r'^bee_fixed:\s+dd 0.*$', text, re.M).group(0) + '\n' + \
        re.search(r'^bee_parity_faults:\s+dd 0.*$', text, re.M).group(0) + '\n'
    TMP.write_text(f'BITS 32\n%include "bm602_px_layout.inc"\n'
                   f'BEE_WORDS equ {words}\n'
                   + block + counters)
    # HEAD built into /tmp/bm602_corrector_only.bin and read its size back, so a
    # run whose build produced nothing still reported the previous run's bytes as
    # this one's measurement (measured: 333 B of planted junk prints as
    # "333 B assembled", rc=0). Per-run directory, removed on exit.
    tmpdir = tempfile.mkdtemp(prefix='bm602_corrector_')
    try:
        out = Path(tmpdir) / 'corrector_only.bin'
        r = subprocess.run(['nasm', '-f', 'bin', '-I', str(HERE) + '/', '-o',
                            str(out), str(TMP)],
                           capture_output=True, text=True)
        if r.returncode or r.stderr.strip():
            print(f'  [RED ] the executed corrector block does not assemble on its '
                  f'own: {r.stderr}{r.stdout}')
            return 1
        n = out.stat().st_size
        body = n - 8                      # the two dd 0 counters are data, not code
        print(f'bee_correct, as it stands in the generated loader: {n} B assembled, '
              f'{body} B of code + 8 B of counters')
        print(f'  against BM601\'s standalone estimate of 244 B: {n - 244:+d} B')
        print(f'  stage2 image is 8192 B, of which BM601 measured 4848 B unused: '
              f'{(n / 4848) * 100:.1f}% of the free budget')
        return 0
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == '__main__':
    sys.exit(main())
