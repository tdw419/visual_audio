//! Raw evdev input handling for Phase 3.
//!
//! Reads mouse events directly from /dev/input using the `evdev` crate
//! and converts them to WindowEvent structs for the GPU interaction shader.
//!
//! Supports:
//! - BTN_LEFT clicks
//! - REL_X / REL_Y motion (relative PS/2-style mice)
//! - ABS_X / ABS_Y motion (QEMU's default "vmmouse" absolute-position device —
//!   this is what actually receives host cursor motion under SDL/GTK display
//!   without an explicit grab, and is the practical default for V5's target
//!   1280x800 KMS mode)

use evdev::{AbsoluteAxisType, InputEventKind, Key};

pub struct EvdevReader {
    device: evdev::Device,
    pos: (i32, i32),
    left_pressed: bool,
    abs_x_range: Option<(i32, i32)>,
    abs_y_range: Option<(i32, i32)>,
    screen_w: i32,
    screen_h: i32,
}

impl EvdevReader {
    /// Open /dev/input/event0 (or device specified by V5_INPUT_DEVICE env var).
    /// `screen_w`/`screen_h` are the display's pixel dimensions, used to scale
    /// absolute-axis events (raw device range, e.g. 0-32767) into pixel coords.
    pub fn open(screen_w: i32, screen_h: i32) -> std::io::Result<Self> {
        let device_path = std::env::var("V5_INPUT_DEVICE")
            .unwrap_or_else(|_| "/dev/input/event0".to_string());

        let mut device = evdev::Device::open(&device_path)?;

        let abs_x_range = device
            .get_abs_state()
            .ok()
            .map(|s| s[AbsoluteAxisType::ABS_X.0 as usize])
            .map(|a| (a.minimum, a.maximum));
        let abs_y_range = device
            .get_abs_state()
            .ok()
            .map(|s| s[AbsoluteAxisType::ABS_Y.0 as usize])
            .map(|a| (a.minimum, a.maximum));

        // Grab the device so events don't go to X11/Wayland
        device.grab()?;

        Ok(Self {
            device,
            pos: (0, 0),
            left_pressed: false,
            abs_x_range,
            abs_y_range,
            screen_w,
            screen_h,
        })
    }

    /// Process events until a complete window event is ready.
    ///
    /// Returns None if no complete window event is available yet (e.g., still
    /// accumulating motion data) or if no events are pending. Returns Some(WindowEvent)
    /// when we have a click or drag event ready to dispatch.
    ///
    /// Non-blocking: returns immediately if no input events are available.
    pub fn next_window_event(&mut self) -> std::io::Result<Option<crate::window::WindowEvent>> {
        // Check if events are available without blocking using libc::poll
        use std::os::fd::AsRawFd;

        let mut poll_fds = [libc::pollfd {
            fd: self.device.as_raw_fd(),
            events: libc::POLLIN,
            revents: 0,
        }];

        let poll_result = unsafe { libc::poll(poll_fds.as_mut_ptr(), 1, 0) };

        if poll_result <= 0 {
            // No events available (or error), return None immediately (non-blocking)
            return Ok(None);
        }

        // Fetch events (non-blocking now since we know data is available)
        let events = self.device.fetch_events()?;

        let mut window_event = None;
        // Accumulate drag deltas across the whole batch. A single fetch can
        // contain REL_X + REL_Y (+ SYN) for one diagonal motion; emitting a
        // drag per axis would drop the earlier delta (window_event is a
        // single slot, so the last RelAxis would overwrite the first).
        let mut acc_dx = 0i32;
        let mut acc_dy = 0i32;
        // A click's position must reflect this batch's motion even when
        // BTN_LEFT arrives before the ABS_X/ABS_Y events that report where
        // the press actually happened (same SYN_REPORT frame) — so defer
        // emitting the click event until self.pos has been fully updated.
        let mut click_pending = false;

        for event in events {
            match event.kind() {
                InputEventKind::Key(Key::BTN_LEFT) => {
                    if event.value() > 0 {
                        self.left_pressed = true;
                        click_pending = true;
                    } else {
                        self.left_pressed = false;
                    }
                }
                InputEventKind::Key(_) => {
                    // Ignore other keys for now
                }
                InputEventKind::RelAxis(rel) => {
                    let delta = event.value() as i32;

                    if rel == evdev::RelativeAxisType::REL_X {
                        if self.left_pressed {
                            acc_dx += delta;
                        }
                        self.pos.0 += delta;
                    } else if rel == evdev::RelativeAxisType::REL_Y {
                        if self.left_pressed {
                            acc_dy += delta;
                        }
                        self.pos.1 += delta;
                    }
                }
                InputEventKind::AbsAxis(abs) => {
                    let raw = event.value();

                    if abs == AbsoluteAxisType::ABS_X {
                        if let Some((min, max)) = self.abs_x_range {
                            let new_x = scale(raw, min, max, self.screen_w);
                            if self.left_pressed {
                                acc_dx += new_x - self.pos.0;
                            }
                            self.pos.0 = new_x;
                        }
                    } else if abs == AbsoluteAxisType::ABS_Y {
                        if let Some((min, max)) = self.abs_y_range {
                            let new_y = scale(raw, min, max, self.screen_h);
                            if self.left_pressed {
                                acc_dy += new_y - self.pos.1;
                            }
                            self.pos.1 = new_y;
                        }
                    }
                }
                _ => {
                    // Ignore other events (including sync)
                }
            }
        }

        // Click takes priority within a batch: a press-then-move in the same
        // SYN_REPORT should register as a click at the up-to-date position,
        // not a drag (there was no prior press to drag from).
        if click_pending {
            window_event = Some(crate::window::WindowEvent::click(self.pos.0, self.pos.1));
        } else if self.left_pressed && (acc_dx != 0 || acc_dy != 0) {
            // Emit ONE drag with the accumulated deltas if any motion occurred
            // while the button was held (anchor = position before this batch).
            window_event = Some(crate::window::WindowEvent::drag(
                self.pos.0 - acc_dx,
                self.pos.1 - acc_dy,
                acc_dx,
                acc_dy,
            ));
        }

        Ok(window_event)
    }
}

/// Map a raw absolute-axis value (device range `[min, max]`) to a pixel coordinate in `[0, screen_dim)`.
fn scale(raw: i32, min: i32, max: i32, screen_dim: i32) -> i32 {
    if max <= min {
        return 0;
    }
    ((raw - min) as i64 * screen_dim as i64 / (max - min) as i64) as i32
}