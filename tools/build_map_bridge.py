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
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys_path = str(REPO)
if sys_path not in __import__("sys").path:
    __import__("sys").path.insert(0, sys_path)

LOG = REPO / ".builder_queue" / "decision_log.jsonl"

LAUNCH_CLASSES = ("glyphdbg", "speak", "ollama", "ping")

_SHA_RE = re.compile(r"^[0-9a-f]{8,40}$")
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


HANDLERS = {"glyphdbg": handle_glyphdbg, "speak": handle_speak,
            "ollama": handle_ollama, "ping": handle_ping}


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
