#!/usr/bin/env python3
"""tools/build_map_bridge.py — BK-58 Stage 2: the build map becomes a console.

Whitelisted launch classes ONLY. No shell, no arbitrary exec:
  glyphdbg   — a scoped GlyphCPUv2 session on a named cell's commit:
               assemble + run a small demo program with the REAL assembler
               and engine at that cell's HEAD state is NOT done (that would
               need a worktree); instead the session assembles/runs the
               caller's program text through the LIVE engine in-process.
  speak      — tools/speak.py encode→decode roundtrip on a caller-supplied
               program TEXT (not a path): text is staged to a temp file
               under a fixed scratch dir, round-tripped, byte-compared.
  ollama     — one System-1 prompt through the local Ollama HTTP API
               (localhost only, fixed model, fixed timeout).
  ping       — liveness, no side effects.

Every launch appends a record to .builder_queue/decision_log.jsonl (the same
log the map renders from) with class, detail digest, verdict, and a sha256
evidence hash of the command spec. REFUSED launches are logged too.

stdlib-only: WebSocket server implemented by hand over asyncio streams
(no pip deps). Localhost bind only.

Security posture (BK-58's non-negotiable gate):
  - command classes are a closed set; anything else -> refuse
  - no host shell is ever spawned; glyphdbg runs the CPU in-process
  - speak/ollama args validated against strict patterns; ollama hits only
    127.0.0.1:11434 with a fixed model
  - every launch (accepted or refused) logged with evidence hash
"""
import asyncio
import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys_path = str(REPO)
if sys_path not in __import__("sys").path:
    __import__("sys").path.insert(0, sys_path)

LOG = REPO / ".builder_queue" / "decision_log.jsonl"

LAUNCH_CLASSES = ("glyphdbg", "speak", "ollama", "ping", "vtshell", "inspect")

_SHA_RE = re.compile(r"^[0-9a-fA-F]{6,40}$")
_PATH_SAFE_RE = re.compile(r"^[\w\-./]{1,256}$")
_PROGRAM_RE = re.compile(r"^[\x20-\x7e\n\r\t]{1,8192}$")

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
OLLAMA_MODEL = "qwen2.5-coder:7b"          # System-1's model, fixed
OLLAMA_TIMEOUT = 30.0
SPEAK_SCRATCH = Path("/tmp/bk58_speak_scratch")


# ------------------------------------------------------------------ logging

def log_launch(cls: str, detail: dict, verdict: str) -> str:
    """Append one launch record. Returns the evidence hash."""
    spec = {"class": cls, "detail": detail, "verdict": verdict,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())}
    evidence = hashlib.sha256(
        json.dumps(spec, sort_keys=True).encode()).hexdigest()[:16]
    rec = dict(spec)
    rec["evidence_hash"] = evidence
    rec["kind"] = "bk58_bridge_launch"
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    return evidence


# ------------------------------------------------------- launch handlers

def handle_glyphdbg(params: dict) -> dict:
    """Run a caller-supplied Glyph program through the live engine, in-process.

    Scoped: no host FS access, no syscall handlers with host posture beyond
    the engine's own fences (which are landed and gated), bounded steps.
    """
    program = params.get("program", "")
    if not isinstance(program, str) or not _PROGRAM_RE.match(program):
        return {"ok": False, "error": "program must be 1..8192 printable chars"}
    max_steps = params.get("max_steps", 200)
    if not isinstance(max_steps, int) or not (1 <= max_steps <= 2000):
        return {"ok": False, "error": "max_steps must be int 1..2000"}

    try:
        from tools.glyph_isa_v2 import GlyphAssemblerV2, GlyphCPUv2, OpcodeMapV2
    except ImportError:
        import glyph_isa_v2 as gi
        GlyphAssemblerV2 = gi.GlyphAssemblerV2
        GlyphCPUv2 = gi.GlyphCPUv2
        OpcodeMapV2 = gi.OpcodeMapV2

    lines = [l for l in program.splitlines() if l.strip()]
    opcode_map = OpcodeMapV2()
    asm = GlyphAssemblerV2(opcode_map)
    try:
        image = asm.assemble(lines, width_instrs=8)
        cpu = GlyphCPUv2(opcode_map, cols_instrs=8)
        steps = cpu.run(image, max_instructions=max_steps)
        out = list(cpu.output)[-16:]
        return {"ok": True, "steps": steps,
                "halted": not cpu.running,
                "output": out,
                "faulted": bool(getattr(cpu, "faulted", False)),
                "mode": getattr(cpu, "mode", None)}
    except Exception as e:
        return {"ok": False, "error": f"run failed: {e}"}
    finally:
        try:
            opcode_map.close()
        except Exception:
            pass


def handle_speak(params: dict) -> dict:
    """speak.py codec roundtrip on staged program TEXT (byte-exact check).

    Scoped: text staged under a fixed scratch dir, no arbitrary host paths.
    """
    text = params.get("text", "")
    if not isinstance(text, str) or not (0 < len(text.encode()) <= 4096):
        return {"ok": False, "error": "text must be 1..4096 bytes"}
    import subprocess as sp
    SPEAK_SCRATCH.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".py", dir=SPEAK_SCRATCH,
                                     delete=False) as f:
        f.write(text)
        src = f.name
    dec = src + ".decoded.py"
    try:
        enc = sp.run([__import__("sys").executable,
                      str(REPO / "tools" / "speak.py"), "encode", src,
                      "-o", src + ".wav"], capture_output=True, timeout=60)
        if enc.returncode != 0:
            return {"ok": False, "error": "encode failed",
                    "stderr": enc.stderr.decode()[-300:]}
        dec_run = sp.run([__import__("sys").executable,
                          str(REPO / "tools" / 'speak.py'), "decode",
                          src + ".wav", "-o", dec],
                         capture_output=True, timeout=60)
        if dec_run.returncode != 0:
            return {"ok": False, "error": "decode failed",
                    "stderr": dec_run.stderr.decode()[-300:]}
        same = Path(dec).read_bytes() == text.encode()
        return {"ok": True, "byte_exact": same}
    finally:
        for p in (src, src + ".wav", dec):
            try:
                os.unlink(p)
            except OSError:
                pass


def handle_ollama(params: dict) -> dict:
    prompt = params.get("prompt", "")
    if not isinstance(prompt, str) or not (0 < len(prompt) <= 4096):
        return {"ok": False, "error": "prompt must be 1..4096 chars"}
    import urllib.request
    body = json.dumps({"model": OLLAMA_MODEL, "prompt": prompt,
                       "stream": False}).encode()
    req = urllib.request.Request(
        OLLAMA_URL, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
        return {"ok": True, "model": OLLAMA_MODEL,
                "response": data.get("response", "")[:2048]}
    except Exception as e:
        return {"ok": False, "error": f"ollama unreachable: {e}"}


def handle_ping(params: dict) -> dict:
    return {"ok": True, "pong": True}


# ------------------------------------------------------------- vtshell (BK-81)

# SCENARIO 9's build is deterministic (fixed fixture + fixed flags) and takes
# ~0.1s measured; caching the transpiled image across batches is safe and keeps
# per-command latency at the run itself (~0.35s measured, BK-81 spike
# .builder_queue/bk81_spike_af3e.py).
_VTSHELL_CACHE: dict = {}
_VTSHELL_MAX_LINE = 64          # INPUT_DATA_CAP — the ring's hard ceiling
_VTSHELL_MAX_SESSIONS = 64      # bound the session store (localhost tooling)


def _vtshell_image():
    """Build the xv6-nano shell EXACTLY as SCENARIO 9 does (_build(9)),
    transpiled + assembled once, reused across batches. Raises on toolchain
    absence (the caller turns that into a loud per-launch error)."""
    if "img" in _VTSHELL_CACHE:
        return _VTSHELL_CACHE
    import tempfile
    sys_mod = __import__("sys")
    repo_tests = str(REPO / "tests")
    for p in (str(REPO), repo_tests):
        if p not in sys_mod.path:
            sys_mod.path.insert(0, p)
    import test_rv64i_to_glyph_xv6_nano as N  # the SCENARIO 9 harness (oracle-adjacent, read-only)
    with tempfile.TemporaryDirectory() as td:
        elf_bytes, _bin_data, _objdump = N._build(9, Path(td))
        sym = N._read_syms(elf_bytes, Path(td),
                           {"g_console", "g_clen", "fault_handler",
                            "syscall_dispatch"})
        from tools.rv64i_to_glyph import (
            PTR_TABLE_BASE, assemble_glyph_to_pixels, build_pointer_table,
            parse_elf, parse_elf_data_sections, transpile_elf_to_glyph)
        from tools.glyph_isa_v2 import GlyphCPUv2, OpcodeMapV2
        from tools.glyph_isa_v2 import KFAULT_PC_ADDR, KSYS_PC_ADDR

        glyph_source = transpile_elf_to_glyph(
            elf_bytes, entry_symbol="_start", byte_to_word_mem=True,
            ptr_table_base=PTR_TABLE_BASE)
        opcode_map = OpcodeMapV2()
        cpu0 = GlyphCPUv2(opcode_map, cols_instrs=64)
        pixels, coords = assemble_glyph_to_pixels(
            glyph_source, cols_instrs=64, min_rows=32)
        memory = [0] * 16384
        for vaddr, blob in parse_elf_data_sections(elf_bytes):
            for i, byte in enumerate(blob):
                a = vaddr + i
                w = a >> 2
                sh = (a & 3) * 8
                memory[w] = (memory[w] & ~(0xFF << sh)) | (byte << sh)
        _tv, tb, _symbols = parse_elf(elf_bytes)
        for wi, packed in build_pointer_table(tb, _tv, coords).items():
            idx = (PTR_TABLE_BASE >> 2) + wi
            if 0 <= idx < len(memory):
                memory[idx] = packed
        col, row = coords[f":pc_{sym['fault_handler']:08x}"]
        memory[KFAULT_PC_ADDR >> 2] = ((row & 0xFFFF) << 16) | (col & 0xFFFF)
        col, row = coords[f":pc_{sym['syscall_dispatch']:08x}"]
        memory[KSYS_PC_ADDR >> 2] = ((row & 0xFFFF) << 16) | (col & 0xFFFF)
        g_console = sym["g_console"]
        _VTSHELL_CACHE.update({"img": pixels, "memory": memory,
                               "opcode_map": opcode_map, "cpu0": cpu0,
                               "g_console": g_console,
                               "g_clen_word": sym["g_clen"] >> 2})
        return _VTSHELL_CACHE


def _vtshell_fresh_cpu():
    """A fresh GlyphCPUv2 with the SCENARIO 9 kernel image + pristine memory
    (the v1 contract: every batch is a fresh shell instance)."""
    import copy
    c = _VTSHELL_CACHE
    cpu = copy.copy(c["cpu0"])
    cpu.memory = list(c["memory"])          # pristine kernel image memory
    cpu.registers = [0] * 32
    cpu.pc = (0, 0)
    cpu.running = True
    cpu.output = []
    cpu.faulted = False
    cpu.fault_reason = None
    cpu.halt_reason = None
    return cpu


# session store: {session_id: {"vt": GlyphVT, "queue": [bytes lines]}}
_VTSHELL_SESSIONS: dict = {}


def handle_vtshell(params: dict) -> dict:
    """BK-81 vtshell — one command batch through the xv6-nano shell on
    GlyphCPUv2, in-process.

    v1 HONEST-SURFACE DISCLOSURE (mirrored in the viewer help): each batch
    runs a FRESH shell instance — the SCREEN persists across commands via
    the session's GlyphVT, PROCESS STATE DOES NOT (the cooperative engine
    has no mid-run input delivery point; v2 interrupt-ring is a separate
    row). Lines are queued per session and seeded into the GO-3 MMIO input
    ring via GlyphVT.seed_bytes() BEFORE the run; the ring cap is 64B per
    batch (INPUT_DATA_CAP) — overlong input is refused LOUD, never
    truncated.

    Scoped: no subprocess, no client-supplied FS paths, same in-process
    engine posture as glyphdbg; every launch logged via log_launch().
    """
    import tools.glyph_vt as VT

    if params.get("new_session"):
        if len(_VTSHELL_SESSIONS) >= _VTSHELL_MAX_SESSIONS:
            return {"ok": False,
                    "error": f"session store full (>{_VTSHELL_MAX_SESSIONS})"}
        sid = uuid.uuid4().hex
        _VTSHELL_SESSIONS[sid] = {"vt": VT.GlyphVT(rows=24, cols=80),
                                  "queue": []}
        return {"ok": True, "session_id": sid,
                "screen": _VTSHELL_SESSIONS[sid]["vt"].text()}

    sid = params.get("session_id")
    if not isinstance(sid, str) or sid not in _VTSHELL_SESSIONS:
        return {"ok": False,
                "error": "unknown session_id — open a session first "
                         "(params.new_session=true)"}
    line = params.get("line")
    if not isinstance(line, str) or not line:
        return {"ok": False, "error": "line must be a non-empty string"}
    n_bytes = len(line.encode("utf-8"))
    if n_bytes > _VTSHELL_MAX_LINE:
        return {"ok": False,
                "error": f"line is {n_bytes}B utf-8; per-batch input cap is "
                         f"{_VTSHELL_MAX_LINE}B (INPUT_DATA_CAP) — refused, "
                         "no silent truncation"}
    sess = _VTSHELL_SESSIONS[sid]
    vt: VT.GlyphVT = sess["vt"]

    try:
        c = _vtshell_image()
    except FileNotFoundError as e:
        return {"ok": False, "error": f"riscv toolchain missing: {e}"}

    # line discipline: every char through feed_key, terminator commits
    for ch in line + "\r":
        vt.feed_key(ch)

    cpu = _vtshell_fresh_cpu()
    try:
        seeded = vt.seed_bytes(cpu)
    except VT.VTRuntimeError as e:
        # roll the line back out of the VT echo stream is not possible
        # cheaply; the session is poisoned for echo purposes — drop and
        # report loud (never truncate).
        del _VTSHELL_SESSIONS[sid]
        return {"ok": False, "error": f"input refused: {e}"}
    if seeded == 0:
        return {"ok": False, "error": "internal: nothing seeded"}

    # WIRE-FORMAT ADAPTER (measured, bk81_debug_af3e.py): the GO-3 ring has
    # TWO readers in this tree with DIFFERENT formats. The engine's builtin
    # SYSCALL 0x02 reads one byte per word (tools/glyph_isa_v2.py:2118-2121)
    # — the format glyph_vt.seed_bytes writes (its V5/V7 gates pin it). The
    # xv6-nano C dispatcher reads the ring via LBU at byte address 0x8180
    # (tests/fixtures/xv6_nano.c:372,405) — PACKED little-endian words, the
    # format the GO-3 harness _seed_input_ring writes
    # (tests/test_rv64i_to_glyph_xv6_nano.py:178-190). seed_bytes() already
    # ran its guards (cap, cursor race) and consumed the pending echo; re-pack
    # its payload into the C dispatcher's format here. glyph_vt.py is
    # oracle-untouchable (BK-81 boundaries) — the adapter lives in the bridge.
    from tools.glyph_isa_v2 import INPUT_DATA_ADDR
    base = INPUT_DATA_ADDR >> 2
    payload = bytes(cpu.memory[base + i] & 0xFF for i in range(seeded))
    for i in range(0, seeded, 4):
        chunk = payload[i:i + 4]
        cpu.memory[base + i // 4] = int.from_bytes(
            chunk + b"\x00" * (4 - len(chunk)), "little")
    for w in range(base + (seeded + 3) // 4, base + seeded):
        cpu.memory[w] = 0          # clear the stale byte-per-word tail

    for _ in range(3_000_000):
        if not cpu.step(c["img"]):
            break
    if cpu.running:
        return {"ok": False, "error": "shell did not halt within budget"}

    g_console = c["g_console"]
    # g_console is a BYTE address; g_clen lives at its own symbol.
    clen = cpu.memory[c["g_clen_word"]] & 0xFFFFFFFF
    out = bytes((cpu.memory[(g_console + i) >> 2] >> (((g_console + i) & 3) * 8)) & 0xFF
                for i in range(clen))
    vt.feed_output(out)
    return {"ok": True, "screen": vt.text(), "session_id": sid,
            "bytes_out": clen}


def handle_inspect(params: dict) -> dict:
    """Surfaces git diff/stat or receipt/advisory content for deep inspection.

    Parameters:
      - sha: 6..40 hex characters. If provided, returns git show metadata and unified diff.
      - path: relative file path within REPO (e.g. .builder_queue/RECEIPT_*, systems/*.md).
    """
    target_sha = params.get("sha")
    target_path = params.get("path")

    if target_sha:
        if not isinstance(target_sha, str) or not _SHA_RE.match(target_sha):
            return {"ok": False, "error": "invalid sha format", "inspect": True}
        try:
            stat_run = subprocess.run(
                ["git", "show", "--stat", "--oneline", target_sha],
                cwd=str(REPO),
                capture_output=True,
                text=True,
                timeout=5.0
            )
            if stat_run.returncode != 0:
                return {"ok": False, "error": f"git show failed: {stat_run.stderr.strip()}", "inspect": True}

            diff_run = subprocess.run(
                ["git", "show", "-p", "--format=", target_sha],
                cwd=str(REPO),
                capture_output=True,
                text=True,
                timeout=5.0
            )
            diff_lines = diff_run.stdout.splitlines()
            truncated = len(diff_lines) > 250
            diff_text = "\n".join(diff_lines[:250])
            if truncated:
                diff_text += f"\n\n... [diff truncated; {len(diff_lines) - 250} more lines]"

            return {
                "ok": True,
                "inspect": True,
                "target": "commit",
                "sha": target_sha,
                "stat": stat_run.stdout.strip(),
                "diff": diff_text
            }
        except Exception as e:
            return {"ok": False, "error": f"inspect commit error: {e}", "inspect": True}

    elif target_path:
        if not isinstance(target_path, str) or not _PATH_SAFE_RE.match(target_path):
            return {"ok": False, "error": "invalid path format", "inspect": True}
        try:
            resolved = (REPO / target_path).resolve()
            if not str(resolved).startswith(str(REPO)):
                return {"ok": False, "error": "path traversal refused", "inspect": True}
            if not resolved.is_file():
                return {"ok": False, "error": f"file not found: {target_path}", "inspect": True}

            size = resolved.stat().st_size
            with open(resolved, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(32768)

            truncated = size > 32768
            if truncated:
                content += f"\n\n... [content truncated at 32KB; total {size} bytes]"

            return {
                "ok": True,
                "inspect": True,
                "target": "file",
                "path": str(resolved.relative_to(REPO)),
                "content": content
            }
        except Exception as e:
            return {"ok": False, "error": f"inspect file error: {e}", "inspect": True}

    return {"ok": False, "error": "either sha or path must be provided", "inspect": True}


HANDLERS = {"glyphdbg": handle_glyphdbg, "speak": handle_speak,
            "ollama": handle_ollama, "ping": handle_ping,
            "vtshell": handle_vtshell, "inspect": handle_inspect}


def dispatch(cls: str, params: dict) -> dict:
    """The BK-58 security gate: closed class set, logged, no shell."""
    if cls not in HANDLERS:
        ev = log_launch(cls, {"params": params}, "refused:unknown_class")
        return {"ok": False, "error": "unknown launch class",
                "evidence_hash": ev}
    if not isinstance(params, dict):
        ev = log_launch(cls, {"params": params}, "refused:bad_params")
        return {"ok": False, "error": "params must be an object",
                "evidence_hash": ev}
    result = HANDLERS[cls](params)
    verdict = "ok" if result.get("ok") else "error"
    ev = log_launch(cls, {"params": params, "result_ok": result.get("ok")},
                    verdict)
    result["evidence_hash"] = ev
    return result


# ------------------------------------------------------- WebSocket server
# Minimal RFC6455 server over asyncio streams, stdlib-only, localhost only.

WS_MAGIC = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def ws_accept(key: str) -> str:
    import base64
    return base64.b64encode(
        hashlib.sha1((key + WS_MAGIC).encode()).digest()).decode()


async def ws_client(reader, writer):
    try:
        request = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 10)
    except asyncio.TimeoutError:
        writer.close()
        return
    headers = {}
    for line in request.decode("latin1").split("\r\n")[1:]:
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip().lower()] = v.strip()
    key = headers.get("sec-websocket-key")
    if not key:
        writer.close()
        return
    writer.write((
        "HTTP/1.1 101 Switching Protocols\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Accept: {ws_accept(key)}\r\n\r\n").encode())
    await writer.drain()

    async def send_json(obj):
        await ws_send(writer, json.dumps(obj).encode())

    # first message must be an auth-free launch (localhost-only posture)
    try:
        while True:
            op = await read_ws_message(reader)
            if op is None:
                break
            try:
                req = json.loads(op.decode())
                cls = req.get("class", "")
                params = req.get("params", {})
            except Exception:
                await send_json({"ok": False, "error": "malformed json"})
                continue
            # dispatch runs handlers in a thread so long launches don't
            # block the socket
            result = await asyncio.get_event_loop().run_in_executor(
                None, dispatch, cls, params)
            await send_json(result)
    except (ConnectionResetError, asyncio.IncompleteReadError):
        pass
    finally:
        writer.close()


async def ws_send(writer, payload: bytes, opcode=0x1):
    import struct
    header = bytearray([0x80 | opcode])
    mask_bit = 0  # server -> client frames are unmasked
    n = len(payload)
    if n < 126:
        header.append((mask_bit << 7) | n)
    elif n < 65536:
        header.append((mask_bit << 7) | 126)
        header += struct.pack(">H", n)
    else:
        header.append((mask_bit << 7) | 127)
        header += struct.pack(">Q", n)
    writer.write(bytes(header) + payload)
    await writer.drain()


async def read_ws_message(reader):
    import struct
    try:
        hdr = await reader.readexactly(2)
    except asyncio.IncompleteReadError:
        return None
    fin_op = hdr[0]
    opcode = fin_op & 0x0F
    masked = hdr[1] & 0x80
    n = hdr[1] & 0x7F
    if n == 126:
        n = struct.unpack(">H", await reader.readexactly(2))[0]
    elif n == 0x7F:
        n = struct.unpack(">Q", await reader.readexactly(8))[0]
    mask = await reader.readexactly(4) if masked else b"\x00" * 4
    data = bytearray(await reader.readexactly(n)) if n else bytearray()
    if masked:
        for i in range(len(data)):
            data[i] ^= mask[i % 4]
    if opcode == 0x8:      # close
        return None
    if opcode == 0x9:      # ping -> handled by caller loop simply
        return b""
    return bytes(data)


def serve(host="127.0.0.1", port=8765):
    async def _main():
        server = await asyncio.start_server(ws_client, host, port)
        print(f"bk58 bridge on ws://{host}:{port}")
        async with server:
            await server.serve_forever()
    asyncio.run(_main())


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    serve(port=args.port)
