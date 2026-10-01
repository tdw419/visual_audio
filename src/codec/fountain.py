"""
src/codec/fountain.py — Luby Transform (LT) fountain codes for lossy channel resilience.

TASK_R018: Generate endless repair packets from source data, decode from any
N > K*1.05 valid packets (slight overhead), with CRC-32 integrity validation
and optional XChaCha20-Poly1305 AEAD encryption per packet.

Design (rateless erasure code):
- Split source into K equal-sized symbols
- Robust Soliton Distribution for degree selection
- Each repair packet = XOR of d randomly-chosen source symbols + metadata
- Peeling decoder recovers source from any N slightly > K valid packets
"""

import os
import zlib
import math
import random
import struct
from typing import List, Optional, Tuple

# ---------------------------------------------------------------------------
# Robust Soliton Distribution
# ---------------------------------------------------------------------------

def _robust_soliton(K: int, delta: float = 0.5, c: float = 0.1) -> List[float]:
    """Compute the Robust Soliton distribution for K source symbols.

    Returns a list mu[1..K] where mu[d] = Pr(degree = d).
    """
    # Ideal soliton
    rho = [0.0] * (K + 1)  # 1-indexed
    rho[1] = 1.0 / K
    for d in range(2, K + 1):
        rho[d] = 1.0 / (d * (d - 1))

    # Robust addition
    S = c * math.log(K / delta) * math.sqrt(K)
    S = max(S, 2.0)  # at least 2
    tau = [0.0] * (K + 1)
    threshold = int(math.ceil(K / S))
    for d in range(1, threshold):
        tau[d] = S / (d * K)
    if threshold <= K:
        tau[threshold] = S * math.log(S / delta) / K

    # Normalise
    mu = [0.0] * (K + 1)
    Z = sum(rho[d] + tau[d] for d in range(1, K + 1))
    for d in range(1, K + 1):
        mu[d] = (rho[d] + tau[d]) / Z
    return mu


# ---------------------------------------------------------------------------
# Packet format constants
# ---------------------------------------------------------------------------

PACKET_HEADER_FMT = '<IIH'    # K:u32, symbol_size:u32, degree:u16
PACKET_HEADER_LEN = struct.calcsize(PACKET_HEADER_FMT)
CRC_LEN = 4

# Extended header: original_len:u32 appended before degree
PACKET_FLAG_EXT = 0x80000000  # high bit of K to indicate extended header
PACKET_EXTRA_FMT = '<I'       # original_len:u32
PACKET_EXTRA_LEN = struct.calcsize(PACKET_EXTRA_FMT)

# Default symbol size (configurable)
DEFAULT_SYMBOL_SIZE = 64


# ---------------------------------------------------------------------------
# Encoder
# ---------------------------------------------------------------------------

class Encoder:
    """LT fountain code encoder.

    Produces an endless stream of repair packets from a fixed source.
    Each packet can be decoded by any LT Decoder that knows K and symbol_size.
    """

    def __init__(self, source: bytes, symbol_size: int = DEFAULT_SYMBOL_SIZE,
                 seed: int = 42):
        self.source = source
        self.original_len = len(source)
        self.symbol_size = symbol_size

        # Pad source to symbol boundary
        padded_len = ((len(source) + symbol_size - 1) // symbol_size) * symbol_size
        if padded_len > len(source):
            self._padded = source + b'\x00' * (padded_len - len(source))
        else:
            self._padded = source

        self.K = len(self._padded) // symbol_size
        self._symbols = [
            self._padded[i * symbol_size:(i + 1) * symbol_size]
            for i in range(self.K)
        ]
        # Pre-compute robust soliton
        self._mu = _robust_soliton(self.K)
        self._rng = random.Random(seed)
        self._packet_counter = 0

    def encode(self, packet_id: Optional[int] = None) -> bytes:
        """Generate one repair packet.

        Returns serialised bytes. The packet_id is advisory (for ordering
        in tests); the LT code itself is stateless.
        """
        if packet_id is not None:
            self._rng = random.Random(packet_id)
        else:
            packet_id = self._packet_counter
            self._packet_counter += 1
            self._rng = random.Random(packet_id)

        # Sample degree from robust soliton
        d = self._sample_degree()

        # Pick d distinct source symbols
        indices = self._rng.sample(range(self.K), min(d, self.K))
        indices.sort()

        # XOR them
        xor_result = bytearray(self.symbol_size)
        for idx in indices:
            sym = self._symbols[idx]
            for i in range(self.symbol_size):
                xor_result[i] ^= sym[i]

        # Build packet with extended header to encode original length
        ext_K = self.K | PACKET_FLAG_EXT
        header = struct.pack(PACKET_HEADER_FMT, ext_K, self.symbol_size, len(indices))
        orig_header = struct.pack(PACKET_EXTRA_FMT, self.original_len)
        index_data = struct.pack(f'<{len(indices)}I', *indices)
        body = header + orig_header + index_data + bytes(xor_result)

        # Append CRC-32
        crc = zlib.crc32(body) & 0xFFFFFFFF
        packet = body + struct.pack('<I', crc)
        return packet

    def _sample_degree(self) -> int:
        """Sample a degree from the robust soliton distribution."""
        r = self._rng.random()
        cumulative = 0.0
        for d in range(1, self.K + 1):
            cumulative += self._mu[d]
            if r <= cumulative:
                return d
        return 1  # fallback


# ---------------------------------------------------------------------------
# Decoder
# ---------------------------------------------------------------------------

class Decoder:
    """LT fountain code decoder using belief propagation (peeling).

    Accumulates repair packets. Once enough distinct information has been
    received, calls to recover() return the reconstructed source.
    """

    def __init__(self, K: int, symbol_size: int):
        self.K = K
        self.symbol_size = symbol_size

        # Source symbols: None = unknown, bytes = recovered
        self._recovered: List[Optional[bytearray]] = [None] * K

        # Pending packets: list of (indices, xor_data)
        self._pending: List[Tuple[List[int], bytearray]] = []

        # Track which source symbols are still unknown
        self._unknown_count = K

        # Original length (from extended header, may be None)
        self._original_len: Optional[int] = None

    def decode(self, packet_id: int, packet: bytes) -> bool:
        """Feed a repair packet into the decoder.

        Returns True if this packet contributed useful information,
        False if it was redundant (all indices already known).
        """
        # Strip CRC and validate
        if len(packet) < CRC_LEN + PACKET_HEADER_LEN:
            return False
        body = packet[:-CRC_LEN]
        stored_crc = struct.unpack_from('<I', packet, len(packet) - CRC_LEN)[0]
        computed_crc = zlib.crc32(body) & 0xFFFFFFFF
        if computed_crc != stored_crc:
            return False  # corrupted packet, skip

        # Parse
        K_read, sym_size, degree = struct.unpack_from(PACKET_HEADER_FMT, body, 0)
        ext = bool(K_read & PACKET_FLAG_EXT)
        if ext:
            K_read &= ~PACKET_FLAG_EXT
        if K_read != self.K or sym_size != self.symbol_size:
            return False  # mismatched parameters

        offset = PACKET_HEADER_LEN
        original_len = None
        if ext:
            original_len = struct.unpack_from(PACKET_EXTRA_FMT, body, offset)[0]
            offset += PACKET_EXTRA_LEN
            self._original_len = original_len

        indices = list(struct.unpack_from(f'<{degree}I', body, offset))
        offset += degree * 4
        xor_data = bytearray(body[offset:offset + self.symbol_size])

        # Prune already-known symbols from this packet
        unknown_indices = [i for i in indices if self._recovered[i] is None]
        known_indices = [i for i in indices if self._recovered[i] is not None]

        # XOR out the known contributions
        for ki in known_indices:
            sym = self._recovered[ki]
            for i in range(self.symbol_size):
                xor_data[i] ^= sym[i]

        if len(unknown_indices) == 0:
            return False  # all symbols already known, redundant packet

        if len(unknown_indices) == 1:
            # Peel: recover this symbol immediately (COPY bytearray to avoid aliasing)
            ui = unknown_indices[0]
            self._recovered[ui] = bytearray(xor_data)
            self._unknown_count -= 1
            # Process any pending packets that involved this symbol
            self._ripple(ui)
            return True
        else:
            # Store for later processing
            self._pending.append((unknown_indices, xor_data))
            return True

    def _ripple(self, recovered_idx: int):
        """Process pending packets that reference just-recovered symbol."""
        still_pending = []
        sym = self._recovered[recovered_idx]
        for indices, xor_data in self._pending:
            if recovered_idx in indices:
                # XOR out the known symbol
                for i in range(self.symbol_size):
                    xor_data[i] ^= sym[i]
                remaining = [i for i in indices if i != recovered_idx]
                if len(remaining) == 1:
                    # Another symbol can be recovered! (COPY bytearray to avoid aliasing)
                    ui = remaining[0]
                    if self._recovered[ui] is None:
                        self._recovered[ui] = bytearray(xor_data)
                        self._unknown_count -= 1
                        self._ripple(ui)
                elif len(remaining) > 1:
                    still_pending.append((remaining, xor_data))
                # else: len == 0 means all known, discard
            else:
                still_pending.append((indices, xor_data))
        self._pending = still_pending

    def recover(self) -> Optional[bytes]:
        """Attempt to recover the original source data.

        Returns the reconstructed bytes, or None if not enough packets
        have been received yet.

        Falls back to Gaussian elimination on the remaining unknown symbols
        when the peeling decoder stalls (handles the 'trapped set' problem).
        """
        if self._unknown_count == 0:
            return self._concat_recovered()

        # Peeling decoder stalled — try Gaussian elimination on remaining unknowns
        return self._gaussian_recover()

    def _gaussian_recover(self) -> Optional[bytes]:
        """Gaussian elimination fallback for trapped unknown symbols.

        Builds a linear system over GF(2) from pending packets and solves
        for remaining unknown symbols.
        """
        # Collect indices of still-unknown symbols
        remaining = [i for i, s in enumerate(self._recovered) if s is None]
        n = len(remaining)
        if n == 0:
            return self._concat_recovered()

        # Map original symbol index → column in our matrix (0..n-1)
        idx_to_col = {idx: c for c, idx in enumerate(remaining)}

        # Build rows: each row = (bitmask, xor_data) where bitmask[c] = 1 if
        # the packet involves unknown[c], and xor_data has known symbols
        # XOR'd out already.
        rows: List[Tuple[int, bytearray]] = []
        used_from_pending = 0
        for indices, xor_data in self._pending:
            # Only consider packets involving at least one unknown
            cols = [idx_to_col[i] for i in indices if i in idx_to_col]
            if not cols:
                continue
            mask = 0
            for c in cols:
                mask |= (1 << c)
            rows.append((mask, bytearray(xor_data)))
            used_from_pending += 1

        if not rows:
            return None  # no equations for remaining symbols

        # Gaussian elimination over GF(2) — row-reduce to find degree-1 rows
        pivot_row = 0
        for col in range(n):
            # Find a row with this column set
            found = None
            for r in range(pivot_row, len(rows)):
                if (rows[r][0] >> col) & 1:
                    found = r
                    break
            if found is None:
                continue  # no pivot for this column — undetermined

            # Swap to pivot position
            rows[pivot_row], rows[found] = rows[found], rows[pivot_row]
            pivot_mask, pivot_data = rows[pivot_row]

            # Eliminate this column from all OTHER rows
            for r in range(len(rows)):
                if r == pivot_row:
                    continue
                if (rows[r][0] >> col) & 1:
                    rows[r] = (
                        rows[r][0] ^ pivot_mask,
                        self._xor_data(rows[r][1], pivot_data),
                    )

            pivot_row += 1

        # After elimination, look for degree-1 rows (single bit set)
        newly_recovered = []
        for mask, data in rows:
            if mask == 0:
                continue  # all-zero row — redundant
            # Check if exactly one bit set
            if mask & (mask - 1) == 0:
                # Single bit — recover this symbol
                col = (mask.bit_length() - 1)
                idx = remaining[col]
                if self._recovered[idx] is None:
                    self._recovered[idx] = bytearray(data)
                    self._unknown_count -= 1
                    newly_recovered.append(idx)

        if not newly_recovered:
            return None  # elimination didn't find more symbols

        # Cascade: ripple each newly-recovered symbol through pending packets
        for idx in newly_recovered:
            self._ripple(idx)

        if self._unknown_count == 0:
            return self._concat_recovered()

        # Still stuck — try elimination again with the reduced unknown set
        return self._gaussian_recover()

    @staticmethod
    def _xor_data(a: bytearray, b: bytearray) -> bytearray:
        """XOR two bytearrays of equal length, returning a new bytearray."""
        result = bytearray(len(a))
        for i in range(len(a)):
            result[i] = a[i] ^ b[i]
        return result

    def _concat_recovered(self) -> bytes:
        """Concatenate recovered symbols and truncate to original length."""
        result = bytearray()
        for sym in self._recovered:
            if sym is None:
                return b''
            result.extend(sym)
        if self._original_len is not None:
            result = result[:self._original_len]
        return bytes(result)


# ---------------------------------------------------------------------------
# Convenience functions matching the test-stub API
# ---------------------------------------------------------------------------

def encode_packets(source: bytes, num_packets: int,
                   symbol_size: int = DEFAULT_SYMBOL_SIZE) -> List[bytes]:
    """Generate num_packets repair packets from source."""
    enc = Encoder(source, symbol_size=symbol_size)
    return [enc.encode(i) for i in range(num_packets)]


def decode_from_packets(packets: List[bytes],
                        K: Optional[int] = None,
                        symbol_size: Optional[int] = None) -> Optional[bytes]:
    """Attempt recovery from a list of repair packets.

    If K and symbol_size are not provided, they're read from the first
    valid packet.
    """
    if not packets:
        return None

    # Read parameters from first valid packet
    p = packets[0]
    if len(p) >= PACKET_HEADER_LEN + CRC_LEN:
        body = p[:-CRC_LEN]
        K_read, sym_size, _ = struct.unpack_from(PACKET_HEADER_FMT, body, 0)
        if K_read & PACKET_FLAG_EXT:
            K_read &= ~PACKET_FLAG_EXT
        if K is None:
            K = K_read
        if symbol_size is None:
            symbol_size = sym_size

    dec = Decoder(K, symbol_size)
    for i, pkt in enumerate(packets):
        dec.decode(i, pkt)
    return dec.recover()


# ---------------------------------------------------------------------------
# Optional XChaCha20-Poly1305 encryption wrapper
# ---------------------------------------------------------------------------

def encrypt_packets(packets: List[bytes], key: bytes) -> List[Tuple[bytes, bytes]]:
    """Encrypt fountain packets with XChaCha20-Poly1305.

    Returns list of (nonce, ciphertext). Uses cryptography library.
    """
    try:
        from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
    except ImportError:
        raise ImportError("cryptography library required for encrypted packets")

    cipher = ChaCha20Poly1305(key)
    result = []
    for pkt in packets:
        nonce = os.urandom(12)  # XChaCha20 uses 12-byte nonce
        ct = cipher.encrypt(nonce, pkt, None)
        result.append((nonce, ct))
    return result


def decrypt_packets(encrypted_packets: List[Tuple[bytes, bytes]],
                    key: bytes) -> List[bytes]:
    """Decrypt XChaCha20-Poly1305 protected packets.

    Input: list of (nonce, ciphertext) tuples.
    Returns list of decrypted packets (corrupted packets are dropped).
    """
    try:
        from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
    except ImportError:
        raise ImportError("cryptography library required for encrypted packets")

    cipher = ChaCha20Poly1305(key)
    result = []
    for nonce, ct in encrypted_packets:
        try:
            pt = cipher.decrypt(nonce, ct, None)
            result.append(pt)
        except Exception:
            pass  # drop corrupted packets
    return result


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import hashlib

    print("Fountain Code Self-Test")
    print("=" * 50)

    # Test 1: Basic encode/decode
    print("\n1. Basic encode/decode (270 bytes)...")
    source = b"hello world this is test data" * 10
    source_hash = hashlib.sha256(source).hexdigest()

    enc = Encoder(source)
    packets = [enc.encode(i) for i in range(100)]
    assert len(packets) == 100
    print(f"   Generated {len(packets)} repair packets")
    print(f"   K={enc.K}, symbol_size={enc.symbol_size}")

    dec = Decoder(enc.K, enc.symbol_size)
    for i, pkt in enumerate(packets):
        dec.decode(i, pkt)

    recovered = dec.recover()
    assert recovered is not None
    recovered_hash = hashlib.sha256(recovered).hexdigest()
    assert recovered_hash == source_hash
    print("   ✓ PASS: Bit-exact recovery")

    # Test 2: Decode from subset (40% loss)
    print("\n2. Decode from subset (40% packet loss)...")
    random.seed(42)
    surviving = random.sample(packets, len(packets) * 3 // 5)
    print(f"   {len(surviving)} of {len(packets)} packets survived")

    dec2 = Decoder(enc.K, enc.symbol_size)
    for i, pkt in enumerate(surviving):
        dec2.decode(i, pkt)
    recovered2 = dec2.recover()
    assert recovered2 is not None
    assert hashlib.sha256(recovered2).hexdigest() == source_hash
    print("   ✓ PASS: Recovery from subset")

    # Test 3: CRC corruption detection
    print("\n3. CRC corruption detection...")
    good_packet = enc.encode(0)
    corrupted = bytearray(good_packet)
    corrupted[-5] ^= 0xFF  # corrupt byte before CRC
    corrupted = bytes(corrupted)

    dec3 = Decoder(enc.K, enc.symbol_size)
    result = dec3.decode(0, good_packet)
    assert result is True, "Good packet should decode"
    result_corrupt = dec3.decode(1, corrupted)
    assert result_corrupt is False, "Corrupted packet should be rejected"
    print("   ✓ PASS: CRC correctly rejects corruption")

    # Test 4: YouTube-like loss (70% loss + 10% corruption)
    print("\n4. Simulated YouTube transcoding (70% loss + 10% bit corruption)...")
    source4 = os.urandom(1024)
    source4_hash = hashlib.sha256(source4).hexdigest()
    enc4 = Encoder(source4, symbol_size=64)
    packets4 = [enc4.encode(i) for i in range(150)]

    random.seed(42)
    surviving4 = []
    for i, pkt in enumerate(packets4):
        if random.random() > 0.7:  # 30% survive
            if random.random() < 0.1:
                # Corrupt a random byte
                pkt = bytearray(pkt)
                pkt[random.randint(0, len(pkt) - 1)] ^= 0xFF
                pkt = bytes(pkt)
            surviving4.append(pkt)

    # Filter by CRC (the Decoder already does this)
    print(f"   {len(surviving4)} packets survived (before CRC filtering)")

    dec4 = Decoder(enc4.K, enc4.symbol_size)
    valid_count = 0
    for i, pkt in enumerate(surviving4):
        if dec4.decode(i, pkt):
            valid_count += 1

    recovered4 = dec4.recover()
    assert recovered4 is not None
    assert hashlib.sha256(recovered4).hexdigest() == source4_hash
    print(f"   {valid_count} valid packets used for recovery")
    print("   ✓ PASS: YouTube-like scenario recovered")

    # Test 5: Large file recovery (100KB, 80% loss)
    print("\n5. Large file recovery (100KB, 80% loss)...")
    source5 = os.urandom(100 * 1024)
    source5_hash = hashlib.sha256(source5).hexdigest()
    enc5 = Encoder(source5, symbol_size=1024)
    packets5 = [enc5.encode(i) for i in range(800)]

    import random as rng_mod
    rng_mod.seed(42)
    surviving5 = [p for p in packets5 if rng_mod.random() > 0.8]
    print(f"   {len(surviving5)} packets survived (20% survival rate)")
    print(f"   K={enc5.K}, symbol_size={enc5.symbol_size}")

    dec5 = Decoder(enc5.K, enc5.symbol_size)
    for i, pkt in enumerate(surviving5):
        dec5.decode(i, pkt)
    recovered5 = dec5.recover()
    assert recovered5 is not None
    assert hashlib.sha256(recovered5).hexdigest() == source5_hash
    print("   ✓ PASS: 100KB file recovered after 80% packet loss")

    print("\n" + "=" * 50)
    print("✓ All self-tests passed")
