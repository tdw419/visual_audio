# Framebuffer Text Editor Architecture

## Overview

A **pixel-native framebuffer text editor** that writes directly to `/dev/fb0` without X11/Wayland. The editor uses:

- **VGA 8x16 bitmap fonts** for rendering
- **evdev input handling** for keyboard/mouse
- **Direct framebuffer writes** for display
- **Zero graphical stack** — just pixels

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    Application Layer                          │
│                     (fb_text_editor.py)                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │ TextBuffer   │  │  FBRenderer  │  │ InputDevice  │       │
│  │ (lines, cursor)│  │ (VGA fonts) │  │ (evdev)      │       │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘       │
└─────────┼────────────────┼──────────────────┼────────────────┘
          │                │                  │
          ▼                ▼                  ▼
┌─────────────────────────────────────────────────────────────┐
│                     Abstraction Layer                          │
│                                                                      │
│  ┌──────────────────┐  ┌──────────────────┐                     │
│  │ TextBufferLogic  │  │ Framebuffer API   │                     │
│  │ - insert_char    │  │ - open/close      │                     │
│  │ - delete_char    │  │ - write_pixel     │                     │
│  │ - move_cursor    │  │ - clear_screen    │                     │
│  │ - render_buffer  │  │ - render_char     │                     │
│  └──────────────────┘  └──────────────────┘                     │
└─────────────────────────────────────────────────────────────┘
          │                │
          ▼                ▼
┌─────────────────────────────────────────────────────────────┐
│                      Hardware Layer                             │
│  ┌──────────────┐  ┌──────────────┐                             │
│  │ /dev/input/  │  │  /dev/fb0    │                             │
│  │ eventX (KB)  │  │ (framebuffer) │                             │
│  └──────────────┘  └──────────────┘                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Component Layers

### 1. Hardware Layer

**Input Devices (`/dev/input/eventX`):**
- Linux evdev subsystem provides raw input events
- `event_read()` returns structured events with timestamps
- Keyboard: `EV_KEY` events with key codes
- Mouse: `EV_REL` (relative) or `EV_ABS` (absolute) events

**Framebuffer (`/dev/fb0`):**
- Raw pixel memory mapped to video hardware
- Formats: 32-bit RGBA, 24-bit RGB, 16-bit RGB565
- `ioctl(FBIOGET_VSCREENINFO)` gets dimensions
- `pwrite()` writes pixels directly to VRAM

### 2. Abstraction Layer

#### InputDevice (`evdev_input.py`)

**Purpose:** Convert raw evdev events to high-level actions.

**Key Components:**
```python
class InputDevice:
    def read_events() -> List[InputEvent]:
        # Parse raw evdev events (24 bytes each)
        pass

    def process_events() -> (List[KeyEvent], List[MouseEvent]):
        # Convert to high-level events
        pass

    def _key_to_char() -> Optional[str]:
        # Map key codes to characters
        # Handles shift, ctrl, alt modifiers
        pass
```

**Event Flow:**
```
Raw evdev event:
  InputEvent(timestamp=1234567890.123456, type=1, code=16, value=1)
                          │
                          ▼
Process (EV_KEY, code=16='q', value=1=pressed)
                          │
                          ▼
High-level event:
  KeyEvent(key_code=16, char='q', pressed=True, modifiers={})
```

**Modifier Handling:**
- Track shift/ctrl/alt states separately
- Apply to character mapping when needed
- Example: shift + 'a' → 'A'

#### Framebuffer API (`fb_text_editor.py`)

**Purpose:** Direct framebuffer manipulation.

**Key Components:**
```python
class FBRenderer:
    def open() -> bool:
        # Open /dev/fb0 with O_RDWR
        # Get screen info via ioctl
        pass

    def clear(color: Tuple[int, int, int]):
        # Fill entire screen with color
        pass

    def write_pixel(x, y, color):
        # Write single pixel (BGR/BGRA/RGB565)
        pass

    def render_char(char, x, y, fg_color, bg_color):
        # Render VGA glyph to framebuffer
        pass
```

**Pixel Format Handling:**
```python
def _write_pixel(self, x, y, color):
    offset = (y * width + x) * bytes_per_pixel

    if bits_per_pixel == 32:
        pixel = struct.pack('BBBB', B, G, R, A)  # BGRA
    elif bits_per_pixel == 24:
        pixel = struct.pack('BBB', B, G, R)    # BGR
    elif bits_per_pixel == 16:
        rgb565 = ((R & 0xF8) << 8) | ((G & 0xFC) << 3) | (B >> 3)
        pixel = struct.pack('H', rgb565)

    os.pwrite(fd, pixel, offset)
```

**VGA Font Integration:**
```python
def render_char(self, char, x, y, fg_color, bg_color):
    # Get VGA bitmap (16 rows × 8 cols)
    glyph_data = VGA_FONT_8X16[char]  # 16 bytes
    bitmap = [vga_row_to_pixels(row) for row in glyph_data]

    # Render each pixel
    for row_idx, row_pixels in enumerate(bitmap):
        for col_idx, pixel_val in enumerate(row_pixels):
            px_x = x + col_idx
            px_y = y + row_idx
            color = fg_color if pixel_val > 0 else bg_color
            self._write_pixel(px_x, px_y, color)
```

### 3. Application Layer

#### TextBuffer

**Purpose:** In-memory text buffer with cursor tracking.

**Data Structures:**
```python
@dataclass
class TextBuffer:
    lines: List[str]        # ["Hello", "World"]
    cursor: Cursor           # Cursor(row=0, col=5)

@dataclass
class Cursor:
    row: int  # Line number
    col: int  # Character position in line
```

**Operations:**
```python
def insert_char(self, char: str):
    # Insert at cursor, move right
    line = self.lines[cursor.row]
    new_line = line[:cursor.col] + char + line[cursor.col:]
    self.lines[cursor.row] = new_line
    self.cursor.col += 1

def delete_char(self):
    # Backspace: delete before cursor
    if cursor.col > 0:
        line = self.lines[cursor.row]
        new_line = line[:cursor.col-1] + line[cursor.col:]
        self.lines[cursor.row] = new_line
        self.cursor.col -= 1

def insert_newline(self):
    # Enter: split line at cursor
    line = self.lines[cursor.row]
    left = line[:cursor.col]
    right = line[cursor.col:]
    self.lines[cursor.row] = left
    self.lines.insert(cursor.row + 1, right)
    self.cursor.row += 1
    self.cursor.col = 0
```

#### FBTextEditor

**Purpose:** Main editor orchestrating all components.

**Main Loop:**
```python
def start(self):
    while self.running:
        # Poll input
        key_events, _ = input_device.poll_events()

        # Process keys
        for event in key_events:
            if not event.pressed:
                continue

            if event.char:
                buffer.insert_char(event.char)
            else:
                handle_special_key(event)

        # Render
        renderer.clear()
        renderer.render_buffer(buffer)
        renderer.render_text(status_line)

        # Small delay (100Hz polling)
        time.sleep(0.01)
```

**Control Flow:**
```
Keyboard Input (evdev)
        │
        ▼
Key Event (char='a', pressed=True)
        │
        ▼
TextBuffer.insert_char('a')
        │
        ▼
Buffer: ["a", ""]
Cursor: row=0, col=1
        │
        ▼
FBRenderer.render_buffer()
        │
        ▼
Framebuffer pixels (VGA glyph for 'a')
        │
        ▼
Display shows "a"
```

---

## Input Handling

### Key Event Processing

**Raw evdev event structure:**
```c
struct input_event {
    struct timeval time;  // 16 bytes
    unsigned short type;  // 2 bytes
    unsigned short code;  // 2 bytes
    unsigned int value;   // 4 bytes
};  // Total: 24 bytes
```

**Parsing:**
```python
data = os.read(fd, 24)
sec, usec, type_, code, value = struct.unpack('llHHi', data)
timestamp = sec + usec / 1_000_000
```

**Key states:**
- `value=0`: Key released
- `value=1`: Key pressed
- `value=2`: Key auto-repeat (hold down)

**Modifier tracking:**
```python
def _process_key_event(self, event):
    if event.code in [KEY_LEFTSHIFT, KEY_RIGHTSHIFT]:
        modifiers['shift'] = (event.value == 1)

    if event.code in [KEY_LEFTCTRL]:
        modifiers['ctrl'] = (event.value == 1)

    # Map to character with modifiers
    char = self._key_to_char(event.code, modifiers)
```

**Character mapping:**
```python
def _key_to_char(self, key_code, modifiers):
    # Try shifted mapping first
    if modifiers['shift'] and key_code in KEY_MAP_SHIFTED:
        return KEY_MAP_SHIFTED[key_code]

    # Try normal mapping
    if key_code in KEY_MAP_NORMAL:
        return KEY_MAP_NORMAL[key_code]

    # Try alpha mapping
    if key_code in KEY_MAP_ALPHA:
        char = KEY_MAP_ALPHA[key_code]
        return char.upper() if modifiers['shift'] else char

    # Special keys
    if key_code == KEY_SPACE:
        return ' '

    return None  # Non-printable (arrows, etc.)
```

---

## Display Rendering

### VGA Font Rendering Pipeline

**1. Glyph Lookup:**
```python
char = 'A'
glyph_data = VGA_FONT_8X16[char]  # List[16] bytes
# Example: [0x00, 0x10, 0x28, 0x44, 0x82, 0x82, 0xFE, 0x82, ...]
```

**2. Row to Pixel Conversion:**
```python
def vga_row_to_pixels(row_bits: int) -> np.ndarray:
    # Bit 7 = leftmost pixel, Bit 0 = rightmost
    return np.array([
        255 if (row_bits >> bit) & 1 else 0
        for bit in range(7, -1, -1)
    ], dtype=np.uint8)

# Example: 0x28 = 0b00101000 → [0, 0, 1, 0, 1, 0, 0, 0]
```

**3. Pixel-by-Pixel Render:**
```python
for row_idx, row_bits in enumerate(glyph_data):
    for col_idx in range(8):
        pixel_bit = (row_bits >> (7 - col_idx)) & 1

        if pixel_bit:
            color = fg_color  # Foreground
        else:
            color = bg_color  # Background

        write_pixel(x + col_idx, y + row_idx, color)
```

**Performance:**
- 16 rows × 8 cols = 128 pixels per character
- At 100Hz: 100 chars × 128 pixels = 12,800 pixel writes/sec
- `pwrite()` is fast enough for real-time rendering

### Double Buffering

**Problem:** Direct framebuffer writes cause flicker.

**Solution:** Use off-screen buffer, swap to framebuffer.

```python
class FBRenderer:
    def __init__(self):
        self.offscreen = np.zeros((height, width, 3), dtype=np.uint8)

    def render_to_offscreen(self):
        # Render all text to offscreen buffer
        pass

    def swap(self):
        # Write offscreen to framebuffer
        os.pwrite(fd, self.offscreen.tobytes(), 0)
```

**For simplicity:** Current implementation writes directly (acceptable for text editors).

---

## Cursor Management

### Cursor Position Tracking

**Data Structure:**
```python
@dataclass
class Cursor:
    row: int  # Line number (0-indexed)
    col: int  # Character position in line (0-indexed)
```

**Cursor Movement:**
```python
def move_cursor(dx, dy, max_cols=80):
    cursor.row = max(0, min(len(lines) - 1, cursor.row + dy))
    cursor.col = max(0, min(len(lines[cursor.row]), cursor.col + dx))
```

**Cursor Rendering:**
```python
# Calculate pixel position
cursor_x = margin_x + cursor.col * char_width
cursor_y = margin_y + cursor.row * char_height

# Draw cursor block (green inverted block)
for y in range(char_height):
    for x in range(char_width):
        write_pixel(cursor_x + x, cursor_y + y, (0, 255, 0))
```

**Cursor Highlight Line:**
```python
# Highlight entire cursor line
if line_num == cursor.row:
    bg_color = (40, 40, 40)  # Dark gray
else:
    bg_color = (0, 0, 0)    # Black
```

---

## File Operations

### Saving

**Direct to file:**
```python
def save_buffer(self, path: str):
    with open(path, 'w') as f:
        f.write(buffer.get_text())  # Join lines with '\n'
```

**Save dialog?**
- No — text editors are minimal
- Prompt shows "Ctrl+S: Save" in status line
- Save path displayed in status line

### Loading

**On startup:**
```python
def load_file(self, path: str):
    with open(path, 'r') as f:
        text = f.read()
    buffer.set_text(text)
```

---

## Performance Characteristics

| Metric | Value |
|--------|-------|
| Input polling rate | 100Hz (10ms) |
| Key event latency | <10ms |
| Screen refresh rate | On-demand (not fixed) |
| Character render time | <1ms |
| Full screen render (80×25) | ~50ms |
| Memory usage | ~10KB (buffer) + ~5MB (offscreen) |

**Bottlenecks:**
- Framebuffer writes (not CPU-bound)
- Can improve with double buffering
- Can improve with region-based updates (only redraw changed lines)

---

## Usage

### Start Editor

```bash
# Basic (uses /dev/fb0)
sudo python3 tools/fb_text_editor.py

# Specific framebuffer
sudo python3 tools/fb_text_editor.py --fb /dev/fb1

# Load file
sudo python3 tools/fb_text_editor.py --file /tmp/document.txt
```

### Controls

| Key | Action |
|-----|--------|
| `a-z`, `0-9` | Type character |
| Arrow keys | Move cursor |
| `Backspace` | Delete character |
| `Enter` | Insert newline |
| `Ctrl+Q` | Quit |
| `Ctrl+S` | Save to file |

### Testing Without Hardware

**Mock framebuffer:**
```python
# Create test framebuffer
dd if=/dev/zero of=/tmp/test_fb bs=1024 count=100

# Test with mock
sudo losetup /dev/loop0 /tmp/test_fb
sudo python3 tools/fb_text_editor.py --fb /dev/loop0
```

---

## Extensions

### Mouse Support

**Adding mouse:**
```python
def handle_mouse_click(x, y, button):
    # Convert pixel to grid position
    grid_x = (x - margin_x) // char_width
    grid_y = (y - margin_y) // char_height

    # Move cursor to clicked position
    cursor.row = grid_y
    cursor.col = grid_x
```

**Mouse events:**
- Left click: Move cursor
- Right click: Context menu
- Scroll: Scroll viewport

### Syntax Highlighting

**Keyword detection:**
```python
def render_line(line, y, keywords):
    # Highlight keywords
    for keyword in keywords:
        if keyword in line:
            highlight_keyword(line, keyword, fg_color=(255, 255, 0))
```

### Multiple Buffers

**Tab support:**
```python
@dataclass
class EditorState:
    buffers: List[TextBuffer] = field(default_factory=list)
    current_buffer: int = 0

    def switch_buffer(self, index: int):
        self.current_buffer = index
        render()
```

---

## Comparison: Pixel-Native vs X11

| Feature | Pixel-Native | X11/Wayland |
|---------|--------------|-------------|
| Dependencies | None | X11/Wayland libraries |
| Memory | ~10KB | ~50MB+ |
| Boot time | Instant | Seconds |
| Graphics | VGA fonts only | Anti-aliased fonts |
| Mouse | Basic evdev | Full support |
| Performance | Faster (no IPC) | Slower (X11 protocol) |

---

## Files

- **`tools/evdev_input.py`** — Linux evdev input handler
- **`tools/fb_text_editor.py`** — Minimal framebuffer text editor
- **`tools/vga_font_8x16.py`** — VGA 8x16 font library

---

**Document Version:** 1.0  
**Last Updated:** 2026-08-25  
**Status:** Complete — Minimal but functional text editor