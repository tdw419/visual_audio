# runtime/shader_os_runtime.py
import re
import time
import wgpu
import numpy as np
from pathlib import Path
from global_bind_group_layout import GLOBAL_BIND_GROUP_LAYOUT_ENTRIES, BUFFER_NAMES

# WGSL Constants from os_abi.wgsl (for buffer sizing in Python)
OS_MAX_REQUESTS = 1024
OS_MAX_RESPONSES = 1024
OS_DEBUG_ENTRIES = 2048
OS_VM_VRAM_SIZE = 1024 * 1024 # 1M u32
OS_VM_THREADS = 1024

OS_DISPLAY_WIDTH = 1920
OS_DISPLAY_HEIGHT = 1080
OS_FRAMEBUFFER_SIZE = OS_DISPLAY_WIDTH * OS_DISPLAY_HEIGHT # Each pixel is a u32 (RGBA)

OS_MAX_DEBUG_TRACES = 65536

OS_MAX_FILES = 65536
OS_MAX_BLOCKS = 262144
OS_BLOCK_SIZE = 4096

OS_MAX_WINDOWS = 256
OS_WINDOW_EVENTS_MAX = 1024
OS_MAX_RENDER_COMMANDS = 4096

OS_MAX_SOCKETS = 1024
OS_MAX_PACKETS = 8192
OS_PACKET_BUFFER_SIZE = 1514

MAX_MODELS = 16
MAX_LAYERS = 128
MAX_AI_REQUESTS = 256
MAX_WEIGHTS = 1048576 # 1M floats

# AI Service ID (must match ai_service.wgsl)
AI_SERVICE_ID = 7

# Service IDs for various ShaderOS functionalities
SERVICE_RELOAD = 1
SERVICE_NETWORK = 2
SERVICE_MANAGER = 3
SERVICE_CONTROL = 4
CTRL_REQUEST_RELOAD = 0
CTRL_REQUEST_EXIT = 1
SERVICE_FILESYSTEM = 5 # Re-assigned to avoid conflict with SHADER_ID_SUBSTRATE_KERNEL
SERVICE_SYSCALL_LOGGER = 6
SERVICE_WINDOW = 8 

# General Shader IDs (non-service-related)
SHADER_ID_SUBSTRATE_KERNEL = 0 # Substrate is the base, give it ID 0
SHADER_ID_FILESYSTEM_SHADER = 10
SHADER_ID_NETWORK_SHADER = 11
SHADER_ID_WINDOW_COMPOSITOR = 12


class ShaderOSRuntime:
    def __init__(self):
        print("🚀 ShaderOSRuntime - The Layer Above Shaders")
        
        self.device = wgpu.utils.get_default_device()
        self.queue = self.device.queue # Added queue for buffer operations

        # Create the global bind group layout and bind group BEFORE creating buffers
        self.global_bind_group_layout = self.device.create_bind_group_layout(
            entries=GLOBAL_BIND_GROUP_LAYOUT_ENTRIES
        )

        self.shared_buffers = self._create_shared_buffers()

        # Write the size of the payload buffer (in u32s) to the system flags buffer
        # This makes the size available to shaders, as they cannot use arrayLength on this buffer.
        payload_size_in_u32s = self.shared_buffers['payload_buffer'].size // 4
        self.queue.write_buffer(
            self.shared_buffers['system_flags'],
            0,  # Offset for the first element
            np.array([payload_size_in_u32s], dtype=np.uint32).tobytes()
        )

        self.shader_registry = {}
        self.service_handlers = {
            SERVICE_FILESYSTEM: self.handle_filesystem,
            SERVICE_RELOAD: self.handle_reload,    
            SERVICE_NETWORK: self.handle_network,    
            SERVICE_MANAGER: self.handle_service_manager,
            SERVICE_CONTROL: self.handle_control_request,
            SERVICE_SYSCALL_LOGGER: self.handle_syscall_logger, 
            SERVICE_WINDOW: self.handle_window_service, 
            AI_SERVICE_ID: self.handle_ai_service, 
        }

        self.global_bind_group = self._create_global_bind_group()
        
    def _create_shared_buffers(self):
        buffers = {}
        # Default sizes for buffers (can be refined later based on actual usage)
        # These are in bytes
        # Match buffer sizes to os_abi.wgsl constants
        # OS_MAX_REQUESTS = 1024, OS_MAX_RESPONSES = 1024, OS_DEBUG_ENTRIES = 2048, etc.
        DEFAULT_BUFFER_SIZES = {
            # Host-Shader ABI (matching os_abi.wgsl)
            'service_requests': 1024 * 20,  # OS_MAX_REQUESTS=1024, ServiceRequest=5 u32s = 20 bytes
            'service_responses': 1024 * 16, # OS_MAX_RESPONSES=1024, ServiceResponse=4 u32s = 16 bytes
            'payload_buffer': 4 * 1024 * 1024, # 4MB for general payload data
            # Debugging (matching os_abi.wgsl)
            'debug_log': 2048 * 16,        # OS_DEBUG_ENTRIES=2048, DebugEntry=4 u32s = 16 bytes
            'debug_index': 4,              # Single u32 for atomic counter
            # Bytecode VM specific (matching os_abi.wgsl)
            'bytecode_program': 4 * 1024 * 1024, # 4MB for bytecode program
            'vm_vram': OS_VM_VRAM_SIZE * 4,    # OS_VM_VRAM_SIZE u32s * 4 bytes/u32
            'vm_thread_state': OS_VM_THREADS * 48,  # OS_VM_THREADS=1024, VMThreadState=~12 u32s = 48 bytes
            # Global OS State
            'global_frame_counter': 4,     # Single u32
            'system_flags': 64,            # 16 u32s as per os_abi.wgsl
            
            # Display/Debug Visualization Buffers
            'os_compositor_framebuffer': OS_FRAMEBUFFER_SIZE * 4, # OS_FRAMEBUFFER_SIZE u32s * 4 bytes/u32
            'os_display_framebuffer': OS_FRAMEBUFFER_SIZE * 4, # OS_FRAMEBUFFER_SIZE u32s * 4 bytes/u32
            'os_debug_traces': OS_MAX_DEBUG_TRACES * 28, # OS_MAX_DEBUG_TRACES * sizeof(DebugTrace) (7 u32s = 28 bytes)
            'os_visual_debug_data': OS_FRAMEBUFFER_SIZE * 4, # OS_FRAMEBUFFER_SIZE u32s * 4 bytes/u32

            # Filesystem Service buffers
            'os_fs_metadata': OS_MAX_FILES * 1092, # OS_MAX_FILES * sizeof(FileEntry) (approx 273 u32s = 1092 bytes)
            'os_fs_data_blocks': OS_MAX_BLOCKS * OS_BLOCK_SIZE, # OS_MAX_BLOCKS * OS_BLOCK_SIZE bytes
            'os_fs_directory_entries': OS_MAX_FILES * 12, # OS_MAX_FILES * sizeof(DirectoryEntry) (3 u32s = 12 bytes)
            'os_fs_file_handles': 1024 * 16, # 1024 handles * sizeof(FileHandle) (4 u32s = 16 bytes)
            'os_fs_operations': 1024 * 52, # 1024 ops * sizeof(FileOperation) (13 u32s = 52 bytes)
            'os_fs_free_blocks_bitmap': (OS_MAX_BLOCKS // 32) * 4, # Bitmap of u32s
            'os_fs_free_inodes_bitmap': (OS_MAX_FILES // 32) * 4, # Bitmap of u32s

            # Window System buffers
            'os_ws_windows': OS_MAX_WINDOWS * 80, # OS_MAX_WINDOWS * sizeof(Window) (approx 20 u32s = 80 bytes)
            'os_ws_events': OS_WINDOW_EVENTS_MAX * 28, # OS_WINDOW_EVENTS_MAX * sizeof(WindowEvent) (7 u32s = 28 bytes)
            'os_ws_render_commands': OS_MAX_RENDER_COMMANDS * 48, # OS_MAX_RENDER_COMMANDS * sizeof(RenderCommand) (12 u32s = 48 bytes)
            'os_ws_free_window_ids_bitmap': (OS_MAX_WINDOWS // 32) * 4, # Bitmap of u32s
            'os_ws_z_order': OS_MAX_WINDOWS * 4, # OS_MAX_WINDOWS u32s
            'os_ws_focused_window': 4, # Single u32

            # Networking Service buffers
            'os_net_sockets': OS_MAX_SOCKETS * 88, # OS_MAX_SOCKETS * sizeof(Socket) (approx 22 u32s = 88 bytes)
            'os_net_packets': OS_MAX_PACKETS * 1540, # OS_MAX_PACKETS * sizeof(Packet) (385 u32s = 1540 bytes)
            'os_net_operations': 1024 * 52, # 1024 ops * sizeof(NetworkOperation) (13 u32s = 52 bytes)
            'os_net_free_socket_ids_bitmap': (OS_MAX_SOCKETS // 32) * 4, # Bitmap of u32s
            'os_net_packet_buffers': OS_MAX_SOCKETS * OS_PACKET_BUFFER_SIZE, # Dedicated buffer space
            'os_net_connection_table': OS_MAX_SOCKETS * 4, # OS_MAX_SOCKETS u32s
            'os_net_routing_table': 256 * 4, # 256 u32s
            'os_net_dns_cache': 1024 * 4, # 1024 u32s

            # AI Service buffers
            'os_ai_models': MAX_MODELS * 49536, # MAX_MODELS * sizeof(NeuralNetwork)
            'os_ai_layers': MAX_LAYERS * 24, # MAX_LAYERS * sizeof(NeuralLayer) (6 u32s = 24 bytes)
            'os_ai_requests': MAX_AI_REQUESTS * 28, # MAX_AI_REQUESTS * sizeof(AIRequest) (7 u32s = 28 bytes)
            'os_ai_results': MAX_AI_REQUESTS * 20, # MAX_AI_REQUESTS * sizeof(AIResult) (5 u32s = 20 bytes)
            'os_ai_weights': MAX_WEIGHTS * 4, # MAX_WEIGHTS f32s * 4 bytes/f32
        }

        for entry in GLOBAL_BIND_GROUP_LAYOUT_ENTRIES:
            binding_type = entry['buffer']['type']
            usage_flags = wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC

            if binding_type == wgpu.BufferBindingType.storage:
                usage_flags |= wgpu.BufferUsage.STORAGE
            elif binding_type == wgpu.BufferBindingType.read_only_storage:
                usage_flags |= wgpu.BufferUsage.STORAGE # Read-only storage still needs STORAGE flag
            # Add other types if needed (uniform, vertex, index etc.)

            # Get buffer name from BUFFER_NAMES mapping
            binding_num = entry['binding']
            buffer_name = BUFFER_NAMES.get(binding_num)

            if not buffer_name:
                print(f"Warning: No buffer name found for binding {binding_num}. Using generic name.")
                buffer_name = f"binding_{binding_num}_buffer"

            size = DEFAULT_BUFFER_SIZES.get(buffer_name, 256) # Default to 256 bytes if not specified

            buffers[buffer_name] = self.device.create_buffer(
                size=size, usage=usage_flags
            )
            print(f"Created buffer '{buffer_name}' (binding {entry['binding']}) with size {size} bytes and usage {usage_flags}")
        return buffers

    def _create_global_bind_group(self):
        entries = []
        for entry_layout in GLOBAL_BIND_GROUP_LAYOUT_ENTRIES:
            # Get buffer name from BUFFER_NAMES mapping
            binding_num = entry_layout['binding']
            buffer_name = BUFFER_NAMES.get(binding_num)

            if not buffer_name:
                print(f"Warning: No buffer name found for binding {binding_num}. Falling back to generic name.")
                buffer_name = f"binding_{binding_num}_buffer"

            if buffer_name and buffer_name in self.shared_buffers:
                entries.append({
                    "binding": entry_layout["binding"],
                    "resource": {"buffer": self.shared_buffers[buffer_name], "offset": 0, "size": self.shared_buffers[buffer_name].size}
                })
            else:
                print(f"Error: Buffer '{buffer_name}' for binding {entry_layout['binding']} not found in shared_buffers during bind group creation. This indicates a mismatch between layout and created buffers.")

        return self.device.create_bind_group(layout=self.global_bind_group_layout, entries=entries)

    def _preprocess_wgsl_includes(self, shader_path: Path, processed_files: set = None) -> str:
        """
        Recursively preprocesses WGSL files to handle `#include` directives.
        Replaces `#include "filename.wgsl"` with the content of the included file.
        """
        if processed_files is None:
            processed_files = set()

        if shader_path in processed_files:
            # Prevent infinite recursion for circular includes
            return ""

        processed_files.add(shader_path)

        code = shader_path.read_text()
        
        # Regex to find #include "filename.wgsl"
        include_pattern = re.compile(r'^#include\s+"([^"]+\.wgsl)"', re.MULTILINE)

        def replace_include(match):
            included_file_name = match.group(1)
            included_file_path = shader_path.parent / included_file_name
            
            if not included_file_path.exists():
                raise FileNotFoundError(f"Included WGSL file not found: {included_file_path}")
            
            # Recursively preprocess the included file
            included_content = self._preprocess_wgsl_includes(included_file_path, processed_files)
            return included_content

        # Replace all #include directives
        preprocessed_code = include_pattern.sub(replace_include, code)
        return preprocessed_code

    def register_shader(self, shader_id, name, path, entry_point):
        """Register a shader with the runtime, handling WGSL includes."""
        shader_path = Path(path)
        # Preprocess the WGSL code to resolve #include directives
        preprocessed_code = self._preprocess_wgsl_includes(shader_path)
        
        module = self.device.create_shader_module(code=preprocessed_code)
        
        # Pipelines are now created with the global_bind_group_layout
        pipeline = self.device.create_compute_pipeline(
            layout=self.device.create_pipeline_layout(bind_group_layouts=[self.global_bind_group_layout]),
            compute={"module": module, "entry_point": entry_point}
        )
        
        self.shader_registry[shader_id] = {
            'name': name, 'path': path, 'entry_point': entry_point,
            'pipeline': pipeline, 'module': module
        }
    
    def dispatch_shader(self, shader_id):
        """Dispatch a single shader by its ID"""
        if shader_id not in self.shader_registry:
            print(f"Error: Shader with ID {shader_id} not registered.")
            return

        shader_meta = self.shader_registry[shader_id]
        command_encoder = self.device.create_command_encoder()
        compute_pass = command_encoder.begin_compute_pass()
        
        compute_pass.set_pipeline(shader_meta['pipeline'])
        compute_pass.set_bind_group(0, self.global_bind_group) # Use the global bind group
        compute_pass.dispatch_workgroups(1, 1, 1) # Example workgroup size, needs to be dynamic or configured
        
        compute_pass.end()
        self.queue.submit([command_encoder.finish()])
    
    def tick(self):
        """Main runtime loop"""
        # Process all pending service requests
        self.process_service_requests()
        
        # Dispatch all active shaders
        for shader_id, meta in self.shader_registry.items():
            self.dispatch_shader(shader_id)
        
        # Read and clear debug log
        self.read_debug_log()
    
    def process_service_requests(self):
        """Process shader->host service requests"""
        # Simplified read for now, proper async handling would be better
        # Read service requests from GPU buffer
        req_buffer_size = self.shared_buffers['service_requests'].size
        requests_raw = self.queue.read_buffer(self.shared_buffers['service_requests'], 0, req_buffer_size)
        requests_data = np.frombuffer(requests_raw, dtype=np.uint32)

        # ServiceRequest struct layout from os_abi.wgsl:
        # opcode: u32, arg0: u32, arg1: u32, arg2: u32, arg3: u32
        # Total size: 5 * 4 = 20 bytes.
        REQ_STRUCT_SIZE_U32 = 5
        MAX_REQUESTS = 1024 # OS_MAX_REQUESTS from os_abi.wgsl

        requests_to_process = []
        for i in range(MAX_REQUESTS):
            offset = i * REQ_STRUCT_SIZE_U32
            # Check opcode (first u32) - 0 means empty/unused slot
            opcode = requests_data[offset + 0]

            if opcode != 0: # Non-zero opcode means there's a request
                req = {
                    'opcode': requests_data[offset + 0],
                    'arg0': requests_data[offset + 1],
                    'arg1': requests_data[offset + 2],
                    'arg2': requests_data[offset + 3],
                    'arg3': requests_data[offset + 4],
                }
                requests_to_process.append((i, req))
                # Clear the request after reading
                requests_data[offset + 0] = 0 
        
        if requests_to_process:
            # Write updated statuses back to GPU before processing to avoid race conditions
            self.queue.write_buffer(self.shared_buffers['service_requests'], 0, requests_data.tobytes())

            for i, req in requests_to_process:
                print(f"HOST: Processing request opcode {req['opcode']} (args: {req['arg0']}, {req['arg1']}, {req['arg2']}, {req['arg3']})")
                # Opcode determines which service to call
                # For now, just acknowledge receipt
                self.write_response(i, status=1, value0=req['arg0']) # Success

    def handle_reload(self, req, slot):
        """Handle shader hot-reload requests"""
        shader_id = req['arg0']
        if shader_id in self.shader_registry:
            meta = self.shader_registry[shader_id]
            print(f"♻️ Hot-reloading shader {meta['name']}")

            # Recompile (privileged host operation)
            new_code = Path(meta['path']).read_text()
            new_module = self.device.create_shader_module(code=new_code)

            # Pipelines are now created with the global_bind_group_layout
            new_pipeline = self.device.create_compute_pipeline(
                layout=self.device.create_pipeline_layout(bind_group_layouts=[self.global_bind_group_layout]),
                compute={"module": new_module, "entry_point": meta['entry_point']}
            )

            # Atomic swap
            self.shader_registry[shader_id]['module'] = new_module
            self.shader_registry[shader_id]['pipeline'] = new_pipeline

            # Write success response back to GPU
            self.write_response(slot, status=1, value0=0)
        else:
            print(f"Error: Shader ID {shader_id} not found for reload.")
            self.write_response(slot, status=2, value0=0xFFFFFFFF)
    
    def handle_filesystem(self, req, slot):
        """Handle filesystem I/O requests"""
        # Placeholder implementation
        print(f"HOST: Filesystem request opcode={req['opcode']}")
        self.write_response(slot, status=1, value0=0) # Success for now

    def handle_network(self, req, slot):
        """Handle network I/O requests"""
        # Placeholder implementation
        print(f"HOST: Network request opcode={req['opcode']}")
        self.write_response(slot, status=1, value0=0) # Success for now

    def handle_service_manager(self, req, slot):
        """Handle service management requests (e.g., launching new shaders/services)"""
        # Placeholder implementation
        print(f"HOST: Service manager request opcode={req['opcode']}")
        self.write_response(slot, status=1, value0=0) # Success for now

    def handle_control_request(self, req, slot):
        """Handle control service requests from shaders."""
        opcode = req['opcode']

        if opcode == CTRL_REQUEST_RELOAD:
            print(f"HOST: Control: Shader requested reload (shader_id={req['arg0']})")
            self.handle_reload(req, slot) # Delegate to handle_reload
        elif opcode == CTRL_REQUEST_EXIT:
            print("HOST: Control: Shader requested exit. Stopping runtime.")
            self.write_response(slot, status=1, value0=0) # Acknowledge exit
            raise KeyboardInterrupt("Shader requested exit.")
        else:
            print(f"HOST: Control: Unknown opcode {opcode}")
            self.write_response(slot, status=2) # Error

    def handle_syscall_logger(self, req, slot):
        """Handle syscall logging requests"""
        print(f"HOST: Syscall Logger request opcode={req['opcode']}")
        self.write_response(slot, status=1, value0=0) # Success for now

    def handle_window_service(self, req, slot):
        """Handle window service requests"""
        print(f"HOST: Window Service request opcode={req['opcode']}")
        self.write_response(slot, status=1, value0=0) # Success for now

    def handle_ai_service(self, req, slot):
        """Handle AI service requests"""
        print(f"HOST: AI Service request opcode={req['opcode']}")
        self.write_response(slot, status=1, value0=0) # Success for now

    
    def write_response(self, slot, status, value0=0, value1=0, value2=0):
        """Write service response back to GPU"""
        # ServiceResponse struct layout from os_abi.wgsl:
        # status: u32, value0: u32, value1: u32, value2: u32
        # Total size: 4 * 4 = 16 bytes.
        response_data_np = np.array([status, value0, value1, value2], dtype=np.uint32)

        RESP_STRUCT_SIZE_U32 = 4
        offset_bytes = slot * RESP_STRUCT_SIZE_U32 * 4

        self.queue.write_buffer(
            self.shared_buffers['service_responses'],
            offset_bytes, response_data_np.tobytes()
        )
    
    def read_payload_string(self, offset, length):
        """Reads a string from the payload buffer."""
        if length == 0:
            return ""
        payload_raw = self.queue.read_buffer(self.shared_buffers['payload_buffer'], offset * 4, length)
        return payload_raw.cast('B').tobytes().decode('utf-8', errors='ignore')

    def write_to_payload(self, data: bytes):
        """Writes bytes to the payload buffer and returns the offset."""
        # This is a very simplistic implementation. A real system would need a payload allocator.
        # For now, append and hope for the best.
        current_size = self.shared_buffers['payload_buffer'].size
        data_len = len(data)
        # Assuming payload_buffer can grow or has enough space
        offset_u32 = current_size // 4 # Return offset in u32s
        self.queue.write_buffer(self.shared_buffers['payload_buffer'], current_size, data)
        return offset_u32

    def read_debug_log(self):
        """Reads debug log entries from the GPU."""
        debug_index_raw = self.queue.read_buffer(self.shared_buffers['debug_index'], 0, 4)
        debug_index = np.frombuffer(debug_index_raw, dtype=np.uint32)[0]

        if debug_index == 0:
            return

        debug_log_raw = self.queue.read_buffer(self.shared_buffers['debug_log'], 0, debug_index * 4 * 4) # Each log entry is 4 u32s
        debug_entries = np.frombuffer(debug_log_raw, dtype=np.uint32)

        print("\n--- SHADER DEBUG LOG ---")
        # Assuming debug_log entries are structured: code, arg0, arg1, arg2
        for i in range(debug_index):
            entry_offset = i * 4
            code = debug_entries[entry_offset]
            arg0 = debug_entries[entry_offset + 1]
            arg1 = debug_entries[entry_offset + 2]
            arg2 = debug_entries[entry_offset + 3]
            print(f"  [{i:03d}] Code: 0x{code:04x}, Args: (0x{arg0:08x}, 0x{arg1:08x}, 0x{arg2:08x})")
        print("------------------------")

        # Clear debug log on GPU
        self.queue.write_buffer(self.shared_buffers['debug_index'], 0, np.array([0], dtype=np.uint32).tobytes())
        self.queue.write_buffer(self.shared_buffers['debug_log'], 0, np.zeros(self.shared_buffers['debug_log'].size // 4, dtype=np.uint32).tobytes())


# Demo usage
def main():
    runtime = ShaderOSRuntime()

    print("\n📦 Loading shaders...\n")

    # Helper function to safely register shaders
    def try_register_shader(shader_id, name, path, entry_point):
        try:
            runtime.register_shader(shader_id, name, path, entry_point)
            print(f"  ✓ Loaded: {name}")
            return True
        except Exception as e:
            print(f"  ✗ Failed: {name}")
            print(f"    Full Error: {str(e)}")
            return False

    # Register core shaders and service shaders
    success_count = 0

    # Core substrate kernel (essential)
    if try_register_shader(SHADER_ID_SUBSTRATE_KERNEL, "substrate_kernel", "runtime/core/substrate.wgsl", "main"):
        success_count += 1

    print("\n  Service shaders:")
    # Register service-related shaders with their assigned IDs
    if try_register_shader(SERVICE_FILESYSTEM, "filesystem_service", "runtime/services/filesystem_service.wgsl", "main"):
        success_count += 1
    if try_register_shader(SERVICE_NETWORK, "network_service", "runtime/services/network_service.wgsl", "main"):
        success_count += 1
    if try_register_shader(SERVICE_SYSCALL_LOGGER, "syscall_logger", "runtime/services/syscall_logger.wgsl", "main"):
        success_count += 1
    if try_register_shader(SERVICE_WINDOW, "window_service", "runtime/services/window_service.wgsl", "main"):
        success_count += 1
    if try_register_shader(AI_SERVICE_ID, "ai_service", "runtime/services/ai_service.wgsl", "main"):
        success_count += 1

    print("\n  General purpose shaders:")
    # Register other general purpose shaders
    if try_register_shader(SHADER_ID_FILESYSTEM_SHADER, "filesystem_shader", "runtime/services/filesystem_shader.wgsl", "main"):
        success_count += 1
    if try_register_shader(SHADER_ID_NETWORK_SHADER, "network_shader", "runtime/services/network_shader.wgsl", "main"):
        success_count += 1
    if try_register_shader(SHADER_ID_WINDOW_COMPOSITOR, "window_compositor", "runtime/services/window_compositor.wgsl", "main"):
        success_count += 1
    if try_register_shader(999, "debug_visualizer", "runtime/core/debug_visualizer.wgsl", "main"): # Using a dummy ID for now
        success_count += 1

    print(f"\n✅ ShaderOSRuntime ready - {success_count} shader(s) loaded")
    print("   Shaders can now request privileged operations\n")

    # --- AI Service Testing Setup ---
    if AI_SERVICE_ID in runtime.shader_registry:
        print("🤖 Setting up AI service test data...")
        AI_OP_INFERENCE = 1
        AI_STATUS_PENDING = 0

        # 2. Prepare dummy model (simple 1-input, 1-output, 1-layer, ReLU)
        # NeuralLayer: layer_id: u32, input_count: u32, output_count: u32, activation_type: u32, weights_offset: u32, bias_offset: u32
        dummy_layer = np.array([
            0,      # layer_id (dummy)
            1,      # input_count
            1,      # output_count
            0,      # activation_type (0=ReLU)
            0,      # weights_offset (start of ai_weights buffer)
            1       # bias_offset (ai_weights[1])
        ], dtype=np.uint32)

        # NeuralNetwork: model_id: u32, layer_count: u32, layers_offset: u32, total_parameters: u32, input_size: u32, output_size: u32
        # MAX_LAYERS is 128. Each NeuralLayer is 6 u32s. So total size for layers array is 128 * 6 = 768 u32s.
        # NeuralNetwork struct padding to be aware of. Assuming C-like packing for now.
        dummy_network_header = np.array([
            0,      # model_id
            1,      # layer_count
            0,      # layers_offset (start of os_ai_layers buffer for this model's layers)
            0,      # total_parameters (placeholder)
            1,      # input_size
            1       # output_size
        ], dtype=np.uint32)
        # Pad for layers array: 128 NeuralLayer structs, each 6 u32s.
        dummy_layers_padded = np.zeros(MAX_LAYERS * 6, dtype=np.uint32)
        dummy_layers_padded[0:6] = dummy_layer # Store the first layer

        dummy_model = np.concatenate([dummy_network_header, dummy_layers_padded])
        # The os_ai_models buffer holds an array of NeuralNetwork structs. Write our dummy_model at index 0.
        runtime.queue.write_buffer(runtime.shared_buffers['os_ai_models'], 0, dummy_model.tobytes()) # Corrected buffer name
        print("  Wrote dummy NeuralNetwork to os_ai_models buffer")

        # 3. Prepare dummy weights (1 weight, 1 bias)
        dummy_weights = np.array([0.5, 0.1], dtype=np.float32) # weight = 0.5, bias = 0.1
        runtime.queue.write_buffer(runtime.shared_buffers['os_ai_weights'], 0, dummy_weights.tobytes()) # Corrected buffer name
        print("  Wrote dummy weights to os_ai_weights buffer")

        # 4. Prepare dummy input data in os_payload_buffer
        dummy_input = np.array([2.0], dtype=np.float32) # Input value = 2.0
        input_payload_offset_bytes = 0
        runtime.queue.write_buffer(runtime.shared_buffers['payload_buffer'], input_payload_offset_bytes, dummy_input.tobytes())
        print("  Wrote dummy input data to os_payload_buffer")

        # 5. Prepare dummy AIRequest
        # AIRequest: request_id: u32, model_id: u32, request_type: u32, input_buffer_offset: u32, output_buffer_offset: u32, batch_size: u32, status: atomic<u32>
        dummy_request = np.array([
            0,                                   # request_id
            0,                                   # model_id (use the dummy model at index 0)
            AI_OP_INFERENCE,                     # request_type
            input_payload_offset_bytes // 4,     # input_buffer_offset (in u32s)
            (input_payload_offset_bytes + dummy_input.nbytes) // 4, # output_buffer_offset (after input)
            1,                                   # batch_size
            AI_STATUS_PENDING                    # status
        ], dtype=np.uint32)

        request_offset_bytes = 0 # Write the first request
        runtime.queue.write_buffer(runtime.shared_buffers['os_ai_requests'], request_offset_bytes, dummy_request.tobytes()) # Corrected buffer name
        print("  Wrote dummy AIRequest to os_ai_requests buffer")

        # 6. Initialize ai_results status for request_id 0
        # AIResult: request_id: u32, status: u32, execution_time: u32, model_id: u32, output_buffer_offset: u32
        initial_ai_result = np.array([0, AI_STATUS_PENDING, 0, 0, 0], dtype=np.uint32) # Added model_id and output_buffer_offset
        runtime.queue.write_buffer(runtime.shared_buffers['os_ai_results'], 0, initial_ai_result.tobytes()) # Corrected buffer name
        print("  Initialized os_ai_results buffer for request_id 0")
        print()

    # --- End AI Service Testing Setup ---

    # Run main loop
    # For a real OS, this would be an infinite loop
    # For now, let's run for a few frames to see debug output
    for i in range(10):
        print(f"\n=== HOST TICK {i} ===")
        runtime.tick()
        time.sleep(0.1) # Simulate frame time

    # Read back results after the ticks (only if AI service loaded)
    if AI_SERVICE_ID in runtime.shader_registry:
        print("\n--- Reading AI Results ---")
        ai_results_raw = runtime.queue.read_buffer(runtime.shared_buffers['os_ai_results'], 0, 20) # Read first AIResult (5 u32s = 20 bytes)
        ai_result_data = np.frombuffer(ai_results_raw, dtype=np.uint32)
        print(f"AI Result for request_id {ai_result_data[0]}: Status={ai_result_data[1]}, Execution Time={ai_result_data[2]}us, Model ID={ai_result_data[3]}, Output Offset={ai_result_data[4]}")

        # Read back output from os_payload_buffer
        output_offset_u32 = (0 + dummy_input.nbytes) // 4 # Same offset as used in AIRequest
        output_raw = runtime.queue.read_buffer(runtime.shared_buffers['payload_buffer'], output_offset_u32 * 4, 4) # Read 1 float
        output_data = np.frombuffer(output_raw, dtype=np.float32)
        print(f"AI Inference Output: {output_data[0]}")
        print("------------------------")

    print("\n🏁 ShaderOSRuntime demo ended.")

if __name__ == "__main__":
    main()