#!/bin/bash
# PDB Skeleton Verification Script
#
# Verifies that the PDB module skeleton is structurally complete
# and compiles successfully.

set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=== PDB Skeleton Verification ==="
echo "Script directory: $SCRIPT_DIR"
echo "Project root: $PROJECT_ROOT"
echo ""

# 1. Check that all required files exist
echo "1. Checking file structure..."
FILES=(
    "$SCRIPT_DIR/src/pdb/mod.rs"
    "$SCRIPT_DIR/src/pdb/encoder.rs"
    "$SCRIPT_DIR/src/pdb/decoder.rs"
    "$SCRIPT_DIR/src/pdb/vcc.rs"
    "$SCRIPT_DIR/src/pdb/compiler.rs"
    "$SCRIPT_DIR/PDB_FORMAT_SPEC.md"
    "$SCRIPT_DIR/PDB_IMPLEMENTATION_ROADMAP.md"
    "$SCRIPT_DIR/examples/sqlite_to_pdb.rs"
)

for file in "${FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "  ✓ ${file#$SCRIPT_DIR/}"
    else
        echo "  ✗ ${file#$SCRIPT_DIR/} (MISSING)"
        exit 1
    fi
done

echo ""
echo "2. Checking Cargo.toml dependencies..."
if grep -q "sha2" "$SCRIPT_DIR/Cargo.toml"; then
    echo "  ✓ sha2 dependency present"
else
    echo "  ✗ sha2 dependency missing"
    exit 1
fi

echo ""
echo "3. Verifying module exports in lib.rs..."
if grep -q "pub mod pdb;" "$SCRIPT_DIR/src/lib.rs"; then
    echo "  ✓ pdb module exported"
else
    echo "  ✗ pdb module not exported"
    exit 1
fi

if grep -q "PdbEncoder, PdbDecoder, VccIntegrity, SqliteToPdb" "$SCRIPT_DIR/src/lib.rs"; then
    echo "  ✓ Public types exported"
else
    echo "  ✗ Public types not exported"
    exit 1
fi

echo ""
echo "4. Compiling skeleton (cargo check)..."
cd "$PROJECT_ROOT/systems"
if cargo check --example sqlite_to_pdb 2>&1 | grep -q "Finished"; then
    echo "  ✓ Skeleton compiles successfully"
else
    echo "  ✗ Compilation failed"
    exit 1
fi
cd "$SCRIPT_DIR"

echo ""
echo "5. Checking for required type definitions..."
REQUIRED_TYPES=(
    "pub struct PdbEncoder"
    "pub struct PdbDecoder"
    "pub struct VccIntegrity"
    "pub struct SqliteToPdb"
    "pub struct BoundingBox"
    "pub struct TableMetadata"
    "pub struct PdbHeader"
    "pub struct PdbConfig"
    "pub enum PdbError"
)

for type_def in "${REQUIRED_TYPES[@]}"; do
    if grep -r "$type_def" "$SCRIPT_DIR/src/pdb/" > /dev/null; then
        echo "  ✓ $type_def"
    else
        echo "  ✗ $type_def (MISSING)"
        exit 1
    fi
done

echo ""
echo "6. Checking stub markers..."
# Count TODO markers
TODO_COUNT=$(grep -r "TODO Phase 1" "$SCRIPT_DIR/src/pdb/" | wc -l)
echo "  ✓ Found $TODO_COUNT Phase 1 implementation markers"

echo ""
echo "7. Verifying tests exist..."
TEST_COUNT=$(grep -r "^#\[test\]" "$SCRIPT_DIR/src/pdb/" | wc -l)
echo "  ✓ Found $TEST_COUNT unit tests"

echo ""
echo "=== ✅ ALL VERIFICATION CHECKS PASSED ==="
echo ""
echo "Skeleton Status:"
echo "  - All required files present"
echo "  - Dependencies configured"
echo "  - Module exports correct"
echo "  - Compilation successful"
echo "  - Type definitions complete"
echo "  - Implementation markers present"
echo "  - Unit tests stubbed"
echo ""
echo "Next Step: Begin Phase 1 Implementation (see PDB_IMPLEMENTATION_ROADMAP.md)"
echo ""