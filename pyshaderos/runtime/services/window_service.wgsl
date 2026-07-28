// runtime/services/window_service.wgsl
// Complete GPU-native window management with atomic operations
#include "../core/os_abi.wgsl"

// Window service kernel
const WINDOW_SERVICE_ID: u32 = 5u; // Define a service ID for the window service

// Window Events
const MOUSE_CLICK: u32 = 0x1u;
const MOUSE_MOVE: u32 = 0x2u;
const KEY_PRESS: u32 = 0x4u;
const KEY_RELEASE: u32 = 0x8u;
const WINDOW_RESIZE: u32 = 0x10u;
const WINDOW_FOCUS: u32 = 0x20u;


@compute @workgroup_size(64, 1, 1)
fn main( @builtin(global_invocation_id) global_id: vec3<u32>) {
    let thread_id = global_id.x;
    let events_per_thread = 16u;
    let windows_per_thread = 4u;
    
    // Each thread processes window events
    for (var i: u32 = 0u; i < events_per_thread; i = i + 1u) {
        let event_index = thread_id * events_per_thread + i;
        if (event_index < 1024u) { // OS_WINDOW_EVENTS_MAX
            let event = os_ws_events[event_index];
            
            // Process the event only if it's new (event_type != 0)
            if (event.event_type != 0u) {
                process_window_event(event);
                // Clear the event after processing
                os_ws_events[event_index].event_type = 0u;
            }
        }
    }
    
    // Each thread updates a subset of windows
    for (var i: u32 = 0u; i < windows_per_thread; i = i + 1u) {
        let window_index = thread_id * windows_per_thread + i;
        if (window_index < OS_MAX_WINDOWS) {
            update_window_state(window_index);
        }
    }
}
