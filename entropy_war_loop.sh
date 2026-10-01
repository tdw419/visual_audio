#!/bin/bash
# entropy_war_loop.sh -- Run the full Entropy War autonomous loop.

# Runs autonomous_seeder to issue directives, then directive_executor to
# execute them, repeating until a faction reaches 51% victory.

CONTAINER="${1:-visual_audio.mkv}"
INTERVAL="${2:-30}"

echo "=== Entropy War Autonomous Loop ==="
echo "Container: $CONTAINER"
echo "Loop interval: ${INTERVAL}s"
echo ""

while true; do
    echo "============================================================"
    date

    # Check for victory
    if python3 tools/faction_tracker.py status "$CONTAINER" 2>/dev/null | grep -q "structures=[0-9]*"; then
        python3 -c "
import sys
sys.path.insert(0, 'tools')
from visual_audio_container import Container
import json
c = Container('$CONTAINER')
try:
    gs = c.read_json('game_state')
    if gs.get('winner'):
        print('')
        print('='*60)
        print(f'  VICTORY: {gs[\"winner\"].upper()} WINS!')
        print(f'  Controls {gs[\"coverage\"]:.1%} of map')
        print('='*60)
        print('')
        sys.exit(0)
except KeyError:
    pass
sys.exit(1)
"
        if [ $? -eq 0 ]; then
            break
        fi
    fi

    # Seed directives
    echo ""
    python3 tools/autonomous_seeder.py "$CONTAINER" --once

    # Execute directives (with timeout to avoid hangs)
    echo ""
    echo "Executing directives..."
    timeout 60 python3 tools/directive_executor.py --container "$CONTAINER" --all || true

    echo ""
    echo "Sleeping ${INTERVAL}s until next cycle..."
    sleep "$INTERVAL"
done