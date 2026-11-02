#!/usr/bin/env python3
"""BM-403 measured baseline v2: boot-to-receipt wall time = time from
qemu start to the FIRST GATE4 line appearing in the serial log (poll),
then kill qemu. This measures the boot itself, not the halt-loop dwell
that a fixed timeout adds. TCG defaults throughout.
"""
import subprocess, time, os, sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))

def leg(scale):
    tag = f"{scale//1024}k"
    subprocess.run(f"nasm -f bin stage2.asm -DRUNG4_SCALE={scale} -o stage2_code.bin",
                   shell=True, check=True)
    subprocess.run(f"python3 rung4_pad.py {scale} stage2_code.bin stage2.bin",
                   shell=True, check=True)
    subprocess.run("python3 rung4_consts.py", shell=True, check=True, capture_output=True)
    subprocess.run("nasm -f bin stage1.asm -o stage1.bin", shell=True, check=True)
    subprocess.run(f"python3 rung4_codec.py encode stage1.bin stage2.bin "
                   f"rung4_medium.png rung4_medium.raw rung4_meta.json >/dev/null",
                   shell=True, check=True)
    logf = f"serial_t_{tag}.log"
    if os.path.exists(logf): os.remove(logf)
    t0 = time.perf_counter()
    p = subprocess.Popen(f"qemu-system-x86_64 -drive file=rung4_medium.raw,"
                         f"format=raw,if=ide -display none -no-reboot "
                         f"-serial file:{logf}", shell=True)
    receipt = None
    while time.perf_counter() - t0 < 120:
        if os.path.exists(logf):
            data = open(logf, "rb").read().decode(errors="replace").replace("\r", "")
            if "GATE4=" in data:
                receipt = time.perf_counter() - t0
                break
        time.sleep(0.002)
    p.kill(); p.wait()
    data = open(logf, "rb").read().decode(errors="replace").replace("\r", "") if os.path.exists(logf) else ""
    ok = receipt is not None and "GATE4=PASS" in data
    return receipt, ok, data

for scale in (65536, 262144):
    r1 = leg(scale)
    r2 = leg(scale)
    for i, (wall, ok, data) in enumerate((r1, r2), 1):
        line = next((l for l in data.splitlines() if "GATE4=" in l), "<none>").strip()
        if wall is None:
            print(f"scale={scale//1024} KB run{i}: NO RECEIPT within 120s")
        else:
            print(f"scale={scale//1024} KB run{i}: boot-to-receipt={wall*1000:.0f} ms  "
                  f"decode_rate={scale/1024/wall:.0f} KB/s  PASS={ok}  [{line}]")
