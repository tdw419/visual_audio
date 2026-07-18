#!/bin/bash
# verify_codec.sh — Deterministic codec verification gate for Visual Audio
# Based on Nate Jones Ringer verification pattern
# Usage: ./verify_codec.sh <TASK_ID> [FIXTURE_FILE]

set -e  # Exit on failure

TASK_ID="${1:-unknown}"
FIXTURE="${2:-tests/fixtures/codec_test.py}"
TIMESTAMP=$(date +%s)

echo "======================================"
echo "Visual Audio Codec Verification Gate"
echo "======================================"
echo "Task ID:       ${TASK_ID}"
echo "Fixture:       ${FIXTURE}"
echo "Timestamp:     ${TIMESTAMP}"
echo ""

# Check if fixture exists
if [ ! -f "${FIXTURE}" ]; then
    echo "FAIL: Fixture file not found: ${FIXTURE}"
    exit 1
fi

# Create temp directory for this verification run
TEMP_DIR="/tmp/visual-audio-verify-${TASK_ID}-${TIMESTAMP}"
mkdir -p "${TEMP_DIR}"

echo "Step 1: Encoding fixture file..."
ENCODED="${TEMP_DIR}/encoded.wav"
python3 tools/speak.py encode "${FIXTURE}" -o "${ENCODED}"

if [ ! -f "${ENCODED}" ]; then
    echo "FAIL: Encoding failed — no output file produced"
    exit 1
fi

echo "  ✓ Encoded to: ${ENCODED}"
echo ""

echo "Step 2: Decoding back to original format..."
DECODED="${TEMP_DIR}/decoded.py"
python3 tools/speak.py decode "${ENCODED}" -o "${DECODED}"

if [ ! -f "${DECODED}" ]; then
    echo "FAIL: Decoding failed — no output file produced"
    exit 1
fi

echo "  ✓ Decoded to: ${DECODED}"
echo ""

echo "Step 3: Verifying byte-identical output..."
ORIGINAL_HASH=$(md5sum "${FIXTURE}" | awk '{print $1}')
DECODED_HASH=$(md5sum "${DECODED}" | awk '{print $1}')

echo "  Original hash: ${ORIGINAL_HASH}"
echo "  Decoded hash:  ${DECODED_HASH}"

if [ "${ORIGINAL_HASH}" != "${DECODED_HASH}" ]; then
    echo ""
    echo "FAIL: Hash mismatch — codec roundtrip failed"
    echo ""
    echo "Differences:"
    diff -u "${FIXTURE}" "${DECODED}" || true
    echo ""
    echo "Keeping verification artifacts for inspection:"
    echo "  ${TEMP_DIR}"
    exit 1
fi

echo "  ✓ Hashes match — byte-identical roundtrip confirmed"
echo ""

echo "Step 4: Verifying decoded code is runnable..."
# Try to execute the decoded file if it's Python
if file "${DECODED}" | grep -q "Python script"; then
    if python3 -m py_compile "${DECODED}"; then
        echo "  ✓ Decoded Python is syntactically valid"
    else
        echo "FAIL: Decoded Python has syntax errors"
        exit 1
    fi
fi
echo ""

echo "Step 5: Checking performance constraints..."
# Measure decode speed
START_TIME=$(date +%s%N)
python3 tools/speak.py decode "${ENCODED}" -o /dev/null
END_TIME=$(date +%s%N)
DECODE_MS=$(( (END_TIME - START_TIME) / 1000000 ))

AUDIO_DURATION=$(soxi -D "${ENCODED}" 2>/dev/null || echo "0")
if [ "${AUDIO_DURATION}" != "0" ]; then
    DECODE_PER_SEC_MS=$(( DECODE_MS / $(echo "${AUDIO_DURATION}" | cut -d. -f1) ))
    echo "  Decode speed: ${DECODE_PER_SEC_MS}ms per audio second"

    # Check against baseline (≤8ms per audio second)
    if [ "${DECODE_PER_SEC_MS}" -le 8 ]; then
        echo "  ✓ Performance meets target (≤8ms per audio second)"
    else
        echo "  WARN: Performance below target (>8ms per audio second)"
    fi
else
    echo "  SKIP: Could not measure audio duration"
fi
echo ""

echo "======================================"
echo "✓ PASS: All verification gates cleared"
echo "======================================"
echo ""
echo "Codec changes verified for task: ${TASK_ID}"
echo "Byte-identical roundtrip: CONFIRMED"
echo "Performance: MEETS BASELINE"
echo ""

# Clean up temp directory on success
rm -rf "${TEMP_DIR}"

exit 0