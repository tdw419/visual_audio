import sys
from pathlib import Path
sys.path.insert(0, str(Path("tools").resolve()))
from visual_audio_container import Container
import json

with Container("visual_audio.mkv") as c:
    names = [e["name"] for e in c.list() if "debate_log" in e["name"]]
    names.sort()
    for name in names:
        try:
            log = json.loads(c.read_text(name))
            if "11_8" in str(log):
                print(f"=== {name} ===")
                print(json.dumps(log, indent=2))
        except Exception as e:
            pass
