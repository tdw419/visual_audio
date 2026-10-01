#!/usr/bin/env python3
"""
QEMU Desktop Driver for AI Agents
Provides headless, programmatic control over a QEMU VM's mouse, keyboard, and screen.
"""

import os
import time
import json
import argparse
import subprocess
import tempfile

SOCKET_PATH = "/tmp/qemu-monitor.sock"
UI_MAP_PATH = os.path.join(os.path.dirname(__file__), "ui_map.json")

def send_monitor_command(cmd: str):
    if not os.path.exists(SOCKET_PATH):
        raise FileNotFoundError(f"QEMU Monitor socket not found at {SOCKET_PATH}")
    socat_cmd = f'echo "{cmd}" | socat - UNIX-CONNECT:{SOCKET_PATH}'
    result = subprocess.run(socat_cmd, shell=True, capture_output=True, text=True)
    return result.stdout

def capture_screen(output_path="/tmp/guest-display.png"):
    with tempfile.TemporaryDirectory() as tmpdir:
        ppm_path = os.path.join(tmpdir, "screen.ppm")
        send_monitor_command(f"screendump {ppm_path}")
        time.sleep(0.2)
        if not os.path.exists(ppm_path) or os.path.getsize(ppm_path) == 0:
            raise RuntimeError("Failed to capture screendump. PPM file is missing or empty.")
        subprocess.run(['convert', ppm_path, output_path], check=True)
        print(f"Screenshot saved to {output_path}")

def send_key(key: str):
    send_monitor_command(f"sendkey {key}")

def type_text(text: str):
    char_map = {' ': 'spc', '-': 'minus', '=': 'equal', '[': 'bracket_left', ']': 'bracket_right', ';': 'semicolon', "'": 'apostrophe', ',': 'comma', '.': 'dot', '/': 'slash', '\\': 'backslash', '\n': 'ret', '\t': 'tab'}
    shift_map = {'!':'1', '@':'2', '#':'3', '$':'4', '%':'5', '^':'6', '&':'7', '*':'8', '(':'9', ')':'0', '_':'minus', '+':'equal', ':':'semicolon', '"':'apostrophe', '<':'comma', '>':'dot', '?':'slash', '|':'backslash'}
    
    for char in text:
        if char.isupper():
            key = f"shift-{char.lower()}"
        elif char in char_map:
            key = char_map[char]
        elif char.isalnum():
            key = char
        elif char in shift_map:
            key = f"shift-{shift_map[char]}"
        else:
            continue
        send_key(key)
        time.sleep(0.05)

def mouse_move(dx: int, dy: int):
    send_monitor_command(f"mouse_move {dx} {dy}")

def mouse_move_absolute(x: int, y: int):
    """
    Hack for HMP: Move extremely far negative to pin the cursor at (0,0),
    then move positively to the desired absolute (x, y).
    """
    send_monitor_command("mouse_move -10000 -10000")
    time.sleep(0.1)
    send_monitor_command(f"mouse_move {x} {y}")

def mouse_click(button="left"):
    btn_map = {"left": 1, "middle": 2, "right": 4, "none": 0}
    state = btn_map.get(button.lower(), 1)
    send_monitor_command(f"mouse_button {state}")
    time.sleep(0.1)
    send_monitor_command("mouse_button 0")

def click_element(element_id: str):
    if not os.path.exists(UI_MAP_PATH):
        raise FileNotFoundError(f"UI map not found at {UI_MAP_PATH}")
    
    with open(UI_MAP_PATH, "r") as f:
        ui_map = json.load(f)
        
    if element_id not in ui_map.get("elements", {}):
        raise ValueError(f"Element '{element_id}' not found in UI map.")
        
    elem = ui_map["elements"][element_id]
    x, y = elem["x"], elem["y"]
    print(f"Targeting {element_id} at ({x}, {y}) - {elem.get('description', '')}")
    
    mouse_move_absolute(x, y)
    time.sleep(0.2)
    mouse_click()

def main():
    parser = argparse.ArgumentParser(description="Headless QEMU Desktop Driver for AI")
    subparsers = parser.add_subparsers(dest="action", required=True)

    cap = subparsers.add_parser("capture", help="Take a screenshot")
    cap.add_argument("--out", default="/tmp/guest-display.png", help="Output PNG path")

    key = subparsers.add_parser("key", help="Send a specific QEMU key")
    key.add_argument("keyname", help="The QEMU key name")

    typ = subparsers.add_parser("type", help="Type a string of text")
    typ.add_argument("text", help="The text to type")

    mv = subparsers.add_parser("mouse_move", help="Move mouse relatively")
    mv.add_argument("dx", type=int)
    mv.add_argument("dy", type=int)

    click = subparsers.add_parser("click", help="Click a mouse button")
    click.add_argument("--button", default="left", choices=["left", "right", "middle"])

    # New click-element command
    clke = subparsers.add_parser("click-element", help="Click a predefined UI element by ID")
    clke.add_argument("element_id", help="Element ID from ui_map.json (e.g., 'gdm.user_jericho')")

    args = parser.parse_args()

    if args.action == "capture":
        capture_screen(args.out)
    elif args.action == "key":
        send_key(args.keyname)
    elif args.action == "type":
        type_text(args.text)
    elif args.action == "mouse_move":
        mouse_move(args.dx, args.dy)
    elif args.action == "click":
        mouse_click(args.button)
    elif args.action == "click-element":
        click_element(args.element_id)

if __name__ == "__main__":
    main()
