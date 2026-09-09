import bz2
import collections
import lzma
import struct
import zlib

import brotli

# tags
_RAW, _ZLIB, _LZMA, _BZ2, _PERIODIC, _BROTLI, _RECURSE, _BPE_LZMA = (
    0, 1, 2, 3, 4, 5, 6, 7,
)


def _find_period(data: bytes, max_period: int = 4096) -> int | None:
    """Smallest p such that data == (data[:p] repeated)[:len(data)], or None."""
    n = len(data)
    if n == 0:
        return None
    for p in range(1, min(max_period, n) + 1):
        if n % p != 0 and data[: n - n % p] != data[:p] * ((n - n % p) // p):
            continue
        head = data[:p]
        reps = -(-n // p)
        if (head * reps)[:n] == data:
            return p
    return None


def _bpe_merge(data: bytes, max_merges: int, min_count: int = 4):
    """Greedy byte-pair-encoding: repeatedly replace the most frequent
    adjacent byte pair with an unused byte code. This is a generic
    "grammar rule" extraction pass (learns the alphabet from the data
    itself, no hardcoded tokens) meant to run before a general-purpose
    compressor so it can find longer matches downstream.
    """
    used = set(data)
    free = [b for b in range(256) if b not in used]
    d = bytearray(data)
    merges = []
    for _ in range(min(max_merges, len(free))):
        if not free:
            break
        counts = collections.Counter(zip(d, d[1:]))
        if not counts:
            break
        (a, b), cnt = counts.most_common(1)[0]
        if cnt < min_count:
            break
        code = free.pop(0)
        merges.append((code, a, b))
        out = bytearray()
        i = 0
        n = len(d)
        while i < n:
            if i < n - 1 and d[i] == a and d[i + 1] == b:
                out.append(code)
                i += 2
            else:
                out.append(d[i])
                i += 1
        d = out
    return bytes(d), merges


def _bpe_unmerge(data: bytes, merges) -> bytes:
    d = bytearray(data)
    for code, a, b in reversed(merges):
        out = bytearray()
        for byte in d:
            if byte == code:
                out.append(a)
                out.append(b)
            else:
                out.append(byte)
        d = out
    return bytes(d)


def _best_bpe_lzma(data: bytes):
    """Try a handful of merge budgets (greedy BPE is non-monotonic, so a
    fixed constant overfits) and keep whichever total (merge table +
    compressed payload) is smallest.
    """
    best = None
    for max_merges in (16, 32, 48, 64):
        merged, merges = _bpe_merge(data, max_merges)
        if not merges:
            continue
        compressed = lzma.compress(merged, preset=9 | lzma.PRESET_EXTREME)
        table = bytes(byte for m in merges for byte in m)
        payload = bytes([len(merges)]) + table + compressed
        if best is None or len(payload) < len(best):
            best = payload
    return best


def encode(data: bytes) -> bytes:
    candidates = [(_RAW, data)]

    period = _find_period(data)
    if period is not None:
        header = struct.pack(">IH", len(data), period)
        candidates.append((_PERIODIC, header + data[:period]))

    candidates.append((_ZLIB, zlib.compress(data, 9)))
    candidates.append((_LZMA, lzma.compress(data, preset=9 | lzma.PRESET_EXTREME)))
    candidates.append((_BZ2, bz2.compress(data, 9)))
    candidates.append((_BROTLI, brotli.compress(data, quality=11)))

    bpe_payload = _best_bpe_lzma(data)
    if bpe_payload is not None:
        candidates.append((_BPE_LZMA, bpe_payload))

    tag, payload = min(candidates, key=lambda c: len(c[1]))

    # recursive pass: try squeezing the winning payload again (fixed-point:
    # only keep if it actually shrinks further)
    if tag not in (_PERIODIC, _BPE_LZMA):
        squeezed = lzma.compress(payload, preset=9 | lzma.PRESET_EXTREME)
        if len(squeezed) < len(payload):
            return bytes([_RECURSE, tag]) + squeezed

    return bytes([tag]) + payload


def _decode_tagged(tag: int, payload: bytes) -> bytes:
    if tag == _RAW:
        return payload
    if tag == _ZLIB:
        return zlib.decompress(payload)
    if tag == _LZMA:
        return lzma.decompress(payload)
    if tag == _BZ2:
        return bz2.decompress(payload)
    if tag == _BROTLI:
        return brotli.decompress(payload)
    if tag == _PERIODIC:
        length, period = struct.unpack(">IH", payload[:6])
        head = payload[6 : 6 + period]
        reps = -(-length // period)
        return (head * reps)[:length]
    if tag == _BPE_LZMA:
        n_merges = payload[0]
        table = payload[1 : 1 + n_merges * 3]
        merges = [
            (table[i], table[i + 1], table[i + 2]) for i in range(0, len(table), 3)
        ]
        compressed = payload[1 + n_merges * 3 :]
        merged = lzma.decompress(compressed)
        return _bpe_unmerge(merged, merges)
    raise ValueError(f"unknown tag {tag}")


def decode(blob: bytes) -> bytes:
    tag, payload = blob[0], blob[1:]
    if tag == _RECURSE:
        inner_tag, squeezed = payload[0], payload[1:]
        inner_payload = lzma.decompress(squeezed)
        return _decode_tagged(inner_tag, inner_payload)
    return _decode_tagged(tag, payload)
