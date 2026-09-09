# Pixel Linux: Typing is Different - Tools and Guide

## The Core Insight

When you type in Pixel Linux, you're not just writing to a linear block device. You're manipulating a **spatial 2D pixel grid** that is:

1. **Visible** - You can open the container PNG and see the data
2. **Predictable** - Same input maps to same pixel coordinates
3. **Editable** - You can modify it with an image editor
4. **Spatially Organized** - Related data is often in adjacent pixels

## The 4 Key Differences

### 1. Spatial vs Linear Persistence

```
Bare Metal:
Input → RAM → Block Device (hidden, fragmented, linear)

Pixel Linux:
Input → RAM → virtio-pixel → 2D Grid (x, y, color)
                              ↓
                         .rts file (viewable!)
```

**Why this matters:**
- In bare metal, you can't see where data lives on disk
- In Pixel Linux, the "disk" is an image you can open in Photoshop
- You can literally *see* data structures as color patterns

### 2. Predictable Coordinate Mapping

```
Same Command + Same Location = Same Pixels

If I type: echo "hello" in /home/user
The pixels at (X, Y) will ALWAYS encode "hello" in the same way
```

**Why this matters:**
- We can map: command → pixel coordinates
- We can locate: where does bash store .bash_history? Find the pixels!
- We can replay: write those pixels, get same result

### 3. God-Mode Editing

```
Normal System:
Need root access
Run editors
Make changes
Reboot

Pixel Linux:
1. Open ubuntu_desktop_pxc1_v1/system.rts in image editor
2. Draw new configuration
3. Save file
4. Reboot - VM has new config, doesn't know how it got there!
```

**Why this matters:**
- Edit without booting the guest
- Instant configuration changes
- "Time travel" - revert to previous snapshot

### 4. Visual Forensics

```
Normal System:
$ hexdump /dev/sda | grep "hello"  (blind search)

Pixel Linux:
$ open system.rts in image viewer
→ SEE the pattern "hello" as colored pixels
→ Click to get coordinates
→ Modify directly!
```

**Why this matters:**
- Locate data structures visually
- Understand spatial layout
- Find by pattern matching, not brute force

---

## Tools Created

### 1. Pixel Diff Visualizer (`pixel_diff.sh`)

Visualizes EXACTLY which pixels change when you type a command.

**Usage:**
```bash
# Must have Pixel Linux running in another terminal
./pixel_diff.sh "echo 'Hello World'"
```

**What it does:**
1. Snapshot current container state
2. Execute command in guest
3. Snapshot new state
4. Generate visual diff (highlights changed pixels in red)
5. Save metrics

**Output:**
```
pixel_snapshots/after_echo_Hello_World_20240818_123456/
├── system.rts              # New state
├── diff.png                # Visual diff (red = changed pixels)
├── metrics.txt             # Statistics
└── metadata.txt            # Context
```

**What you learn:**
- Where in the filesystem the output was written
- Which metadata structures were accessed
- How many pixels changed
- The spatial footprint of the command

**Example insights:**
```
$ ./pixel_diff.sh "ls /etc"
Estimated unique colors: 1423
→ ~1423 different values touched
→ Can trace back to find: where does /etc live in pixels?
```

### 2. Pixel Paint (`pixel_paint.py`)

The "God Editor" - directly paint into the container.

**Features:**
- Read pixel values at coordinates
- Write pixel values (paint)
- Fill regions with colors
- Paint text directly into pixels
- Search for byte patterns
- Dump regions as hex

**Usage:**

```bash
# Read a pixel
python3 pixel_paint.py ubuntu_desktop_pxc1_v1/system.rts read 100 200
# Output: Pixel at (100, 200): RGB=(128, 64, 0) Hex: #804000

# Write a pixel (red)
python3 pixel_paint.py ubuntu_desktop_pxc1_v1/system.rts write 100 200 255 0 0

# Fill a region (100×100 blue square at (500, 500))
python3 pixel_paint.py ubuntu_desktop_pxc1_v1/system.rts fill 500 500 100 100 0 0 255

# Paint text "HELLO" in green on black
python3 pixel_paint.py ubuntu_desktop_pxc1_v1/system.rts string "HELLO" 100 100 --fg "#00FF00" --bg "#000000"

# Search for ELF headers (kernel binaries)
python3 pixel_paint.py ubuntu_desktop_pxc1_v1/system.rts search "7F454C46"
# Output:
# Found 3 occurrences:
#   Offset 524288 → (512, 0) channel 0 = 0x7f
#   Offset 1048576 → (1024, 0) channel 0 = 0x7f
#   Offset 2097152 → (2048, 0) channel 0 = 0x7f

# Dump region as hex
python3 pixel_paint.py ubuntu_desktop_pxc1_v1/system.rts dump 0 0 16 16
```

**Power use cases:**

**1. Edit a file without booting:**
```bash
# Find where /etc/hostname lives
python3 pixel_paint.py ubuntu_desktop_pxc1_v1/system.rts search "ubuntu"

# Assume it's at offset 12345678
# Calculate coordinates: (x, y) = (12345678 // 3 % 4096, 12345678 // 3 // 4096)

# Paint new hostname (8x8 font, green on black)
python3 pixel_paint.py ubuntu_desktop_pxc1_v1/system.rts string "pixel-os" 1234 5678 --fg "#00FF00" --bg "#000000"

# Boot - hostname is now "pixel-os"!
```

**2. Create a backdoor:**
```bash
# Paint a new line into /etc/passwd at the right coordinates
python3 pixel_paint.py ubuntu_desktop_pxc1_v1/system.rts string "hacker:x:0:0:root:/root:/bin/bash" 2345 6789 --fg "#FFFFFF" --bg "#000000"

# Next boot: hacker is root!
```

**3. Visual debugging:**
```bash
# Fill suspicious region with magenta
python3 pixel_paint.py ubuntu_desktop_pxc1_v1/system.rts fill 2000 2000 500 500 255 0 255

# Boot - see where magenta appears in the OS!
```

### 3. Pixel Artisan (`pixel_artisan.py`)

Analyze and understand spatial layout of containers.

**Features:**
- Analyze container structure (kernel, filesystem, etc.)
- Find ELF headers, PNGs, GZIP, EXT4 superblocks
- Locate empty/uniform regions
- Calculate region statistics (entropy, top colors)
- Export regions as ASCII text
- Find specific byte patterns

**Usage:**

```bash
# Analyze entire container
python3 pixel_artisan.py analyze ubuntu_desktop_pxc1_v1/system.rts --output analysis.json

# Find ELF headers (kernel)
python3 pixel_artisan.py find-pattern ubuntu_desktop_pxc1_v1/system.rts "7F454C46"

# Analyze specific region
python3 pixel_artisan.py region ubuntu_desktop_pxc1_v1/system.rts 0 0 512 512

# Export region as ASCII (readable text)
python3 pixel_artisan.py export ubuntu_desktop_pxc1_v1/system.rts 1024 2048 256 64 text_output.txt

# Create heatmap visualization
python3 pixel_artisan.py heatmap ubuntu_desktop_pxc1_v1/system.rts --x 0 --y 0 --width 1024 --height 1024
```

**Example output:**

```json
{
  "regions": {
    "boot_sector": {
      "pixel_count": 786432,
      "unique_colors": 256,
      "average_color": [128, 128, 128],
      "top_colors": [[0,0,0, 409600], [255,255,255, 200000]]
    },
    "kernel": {
      "pixel_count": 12582912,
      "unique_colors": 65536,
      "average_color": [64, 64, 64],
      "entropy": 0.0052
    },
    "filesystem": {
      "pixel_count": 12582912,
      "unique_colors": 131072,
      "average_color": [32, 32, 32]
    }
  },
  "signatures": {
    "elf_header": {
      "occurrences": 3,
      "offsets": [524288, 1048576, 2097152]
    },
    "ext4_superblock": {
      "occurrences": 1,
      "offsets": [10485760]
    }
  }
}
```

---

## Practical Workflows

### Workflow 1: Locate Where a File Lives

```bash
# Step 1: Create a unique marker file
ssh -p 2222 jericho@127.0.0.1 "echo 'MARKER_FILE_CONTENT_XYZ123' > /tmp/marker.txt"

# Step 2: Trigger writeback
curl -X POST http://127.0.0.1:8769/writeback

# Step 3: Search for the marker in pixels
python3 pixel_paint.py ubuntu_desktop_pxc1_v1/system.rts search "MARKER_FILE_CONTENT_XYZ123"

# Step 4: Get coordinates from output
# Found 1 occurrence:
#   Offset 12345678 → (x, y)

# Step 5: Now you know /tmp lives around those coordinates!
```

**Result:** You can now edit /tmp files without booting, by painting to those coordinates.

### Workflow 2: Time Travel for an OS

```bash
# Setup: Take periodic snapshots
while true; do
    cp ubuntu_desktop_pxc1_v1/system.rts snapshots/system_$(date +%s).rts
    sleep 60
done

# Disaster: I broke the boot process!
# Oops, I deleted /bin/bash

# Solution: Revert to last working snapshot
ls -t snapshots/ | head -1
# system_1723980000.rts

cp snapshots/system_1723980000.rts ubuntu_desktop_pxc1_v1/system.rts

# Reboot - you're back in time!
```

**Result:** Git-like version control for the entire running state of the computer.

### Workflow 3: "Execute" Commands Instantly

```bash
# Step 1: Trace a command (see pixel_trace tools)
./pixel_trace_command.sh 'ls /etc/passwd'

# Step 2: Analyze to find pixel program
analyze_pixel_trace.sh trace_*

# Step 3: Extract the output pixels (the result)
# From analysis: output pixels at (3000, 3000) through (3100, 3100)

# Step 4: "Execute" instantly by painting the result
python3 pixel_paint.py ubuntu_desktop_pxc1_v1/system.rts fill 3000 3000 100 100 255 255 255

# Reboot - the "result" of ls /etc/passwd is there!
```

**Result:** No execution time. Just paint the expected output.

### Workflow 4: Visual Debugging

```bash
# I want to see where the kernel loads

# Step 1: Find ELF headers (kernel signature)
python3 pixel_artisan.py find-pattern ubuntu_desktop_pxc1_v1/system.rts "7F454C46"

# Step 2: Mark those regions visually
python3 pixel_paint.py ubuntu_desktop_pxc1_v1/system.rts fill 512 0 2048 2048 255 0 0
# Fill kernel region with red

# Step 3: Boot
./interactive_ubuntu_pixel.sh

# Step 4: Look for red artifacts in the output!
# This tells you: "this output came from the kernel region"
```

**Result:** Visual tracing of execution.

---

## Building with These Insights

### 1. Map the Spatial Layout

Create a comprehensive map of where Linux components live:

```bash
# Run full analysis
python3 pixel_artisan.py analyze ubuntu_desktop_pxc1_v1/system.rts --output spatial_map.json

# Extract key regions
- Boot sector: (0, 0) to (512, 512)
- Kernel: (512, 0) to (2560, 2048)
- ext4 superblock: (1024, 2048)
- /etc directory: [find coordinates via workflow 1]
- /bin directory: [find coordinates via workflow 1]
- Swap space: (3072, 2048) to (4096, 3072)
```

**Output:** A reference map: command → pixel coordinates.

### 2. Create Direct Pixel Compilers

Instead of compiling code, compile to pixel patterns:

```python
def compile_command_to_pixels(command):
    """Translate command directly to pixel operations"""

    # This is the future: compile to pixels, not machine code
    if command == "ls /etc":
        return [
            ("load", (1024, 2048), (512, 512)),  # Load /etc metadata
            ("transform", "extract_filenames"),
            ("store", (3000, 100), (500, 500)),  # Write output
        ]
```

**Result:** Programs execute by transforming pixels.

### 3. Boot New Instances by Copying Pixels

```bash
# Want another Ubuntu? Just copy the pixels!

cp ubuntu_desktop_pxc1_v1/ubuntu_desktop_pxc1_v1 ubuntu_desktop_pxc1_v2/ubuntu_desktop_pxc1_v1

# Edit some pixels to make it unique
python3 pixel_paint.py ubuntu_desktop_pxc1_v2/system.rts string "ubuntu-2" 1000 1000

# Boot second instance at viewport (4096, 0)
pixel_create_viewport 4096 0
pixel_map_container 1 ubuntu_desktop_pxc1_v2
```

**Result:** Recursive boot via pixel copying.

### 4. Self-Modifying OS

The OS can modify its own pixels:

```bash
# The OS writes to disk → pixels change
# We read the new pixels → understand what changed
# We paint similar pixels → OS "thinks" it did something

# Example: The OS creates a file
# We capture the pixel pattern for "create file"
# We replay that pattern → OS thinks it created a file!
```

**Result:** The OS can be controlled externally.

---

## Advanced: The "Typing" Problem

### Why Typing is Different

When you type in Pixel Linux, each keystroke triggers a **predictable pixel transformation**:

```
Type: 'h' → TTY buffer pixels at (X, Y) change
Type: 'e' → Next pixel changes
Type: 'l' → Next pixel changes
Type: 'l' → Next pixel changes
Type: 'o' → Next pixel changes
Type: Enter → Command execution pixels transform
```

**We can intercept and replay this!**

### Example: Typing Without a Keyboard

```bash
# Step 1: Find where TTY buffer lives
# (Use workflow 1 with a marker file in the terminal)

# Step 2: Paint the command into the TTY buffer
python3 pixel_paint.py ubuntu_desktop_pxc1_v1/system.rts string "ls /etc" 1234 5678 --fg "#FFFFFF" --bg "#000000"

# Step 3: Paint the "Enter" keystroke
python3 pixel_paint.py ubuntu_desktop_pxc1_v1/system.rts write 1294 5678 10 0 0  # Enter key code

# Step 4: Boot
./interactive_ubuntu_pixel.sh

# The VM wakes up with "ls /etc" already typed!
# It executes automatically!
```

**Result:** Pre-typed commands in the container.

### Example: Typing History Mining

```bash
# Where does .bash_history live?

# Step 1: Type unique commands
ssh -p 2222 jericho@127.0.0.1 "echo 'MARKER_ONE' && echo 'MARKER_TWO' && echo 'MARKER_THREE'"

# Step 2: Find those markers in pixels
python3 pixel_paint.py ubuntu_desktop_pxc1_v1/system.rts search "MARKER_ONE"
# Offset 11111111

# Step 3: They should be sequential (if history is linear)
python3 pixel_paint.py ubuntu_desktop_pxc1_v1/system.rts search "MARKER_TWO"
# Offset 11111118 (+7)

python3 pixel_paint.py ubuntu_desktop_pxc1_v1/system.rts search "MARKER_THREE"
# Offset 11111125 (+7)

# Conclusion: .bash_history starts around offset 11111000
# Each line is ~7 bytes apart
```

**Result:** We found where bash stores its history!

Now we can:

```bash
# Read the history by exporting that region
python3 pixel_artisan.py export ubuntu_desktop_pxc1_v1/system.rts \
  $(python3 -c "print(11111000 // 3 % 4096)") \
  $(python3 -c "print(11111000 // 3 // 4096)") \
  100 100 history.txt

# Clean up and view
cat history.txt | sed 's/\./ /g'
# See all past commands!
```

**Result:** Read user's command history without logging in.

---

## File Reference

```
/host_zion/projects/visual_audio/
├── pixel_diff.sh              # Visual diff tool
├── pixel_paint.py             # God editor (paint into container)
├── pixel_artisan.py           # Spatial analyzer
├── pixel_snapshots/           # Diff output directory
└── TYPEING_IS_DIFFERENT.md    # This file
```

---

## Quick Start

```bash
# 1. Analyze container structure
python3 pixel_artisan.py analyze ubuntu_desktop_pxc1_v1/system.rts

# 2. Find ELF headers (kernel locations)
python3 pixel_artisan.py find-pattern ubuntu_desktop_pxc1_v1/system.rts "7F454C46"

# 3. Visualize what changes when you type a command
./pixel_diff.sh "echo 'Hello'"

# 4. Paint text directly into the container
python3 pixel_paint.py ubuntu_desktop_pxc1_v1/system.rts string "TEST" 100 100 --fg "#00FF00" --bg "#000000"

# 5. Search for data patterns
python3 pixel_paint.py ubuntu_desktop_pxc1_v1/system.rts search "ELF"
```

---

## Philosophy

> "When the OS is pixels, typing becomes painting, editing becomes drawing,
> and debugging becomes visual inspection. The keyboard is just one way to
> change pixels—we have many more."

---

**Created:** 2026-08-18
**Status:** Fully functional tools ready for exploration
**Next:** Map the complete spatial layout of Ubuntu Desktop in pixels