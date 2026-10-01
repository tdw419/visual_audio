"""Normalized 32-bit word equality assertion helper for Glyph OS test suites.

Eliminates signed/unsigned (e.g. -1 vs 0xFFFFFFFF), char/int (e.g. 'E' vs 69),
and numpy uint32 vs python int discrepancies with clear diagnostic formatting.
"""

from typing import Any, Optional


def to_word(val: Any) -> int:
    """Normalize any value to an unsigned 32-bit integer."""
    if val is None:
        return 0
    if isinstance(val, str):
        if len(val) == 1:
            return ord(val)
        val = int(val, 0)
    elif isinstance(val, bytes):
        if len(val) == 1:
            return val[0]
        if len(val) == 4:
            import struct
            return struct.unpack("<I", val)[0]
        raise ValueError(f"Cannot convert bytes of length {len(val)} to word: {val!r}")

    val = int(val)
    return val & 0xFFFFFFFF


def assert_word_eq(
    actual: Any,
    expected: Any,
    msg: str = "",
    word_addr: Optional[int] = None,
) -> None:
    """Assert actual == expected as unsigned 32-bit words."""
    act_u = to_word(actual)
    exp_u = to_word(expected)
    if act_u != exp_u:
        addr_str = f" at word {word_addr} (0x{word_addr*4:04x})" if word_addr is not None else ""
        detail = (
            f"Word mismatch{addr_str}:\n"
            f"  Expected: 0x{exp_u:08x} ({exp_u}"
            + (f", signed {exp_u - 0x100000000}" if exp_u >= 0x80000000 else "")
            + (f", chr {chr(exp_u)!r}" if 32 <= exp_u <= 126 else "")
            + ")\n"
            f"  Actual:   0x{act_u:08x} ({act_u}"
            + (f", signed {act_u - 0x100000000}" if act_u >= 0x80000000 else "")
            + (f", chr {chr(act_u)!r}" if 32 <= act_u <= 126 else "")
            + ")"
        )
        if msg:
            detail = f"{msg}\n{detail}"
        raise AssertionError(detail)


if __name__ == "__main__":
    # Self-test
    assert to_word(-1) == 0xFFFFFFFF
    assert to_word("E") == 69
    assert to_word(b"A") == 65
    assert_word_eq(-1, 0xFFFFFFFF)
    assert_word_eq("E", 69)
    print("assert_word_eq self-tests PASS")
