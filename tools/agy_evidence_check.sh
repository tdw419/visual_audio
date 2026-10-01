#!/usr/bin/env bash
# tools/agy_evidence_check.sh — detector for agy reply gate evidence
#
# Part of INSTRUMENT-2: agy wrapper DIFF SUMMARY recall fix.
#
# Contract:
# VERIFIED (exit 0) iff:
#   Literal block header "DIFF SUMMARY" is present
#   OR ALL of:
#     (a) a gate-command line (matches pytest / python3 -m pytest / -m pytest)
#     (b) a pytest-summary tail line (N passed / N failed / N xfailed / no tests ran)
#     (c) a changed-files section (git diff / git status / git diff --stat invocation or output)
# UNVERIFIED (exit 1) otherwise.
# Exit 2 on bad arguments or missing file.

set -euo pipefail

TARGET="${1:-}"
TMP_FILE=""

cleanup() {
    if [[ -n "$TMP_FILE" && -f "$TMP_FILE" ]]; then
        rm -f "$TMP_FILE"
    fi
}
trap cleanup EXIT

if [[ -n "$TARGET" && "$TARGET" != "-" ]]; then
    if [[ ! -f "$TARGET" ]]; then
        echo "agy_evidence_check: file not found: $TARGET" >&2
        exit 2
    fi
    FILE="$TARGET"
else
    TMP_FILE="$(mktemp /tmp/agy_evidence_check_XXXXXX)"
    cat > "$TMP_FILE"
    FILE="$TMP_FILE"
fi

# Fast path: literal "DIFF SUMMARY" block header
if grep -q "DIFF SUMMARY" "$FILE"; then
    exit 0
fi

# Three-part conjunction arm:
# (a) gate-command line (matches pytest, python3 -m pytest, -m pytest)
has_gate_cmd=0
if grep -qE '(-m[[:space:]]+pytest|\bpytest\b)' "$FILE"; then
    has_gate_cmd=1
fi

# (b) pytest-summary tail line (N passed / N failed / N xfailed / no tests ran)
has_pytest_tail=0
if grep -qE '([0-9]+[[:space:]]+(passed|failed|xfailed)|no tests ran)' "$FILE"; then
    has_pytest_tail=1
fi

# (c) changed-files section (git diff / git status / git diff --stat invocation or output)
has_changed_files=0
if grep -qE '(git[[:space:]]+(diff|status)|diff[[:space:]]+--git|[0-9]+[[:space:]]+files?[[:space:]]+changed)' "$FILE"; then
    has_changed_files=1
fi

if [[ $has_gate_cmd -eq 1 && $has_pytest_tail -eq 1 && $has_changed_files -eq 1 ]]; then
    exit 0
fi

exit 1
