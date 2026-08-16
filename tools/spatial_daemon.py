#!/usr/bin/env python3
"""
Spatial OS Daemon (Interaction Stratum Monitor)

This script acts as the OS supervisor (SystemServicesAgent). It monitors
a FIXED, RESERVED region of the spatial memory grid for semantic commands
written by the AI, and executes the corresponding real-world POSIX system
calls, bridging the spatial visual interface with the underlying Linux
kernel.

IMPORTANT: The daemon does NOT scan the entire memory. It only reads from a
reserved, fixed-address Interaction Stratum at SYSRESERVED_REGION_BASE.
This prevents false positives and provides deterministic contract behavior.

All filesystem operations are sandboxed under SANDBOX_ROOT: arguments are
real paths, read as null-terminated strings from spatial memory (not a
magic-number length bucketed into hardcoded directory names), and every
resolved path must stay within SANDBOX_ROOT or the operation is refused.
This mirrors tools/pixel_os_listener.py's _validate_path_in_sandbox pattern.

RESERVED MEMORY LAYOUT at SYSRESERVED_REGION_BASE:
    Offset 0: MAGIC_1 (0xADBEEF - signature marker, low 24 bits of 0xDEADBEEF)
    Offset 1: MAGIC_2 (0xFEBABE - signature marker, low 24 bits of 0xCAFEBABE)
    Offset 2: CMD_OPCODE (the semantic command, e.g., 0x4C53 for LS)
    Offset 3: ARG1_ADDR (spatial address of a null-terminated path string;
                          meaning depends on opcode - see per-command docs)
    Offset 4: ARG2_ADDR (second argument; unused by LS)
    Offset 5: RESULT_BASE (where the daemon will write output bytes)
    Offset 6+: Reserved for future parameters
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from tools.glyph_isa_v2 import GlyphAssemblerV2, GlyphCPUv2, OpcodeMapV2

# The fixed base address for the Interaction Stratum
# This MUST match the address used by semantic macros
SYSRESERVED_REGION_BASE = 8192

# Two-word signature to prevent false positives
# Note: pixel storage is 24-bit, so only lower 24 bits are stored
MAGIC_1_LOW24 = 0xADBEEF   # From 0xDEADBEEF
MAGIC_2_LOW24 = 0xFEBABE   # From 0xCAFEBABE

# Command opcodes
CMD_LS = 0x4C53      # "LS" in little-endian ASCII
CMD_MV = 0x4D56      # "MV"
CMD_SPAWN = 0x5350   # "SP" (spawn)

# Safety: maximum path/arg string length to prevent unbounded reads
MAX_STRING_LEN = 256

# Every filesystem operation is confined here. A daemon that could touch
# any host path from a spatial command would let a compromised or buggy
# .glyph program read/write/execute arbitrary files - this directory is
# the entire reachable filesystem as far as the daemon is concerned.
SANDBOX_ROOT = (Path(__file__).parent / "daemon_sandbox").resolve()
SANDBOX_ROOT.mkdir(exist_ok=True)


def write_string_to_image(image, addr, s, cpu):
    """Write a string as null-terminated bytes into spatial memory.

    Returns:
        Tuple of (data_bytes_written, total_bytes_with_null)
    """
    bytes_data = s.encode('utf-8')
    for i, byte_val in enumerate(bytes_data):
        cpu._mem_write(image, addr + i, byte_val)
    cpu._mem_write(image, addr + len(bytes_data), 0)
    return len(bytes_data), len(bytes_data) + 1


def read_string_from_image(image, addr, cpu, max_len=MAX_STRING_LEN):
    """Read a null-terminated string from spatial memory.

    This is what replaced the old target_addr-as-magic-length bucketing
    (target_addr > 1000 -> "tools", > 500 -> ".", else -> "tests"): a
    command's path argument is now an address, and the daemon reads the
    actual path string an AI/compiler wrote there, the same way it reads
    back its own RESULT_BASE output.
    """
    raw = bytearray()
    for i in range(max_len):
        val = cpu._mem_read(image, addr + i) & 0xFF
        if val == 0:
            break
        raw.append(val)
    else:
        raise ValueError(f"String at {addr} exceeds MAX_STRING_LEN={max_len} without a null terminator")
    return raw.decode('utf-8', errors='replace')


def validate_path_in_sandbox(name: str, desc: str = "path"):
    """Validate and resolve a path within SANDBOX_ROOT.

    Mirrors tools/pixel_os_listener.py's _validate_path_in_sandbox: reject
    traversal/absolute paths up front, then confirm the resolved path is
    still inside SANDBOX_ROOT (belt-and-suspenders against symlink tricks
    that '..' string-matching alone wouldn't catch).

    Returns:
        (success, resolved_path_or_None)
    """
    if '..' in name or name.startswith('/'):
        print(f"[OS DAEMON] Refusing op with dangerous {desc}: {name!r}")
        return False, None

    candidate = (SANDBOX_ROOT / name).resolve()
    try:
        candidate.relative_to(SANDBOX_ROOT)
    except ValueError:
        print(f"[OS DAEMON] Refusing op: path traversal attempt detected: {name!r} -> {candidate}")
        return False, None

    return True, candidate


def execute_ls_cmd(arg1_addr, result_base, image, cpu):
    """LS: ARG1_ADDR is the spatial address of a null-terminated path
    (relative to SANDBOX_ROOT, "." for the sandbox root itself)."""
    try:
        rel_path = read_string_from_image(image, arg1_addr, cpu)
    except ValueError as e:
        error_msg = f"ERROR: {e}\n"
        data_bytes, total_bytes = write_string_to_image(image, result_base, error_msg, cpu)
        print(f"[OS DAEMON] {e}")
        return data_bytes

    valid, target = validate_path_in_sandbox(rel_path, "ls path")
    if not valid:
        error_msg = f"ERROR: path rejected: {rel_path!r}\n"
        data_bytes, total_bytes = write_string_to_image(image, result_base, error_msg, cpu)
        return data_bytes

    try:
        files = sorted(p.name for p in target.iterdir())
        result_str = "\n".join(files) + "\n"
        data_bytes, total_bytes = write_string_to_image(image, result_base, result_str, cpu)
        print(f"[OS DAEMON] Executed ls on '{rel_path}' ({target})")
        print(f"[OS DAEMON] Wrote {data_bytes} data bytes ({total_bytes} total with null terminator) to spatial address {result_base}")
        print(f"[OS DAEMON] Result: {result_str[:100]}{'...' if len(result_str) > 100 else ''}")
        return data_bytes
    except Exception as e:
        error_msg = f"ERROR: {e}\n"
        data_bytes, total_bytes = write_string_to_image(image, result_base, error_msg, cpu)
        print(f"[OS DAEMON] Error listing '{rel_path}': {e}")
        return data_bytes


def execute_mv_cmd(arg1_addr, arg2_addr, result_base, image, cpu):
    """MV: ARG1_ADDR = source path string address, ARG2_ADDR = destination
    path string address (both relative to SANDBOX_ROOT)."""
    try:
        src_name = read_string_from_image(image, arg1_addr, cpu)
        dst_name = read_string_from_image(image, arg2_addr, cpu)
    except ValueError as e:
        error_msg = f"ERROR: {e}\n"
        data_bytes, _ = write_string_to_image(image, result_base, error_msg, cpu)
        print(f"[OS DAEMON] {e}")
        return data_bytes

    src_valid, src_path = validate_path_in_sandbox(src_name, "mv source")
    dst_valid, dst_path = validate_path_in_sandbox(dst_name, "mv destination")

    if not src_valid or not dst_valid:
        error_msg = "ERROR: mv path rejected\n"
        data_bytes, _ = write_string_to_image(image, result_base, error_msg, cpu)
        return data_bytes

    if not src_path.exists():
        error_msg = f"ERROR: mv source not found: {src_name}\n"
        data_bytes, _ = write_string_to_image(image, result_base, error_msg, cpu)
        print(f"[OS DAEMON] mv source not found: {src_path}")
        return data_bytes

    try:
        src_path.rename(dst_path)
        result_str = f"OK: moved {src_name} -> {dst_name}\n"
        data_bytes, total_bytes = write_string_to_image(image, result_base, result_str, cpu)
        print(f"[OS DAEMON] Moved {src_path} -> {dst_path}")
        print(f"[OS DAEMON] Wrote {data_bytes} data bytes ({total_bytes} total with null terminator) to spatial address {result_base}")
        return data_bytes
    except Exception as e:
        error_msg = f"ERROR: {e}\n"
        data_bytes, _ = write_string_to_image(image, result_base, error_msg, cpu)
        print(f"[OS DAEMON] Failed to move {src_path} to {dst_path}: {e}")
        return data_bytes


def execute_spawn_cmd(arg1_addr, arg2_addr, result_base, image, cpu):
    """SPAWN: ARG1_ADDR = script path string address (relative to
    SANDBOX_ROOT). ARG2_ADDR = space-separated args string address, or 0
    for no args."""
    try:
        script_name = read_string_from_image(image, arg1_addr, cpu)
        args_str = read_string_from_image(image, arg2_addr, cpu) if arg2_addr != 0 else ""
    except ValueError as e:
        error_msg = f"ERROR: {e}\n"
        data_bytes, _ = write_string_to_image(image, result_base, error_msg, cpu)
        print(f"[OS DAEMON] {e}")
        return data_bytes

    valid, script_path = validate_path_in_sandbox(script_name, "spawn script")
    if not valid:
        error_msg = f"ERROR: script path rejected: {script_name!r}\n"
        data_bytes, _ = write_string_to_image(image, result_base, error_msg, cpu)
        return data_bytes

    if not script_path.exists():
        error_msg = f"ERROR: spawn script not found: {script_name}\n"
        data_bytes, _ = write_string_to_image(image, result_base, error_msg, cpu)
        print(f"[OS DAEMON] Spawn script not found: {script_path}")
        return data_bytes

    try:
        args = args_str.split() if args_str else []
        cmd = [sys.executable, str(script_path)] + args
        process = subprocess.Popen(
            cmd,
            cwd=SANDBOX_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
        )
        result_str = f"OK: spawned pid={process.pid} cmd={' '.join(cmd)}\n"
        data_bytes, total_bytes = write_string_to_image(image, result_base, result_str, cpu)
        print(f"[OS DAEMON] Spawned background process: PID={process.pid}, cmd={' '.join(cmd)}")
        print(f"[OS DAEMON] Wrote {data_bytes} data bytes ({total_bytes} total with null terminator) to spatial address {result_base}")
        return data_bytes
    except Exception as e:
        error_msg = f"ERROR: {e}\n"
        data_bytes, _ = write_string_to_image(image, result_base, error_msg, cpu)
        print(f"[OS DAEMON] Failed to spawn {script_path}: {e}")
        return data_bytes


def scan_interaction_stratum(image, cpu):
    """Scan the reserved Interaction Stratum for a semantic command.

    Only reads from the fixed, reserved SYSRESERVED_REGION_BASE address
    with a multi-word signature - never scans the rest of memory, so an
    incidental value elsewhere can't be mistaken for a command.

    Returns:
        True if a command was found and dispatched, False otherwise.
    """
    magic1 = cpu._mem_read(image, SYSRESERVED_REGION_BASE + 0)
    magic2 = cpu._mem_read(image, SYSRESERVED_REGION_BASE + 1)
    cmd_opcode = cpu._mem_read(image, SYSRESERVED_REGION_BASE + 2)
    arg1_addr = cpu._mem_read(image, SYSRESERVED_REGION_BASE + 3)
    arg2_addr = cpu._mem_read(image, SYSRESERVED_REGION_BASE + 4)
    result_base = cpu._mem_read(image, SYSRESERVED_REGION_BASE + 5)

    if magic1 != MAGIC_1_LOW24 or magic2 != MAGIC_2_LOW24:
        print(f"[*] Signature mismatch!")
        print(f"    -> Expected magic1: 0x{MAGIC_1_LOW24:08X}, got: 0x{magic1:08X}")
        print(f"    -> Expected magic2: 0x{MAGIC_2_LOW24:08X}, got: 0x{magic2:08X}")
        return False

    print(f"[*] Detected valid command signature at reserved region {SYSRESERVED_REGION_BASE}")
    print(f"    -> CMD_OPCODE: 0x{cmd_opcode:08X}")
    print(f"    -> ARG1_ADDR: {arg1_addr}")
    print(f"    -> ARG2_ADDR: {arg2_addr}")
    print(f"    -> RESULT_BASE: {result_base}")

    if cmd_opcode == CMD_LS:
        execute_ls_cmd(arg1_addr, result_base, image, cpu)
    elif cmd_opcode == CMD_MV:
        execute_mv_cmd(arg1_addr, arg2_addr, result_base, image, cpu)
    elif cmd_opcode == CMD_SPAWN:
        execute_spawn_cmd(arg1_addr, arg2_addr, result_base, image, cpu)
    else:
        print(f"[OS DAEMON] Unknown command opcode: 0x{cmd_opcode:08X}")

    return True


def run_daemon(glyph_file: str, output_image: str = None):
    """Run the spatial daemon. If output_image provided, save modified grid."""
    print(f"=== Starting Spatial OS Daemon ===")

    opcode_map = OpcodeMapV2()
    try:
        assembler = GlyphAssemblerV2(opcode_map)
        code = Path(glyph_file).read_text().strip().split('\n')
        image = assembler.assemble(code, width_instrs=8)

        cpu = GlyphCPUv2(opcode_map, cols_instrs=8)
        print(f"[*] Booting spatial execution from {glyph_file}...")
        cpu.run(image, max_instructions=5000)

        print("[*] Execution halted. Checking Interaction Stratum...")
        found = scan_interaction_stratum(image, cpu)

        if not found:
            print("    -> No valid command signature in reserved region.")
        else:
            print("[*] Command executed. Spatial grid updated.")
            if output_image:
                import numpy as np
                np.save(output_image, image)
                print(f"[*] Saved modified spatial grid to {output_image}")

    finally:
        opcode_map.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 spatial_daemon.py <input.glyph> [output.npy]")
        sys.exit(1)

    output_image = sys.argv[2] if len(sys.argv) >= 3 else None
    run_daemon(sys.argv[1], output_image)
