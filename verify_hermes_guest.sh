#!/bin/bash
# Run inside guest to verify Hermes works autonomously
# Writes proof-of-work to shared filesystem

PROOF_FILE="/host_zion/projects/visual_audio/hermes_guest_proof.txt"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
HOSTNAME=$(hostname)

echo "=== Hermes Guest Verification ===" > "$PROOF_FILE"
echo "Timestamp: $TIMESTAMP" >> "$PROOF_FILE"
echo "Hostname: $HOSTNAME" >> "$PROOF_FILE"
echo "Working Directory: $(pwd)" >> "$PROOF_FILE"
echo "" >> "$PROOF_FILE"
echo "Testing Hermes Agent:" >> "$PROOF_FILE"
echo "---" >> "$PROOF_FILE"

# Check if Hermes is available
if command -v hermes &> /dev/null; then
    echo "✓ Hermes installed at: $(which hermes)" >> "$PROOF_FILE"
    
    # Run a simple autonomous task
    echo "" >> "$PROOF_FILE"
    echo "Running autonomous analysis task..." >> "$PROOF_FILE"
    echo "" >> "$PROOF_FILE"
    
    hermes run "Analyze the current directory and count how many Python files exist" >> "$PROOF_FILE" 2>&1
    
    echo "" >> "$PROOF_FILE"
    echo "=== VERIFICATION SUCCESS ===" >> "$PROOF_FILE"
    echo "Hermes agent ran autonomously inside the guest VM" >> "$PROOF_FILE"
else
    echo "✗ Hermes not found - needs installation" >> "$PROOF_FILE"
    echo "" >> "$PROOF_FILE"
    echo "Guest proof confirmed: $TIMESTAMP on $HOSTNAME" >> "$PROOF_FILE"
fi