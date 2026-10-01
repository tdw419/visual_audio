"""DTF-3 twin-boundary probe: run the GH-8b FS append image through BOTH engines.

Question (amendment: "WGSL twin: FS handlers are host-side; record twin-boundary
note"): is the BK-7 SYS 9 append story host-side-handler or shader-executable?

Measured answer (this probe): the FS kernel (SYS 6/7/9) is IN-IMAGE guest code —
no host handler — so the WGSL twin executes it. Post-halt RAM state must match
the CPU oracle word-exact (name, len=16, in_use, data extent incl. both appends,
read-out window, both task exit words, kernel status word).

Exit 0 = MATCH (append works identically on the WGSL shader path).
Exit 1 = DIVERGENT or ERROR.
"""
import sys, tempfile
from pathlib import Path
repo = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo))
sys.path.insert(0, str(repo / "tools"))
import tools  # noqa: E402
from tools.glyph_gpt.baker import (fs_kernel_image, GH8_FSTAB_WORD, GH8_DATA_WORD,
    GH8_READOUT_WORD, GH8_EXIT_A, GH8_EXIT_B, GH8_PAYLOAD0, GH8_PAYLOAD1)
from tools.glyph_gpt.runner import GlyphRunner

BK7_PAYLOAD2 = 0x99AABBCC
BK7_PAYLOAD3 = 0xDDEEFF10
NAME_DATA = 0x41544144  # 'DATA' little-endian
KERNEL_OK = 0xCAFE0008
EXIT_OK_A = 0xFEED0006
EXIT_OK_B = 0xFEED0007


def check(mem, label):
    checks = {
        "slot0.name==DATA": mem[GH8_FSTAB_WORD] == NAME_DATA,
        "slot0.len==16": mem[GH8_FSTAB_WORD + 2] == 16,
        "slot0.in_use==1": mem[GH8_FSTAB_WORD + 3] == 1,
        "data0==payload0": mem[GH8_DATA_WORD] == GH8_PAYLOAD0,
        "data1==payload1": mem[GH8_DATA_WORD + 1] == GH8_PAYLOAD1,
        "data2==append1": mem[GH8_DATA_WORD + 2] == BK7_PAYLOAD2,
        "data3==append2": mem[GH8_DATA_WORD + 3] == BK7_PAYLOAD3,
        "readout0==payload0": mem[GH8_READOUT_WORD] == GH8_PAYLOAD0,
        "readout1==payload1": mem[GH8_READOUT_WORD + 1] == GH8_PAYLOAD1,
        "readout2==append1": mem[GH8_READOUT_WORD + 2] == BK7_PAYLOAD2,
        "readout3==append2": mem[GH8_READOUT_WORD + 3] == BK7_PAYLOAD3,
        "exit_A==0xFEED0006": mem[GH8_EXIT_A] == EXIT_OK_A,
        "exit_B==0xFEED0007": mem[GH8_EXIT_B] == EXIT_OK_B,
        "status==0xCAFE0008": mem[950] == KERNEL_OK,
    }
    bad = [k for k, v in checks.items() if not v]
    print(f"[{label}] " + ("ALL PASS" if not bad else "FAIL: " + ", ".join(bad)))
    return not bad


def main():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "bk7_append.npy"
        fs_kernel_image(None, append_leg=True, hole_leg=False, min_rows=80, out_path=p)
        r = GlyphRunner(p, ram_words=16384)

        rec_cpu = r.run(max_instructions=60000)
        print("cpu halted:", rec_cpu.get("halted"), "faulted:", rec_cpu.get("faulted"),
              "steps:", rec_cpu.get("steps"))
        ok_cpu = rec_cpu.get("halted") and not rec_cpu.get("faulted") and check(rec_cpu["memory"], "CPU")

        rec_wgsl = r.run_wgsl(max_steps=60000)
        print("wgsl halted:", rec_wgsl.get("halted"), "faulted:", rec_wgsl.get("faulted"),
              "steps:", rec_wgsl.get("steps"))
        ok_wgsl = rec_wgsl.get("halted") and not rec_wgsl.get("faulted") and check(rec_wgsl["ram"], "WGSL")

        diffs = [w for w in range(0, 16384) if rec_cpu["memory"][w] != rec_wgsl["ram"][w]]
        MMIO_WORDS = range(8192, 8211)  # BOX_MMIO_BASE>>2 .. (TICK_PC_ADDR+4)>>2
        outside = [w for w in diffs if w not in MMIO_WORDS]
        inside = [w for w in diffs if w in MMIO_WORDS]
        print(f"RAM diff count total={len(diffs)} mmio_block={len(inside)} "
              f"outside_mmio={len(outside)}")
        if inside:
            print("mmio-block diffs (twin keeps MMIO in its own binding; "
                  "engine-storage boundary, not FS drift):", inside)
        if outside:
            print("UNCLASSIFIED diffs:", [(w, hex(rec_cpu['memory'][w]),
                  hex(rec_wgsl['ram'][w])) for w in outside[:8]])
        ok_parity = len(outside) == 0

        ok = ok_cpu and ok_wgsl and ok_parity
        print("VERDICT:", "MATCH" if ok else "DIVERGENT")
        return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
