#!/usr/bin/env bash
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
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

