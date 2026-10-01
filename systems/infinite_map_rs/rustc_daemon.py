#!/usr/bin/env python3
import subprocess
import json
import time
import os
from agent_bridge import SpatialCompositorClient

def parse_rustc_json(line):
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None

def run_daemon():
    client = SpatialCompositorClient()
    print("[*] Rustc Auto-Annotator Daemon started. Running cargo check...", flush=True)
    
    cmd = ["cargo", "check", "--message-format=json"]
    
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    
    current_annotations = []
    primary_error_msg = None
    
    try:
        for line in iter(process.stdout.readline, ''):
            if not line: continue
            msg = parse_rustc_json(line)
            if not msg: continue
                
            if msg.get("reason") == "compiler-message":
                diag = msg.get("message", {})
                level = diag.get("level")
                
                if level in ["error", "warning"]:
                    spans = diag.get("spans", [])
                    primary_span = next((s for s in spans if s.get("is_primary")), None)
                    
                    if primary_span:
                        if level == "error" and not primary_error_msg:
                            code_type = diag.get('code', {}).get('code', '') if diag.get('code') else ''
                            detailed_msg = diag.get('message', 'Error')
                            primary_error_msg = f"## Compiler Error {code_type}\n\n**{detailed_msg}**\n\n*Review the underlined span for context.*"
                        
                        line_start = primary_span.get("line_start", 1)
                        col_start = primary_span.get("column_start", 1)
                        col_end = primary_span.get("column_end", 1)
                        color = [1.0, 0.2, 0.3, 0.9] if level == "error" else [1.0, 0.8, 0.2, 0.9]
                        row_approx = (line_start % 40)
                        if row_approx == 0: row_approx = 40
                        
                        current_annotations.append({
                            "type": "span",
                            "node_id": "Node A (User Shell)",
                            "row": row_approx,
                            "col_start": col_start,
                            "col_end": col_end,
                            "color": color,
                            "underline": True
                        })
                        
                        callout_text = f"[{level}] {diag.get('message', 'Error')}"
                        current_annotations.append({
                            "type": "callout",
                            "node_id": "Node A (User Shell)",
                            "row": row_approx,
                            "col": col_end,
                            "text": callout_text,
                            "badge_color": [0.1, 0.1, 0.15, 0.95],
                            "border_color": color
                        })
                        
                        print(f"[{time.strftime('%H:%M:%S')}] Detected {level} at row {row_approx}, col {col_start}-{col_end}: {callout_text}", flush=True)
            
            elif msg.get("reason") == "build-finished":
                client.set_annotations(current_annotations)
                
                if primary_error_msg:
                    client.update_markdown(
                        node_id="rustc_explainer",
                        x=1.4,
                        y=0.0,
                        source=primary_error_msg
                    )
                    print(f"[{time.strftime('%H:%M:%S')}] Updated Markdown Explainer Node.", flush=True)
                else:
                    client.close_node("rustc_explainer")
                
                # Pan camera to the first error (if any)
                if len(current_annotations) > 0:
                    print(f"[{time.strftime('%H:%M:%S')}] Batch complete. Panning camera to user_sh once.", flush=True)
                    client.focus("user_sh", zoom=1.1)

                current_annotations = []
                primary_error_msg = None

    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    run_daemon()
