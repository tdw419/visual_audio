"""tests/fixtures/faulthandler_segv_fixture.py — deterministic SIGSEGV fixture for DEFECT-22 live capture gate."""
import ctypes
import faulthandler
import sys

faulthandler.enable()
print("FAULTHANDLER_SEGV_FIXTURE_SENTINEL", flush=True)
ctypes.string_at(0)
