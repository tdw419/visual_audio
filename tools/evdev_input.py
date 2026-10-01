#!/usr/bin/env python3
"""
evdev_input.py — Linux evdev input handling.

Reads keyboard and mouse events from /dev/input/eventX devices.
Converts raw input events to high-level actions for the text editor.

Usage:
    from evdev_input import InputDevice

    # Initialize input device
    device = InputDevice('/dev/input/event0')

    # Read events (blocking or non-blocking)
    for event in device.read_events():
        if event.type == 'key':
            handle_key_event(event)
        elif event.type == 'absolute':
            handle_mouse_event(event)
"""

import struct
import fcntl
import os
from typing import Optional, List, NamedTuple
from dataclasses import dataclass

# Linux evdev event codes
EV_KEY = 0x01
EV_REL = 0x02
EV_ABS = 0x03
EV_SYN = 0x00

# Keyboard key codes (subset of linux/input.h)
KEY_ESC = 1
KEY_1 = 2
KEY_2 = 3
KEY_3 = 4
KEY_4 = 5
KEY_5 = 6
KEY_6 = 7
KEY_7 = 8
KEY_8 = 9
KEY_9 = 10
KEY_0 = 11
KEY_MINUS = 12
KEY_EQUAL = 13
KEY_BACKSPACE = 14
KEY_TAB = 15
KEY_Q = 16
KEY_W = 17
KEY_E = 18
KEY_R = 19
KEY_T = 20
KEY_Y = 21
KEY_U = 22
KEY_I = 23
KEY_O = 24
KEY_P = 25
KEY_LEFTBRACE = 26
KEY_RIGHTBRACE = 27
KEY_ENTER = 28
KEY_LEFTCTRL = 29
KEY_A = 30
KEY_S = 31
KEY_D = 32
KEY_F = 33
KEY_G = 34
KEY_H = 35
KEY_J = 36
KEY_K = 37
KEY_L = 38
KEY_SEMICOLON = 39
KEY_APOSTROPHE = 40
KEY_GRAVE = 41
KEY_LEFTSHIFT = 42
KEY_BACKSLASH = 43
KEY_Z = 44
KEY_X = 45
KEY_C = 46
KEY_V = 47
KEY_B = 48
KEY_N = 49
KEY_M = 50
KEY_COMMA = 51
KEY_DOT = 52
KEY_SLASH = 53
KEY_RIGHTSHIFT = 54
KEY_KPASTERISK = 55
KEY_LEFTALT = 56
KEY_SPACE = 57
KEY_CAPSLOCK = 58
KEY_F1 = 59
KEY_F2 = 60
KEY_F3 = 61
KEY_F4 = 62
KEY_F5 = 63
KEY_F6 = 64
KEY_F7 = 65
KEY_F8 = 66
KEY_F9 = 67
KEY_F10 = 68
KEY_NUMLOCK = 69
KEY_SCROLLLOCK = 70
KEY_KP7 = 71
KEY_KP8 = 72
KEY_KP9 = 73
KEY_KPMINUS = 74
KEY_KP4 = 75
KEY_KP5 = 76
KEY_KP6 = 77
KEY_KPPLUS = 78
KEY_KP1 = 79
KEY_KP2 = 80
KEY_KP3 = 81
KEY_KP0 = 82
KEY_KPDOT = 83
KEY_HOME = 102
KEY_UP = 103
KEY_PAGEUP = 104
KEY_LEFT = 105
KEY_RIGHT = 106
KEY_END = 107
KEY_DOWN = 108
KEY_PAGEDOWN = 109
KEY_INSERT = 110
KEY_DELETE = 111

# Mouse axis codes
REL_X = 0x00
REL_Y = 0x01
REL_WHEEL = 0x08
ABS_X = 0x00
ABS_Y = 0x01

# Key states
KEY_RELEASED = 0
KEY_PRESSED = 1
KEY_REPEATED = 2

# Key code to character mapping (US layout)
KEY_MAP_SHIFTED = {
    KEY_1: '!', KEY_2: '@', KEY_3: '#', KEY_4: '$', KEY_5: '%',
    KEY_6: '^', KEY_7: '&', KEY_8: '*', KEY_9: '(', KEY_0: ')',
    KEY_MINUS: '_', KEY_EQUAL: '+', KEY_LEFTBRACE: '{', KEY_RIGHTBRACE: '}',
    KEY_SEMICOLON: ':', KEY_APOSTROPHE: '"', KEY_GRAVE: '~',
    KEY_BACKSLASH: '|', KEY_COMMA: '<', KEY_DOT: '>', KEY_SLASH: '?',
}

KEY_MAP_NORMAL = {
    KEY_1: '1', KEY_2: '2', KEY_3: '3', KEY_4: '4', KEY_5: '5',
    KEY_6: '6', KEY_7: '7', KEY_8: '8', KEY_9: '9', KEY_0: '0',
    KEY_MINUS: '-', KEY_EQUAL: '=', KEY_LEFTBRACE: '[', KEY_RIGHTBRACE: ']',
    KEY_SEMICOLON: ';', KEY_APOSTROPHE: "'", KEY_GRAVE: '`',
    KEY_BACKSLASH: '\\', KEY_COMMA: ',', KEY_DOT: '.', KEY_SLASH: '/',
}

KEY_MAP_ALPHA = {
    KEY_Q: 'q', KEY_W: 'w', KEY_E: 'e', KEY_R: 'r', KEY_T: 't',
    KEY_Y: 'y', KEY_U: 'u', KEY_I: 'i', KEY_O: 'o', KEY_P: 'p',
    KEY_A: 'a', KEY_S: 's', KEY_D: 'd', KEY_F: 'f', KEY_G: 'g',
    KEY_H: 'h', KEY_J: 'j', KEY_K: 'k', KEY_L: 'l',
    KEY_Z: 'z', KEY_X: 'x', KEY_C: 'c', KEY_V: 'v', KEY_B: 'b',
    KEY_N: 'n', KEY_M: 'm',
}

@dataclass
class InputEvent:
    """Raw evdev input event."""
    timestamp: float  # Seconds since epoch
    type: int  # EV_KEY, EV_REL, EV_ABS, etc.
    code: int  # Key code or axis
    value: int  # 0=released, 1=pressed, 2=repeated

    def __repr__(self):
        type_names = {EV_KEY: 'key', EV_REL: 'rel', EV_ABS: 'abs', EV_SYN: 'syn'}
        type_name = type_names.get(self.type, f'ev_{self.type}')
        return f"InputEvent({type_name}, code={self.code}, value={self.value})"


@dataclass
class KeyEvent:
    """High-level keyboard event."""
    key_code: int  # EVDEV key code
    char: Optional[str]  # Character if printable
    pressed: bool  # True=pressed, False=released
    modifiers: dict  # {'shift': bool, 'ctrl': bool, 'alt': bool}


@dataclass
class MouseEvent:
    """High-level mouse event."""
    x: int  # X position
    y: int  # Y position
    dx: int  # Relative X movement
    dy: int  # Relative Y movement
    left_button: bool  # Left button state
    right_button: bool  # Right button state
    wheel: int  # Wheel delta (-1, 0, +1)


class InputDevice:
    """Linux evdev input device handler."""

    def __init__(self, device_path: str):
        self.device_path = device_path
        self.fd = None
        self.modifiers = {'shift': False, 'ctrl': False, 'alt': False}
        self.mouse_state = {'x': 0, 'y': 0, 'left': False, 'right': False}

    def open(self) -> bool:
        """Open the input device."""
        try:
            self.fd = os.open(self.device_path, os.O_RDONLY | os.O_NONBLOCK)
            # Get device name
            name = self._get_device_name()
            print(f"Opened input device: {name}")
            return True
        except (FileNotFoundError, PermissionError) as e:
            print(f"Failed to open {self.device_path}: {e}")
            return False

    def _get_device_name(self) -> str:
        """Get device name using EVIOCGNAME."""
        if self.fd is None:
            return "Unknown"

        EVIOCGNAME = 0x5506
        try:
            name = fcntl.ioctl(self.fd, EVIOCGNAME, b'\x00' * 256)
            return name.decode('utf-8').rstrip('\x00')
        except:
            return "Unknown"

    def close(self) -> None:
        """Close the input device."""
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def read_events(self) -> List[InputEvent]:
        """Read raw evdev events (non-blocking)."""
        if self.fd is None:
            return []

        events = []
        try:
            # Read up to 64 events at once
            data = os.read(self.fd, 64 * 24)

            # Parse events
            for i in range(0, len(data), 24):
                sec, usec, type_, code, value = struct.unpack('llHHi', data[i:i+24])
                timestamp = sec + usec / 1_000_000
                events.append(InputEvent(timestamp, type_, code, value))

        except BlockingIOError:
            # No data available
            pass
        except OSError:
            pass

        return events

    def process_events(self, events: List[InputEvent]) -> tuple:
        """Process raw events into high-level keyboard/mouse events."""
        key_events = []
        mouse_events = []

        for event in events:
            if event.type == EV_SYN:
                continue

            elif event.type == EV_KEY:
                key_event = self._process_key_event(event)
                if key_event:
                    key_events.append(key_event)

            elif event.type == EV_REL:
                # Relative mouse movement
                if event.code == REL_X:
                    self.mouse_state['x'] = max(0, self.mouse_state['x'] + event.value)
                elif event.code == REL_Y:
                    self.mouse_state['y'] = max(0, self.mouse_state['y'] + event.value)
                elif event.code == REL_WHEEL:
                    mouse_events.append(MouseEvent(
                        x=self.mouse_state['x'],
                        y=self.mouse_state['y'],
                        dx=0,
                        dy=0,
                        left_button=self.mouse_state['left'],
                        right_button=self.mouse_state['right'],
                        wheel=event.value
                    ))

            elif event.type == EV_ABS:
                # Absolute mouse position
                if event.code == ABS_X:
                    self.mouse_state['x'] = event.value
                elif event.code == ABS_Y:
                    self.mouse_state['y'] = event.value

        return key_events, mouse_events

    def _process_key_event(self, event: InputEvent) -> Optional[KeyEvent]:
        """Process a single key event."""
        pressed = (event.value != KEY_RELEASED)

        # Update modifier states
        if event.code == KEY_LEFTSHIFT or event.code == KEY_RIGHTSHIFT:
            self.modifiers['shift'] = pressed
            return None

        if event.code == KEY_LEFTCTRL:
            self.modifiers['ctrl'] = pressed
            return None

        if event.code == KEY_LEFTALT:
            self.modifiers['alt'] = pressed
            return None

        # Map key code to character
        char = None
        if pressed:
            char = self._key_to_char(event.code)

        return KeyEvent(
            key_code=event.code,
            char=char,
            pressed=pressed,
            modifiers=self.modifiers.copy()
        )

    def _key_to_char(self, key_code: int) -> Optional[str]:
        """Convert key code to character (handles shift)."""
        # Try shifted mapping first
        if self.modifiers['shift'] and key_code in KEY_MAP_SHIFTED:
            return KEY_MAP_SHIFTED[key_code]

        # Try normal mapping
        if key_code in KEY_MAP_NORMAL:
            return KEY_MAP_NORMAL[key_code]

        # Try alpha mapping
        if key_code in KEY_MAP_ALPHA:
            char = KEY_MAP_ALPHA[key_code]
            if self.modifiers['shift']:
                return char.upper()
            return char

        # Special keys
        if key_code == KEY_SPACE:
            return ' '

        # Non-printable keys (arrows, etc.)
        return None

    def poll_events(self) -> tuple:
        """Poll and process events (non-blocking)."""
        events = self.read_events()
        return self.process_events(events)


def list_input_devices() -> List[str]:
    """List available input devices."""
    devices = []
    for i in range(0, 32):  # Check event0-event31
        path = f'/dev/input/event{i}'
        if os.path.exists(path):
            try:
                # Try to open and read name
                temp = InputDevice(path)
                if temp.open():
                    name = temp._get_device_name()
                    devices.append(f'{path} ({name})')
                    temp.close()
            except:
                pass

    return devices


def find_keyboard_device() -> Optional[str]:
    """Find the first keyboard device."""
    devices = list_input_devices()
    for device in devices:
        if 'keyboard' in device.lower() or 'kbd' in device.lower():
            return device.split(' ')[0]
    return None


def find_mouse_device() -> Optional[str]:
    """Find the first mouse device."""
    devices = list_input_devices()
    for device in devices:
        if 'mouse' in device.lower() or 'pointer' in device.lower():
            return device.split(' ')[0]
    return None


if __name__ == '__main__':
    print("Available input devices:")
    for device in list_input_devices():
        print(f"  {device}")

    # Try keyboard
    kb_path = find_keyboard_device()
    if kb_path:
        print(f"\nUsing keyboard: {kb_path}")
        kb = InputDevice(kb_path)
        if kb.open():
            print("Press keys (Ctrl+C to exit)...")
            try:
                while True:
                    key_events, _ = kb.poll_events()
                    for event in key_events:
                        if event.pressed and event.char:
                            print(f"Key pressed: {repr(event.char)}")
                        else:
                            print(f"Key event: code={event.key_code}, pressed={event.pressed}")
            except KeyboardInterrupt:
                print("\nStopped")
            finally:
                kb.close()
    else:
        print("\nNo keyboard device found (try running with sudo)")