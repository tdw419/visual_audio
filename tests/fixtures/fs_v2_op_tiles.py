"""tests/fixtures/fs_v2_op_tiles.py — Pinned, supply-verified tiles for Pixel-FS v2 operations.

Supply-verified: obtained from real pipeline execution / probes, confirmed via run_oracle.
Used by deterministic siblings in tests/test_gh20_fs_v2.py through the aa.escalate seam.
"""
from __future__ import annotations
import socket
from typing import Callable, Optional, Union

# ── FSV2_N_APPEND (SYS 10) ───────────────────────────────────────────────
FSV2_APPEND_TILE = """LDI r15 750
LD r1 r15
LDI r3 65
XOR r4 r4
CMP r1 r3
JZ :match
LDI r2 69
JMP :done
:match
LDI r15 1026
LD r5 r15
LDI r7 1
ADD r5 r7
ST r15 r5
XOR r2 r2
:done
LDI r15 754
ST r15 r2
HALT"""

# ── FSV2_N_RENAME (SYS 11) ───────────────────────────────────────────────
FSV2_RENAME_TILE = """LDI r15 750
LD r1 r15
LDI r3 65
XOR r4 r4
CMP r1 r3
JZ :match
LDI r2 69
JMP :done
:match
LDI r15 751
LD r5 r15
LDI r15 1024
ST r15 r5
XOR r2 r2
:done
LDI r15 754
ST r15 r2
HALT"""

# ── FSV2_N_UNLINK (SYS 12) ───────────────────────────────────────────────
FSV2_UNLINK_TILE = """LDI r15 750
LD r1 r15
LDI r3 65
XOR r4 r4
CMP r1 r3
JZ :match
LDI r2 69
JMP :done
:match
LDI r15 1028
LD r5 r15
XOR r6 r6
CMP r5 r6
JZ :ok
LDI r2 69
JMP :done
:ok
XOR r2 r2
:done
LDI r15 754
ST r15 r2
HALT"""


def dispatch_fs_tile_by_contract(task: str) -> str:
    """Dispatch the pinned supply-verified tile by contract text for the loop legs."""
    if "1026" in task:
        return FSV2_APPEND_TILE
    elif "751" in task:
        return FSV2_RENAME_TILE
    elif "1028" in task:
        return FSV2_UNLINK_TILE
    raise ValueError(f"Unknown FS contract task for pinned dispatch: {task[:100]}")


def install_fs_seam(monkeypatch, tile_or_dispatch: Optional[Union[str, Callable[[str], str]]] = None) -> list:
    """Installs socket connect guard and aa.escalate seam returning verified pinned tile.

    Returns the connect_attempts list which must be asserted to have length 0.
    """
    from tools.glyph_gpt import autoatlas as aa
    from tools.glyph_gpt.escalate import EscalationResult
    from tools.glyph_gpt.oracle import run_oracle

    connect_attempts = []

    def _guard_connect(self, address):
        connect_attempts.append(address)
        raise AssertionError(f"unexpected network connection attempt to {address}")

    monkeypatch.setattr(socket.socket, "connect", _guard_connect)

    def _fake_escalate(task, expect_registers=None, seed_memory=None,
                       input_registers=None, max_attempts=6, model="x",
                       extra_vectors=None):
        if callable(tile_or_dispatch):
            tile_text = tile_or_dispatch(task)
        elif isinstance(tile_or_dispatch, str):
            tile_text = tile_or_dispatch
        else:
            tile_text = dispatch_fs_tile_by_contract(task)

        ores = run_oracle(tile_text, expect_registers=expect_registers,
                          seed_memory=seed_memory, input_registers=input_registers)
        if ores.passed:
            return EscalationResult(
                contract=task, verified=True, attempts=1,
                glyph_text=tile_text, oracle=ores)
        return EscalationResult(
            contract=task, verified=False, attempts=1,
            glyph_text=None, oracle=ores, error=ores.error)

    monkeypatch.setattr(aa, "escalate", _fake_escalate)
    return connect_attempts
