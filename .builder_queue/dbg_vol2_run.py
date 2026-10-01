#!/usr/bin/env python3
"""Debug one vol2 fixture end-to-end: compile, load, run, dump receipt."""
import sys, tempfile
from pathlib import Path
REPO = Path('/home/jericho/projects/zion/projects/visual_audio')
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / 'tools'))

from tools.glyph_gpt.atlas import build_default_atlas
from tools.glyph_gpt.runner import GlyphRunner
from tools.glyph_gpt.baker import libc_runtime_kernel_image
from tools.glyph_gpt.libc_runtime import GH23_WRITE_CURSOR, GH23_WRITE_RING_BASE
from tools.glyph_gpt.coreutils_port import coreutils2_tool_elf, COREUTILS2_FIXTURES
from tests.test_gh23_libc_runtime import _load_posix_program, GH23_EXIT_CODE

tool = sys.argv[1] if len(sys.argv) > 1 else 'grep'
fx_name = sys.argv[2] if len(sys.argv) > 2 else sorted(COREUTILS2_FIXTURES[tool])[0]
with tempfile.TemporaryDirectory() as d:
    tmp = Path(d)
    fx = COREUTILS2_FIXTURES[tool][fx_name]
    want = fx['output'].encode('ascii')
    elf_bytes = coreutils2_tool_elf(tool, fx_name, tmp)
    program = _load_posix_program(elf_bytes)
    out = tmp / 'dbg.npy'
    libc_runtime_kernel_image(build_default_atlas(), out_path=out, user_program=program)
    runner = GlyphRunner(out, ram_words=16384)
    receipt = runner.run(max_instructions=300000, trace=True)
    print('halted:', receipt.get('halted'), 'faulted:', receipt.get('faulted'),
          'executed:', receipt.get('executed'), 'err:', receipt.get('error'))
    mem = receipt['memory']
    print('exit code word:', mem[GH23_EXIT_CODE])
    print('cursor:', hex(mem[GH23_WRITE_CURSOR]), 'ring base:', hex(GH23_WRITE_RING_BASE))
    frames = (len(want) + 15) // 16 if want else 1
    stream = b''.join(int(mem[w]).to_bytes(4, 'little')
                      for w in range(GH23_WRITE_RING_BASE, GH23_WRITE_RING_BASE + frames * 4))
    print('want:', want)
    print('got :', stream)
    # also dump window mirror
    window = b''.join(int(mem[w]).to_bytes(4, 'little') for w in (718, 719, 720, 721))
    print('window 718..721:', window)
