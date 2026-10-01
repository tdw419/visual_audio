import wgpu

# Global bind group layout for ShaderOS
GLOBAL_BIND_GROUP_LAYOUT_ENTRIES = [
    {"binding": 0, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}},  # service_requests
    {"binding": 1, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}},  # service_responses
    {"binding": 2, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}},  # payload_buffer
    {"binding": 3, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}},  # debug_log
    {"binding": 4, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}},  # debug_index

    {"binding": 5, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.read_only_storage}},  # bytecode_program (read-only)
    {"binding": 6, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}},  # vm_vram
    {"binding": 7, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}},  # vm_thread_state
    {"binding": 8, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}},  # global_frame_counter
    {"binding": 9, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}},  # system_flags

    {"binding": 10, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}}, # os_compositor_framebuffer
    {"binding": 11, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}}, # os_display_framebuffer
    {"binding": 12, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}}, # os_debug_traces
    {"binding": 13, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}}, # os_visual_debug_data

    # Filesystem Service Bindings
    {"binding": 14, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}}, # os_fs_metadata
    {"binding": 15, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}}, # os_fs_data_blocks
    {"binding": 16, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}}, # os_fs_directory_entries
    {"binding": 17, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}}, # os_fs_file_handles
    {"binding": 18, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}}, # os_fs_operations
    {"binding": 19, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}}, # os_fs_free_blocks_bitmap
    {"binding": 20, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}}, # os_fs_free_inodes_bitmap

    # Window System Bindings
    {"binding": 21, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}}, # os_ws_windows
    {"binding": 22, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}}, # os_ws_events
    {"binding": 23, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}}, # os_ws_render_commands
    {"binding": 24, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}}, # os_ws_free_window_ids_bitmap
    {"binding": 25, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}}, # os_ws_z_order
    {"binding": 26, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}}, # os_ws_focused_window

    # Networking Service Bindings
    {"binding": 27, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}}, # os_net_sockets
    {"binding": 28, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}}, # os_net_packets
    {"binding": 29, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}}, # os_net_operations
    {"binding": 30, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}}, # os_net_free_socket_ids_bitmap
    {"binding": 31, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}}, # os_net_packet_buffers
    {"binding": 32, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}}, # os_net_connection_table
    {"binding": 33, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}}, # os_net_routing_table
    {"binding": 34, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}}, # os_net_dns_cache

    # AI Service Bindings
    {"binding": 35, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}}, # os_ai_models
    {"binding": 36, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}}, # os_ai_layers
    {"binding": 37, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}}, # os_ai_requests
    {"binding": 38, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}}, # os_ai_results
    {"binding": 39, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}}, # os_ai_weights
]

# Buffer name mapping (binding number -> buffer name)
BUFFER_NAMES = {
    0: 'service_requests',
    1: 'service_responses',
    2: 'payload_buffer',
    3: 'debug_log',
    4: 'debug_index',
    5: 'bytecode_program',
    6: 'vm_vram',
    7: 'vm_thread_state',
    8: 'global_frame_counter',
    9: 'system_flags',
    10: 'os_compositor_framebuffer',
    11: 'os_display_framebuffer',
    12: 'os_debug_traces',
    13: 'os_visual_debug_data',
    14: 'os_fs_metadata',
    15: 'os_fs_data_blocks',
    16: 'os_fs_directory_entries',
    17: 'os_fs_file_handles',
    18: 'os_fs_operations',
    19: 'os_fs_free_blocks_bitmap',
    20: 'os_fs_free_inodes_bitmap',
    21: 'os_ws_windows',
    22: 'os_ws_events',
    23: 'os_ws_render_commands',
    24: 'os_ws_free_window_ids_bitmap',
    25: 'os_ws_z_order',
    26: 'os_ws_focused_window',
    27: 'os_net_sockets',
    28: 'os_net_packets',
    29: 'os_net_operations',
    30: 'os_net_free_socket_ids_bitmap',
    31: 'os_net_packet_buffers',
    32: 'os_net_connection_table',
    33: 'os_net_routing_table',
    34: 'os_net_dns_cache',
    35: 'os_ai_models',
    36: 'os_ai_layers',
    37: 'os_ai_requests',
    38: 'os_ai_results',
    39: 'os_ai_weights',
}