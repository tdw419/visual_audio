#!/bin/bash
# verification_matrix.sh - Systematic verification of all claimed complete tasks

echo "=== Visual Audio Verification Matrix ==="
echo "Date: $(date -I)"
echo ""

# Tasks that are claimed COMPLETE but need verification
tasks=(
    "TASK_S001:test_phy.py:16-tone MFSK codec"
    "TASK_E001:test_spectral_ecc.py:Reed-Solomon ECC"
    "TASK_S002:test_synthesis_performance.py:UPIC vectorization"
    "TASK_R017:test_container_security.py:Container security"
    "TASK_W002:test_token_chord_codec.py:Test design (pytest decision)"
    "TASK_M004-M005:test_pixel_lm.py:Pixel LM"
    "TASK_VAC001-007:container:Container system"
    "TASK_C038:native_boot:Native pixel boot"
)

# Test commands for container-internal tasks
verify_container() {
    local task=$1
    local script=$2
    
    echo "  Verifying $task via container..."
    python3 tools/va_container.py run visual_audio.mkv "$script" 2>&1 | head -10
}

echo "## Direct Test Execution (HOST-ACCESSIBLE)"
echo ""

for entry in "${tasks[@]}"; do
    IFS=':' read -r task testfile desc <<< "$entry"
    
    if [ "$testfile" = "container" ] || [ "$testfile" = "native_boot" ]; then
        continue  # Skip container-internal tasks for now
    fi
    
    echo "### $task: $desc"
    echo "Test file: tests/$testfile"
    
    if [ -f "tests/$testfile" ]; then
        echo "Status: RUNNING"
        python3 -m pytest "tests/$testfile" -v --tb=no -q 2>&1 | tail -3
        echo ""
    else
        echo "Status: NOT FOUND"
        echo "Issue: Test file does not exist"
        echo "Action: Revert task to PENDING"
        echo ""
    fi
done

echo "## Container-Internal Tasks (NEED VERIFICATION)"
echo ""

for entry in "${tasks[@]}"; do
    IFS=':' read -r task testfile desc <<< "$entry"
    
    if [ "$testfile" = "container" ]; then
        echo "### $task: $desc"
        echo "Verification: python3 tools/va_container.py run visual_audio.mkv [script]"
        echo "Action: Need actual command to verify"
        echo ""
    fi
    
    if [ "$testfile" = "native_boot" ]; then
        echo "### $task: $desc"
        echo "Verification: Container run command needed"
        echo "Action: Need actual command to verify"
        echo ""
    fi
done

echo "## Phase 0 Test Coverage"
echo ""

phase0_tests=(
    "Phoneme codec:test_phoneme_codec.py"
    "Byte-level spectral codec:test_phy.py"
    "Dense pixel codec:test_dense_pixel_codec.py"
    "Dual-band concept:test_dual_band_roundtrip.py"
    "Canvas-based pixel OS:test_pixel_os_lm_input.py"
)

for entry in "${phase0_tests[@]}"; do
    IFS=':' read -r component testfile <<< "$entry"
    
    if [ -f "tests/$testfile" ]; then
        echo "✅ $component: $testfile EXISTS"
    else
        echo "❌ $component: $testfile NOT FOUND"
    fi
done

echo ""
echo "=== End Verification Matrix ==="