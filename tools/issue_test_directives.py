import sys
from pathlib import Path
sys.path.insert(0, str(Path("tools").resolve()))

from visual_audio_container import Container
from village_center_handler import issue_directive

with Container("visual_audio.mkv") as c:
    # Issue build for Red (8_8)
    issue_directive(c, "user_test", "village_center.py.8_8", "build", {"target_x": 50, "target_y": 50, "structure": "watchtower"})
    # Issue build for Blue (10_8)
    issue_directive(c, "user_test", "village_center.py.10_8", "build", {"target_x": 50, "target_y": 50, "structure": "watchtower"})

print("Directives issued.")
