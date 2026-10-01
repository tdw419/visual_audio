#!/usr/bin/env python3
"""probe_bk24_wrapper_falsifier.py — BK-24 defect ticket's cheapest falsifier.

Ticket: .builder_queue/DEFECT_BK24_GH23_comparator_return_20260924.md
Hypothesis under test (fenced speculation in the ticket): the NEW write()
C wrapper (loop + static char frame[16] + _write_frame calls) changes the
call/return shape such that qsort's SECOND comparator RET pops a stale PC.

Legs (all on the CURRENT dirty tree's image builder — tile exoneration
already measured in the ticket's bisect legs 2/5):
  V_new        LIBC_C verbatim (control)        -> expect RED (fault ~32820)
  V_trivial    write() = pass-through to
               _write_frame (no loop, no
               static frame, no memcpy calls)   -> GREEN => wrapper complexity
  V_localframe wrapper body kept, but the
               frame buffer moved from static
               (BSS) to the C stack             -> GREEN => static/BSS var

READ-ONLY on tracked files: imports the dirty test module from its working-
tree path and passes libc_text= variants through its own _compile_elf hook.
No fixture is mutated; nothing here edits tools/ or tests/.
"""
import importlib.util
import sys
import tempfile
from pathlib import Path

_REPO = Path("/home/jericho/projects/zion/projects/visual_audio")
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

spec = importlib.util.spec_from_file_location(
    "t_gh23", _REPO / "tests" / "test_gh23_libc_runtime.py")
t = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t)

from tools.glyph_gpt.atlas import build_default_atlas
from tools.glyph_gpt.runner import GlyphRunner

QSORT_ONLY_C = r"""\
extern void *malloc(unsigned nwords);
extern void qsort(int *base, unsigned n, int (*cmp)(const void *, const void *));
extern int cmp_ilv_unused(const void *a, const void *b);
extern void exit(int code);

void _start(void) {
    int *arr = (int *)malloc(4);
    for (int i = 0; i < 4; i++) arr[i] = 40 - 10 * i;
    qsort(arr, 4, cmp_ilv_unused);
    exit(arr[0]);          /* sorted head = 10 on success; visible in 722 */
}

int cmp_ilv_unused(const void *a, const void *b);
int cmp_ilv_unused(const void *a, const void *b) {
    int x = *(const int *)a, y = *(const int *)b;
    return (x > y) - (x < y);
}
"""

WRAPPER_START = "/* ── BK-24: streaming write"
WRAPPER_END = "    return (int)len;\n}\n"

TRIVIAL_WRITE = """\
extern int _write_frame(int fd, const void *src);

int write(int fd, const void *buf, unsigned len) {
    (void)len;
    return _write_frame(fd, buf);
}
"""

LOCALFRAME_WRITE = """\
#define FRAME 16
extern int _write_frame(int fd, const void *src);
extern void memcpy(void *d, const void *s, unsigned n);

int write(int fd, const void *buf, unsigned len) {
    const unsigned char *p = buf;
    char frame[FRAME] __attribute__((aligned(16)));   /* ON THE C STACK */
    unsigned left = len;
    while (left >= FRAME) {
        memcpy(frame, p, FRAME);
        _write_frame(fd, frame);
        p += FRAME;
        left -= FRAME;
    }
    if (left) {
        for (unsigned i = 0; i < FRAME; i++) frame[i] = 0;
        memcpy(frame, p, left);
        _write_frame(fd, frame);
    }
    return (int)len;
}
"""


def _swap_wrapper(libc: str, replacement: str) -> str:
    i = libc.index(WRAPPER_START)
    j = libc.index(WRAPPER_END) + len(WRAPPER_END)
    return libc[:i] + replacement + libc[j:]


VARIANTS = {
    "V_new_control": t.LIBC_C,
    "V_trivial_write": _swap_wrapper(t.LIBC_C, TRIVIAL_WRITE),
    "V_localframe": _swap_wrapper(t.LIBC_C, LOCALFRAME_WRITE),
}


def run_variant(name: str, libc_text: str) -> dict:
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        elf = t._compile_elf(tmp, QSORT_ONLY_C, libc_text=libc_text)
        program = t._load_posix_program(elf)
        out = tmp / "qsort_only.npy"
        import tools.glyph_gpt.libc_runtime as lr
        lr.libc_runtime_kernel_image(build_default_atlas(), out_path=out,
                                     user_program=program)
        runner = GlyphRunner(out, ram_words=16384)
        r = runner.run(max_instructions=200000, trace=True)
        mem = r["memory"]
        info = {
            "variant": name,
            "halted": r["halted"],
            "faulted": r["faulted"],
            "steps": r.get("steps") or r.get("n_instructions"),
            "exit_word": mem[722],
            "brk": mem[723],
            "cursor": mem[724],
            "heap": [mem[2560 + i] for i in range(4)],
            "error": r.get("error"),
            "fault_addr": r.get("fault_addr"),
        }
        return info


def main() -> int:
    results = []
    for name, txt in VARIANTS.items():
        try:
            info = run_variant(name, txt)
        except Exception as e:  # noqa: BLE001 — probe records, never raises
            info = {"variant": name, "exception": repr(e)}
        results.append(info)
        print(info, flush=True)
    ok = all(("exception" not in r) for r in results)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
