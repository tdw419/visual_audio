---
category: autonomous-agents
---

# Pixel VM Agent Collaboration

Work autonomously across host and pixel-booted guest environments using the guest context bridge.

## The Problem

When I receive a prompt, I don't know whether I'm operating in:
- **Host environment** (this terminal, direct file access)
- **Guest environment** (inside pixel-booted VM, accessed via SSH/shared FS)

This makes context-aware work difficult.

## The Solution

### Guest Context Bridge

The guest runs a daemon that exposes its state to the host via shared filesystem:

```
Guest Context Daemon (inside VM)
    ↓ writes state to
/host_zion/projects/visual_audio/.hermes_guest_context/guest_state.json
    ↓ read by
Host Agent (me)
```

### Context Detection

I can detect my environment by checking:

1. **Context marker exists**: `/host_zion/.hermes_guest_context/ACTIVE_GUEST_SESSION`
   - If present: I'm running in **guest mode**
   - If absent: I'm running in **host mode**

2. **Guest state file**: `/host_zion/.hermes_guest_context/guest_state.json`
   - Contains hostname, user, hermes status, available tools
   - Tells me exactly what's available in the guest

## When to Use Guest Mode

Use guest mode when:
- User prompts "in the vm", "in the pixel system", "guest"
- Task requires running inside the guest environment
- Need to test code that will run on the pixel-booted OS
- User explicitly mentions "SSH to guest" or similar

## How to Work in Guest Mode

### Step 1: Detect Guest Availability

```bash
# Check if guest is running
ls /host_zion/projects/visual_audio/.hermes_guest_context/guest_state.json
```

If file exists, guest context daemon is running.

### Step 2: Read Guest State

```python
import json

guest_state_path = "/host_zion/projects/visual_audio/.hermes_guest_context/guest_state.json"
with open(guest_state_path) as f:
    state = json.load(f)

# Inspect:
# - state["hostname"] → "hermes-guest"
# - state["hermes"]["installed"] → True/False
# - state["available_tools"] → List of tools
```

### Step 3: Execute Commands via Host Bridge

**Option A: Direct SSH (for simple commands)**
```bash
ssh -o StrictHostKeyChecking=no -p 2222 jericho@127.0.0.1 <command>
```

**Option B: Host-to-Guest command bridge (for structured commands)**
```python
# Write command to guest
command = {
    "action": "hermes_run",
    "task": "Analyze current directory structure"
}

command_path = "/host_zion/projects/visual_audio/.hermes_guest_context/host_command.json"
with open(command_path, 'w') as f:
    json.dump(command, f)

# Wait for response
response_path = "/host_zion/projects/visual_audio/.hermes_guest_context/guest_response.json"

import time
time.sleep(2)  # Wait for daemon to process

with open(response_path) as f:
    response = json.load(f)

print(response["output"])
```

### Step 4: Read Guest Files via Shared FS

```bash
# Guest file is accessible at:
ls -la /host_zion/projects/visual_audio/<guest_files>

# Example: Read guest's AGENTS.md
cat /host_zion/projects/visual_audio/ubuntu_desktop_pxc1_v1/AGENTS.md
```

## Getting Started With the Guest

### First-Time Setup (Run Once in Guest)

```bash
# In guest (via SSH or serial console):
bash /host_zion/projects/visual_audio/setup_guest_for_agent_collab.sh

# Start context daemon:
python3 /host_zion/projects/visual_audio/guest_context_daemon.py &
```

### Verification

```bash
# On host, check guest is available:
cat /host_zion/projects/visual_audio/.hermes_guest_context/guest_state.json

# Should see:
# {
#   "hostname": "hermes-guest",
#   "user": "jericho",
#   "hermes": {
#     "installed": true,
#     "path": "/home/jericho/.hermes/hermes-agent",
#     "version": "..."
#   },
#   ...
# }
```

## Example Workflows

### Example 1: Run Hermes Task in Guest

User prompt: "Run Hermes in the guest to analyze the project structure"

My response (in guest mode):

1. Read guest state: Hermes installed? Yes
2. Write command via bridge:
   ```python
   command = {"action": "hermes_run", "task": "Analyze project structure"}
   ```
3. Read response
4. Report result

### Example 2: Edit File in Guest, Verify in Host

User prompt: "Create a test file in the guest, then verify it appears on host"

My response (guest mode):

1. Write command:
   ```python
   command = {
     "action": "file_write",
     "path": "/tmp/guest_test.txt",
     "content": "Hello from guest!"
   }
   ```
2. Verify via shared FS:
   ```bash
   ls -la /host_zion/tmp/guest_test.txt
   ```

### Example 3: Compare Host vs Guest Environments

User prompt: "What's different between the host and guest Python environments?"

My response:

1. Read host: `python3 --version`
2. Read guest state from `guest_state.json`
3. Compare and report differences

## Important Notes

- **Shared FS is read-write**: Guest can write to host, host can write to guest
- **Guest reboot resets state**: If guest reboots, restart context daemon
- **Writeback to pixels**: If guest writes to `/dev/vda`, changes go to pixel container
- **SSH timeout**: If SSH hangs, try serial console or VNC

## Troubleshooting

### Guest state file missing

**Cause:** Guest context daemon not running

**Fix:**
```bash
# In guest:
python3 /host_zion/projects/visual_audio/guest_context_daemon.py &
```

### SSH timeout

**Cause:** Authentication hanging or network issue

**Fix:**
- Use serial console: `echo "<command>" > /dev/pts/X` (find pts via `ps aux | grep qemu`)
- Or use host bridge (no SSH needed)

### Shared FS not mounted

**Cause:** 9p mount failed

**Fix:**
```bash
# In guest:
mount -t 9p -o trans=virtio host_zion /host_zion
```

---

**Remember:** The key is checking the context marker (`ACTIVE_GUEST_SESSION`) to know which environment you're in. If it exists, you're in guest mode — use the bridge. If not, operate directly on the host.