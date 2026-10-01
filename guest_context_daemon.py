#!/usr/bin/env python3
"""
Guest Context Daemon - Runs inside the pixel-booted guest

Exposes guest environment/state to host via shared filesystem for seamless
agent collaboration across environments.

How it works:
1. Daemon writes guest state to /host_zion/projects/visual_audio/.hermes_guest_context/guest_state.json
2. Host-side agent reads this file to understand guest context
3. Context marker files tell agents: "you're operating in guest mode"
"""

import json
import os
import time
import socket
import subprocess
from pathlib import Path
from datetime import datetime

# Paths
CONTEXT_DIR = Path("/host_zion/projects/visual_audio/.hermes_guest_context")
STATE_FILE = CONTEXT_DIR / "guest_state.json"
CONTEXT_MARKER = CONTEXT_DIR / "ACTIVE_GUEST_SESSION"

# Poll interval (seconds)
POLL_INTERVAL = 5


def get_guest_info():
    """Collect guest environment information"""
    try:
        hostname = socket.gethostname()
        user = os.getenv("USER", os.getenv("USERNAME", "unknown"))

        # Get current working directory
        cwd = os.getcwd()

        # Check Hermes installation
        hermes_path = None
        hermes_version = None
        try:
            result = subprocess.run(
                ["which", "hermes"],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                hermes_path = result.stdout.strip()

                # Get version
                version_result = subprocess.run(
                    ["hermes", "--version"],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                if version_result.returncode == 0:
                    hermes_version = version_result.stdout.strip()
        except Exception:
            pass

        # Check available tools
        available_tools = []
        tool_commands = [
            ("git", ["git", "--version"]),
            ("python3", ["python3", "--version"]),
            ("hermes", ["hermes", "--version"]),
            ("claude", ["claude", "--version"]),
        ]

        for tool_name, cmd in tool_commands:
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
                if result.returncode == 0:
                    available_tools.append({
                        "name": tool_name,
                        "version": result.stdout.strip()
                    })
            except Exception:
                pass

        # Storage info
        storage_info = {}
        try:
            result = subprocess.run(
                ["df", "-h", "/"],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                lines = result.stdout.split('\n')
                if len(lines) >= 2:
                    parts = lines[1].split()
                    if len(parts) >= 6:
                        storage_info = {
                            "size": parts[1],
                            "used": parts[2],
                            "available": parts[3],
                            "use_percent": parts[4],
                            "mounted_on": parts[5]
                        }
        except Exception:
            pass

        # Network info
        network_info = {}
        try:
            result = subprocess.run(
                ["ip", "addr", "show"],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                network_info["interfaces"] = result.stdout.strip()
        except Exception:
            pass

        return {
            "hostname": hostname,
            "user": user,
            "cwd": cwd,
            "hermes": {
                "installed": hermes_path is not None,
                "path": hermes_path,
                "version": hermes_version
            },
            "available_tools": available_tools,
            "storage": storage_info,
            "network": network_info,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        return {
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


def main():
    """Main daemon loop"""
    print("[Guest Context Daemon] Starting...")

    # Ensure context directory exists
    CONTEXT_DIR.mkdir(parents=True, exist_ok=True)

    # Create context marker
    CONTEXT_MARKER.write_text(datetime.now().isoformat())

    # Listen for commands from host
    COMMAND_FILE = CONTEXT_DIR / "host_command.json"
    RESPONSE_FILE = CONTEXT_DIR / "guest_response.json"

    print(f"[Guest Context Daemon] Context dir: {CONTEXT_DIR}")
    print(f"[Guest Context Daemon] Writing state to: {STATE_FILE}")

    while True:
        try:
            # Write current state
            state = get_guest_info()
            STATE_FILE.write_text(json.dumps(state, indent=2))

            # Check for commands from host
            if COMMAND_FILE.exists():
                try:
                    command = json.loads(COMMAND_FILE.read_text())

                    print(f"[Guest Context Daemon] Received command: {command.get('action')}")

                    # Execute command
                    response = execute_command(command)

                    # Write response
                    RESPONSE_FILE.write_text(json.dumps(response, indent=2))

                    # Clean up command
                    COMMAND_FILE.unlink()

                except Exception as e:
                    error_response = {
                        "status": "error",
                        "error": str(e),
                        "timestamp": datetime.now().isoformat()
                    }
                    RESPONSE_FILE.write_text(json.dumps(error_response, indent=2))
                    COMMAND_FILE.unlink()

            time.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            print("[Guest Context Daemon] Shutting down...")
            break
        except Exception as e:
            print(f"[Guest Context Daemon] Error: {e}")
            time.sleep(POLL_INTERVAL)


def execute_command(command):
    """Execute a command from the host"""
    action = command.get("action")

    if action == "hermes_run":
        # Run Hermes task
        task = command.get("task", "")
        try:
            result = subprocess.run(
                ["hermes", "-z", task],
                capture_output=True,
                text=True,
                timeout=60
            )
            return {
                "status": "success" if result.returncode == 0 else "error",
                "output": result.stdout,
                "error": result.stderr,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    elif action == "file_read":
        # Read a file
        path = command.get("path", "")
        try:
            content = Path(path).read_text()
            return {
                "status": "success",
                "content": content,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    elif action == "file_write":
        # Write a file
        path = command.get("path", "")
        content = command.get("content", "")
        try:
            Path(path).write_text(content)
            return {
                "status": "success",
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    else:
        return {
            "status": "error",
            "error": f"Unknown action: {action}",
            "timestamp": datetime.now().isoformat()
        }


if __name__ == "__main__":
    main()