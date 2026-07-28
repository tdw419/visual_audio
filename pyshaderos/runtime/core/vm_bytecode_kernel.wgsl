// vm_bytecode_kernel.wgsl
#include "os_abi.wgsl"

// --- VM Opcodes ---
const OP_NOP        : u32 = 0u;
const OP_WRITE_CONST: u32 = 1u; // R0 = arg (renamed from WRITE_CONST)
const OP_SYSCALL    : u32 = 2u; // Generic syscall. arg encodes service_id and opcode.

// --- Syscall argument encoding for VM ---
// arg format for OP_SYSCALL:
// Bits 31-24: Service ID
// Bits 23-16: Service Opcode
// Bits 15-0: Arg0 for the syscall

@compute @workgroup_size(64)
fn main( @builtin(global_invocation_id) gid: vec3<u32>) {
    let tid = gid.x;
    if (tid >= OS_VM_THREADS) { return; }

    let thread = &os_vm_threads[tid];
    if (thread.active == 0u) { return; }

    var pc = thread.pc;
    if (pc >= arrayLength(&os_vm_bytecode)) { return; }

    let instr = os_vm_bytecode[pc];
    let opcode = instr & 0xffu;
    let arg = instr >> 8u;

    switch (opcode) {
        case OP_NOP: { // NOP
            os_trace_debug_log(tid, pc, opcode, arg, 0u, 0u, 0u);
        }
        case OP_WRITE_CONST: { // WRITE_CONST arg -> VRAM[0]
            os_vm_vram[0u] = arg;
            os_trace_debug_log(tid, pc, opcode, arg, 0u, 0u, 0u);
        }
        case OP_SYSCALL: { // Generic SYSCALL
            let service_id = (arg >> 24u) & 0xFFu;
            let service_opcode = (arg >> 16u) & 0xFFu;
            let syscall_arg0 = arg & 0xFFFFu; 

            var args_consumed = 0u;

            // Find an empty request slot (very basic, no locking)
            for (var i: u32 = 0u; i < OS_MAX_REQUESTS; i = i + 1u) {
                let request_entry = &os_service_requests[i];
                if (request_entry.arg0 == 0u) { // Assuming arg0 == 0u means slot is free
                    request_entry.opcode = service_opcode;
                    request_entry.arg0 = service_id;
                    request_entry.arg1 = syscall_arg0; 

                    switch (service_id) {
                        case WINDOW_COMPOSITOR_SERVICE_ID: {
                            request_entry.arg2 = os_vm_bytecode[pc + 1u];
                            request_entry.arg3 = os_vm_bytecode[pc + 2u];
                            request_entry.payload_offset = os_vm_bytecode[pc + 3u];
                            args_consumed = 3u; // 3 additional args
                        }
                        case FILESYSTEM_SERVICE_ID: {
                            // For FS_CREATE: arg1 = name_hash, arg2 = size, arg3 = permissions, payload_offset = is_directory, owner_shader, parent_dir
                            request_entry.arg2 = os_vm_bytecode[pc + 1u]; // size
                            request_entry.arg3 = os_vm_bytecode[pc + 2u]; // permissions
                            request_entry.payload_offset = os_vm_bytecode[pc + 3u]; // is_directory (in payload_offset for simplicity)
                            // Additional args for filesystem operations will need to be read from os_payload_buffer directly by the service.
                            args_consumed = 3u; // 3 additional args (size, permissions, is_directory_payload_offset)
                        }
                        case WINDOW_SERVICE_ID: {
                            // Example for WS_CREATE_WINDOW: arg1=x, arg2=y, arg3=width, payload_offset=height (in payload)
                            request_entry.arg2 = os_vm_bytecode[pc + 1u]; // y
                            request_entry.arg3 = os_vm_bytecode[pc + 2u]; // width
                            request_entry.payload_offset = os_vm_bytecode[pc + 3u]; // height (in payload)
                            args_consumed = 3u;
                        }
                        case NETWORKING_SERVICE_ID: {
                            // Example for NET_OP_SOCKET: arg1=domain, arg2=type, arg3=protocol
                            // Example for NET_OP_BIND: arg1=socket_id, arg2=ip, arg3=port
                            // Example for NET_OP_SEND: arg1=socket_id, arg2=data_buffer_offset, arg3=data_size
                            request_entry.arg2 = os_vm_bytecode[pc + 1u]; // param2 (e.g., y for window, ip for bind)
                            request_entry.arg3 = os_vm_bytecode[pc + 2u]; // param3 (e.g., width for window, port for bind)
                            // payload_offset will be used for complex data structures or additional parameters
                            request_entry.payload_offset = os_vm_bytecode[pc + 3u]; // Additional payload offset
                            args_consumed = 3u;
                        }
                        default: {
                            // For syscall_logger or other simple syscalls, arg1 is enough
                            args_consumed = 0u;
                        }
                    }
                    
                    os_trace_debug_log(tid, pc, opcode, service_id, service_opcode, syscall_arg0, i); // Log syscall creation
                    pc = pc + args_consumed; 
                    break;
                }
            }
        }
        default: {
            os_trace_debug_log(tid, pc, 0xFFFFu, instr, 0u, 0u, 0u);
        }
    }

    thread.pc = pc + 1u;
}