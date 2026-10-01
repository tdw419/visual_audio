"""BK-58 gate: tests/test_build_map_bridge.py — RED-first bridge security gate.

L1: the bridge REFUSES a non-whitelisted launch class (dispatch-level and
    over a real WebSocket round-trip).
L2: the bridge executes a whitelisted glyphdbg session and returns the
    program's real output (dispatch-level and over a real socket).
L3: concurrent sessions are isolated (two sockets interleaved, results do
    not cross-contaminate).
L4: every launch — accepted AND refused — is logged to
    .builder_queue/decision_log.jsonl with an evidence hash.

Scope: tools/build_map_bridge.py + this file. No engine, no viewer HTML
changes required for the gate (drawer wiring is the manual-checklist leg).
"""
import asyncio
import base64
import importlib.util
import json
import os
import struct
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
BRIDGE = REPO / "tools" / "build_map_bridge.py"
LOG = REPO / ".builder_queue" / "decision_log.jsonl"


def _load_bridge():
    spec = importlib.util.spec_from_file_location("bk58_bridge", BRIDGE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def bridge(tmp_path, monkeypatch):
    """Bridge module with the launch log redirected to a tmp file."""
    m = _load_bridge()
    monkeypatch.setattr(m, "LOG", tmp_path / "decision_log.jsonl")
    return m


def _bridge_records(tmp_path):
    p = tmp_path / "decision_log.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


# ------------------------------------------------------------------ L1/L2/L4
# dispatch level

def test_l1_refuses_unknown_class(bridge, tmp_path):
    r = bridge.dispatch("rm_rf_everything", {"x": 1})
    assert r["ok"] is False
    assert r["error"] == "unknown launch class"
    assert len(r["evidence_hash"]) == 16
    recs = _bridge_records(tmp_path)
    assert recs and recs[-1]["verdict"] == "refused:unknown_class"
    assert recs[-1]["kind"] == "bk58_bridge_launch"


def test_l2_glyphdbg_session_returns_real_output(bridge):
    r = bridge.dispatch("glyphdbg",
                        {"program": "LDI r5 42\nPRT r5\nHALT",
                         "max_steps": 10})
    assert r["ok"] is True
    assert 42 in r["output"]
    assert r["halted"] is True and r["faulted"] is False


def test_l2b_glyphdbg_validation_refusals(bridge):
    bad_control = bridge.dispatch("glyphdbg", {"program": "LDI r1 1\x00\x07x"})
    assert bad_control["ok"] is False
    bad_bound = bridge.dispatch("glyphdbg",
                                {"program": "HALT", "max_steps": 10**9})
    assert bad_bound["ok"] is False


def test_l4_every_launch_logged(bridge, tmp_path):
    bridge.dispatch("ping", {})
    bridge.dispatch("no_such_class", {})
    recs = _bridge_records(tmp_path)
    assert len(recs) >= 2
    verdicts = {r["verdict"] for r in recs}
    assert "ok" in verdicts and "refused:unknown_class" in verdicts
    for r in recs:
        assert len(r["evidence_hash"]) == 16
        assert r["kind"] == "bk58_bridge_launch"


# ------------------------------------------------------------------ L1/L2/L3
# real WebSocket level: spins the server's client-handler on a real
# localhost socket pair using the module's own frame codec.


async def _recv_json(r):
    two = await r.readexactly(2)
    n = two[1] & 0x7F
    if n == 126:
        n = struct.unpack(">H", await r.readexactly(2))[0]
    elif n == 127:
        n = struct.unpack(">Q", await r.readexactly(8))[0]
    return json.loads((await r.readexactly(n)).decode())


def test_ws_roundtrip_refuse_ok_isolate(bridge, monkeypatch):
    """L1+L2 over a real socket; L3 two interleaved sessions."""
    monkeypatch.setattr(bridge, "serve", lambda **kw: None)  # never block

    async def run():
        async def fake_server(reader, writer):
            await bridge.ws_client(reader, writer)

        server = await asyncio.start_server(fake_server, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]

        async def one_session(prog_val):
            r, w = await asyncio.open_connection("127.0.0.1", port)
            key = base64.b64encode(os.urandom(16)).decode()
            w.write((f"GET / HTTP/1.1\r\nHost: t\r\nUpgrade: websocket\r\n"
                     f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
                     f"Sec-WebSocket-Version: 13\r\n\r\n").encode())
            await w.drain()
            await r.readuntil(b"\r\n\r\n")

            async def send(obj):
                payload = json.dumps(obj).encode()
                mask = os.urandom(4)
                n = len(payload)
                if n < 126:
                    hdrb = bytes([0x81, 0x80 | n])
                else:
                    hdrb = bytes([0x81, 0x80 | 126]) + struct.pack(">H", n)
                w.write(hdrb + mask +
                        bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))
                await w.drain()

            await send({"class": "glyphdbg",
                        "params": {"program": f"LDI r5 {prog_val}\nPRT r5\nHALT",
                                   "max_steps": 10}})
            res = await _recv_json(r)
            await send({"class": "not_a_class", "params": {}})
            ref = await _recv_json(r)
            w.close()
            return res, ref

        results = await asyncio.gather(one_session(11), one_session(22))
        server.close()
        return results

    (res_a, ref_a), (res_b, ref_b) = asyncio.run(run())

    # L2: each session got its OWN program's output (isolation + real exec)
    assert res_a["ok"] and 11 in res_a["output"], res_a
    assert res_b["ok"] and 22 in res_b["output"], res_b
    # L1: refusals over the socket
    assert ref_a["ok"] is False and ref_b["ok"] is False
    assert ref_a["error"] == "unknown launch class"
