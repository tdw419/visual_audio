#!/usr/bin/env bash
set -e

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

# Check if any staged files touch fast-path core or decode tables
TOUCHED_FASTPATH=$(git diff --cached --name-only | grep -E '^(tools/SPATIAL_RV64I\.wgsl|tools/fastpath_core\.py|tools/rv64i_decode\.py|glyph_dispatch/src/riscv/)' || true)

if [ -n "$TOUCHED_FASTPATH" ]; then
    echo "============================================================"
    echo "PRE-COMMIT: Fast-path core or decode tables touched:"
    echo "$TOUCHED_FASTPATH"
    echo "Running regression gate..."
    echo "============================================================"
    python3 glyph_dispatch/tools/regression_gate.py --quick --output /tmp/regression_gate_receipt.json
    echo "============================================================"
    echo "PRE-COMMIT: Regression gate passed!"
    echo "============================================================"
else
    echo "PRE-COMMIT: No fast-path core files modified in staged changes."
fi

# Check if any staged files touch Glyph ISA, transpiler, or differential test suites
TOUCHED_GLYPH=$(git diff --cached --name-only | grep -E '^(tools/rv64i_to_glyph\.py|tools/glyph_isa_v2\.py|glyph_dispatch/src/glyph/|tests/test_rv64i_to_glyph.*|tests/test_glyph_isa_v2\.py)' || true)

if [ -n "$TOUCHED_GLYPH" ]; then
    echo "============================================================"
    echo "PRE-COMMIT: Glyph ISA or transpiler touched:"
    echo "$TOUCHED_GLYPH"
    echo "Verifying glyph_isa_v2.py synchronization..."
    if ! cmp -s tools/glyph_isa_v2.py glyph_dispatch/src/glyph/glyph_isa_v2.py; then
        echo "ERROR: tools/glyph_isa_v2.py and glyph_dispatch/src/glyph/glyph_isa_v2.py are out of sync!"
        exit 1
    fi
    echo "Running Glyph & Transpiler differential test suites..."
    echo "============================================================"
    # Glob, not a hand-maintained list: a hardcoded list silently stopped
    # running new primitives (proc-table, switch_to) the moment they landed
    # in a differently-named file -- caught while wiring switch_to in.
    # Tracked/staged files only, not a raw disk glob: an in-progress WIP
    # fixture sitting untracked in the working tree (failing on purpose,
    # mid-debug) must not block an unrelated staged commit from landing.
    GLYPH_TEST_FILES=$(git ls-files 'tests/test_rv64i_to_glyph*.py' 'tests/test_glyph_isa_v2.py')
    pytest $GLYPH_TEST_FILES -v
    echo "============================================================"
    echo "PRE-COMMIT: Glyph & Transpiler suites passed!"
    echo "============================================================"
else
    echo "PRE-COMMIT: No Glyph ISA/transpiler files modified in staged changes."
fi


# Check if any staged files touch the WGSL Glyph twin (3 copies must stay
# byte-identical - see tests/test_wgsl_triple_sync.py for the standing
# gate; that test also catches out-of-band drift this staged-files check
# can't see. Added 2026-09-16 after a 2.2a-era edit drifted for a full
# day undetected because every prior "twin synced" check here only ever
# looked at the Python glyph_isa_v2.py twin.)
TOUCHED_WGSL=$(git diff --cached --name-only | grep -E '^(tools/wgsl_glyph_isa_v2\.py|glyph_dispatch/src/wgsl_glyph_isa_v2\.py|glyph_dispatch/src/glyph/wgsl_glyph_isa_v2\.py)' || true)

if [ -n "$TOUCHED_WGSL" ]; then
    echo "============================================================"
    echo "PRE-COMMIT: WGSL Glyph twin touched:"
    echo "$TOUCHED_WGSL"
    echo "Verifying all 3 wgsl_glyph_isa_v2.py copies are in sync..."
    if ! cmp -s tools/wgsl_glyph_isa_v2.py glyph_dispatch/src/wgsl_glyph_isa_v2.py; then
        echo "ERROR: tools/wgsl_glyph_isa_v2.py and glyph_dispatch/src/wgsl_glyph_isa_v2.py are out of sync!"
        exit 1
    fi
    if ! cmp -s tools/wgsl_glyph_isa_v2.py glyph_dispatch/src/glyph/wgsl_glyph_isa_v2.py; then
        echo "ERROR: tools/wgsl_glyph_isa_v2.py and glyph_dispatch/src/glyph/wgsl_glyph_isa_v2.py are out of sync!"
        exit 1
    fi
    echo "PRE-COMMIT: WGSL twin sync verified!"
    echo "============================================================"
else
    echo "PRE-COMMIT: No WGSL Glyph twin files modified in staged changes."
fi

# Pillar 2.3 (GLYPH_ISA_ROADMAP.md §2.3): parity gate as a STANDING CI leg.
# Fires when EITHER engine changes (Python oracle or WGSL twin): the golden
# corpus re-runs both engines on every load-bearing dispatch surface, and
# its own RED probe proves a one-engine dispatch edit is caught. Added
# 2026-09-16 after 2.2a — the twin's syscall stub drifted from the Python
# engine silently; ad-hoc parity checks only ever ran when someone remembered.
TOUCHED_ENGINE=$(git diff --cached --name-only | grep -E '^(tools/glyph_isa_v2\.py|tools/wgsl_glyph_isa_v2\.py|glyph_dispatch/src/wgsl_glyph_isa_v2\.py|glyph_dispatch/src/glyph/wgsl_glyph_isa_v2\.py)' || true)

if [ -n "$TOUCHED_ENGINE" ]; then
    echo "============================================================"
    echo "PRE-COMMIT: Glyph engine surface touched (Pillar 2.3 parity-CI):"
    echo "$TOUCHED_ENGINE"
    echo "Running golden-corpus cross-engine parity gate..."
    echo "============================================================"
    python3 -m pytest tests/test_pillar23_parity_ci.py -q || {
        echo "ERROR: Pillar 2.3 parity gate FAILED — one-engine dispatch drift?"
        exit 1
    }
    echo "============================================================"
    echo "PRE-COMMIT: Pillar 2.3 parity gate passed!"
    echo "============================================================"
else
    echo "PRE-COMMIT: No engine files modified — Pillar 2.3 parity gate skipped."
fi
