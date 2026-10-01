import sys
sys.path.insert(0, '.')
sys.path.insert(0, 'tools')  # so 'glyph_gpt.tokenizer' resolves
import tracemalloc, resource
from tools.glyph_gpt.baker import syscall_abi_kernel_image
from tools.glyph_gpt.atlas import build_default_atlas
import tempfile, pathlib
tracemalloc.start(15)
with tempfile.TemporaryDirectory() as d:
    img = syscall_abi_kernel_image(build_default_atlas(), mode='baseline', out_path=pathlib.Path(d)/'x.npy')
snap = tracemalloc.take_snapshot()
tracemalloc.stop()
print('VmHWM MB:', resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024)
print('img shape:', img.shape, img.dtype)
for s in snap.statistics('lineno')[:10]:
    f = s.traceback[0]
    print(f'{s.size/1048576:10.1f} MiB count={s.count:9d} {f.filename}:{f.lineno}')
