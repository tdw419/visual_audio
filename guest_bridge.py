#!/usr/bin/env python3
"""
Host-side guest bridge - Run commands in the pixel-booted guest

This is the tool I (the agent) use to execute work in the guest environment
seamlessly.

Usage:
    python3 guest_bridge.py hermes_run "Analyze current directory"
    python3 guest_bridge.py read_file "/tmp/test.txt"
    python3 guest_bridge.py write_file "/tmp/test.txt" "Hello world"
"""

import json
import sys
import time
from pathlib import Path

# Paths (host-side view of the shared 9p directory; the guest sees the
# same directory at /host_zion/projects/visual_audio/.hermes_guest_context)
CONTEXT_DIR = Path(__file__).resolve().parent / ".hermes_guest_context"
COMMAND_FILE = CONTEXT_DIR / "host_command.json"
RESPONSE_FILE = CONTEXT_DIR / "guest_response.json"
STATE_FILE = CONTEXT_DIR / "guest_state.json"


def check_guest_available():
    """Check if guest context daemon is running"""
    if not STATE_FILE.exists():
        return False, "Guest state file not found - daemon not running"

    try:
        state = json.loads(STATE_FILE.read_text())
        if "error" in state:
            return False, f"Guest error: {state['error']}"
        return True, state
    except Exception as e:
        return False, f"Failed to read guest state: {e}"


def execute_in_guest(action, **kwargs):
    """Execute a command in the guest via the bridge"""

    # Check guest is available
    available, state_or_error = check_guest_available()
    if not available:
        return {
            "status": "error",
            "error": f"Guest not available: {state_or_error}"
        }

    state = state_or_error
    guest_info = {
        "hostname": state.get("hostname", "unknown"),
        "user": state.get("user", "unknown"),
        "hermes_installed": state.get("hermes", {}).get("installed", False)
    }

    # Build command
    command = {
        "action": action,
        **kwargs
    }

    # Clear any stale response from a previous command before issuing a new
    # one, so we don't race and pick up an old answer.
    RESPONSE_FILE.unlink(missing_ok=True)

    # Write command
    try:
        COMMAND_FILE.write_text(json.dumps(command, indent=2))
    except Exception as e:
        return {
            "status": "error",
            "error": f"Failed to write command: {e}"
        }

    # Wait for response (with timeout). hermes_run invokes an LLM and can
    # legitimately take tens of seconds; other actions are near-instant.
    max_wait = 90 if action == "hermes_run" else 10
    waited = 0

    while waited < max_wait:
        if RESPONSE_FILE.exists():
            try:
                response = json.loads(RESPONSE_FILE.read_text())
                return {
                    "status": "success",
                    "response": response,
                    "guest_info": guest_info
                }
            except Exception as e:
                return {
                    "status": "error",
                    "error": f"Failed to read response: {e}"
                }

        time.sleep(0.5)
        waited += 0.5

    return {
        "status": "error",
        "error": f"Timeout waiting for guest response (waited {max_wait}s)"
    }


def hermes_run(task):
    """Run a Hermes task in the guest"""
    print(f"📤 Running Hermes in guest: {task}")
    print()

    result = execute_in_guest("hermes_run", task=task)

    if result["status"] == "success":
        response = result["response"]
        if response["status"] == "success":
            print("✅ Success")
            print()
            print("Output:")
            print(response["output"])

            if response.get("error"):
                print()
                print("Errors:")
                print(response["error"])
        else:
            print("❌ Hermes task failed")
            print(f"Error: {response.get('error')}")
    else:
        print("❌ Failed to execute in guest")
        print(f"Error: {result.get('error')}")


def read_file(path):
    """Read a file in the guest"""
    print(f"📖 Reading guest file: {path}")
    print()

    result = execute_in_guest("file_read", path=path)

    if result["status"] == "success":
        response = result["response"]
        if response["status"] == "success":
            print("✅ Success")
            print()
            print("Content:")
            print(response["content"])
        else:
            print("❌ File read failed")
            print(f"Error: {response.get('error')}")
    else:
        print("❌ Failed to execute in guest")
        print(f"Error: {result.get('error')}")


def write_file(path, content):
    """Write a file in the guest"""
    print(f"✍️  Writing guest file: {path}")
    print(f"Content: {content[:50]}{'...' if len(content) > 50 else ''}")
    print()

    result = execute_in_guest("file_write", path=path, content=content)

    if result["status"] == "success":
        response = result["response"]
        if response["status"] == "success":
            print("✅ Success - File written")
        else:
            print("❌ File write failed")
            print(f"Error: {response.get('error')}")
    else:
        print("❌ Failed to execute in guest")
        print(f"Error: {result.get('error')}")


def guest_status():
    """Show guest status"""
    available, state_or_error = check_guest_available()

    if not available:
        print("❌ Guest not available")
        print(f"Reason: {state_or_error}")
        return

    state = state_or_error
    print("✅ Guest Available")
    print()
    print(f"Hostname: {state.get('hostname')}")
    print(f"User: {state.get('user')}")
    print(f"CWD: {state.get('cwd')}")
    print()
    print("Hermes:")
    hermes = state.get('hermes', {})
    print(f"  Installed: {hermes.get('installed')}")
    if hermes.get('installed'):
        print(f"  Path: {hermes.get('path')}")
        print(f"  Version: {hermes.get('version')}")
    print()
    print("Available Tools:")
    for tool in state.get('available_tools', []):
        print(f"  - {tool['name']}: {tool.get('version', 'unknown')}")
    print()
    print(f"Last Updated: {state.get('timestamp')}")


def main():
    if len(sys.argv) < 2:
        print("Usage: guest_bridge.py <command> [args...]")
        print()
        print("Commands:")
        print("  status                          - Show guest status")
        print("  hermes_run <task>              - Run Hermes task in guest")
        print("  read_file <path>               - Read guest file")
        print("  write_file <path> <content>    - Write guest file")
        sys.exit(1)

    command = sys.argv[1]

    if command == "status":
        guest_status()
    elif command == "hermes_run":
        if len(sys.argv) < 3:
            print("Error: hermes_run requires a task")
            sys.exit(1)
        hermes_run(sys.argv[2])
    elif command == "read_file":
        if len(sys.argv) < 3:
            print("Error: read_file requires a path")
            sys.exit(1)
        read_file(sys.argv[2])
    elif command == "write_file":
        if len(sys.argv) < 4:
            print("Error: write_file requires path and content")
            sys.exit(1)
        write_file(sys.argv[2], sys.argv[3])
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()