#!/usr/bin/env python3
"""
Regression suite for the pixel_interpreter CPU. Re-run this after ANY
change to cpu_emulator.py or assembler.py -- including changes you did
not make yourself. This file's history has repeatedly been edited
outside of a verified session (see memory: pixel-interpreter-call-ret-
verified.md), silently reintroducing bugs that individually-run demo
scripts do not catch. Do not trust "it should still work" -- run this.
"""
from pathlib import Path
from cpu_emulator import PixelCPU

HERE = Path(__file__).parent


def run(png, cycles=300):
    cpu = PixelCPU(256, 256)
    cpu.load_program(HERE / png)
    for _ in range(cycles):
        if cpu.step():
            break
    return cpu


def test_subroutine():
    cpu = run("test_subroutine.png", 100)
    assert cpu.memory[100, 10][0] == 255
    assert cpu.memory[100, 20][0] == 255
    assert cpu.memory[110, 15][0] == 255


def test_interrupt():
    cpu = PixelCPU(256, 256)
    cpu.load_program(HERE / "test_interrupt.png")
    for _ in range(6):
        cpu.step()
    cpu.raise_interrupt(1, 42, 99)
    for _ in range(10):
        if cpu.step():
            break
    assert cpu.memory[0, 8][0] == 42


def test_scheduler():
    cpu = PixelCPU(256, 256)
    cpu.load_program(HERE / "scheduler.png")
    pids = []
    for cycle in range(60):
        if cycle > 0 and cycle % 15 == 0:
            cpu.raise_interrupt(1)
        cpu.step()
        pids.append(int(cpu.memory[0, 100][0]))
    assert pids[21] == 1 and pids[36] == 0 and pids[51] == 1, pids
    p1 = int(cpu.memory[0, 60][0])
    assert p1 == 3, p1


def test_vfs():
    cpu = PixelCPU(256, 256)
    cpu.load_program(HERE / "vfs_demo.png")
    cpu.mount_vfs(str(HERE / "sprite.png"), 0, 192)
    while not cpu.halt_flag:
        cpu.step()
    mismatches = [
        (x, y)
        for y in range(8)
        for x in range(8)
        if cpu.memory[192 + y, x][0] != cpu.memory[100 + y, 100 + x][0]
    ]
    assert not mismatches, mismatches


def test_guest_vm():
    cpu = run("guest_vm.png", 300)
    assert cpu.halt_flag
    assert cpu.memory[0, 136][0] == 8
    assert cpu.memory[200, 8][0] == 255


def test_alu():
    cpu = run("test_alu.png", 60)
    expected = {200: 8, 201: 15, 202: 6, 203: 48, 204: 3, 205: 105, 206: 150}
    for x, v in expected.items():
        assert int(cpu.memory[0, x][0]) == v, (x, int(cpu.memory[0, x][0]), v)


def test_indirect_store_mem():
    cpu = run("test_indirect_store_mem.png", 10)
    assert cpu.memory[40, 30][0] == 77


def test_fib():
    cpu = run("fib.png", 200000)
    assert cpu.halt_flag
    assert cpu.memory[0, 230][0] == 55, cpu.memory[0, 230][0]
    assert cpu.memory[0, 220][0] == 0, cpu.memory[0, 220][0]  # dsp balanced


TESTS = [
    test_subroutine,
    test_interrupt,
    test_scheduler,
    test_vfs,
    test_guest_vm,
    test_alu,
    test_indirect_store_mem,
    test_fib,
]

if __name__ == "__main__":
    failures = []
    for t in TESTS:
        try:
            t()
            print(f"{t.__name__}: OK")
        except Exception as e:
            print(f"{t.__name__}: FAIL ({e})")
            failures.append(t.__name__)
    if failures:
        print(f"\n{len(failures)} FAILED: {failures}")
        raise SystemExit(1)
    print(f"\nALL {len(TESTS)} REGRESSION TESTS PASS")
