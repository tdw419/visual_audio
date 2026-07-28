// runtime/services/window_compositor.wgsl
#include "../core/os_abi.wgsl"

// --- Service ID and Opcodes ---
const WINDOW_COMPOSITOR_SERVICE_ID: u32 = 2u; // Define a service ID for the compositor

const OPCODE_CLEAR: u32 = 0u;
const OPCODE_DRAW_RECT: u32 = 1u;
const OPCODE_DRAW_TEXT: u32 = 2u;
const OPCODE_PRESENT: u32 = 3u; // Copy composed frame to the final framebuffer

// A helper function to set a pixel in the compositor's framebuffer
fn set_pixel(x: u32, y: u32, color: u32) {
    if (x >= OS_DISPLAY_WIDTH || y >= OS_DISPLAY_HEIGHT) { return; }
    let idx = y * OS_DISPLAY_WIDTH + x;
    os_compositor_framebuffer[idx] = color;
}

// Main compositor entry point
@compute @workgroup_size(1)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
    if (gid.x != 0u) { return; }

    // Process service requests for window compositor
    for (var i: u32 = 0u; i < OS_MAX_REQUESTS; i = i + 1u) {
        let request = &os_service_requests[i];

        // Check if this request is for the Window Compositor service
        if (request.arg0 == WINDOW_COMPOSITOR_SERVICE_ID) { // arg0 now stores service_id
            let opcode = request.opcode;
            let param0 = request.arg1; 
            let param1 = request.arg2;
            let param2 = request.arg3;

            switch (opcode) {
                case OPCODE_CLEAR: {
                    let color = param0;
                    for (var y: u32 = 0u; y < OS_DISPLAY_HEIGHT; y = y + 1u) {
                        for (var x: u32 = 0u; x < OS_DISPLAY_WIDTH; x = x + 1u) {
                            set_pixel(x, y, color);
                        }
                    }
                    os_debug_log(opcode, color, 0u);
                }
                case OPCODE_DRAW_RECT: {
                    // ServiceRequest { opcode, service_id, color, x_y_packed, width_height_packed }
                    let rect_color = request.arg1; // arg1 = color
                    let rect_x = (request.arg2 >> 16u) & 0xFFFFu; // arg2 high 16 bits = x
                    let rect_y = request.arg2 & 0xFFFFu; // arg2 low 16 bits = y
                    let rect_width = (request.arg3 >> 16u) & 0xFFFFu; // arg3 high 16 bits = width
                    let rect_height = request.arg3 & 0xFFFFu; // arg3 low 16 bits = height

                    for (var y_off: u32 = 0u; y_off < rect_height; y_off = y_off + 1u) {
                        for (var x_off: u32 = 0u; x_off < rect_width; x_off = x_off + 1u) {
                            set_pixel(rect_x + x_off, rect_y + y_off, rect_color);
                        }
                    }
                    os_debug_log(opcode, rect_x, rect_y); // Log rect draw
                }
                case OPCODE_DRAW_TEXT: {
                    // Not implementing in MVP, but will use ptr to payload for string and font info
                    os_debug_log(opcode, 0u, 0u);
                }
                case OPCODE_PRESENT: {
                    // Copy our internal compositor FB to the actual display FB
                    for (var idx: u32 = 0u; idx < OS_FRAMEBUFFER_SIZE; idx = idx + 1u) {
                        os_display_framebuffer[idx] = os_compositor_framebuffer[idx];
                    }
                    os_debug_log(opcode, 0u, 0u);
                }
                default: {
                    os_debug_log(0xFFFFu, opcode, request.arg1); // Unknown opcode
                }
            }

            // Acknowledge the request
            let response = &os_service_responses[i];
            response.status = 1u; // Success
            response.value0 = opcode;
            response.value1 = request.arg1;
            response.value2 = i; // Echo back request index

            // Mark request as processed
            request.arg0 = 0u; // Clear service ID to mark as processed
        }
    }
}
