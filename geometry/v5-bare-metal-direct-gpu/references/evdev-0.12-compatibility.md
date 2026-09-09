# evdev 0.12 API Compatibility Issues

## Blocked API Patterns

The `evdev` crate version 0.12 does not match the expected API patterns from higher versions or documentation.

### Issue 1: InputEventKind::Key Pattern

**Expected pattern:**
```rust
match event.kind() {
    InputEventKind::Key(Key::BTN_LEFT) => { ... }
}
```

**Actual evdev 0.12 reality:**
- `InputEventKind::Key` takes a `Key` enum directly
- But the pattern `InputEventKind::Key(Key::BTN_LEFT)` is wrong — `Key::BTN_LEFT` is passed directly to `InputEventKind::Key`, not nested
- Correct pattern is:
```rust
match event.kind() {
    InputEventKind::Key(key) if key == Key::BTN_LEFT => { ... }
}
```

### Issue 2: Relative Axis Access

**Expected pattern:**
```rust
InputEventKind::RelAxis(RelAxisType::REL_X) => { ... }
```

**Actual evdev 0.12 reality:**
- No `InputEventKind::RelAxis` variant exists
- Relative axis events are accessed differently (likely via `event.code()` with manual mapping)
- Need to check evdev documentation for the correct way to get REL_X/REL_Y from events

### Issue 3: ClipRect Construction

**Expected pattern:**
```rust
let clip = ClipRect {
    x1: 0,
    y1: 0,
    x2: disp_w,
    y2: disp_h,
};
card.dirty_framebuffer(fb, &[clip])?;
```

**Actual evdev 0.12 reality:**
- `ClipRect` is a tuple struct wrapping `drm_sys::drm_clip_rect`
- The inner struct has private fields, can't construct directly via tuple syntax
- Need to use constructor method (likely `ClipRect::new()`) or find the correct API

## Current Workaround

Skip `evdev` integration for now. Focus on Phase 2 rendering loop stability.

Phase 2 is fully functional:
- Direct KMS rendering confirmed via screenshot
- virtio-gpu shadow buffer sync working
- GPU Window Coordinator output verified on host and VM

Resume Phase 3 after fixing evdev API compatibility.

## Reference Links

- evdev crate: https://crates.io/crates/evdev (check version-specific docs)
- drm-rs crate: https://crates.io/crates/drm
- Linux input subsystem: https://www.kernel.org/doc/html/input/input.html