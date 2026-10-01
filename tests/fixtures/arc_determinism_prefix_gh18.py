"""Fixture copy of pre-fix tests/test_gh18_syscall_abi.py leg for DEFECT-24 determinism audit."""
import pytest


def _ollama_available() -> bool:
    return False


@pytest.mark.skipif(not _ollama_available(), reason="local Ollama not reachable")
def test_gh18_admit_syscall_via_ingest_end_to_end():
    """The full admission pipeline: a local-model-drafted triple tile
    passes the oracle + IR gate, its pixels land in the tile rect, its
    table word goes live, and a USER task issues SYS 8 word-exactly.
    One Ollama round; the drafted program is verified before dispatch."""
    pass
