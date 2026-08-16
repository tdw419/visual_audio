import time
from pathlib import Path

import numpy as np
import pytest

from tools.glyph_isa_v2 import GlyphAssemblerV2, GlyphCPUv2, OpcodeMapV2
from tools import spatial_daemon as daemon


@pytest.fixture
def cpu_image():
    opcode_map = OpcodeMapV2()
    assembler = GlyphAssemblerV2(opcode_map)
    # A single HALT is enough; the daemon reads/writes memory directly and
    # never re-runs the CPU after setup, so no real program logic is needed.
    image = assembler.assemble(["HALT"], width_instrs=8)
    # Grow the image well past the reserved region + string/result areas so
    # nothing wraps around (the exact bug BYTE_COUNT_FIX.md documented).
    big = np.zeros((200, 32, 3), dtype=np.uint8)
    big[: image.shape[0], : image.shape[1]] = image
    cpu = GlyphCPUv2(opcode_map, cols_instrs=8)
    yield big, cpu
    opcode_map.close()


def _write_command(image, cpu, opcode, arg1_addr, arg2_addr, result_base):
    base = daemon.SYSRESERVED_REGION_BASE
    cpu._mem_write(image, base + 0, daemon.MAGIC_1_LOW24)
    cpu._mem_write(image, base + 1, daemon.MAGIC_2_LOW24)
    cpu._mem_write(image, base + 2, opcode)
    cpu._mem_write(image, base + 3, arg1_addr)
    cpu._mem_write(image, base + 4, arg2_addr)
    cpu._mem_write(image, base + 5, result_base)


def _write_string(image, cpu, addr, s):
    daemon.write_string_to_image(image, addr, s, cpu)


@pytest.fixture(autouse=True)
def clean_sandbox():
    for p in daemon.SANDBOX_ROOT.iterdir():
        if p.is_file() and p.name != "greeting.txt":
            p.unlink()
    yield
    for p in daemon.SANDBOX_ROOT.iterdir():
        if p.is_file() and p.name != "greeting.txt":
            p.unlink()


def test_ls_real_path_resolution(cpu_image):
    image, cpu = cpu_image
    (daemon.SANDBOX_ROOT / "subdir").mkdir(exist_ok=True)
    (daemon.SANDBOX_ROOT / "subdir" / "a.txt").write_text("a")
    (daemon.SANDBOX_ROOT / "subdir" / "b.txt").write_text("b")

    _write_string(image, cpu, 100, "subdir")
    _write_command(image, cpu, daemon.CMD_LS, arg1_addr=100, arg2_addr=0, result_base=200)

    found = daemon.scan_interaction_stratum(image, cpu)
    assert found

    result = daemon.read_string_from_image(image, 200, cpu, max_len=4096)
    assert set(result.strip().split("\n")) == {"a.txt", "b.txt"}

    (daemon.SANDBOX_ROOT / "subdir" / "a.txt").unlink()
    (daemon.SANDBOX_ROOT / "subdir" / "b.txt").unlink()
    (daemon.SANDBOX_ROOT / "subdir").rmdir()


def test_ls_rejects_path_traversal(cpu_image):
    image, cpu = cpu_image
    _write_string(image, cpu, 100, "../../../etc")
    _write_command(image, cpu, daemon.CMD_LS, arg1_addr=100, arg2_addr=0, result_base=200)

    daemon.scan_interaction_stratum(image, cpu)

    result = daemon.read_string_from_image(image, 200, cpu, max_len=4096)
    assert result.startswith("ERROR")


def test_mv_moves_file_and_rejects_traversal(cpu_image):
    image, cpu = cpu_image
    src = daemon.SANDBOX_ROOT / "movable.txt"
    src.write_text("payload")

    _write_string(image, cpu, 100, "movable.txt")
    _write_string(image, cpu, 300, "moved.txt")
    _write_command(image, cpu, daemon.CMD_MV, arg1_addr=100, arg2_addr=300, result_base=500)

    daemon.scan_interaction_stratum(image, cpu)

    result = daemon.read_string_from_image(image, 500, cpu, max_len=4096)
    assert result.startswith("OK")
    assert not src.exists()
    dst = daemon.SANDBOX_ROOT / "moved.txt"
    assert dst.exists()
    assert dst.read_text() == "payload"
    dst.unlink()

    # Traversal on the destination must also be rejected.
    src2 = daemon.SANDBOX_ROOT / "movable2.txt"
    src2.write_text("payload2")
    _write_string(image, cpu, 100, "movable2.txt")
    _write_string(image, cpu, 300, "../escape.txt")
    _write_command(image, cpu, daemon.CMD_MV, arg1_addr=100, arg2_addr=300, result_base=500)
    daemon.scan_interaction_stratum(image, cpu)
    result = daemon.read_string_from_image(image, 500, cpu, max_len=4096)
    assert result.startswith("ERROR")
    assert src2.exists()  # never moved
    src2.unlink()


def test_spawn_launches_real_process(cpu_image):
    image, cpu = cpu_image
    script = daemon.SANDBOX_ROOT / "worker.py"
    marker = daemon.SANDBOX_ROOT / "worker_ran.txt"
    marker.unlink(missing_ok=True)
    script.write_text(
        "import sys\n"
        "from pathlib import Path\n"
        "Path('worker_ran.txt').write_text(' '.join(sys.argv[1:]))\n"
    )

    _write_string(image, cpu, 100, "worker.py")
    _write_string(image, cpu, 300, "hello world")
    _write_command(image, cpu, daemon.CMD_SPAWN, arg1_addr=100, arg2_addr=300, result_base=500)

    daemon.scan_interaction_stratum(image, cpu)

    result = daemon.read_string_from_image(image, 500, cpu, max_len=4096)
    assert result.startswith("OK: spawned pid=")

    for _ in range(50):
        if marker.exists():
            break
        time.sleep(0.1)
    assert marker.exists()
    assert marker.read_text() == "hello world"

    script.unlink()
    marker.unlink()


def test_spawn_rejects_script_outside_sandbox(cpu_image):
    image, cpu = cpu_image
    _write_string(image, cpu, 100, "/etc/passwd")
    _write_string(image, cpu, 300, "")
    _write_command(image, cpu, daemon.CMD_SPAWN, arg1_addr=100, arg2_addr=0, result_base=500)

    daemon.scan_interaction_stratum(image, cpu)

    result = daemon.read_string_from_image(image, 500, cpu, max_len=4096)
    assert result.startswith("ERROR")


def test_signature_mismatch_is_not_dispatched(cpu_image):
    image, cpu = cpu_image
    base = daemon.SYSRESERVED_REGION_BASE
    cpu._mem_write(image, base + 0, 0x123456)  # wrong magic
    cpu._mem_write(image, base + 1, daemon.MAGIC_2_LOW24)
    cpu._mem_write(image, base + 2, daemon.CMD_LS)

    found = daemon.scan_interaction_stratum(image, cpu)
    assert found is False
