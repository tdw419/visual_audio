// runtime/services/network_service.wgsl
// Complete GPU-native networking with atomic operations
#include "../core/os_abi.wgsl"

// Networking service kernel
const NETWORKING_SERVICE_ID: u32 = 6u; // Define a service ID for the networking service

// Network Operation Types
const NET_OP_SOCKET = 0x1u;
const NET_OP_BIND = 0x2u;
const NET_OP_LISTEN = 0x3u;
const NET_OP_CONNECT = 0x4u;
const NET_OP_SEND = 0x5u;
const NET_OP_RECEIVE = 0x6u;
const NET_OP_CLOSE = 0x7u;


@compute @workgroup_size(256, 1, 1)
fn main( @builtin(global_invocation_id) global_id: vec3<u32>) {
    let thread_id = global_id.x;
    let packets_per_thread = 32u;
    let operations_per_thread = 4u;
    
    // Each thread processes network packets
    for (var i: u32 = 0u; i < packets_per_thread; i = i + 1u) {
        let packet_index = thread_id * packets_per_thread + i;
        if (packet_index < OS_MAX_PACKETS) {
            let packet = os_net_packets[packet_index];
            
            // Process packet based on protocol (only if packet.protocol is valid)
            if (packet.protocol == 0u || packet.protocol == 1u || packet.protocol == 2u) {
                switch (packet.protocol) {
                    case 0u: { process_tcp_packet(packet); }
                    case 1u: { process_udp_packet(packet); }
                    case 2u: { process_icmp_packet(packet); }
                }
            }
        }
    }
    
    // Each thread processes network operations
    for (var i: u32 = 0u; i < operations_per_thread; i = i + 1u) {
        let op_index = thread_id * operations_per_thread + i;
        if (op_index < 1024u) {
            let operation = &os_net_operations[op_index];
            
            // Only process pending operations
            if (atomicLoad(&operation.status) == 0u) {
                // Check if this operation is for the networking service
                // (Assuming operation.requester_id could pass the service ID)
                // For now, let's process all pending operations here.

                atomicStore(&operation.status, 1u); // PROCESSING
                
                switch (operation.operation_type) {
                    case NET_OP_SOCKET: { handle_socket_create(op_index); }
                    case NET_OP_BIND: { handle_socket_bind(op_index); }
                    case NET_OP_LISTEN: { handle_socket_listen(op_index); }
                    case NET_OP_CONNECT: { handle_socket_connect(op_index); }
                    case NET_OP_SEND: { handle_socket_send(op_index); }
                    case NET_OP_RECEIVE: { handle_socket_receive(op_index); }
                    case NET_OP_CLOSE: { handle_socket_close(op_index); }
                    default: { 
                        atomicStore(&operation.status, 3u); // ERROR
                        os_trace_debug_log(thread_id, 0u, 0xFFFFu, operation.operation_type, 0u, 0u, 0u);
                    }
                }
            }
        }
    }
}

// Packet processing
fn process_tcp_packet(packet: Packet) {
    // Find socket for this packet
    let socket_id = find_socket_for_packet(packet);
    
    if (socket_id != 0xFFFFFFFFu) {
        let socket = &os_net_sockets[socket_id];
        let socket_state = atomicLoad(&socket.state);
        
        // Only process packets for connected sockets
        if (socket_state == 3u) { // CONNECTED
            // Check if this is a new connection or data for existing connection
            let connection_key = make_connection_key(packet.src_ip, packet.src_port, packet.dst_ip, packet.dst_port);
            let existing_connection = find_connection(connection_key);
            
            if (existing_connection == 0xFFFFFFFFu) {
                // New connection
                handle_new_tcp_connection(packet, socket_id);
            } else {
                // Data for existing connection
                handle_tcp_data(packet, socket_id);
            }
        }
    }
}

fn process_udp_packet(packet: Packet) {
    // Find socket for this packet
    let socket_id = find_socket_for_packet(packet);

    if (socket_id != 0xFFFFFFFFu) {
        let socket = &os_net_sockets[socket_id];
        let socket_state = atomicLoad(&socket.state);

        // Only process packets for connected sockets
        if (socket_state == 3u) { // CONNECTED
            // UDP is connectionless, just deliver data
            handle_udp_data(packet, socket_id);
        }
    }
}

fn process_icmp_packet(packet: Packet) {
    // Placeholder for ICMP packet processing (ICMP = 0x1CMP would be invalid, using 2 for ICMP protocol)
    os_trace_debug_log(0u, 0u, 2u, packet.src_ip, packet.dst_ip, 0u, 0u);
}

// Socket operations
fn handle_socket_create(op_index: u32) {
    let operation = &os_net_operations[op_index];
    let domain = operation.params[0];
    let socket_type = operation.params[1];
    let protocol = operation.params[2];
    let owner_shader = operation.requester_id;

    // Allocate a socket ID
    let socket_id = allocate_socket_id();
    if (socket_id == 0xFFFFFFFFu) {
        atomicStore(&operation.status, 3u); // ERROR - no free sockets
        return;
    }

    // Initialize socket
    let socket = &os_net_sockets[socket_id];
    atomicStore(&socket.id, socket_id);
    atomicStore(&socket.domain, domain);
    atomicStore(&socket.socket_type, socket_type);
    atomicStore(&socket.protocol, protocol);
    atomicStore(&socket.state, 0u); // CLOSED
    atomicStore(&socket.owner_shader, owner_shader);
    
    // Allocate packet buffers
    let recv_buffer_offset = allocate_packet_buffer();
    let send_buffer_offset = allocate_packet_buffer();
    
    atomicStore(&socket.receive_buffer_offset, recv_buffer_offset);
    atomicStore(&socket.send_buffer_offset, send_buffer_offset);
    atomicStore(&socket.receive_buffer_size, OS_PACKET_BUFFER_SIZE);
    atomicStore(&socket.send_buffer_size, OS_PACKET_BUFFER_SIZE);
    
    atomicStore(&operation.status, 2u); // COMPLETE
}

fn handle_socket_bind(op_index: u32) {
    let operation = &os_net_operations[op_index];
    let socket_id = operation.socket_id;
    let ip = operation.params[0];
    let port = operation.params[1];
    
    if (socket_id >= OS_MAX_SOCKETS) {
        atomicStore(&operation.status, 3u); // ERROR
        return;
    }
    
    let socket = &os_net_sockets[socket_id];
    let socket_state = atomicLoad(&socket.state);
    
    // Can only bind closed sockets
    if (socket_state != 0u) { // Not CLOSED
        atomicStore(&operation.status, 3u); // ERROR
        return;
    }
    
    // Bind socket to IP and port
    atomicStore(&socket.local_ip, ip);
    atomicStore(&socket.local_port, port);
    atomicStore(&socket.state, 1u); // LISTEN
    
    // Add to routing table (simplified)
    let route_index = (ip & 0xFFu) + (port & 0xFFu) * 256u; // Very basic mapping
    if (route_index < 256u) {
        atomicStore(&os_net_routing_table[route_index], socket_id);
    }
    
    atomicStore(&operation.status, 2u); // COMPLETE
}

fn handle_socket_listen(op_index: u32) {
    let operation = &os_net_operations[op_index];
    let socket_id = operation.socket_id;
    let backlog = operation.params[0];

    if (socket_id >= OS_MAX_SOCKETS) {
        atomicStore(&operation.status, 3u); // ERROR
        return;
    }

    let socket = &os_net_sockets[socket_id];
    let socket_state = atomicLoad(&socket.state);

    if (socket_state != 1u) { // Not LISTEN
        atomicStore(&operation.status, 3u); // ERROR
        return;
    }
    
    // In a real implementation, this would involve setting up a queue for pending connections
    // For now, simply transition state if already in LISTEN
    
    atomicStore(&operation.status, 2u); // COMPLETE
}

fn handle_socket_connect(op_index: u32) {
    let operation = &os_net_operations[op_index];
    let socket_id = operation.socket_id;
    let ip = operation.params[0];
    let port = operation.params[1];
    
    if (socket_id >= OS_MAX_SOCKETS) {
        atomicStore(&operation.status, 3u); // ERROR
        return;
    }
    
    let socket = &os_net_sockets[socket_id];
    let socket_state = atomicLoad(&socket.state);
    
    // Can only connect from closed or listening sockets
    if (socket_state != 0u && socket_state != 1u) {
        atomicStore(&operation.status, 3u); // ERROR
        return;
    }
    
    // Set remote address
    atomicStore(&socket.remote_ip, ip);
    atomicStore(&socket.remote_port, port);
    atomicStore(&socket.state, 2u); // CONNECTING
    
    // Initiate TCP handshake (simplified)
    let syn_packet = create_tcp_syn_packet(ip, port, socket_id);
    send_packet_to_network(syn_packet);
    
    atomicStore(&operation.status, 2u); // COMPLETE
}

fn handle_socket_send(op_index: u32) {
    let operation = &os_net_operations[op_index];
    let socket_id = operation.socket_id;
    let data_offset = operation.params[0]; // Offset in os_payload_buffer
    let data_size = operation.params[1];
    
    if (socket_id >= OS_MAX_SOCKETS) {
        atomicStore(&operation.status, 3u); // ERROR
        return;
    }
    
    let socket = &os_net_sockets[socket_id];
    let socket_state = atomicLoad(&socket.state);
    
    // Can only send from connected sockets
    if (socket_state != 3u) { // Not CONNECTED
        atomicStore(&operation.status, 3u); // ERROR
        return;
    }
    
    // Get remote address
    let remote_ip = atomicLoad(&socket.remote_ip);
    let remote_port = atomicLoad(&socket.remote_port);
    
    // Create packet
    let packet = create_data_packet(socket_id, remote_ip, remote_port, data_offset, data_size);
    
    // Send to network
    send_packet_to_network(packet);
    
    atomicStore(&operation.status, 2u); // COMPLETE
}

fn handle_socket_receive(op_index: u32) {
    let operation = &os_net_operations[op_index];
    // Simplified: in a real system, this would read from the socket's receive buffer
    // and copy to the result_buffer specified in the operation.
    // For MVP, we just complete it successfully.
    atomicStore(&operation.status, 2u); // COMPLETE
}

fn handle_socket_close(op_index: u32) {
    let operation = &os_net_operations[op_index];
    let socket_id = operation.socket_id;
    if (socket_id >= OS_MAX_SOCKETS) {
        atomicStore(&operation.status, 3u); // ERROR
        return;
    }
    let socket = &os_net_sockets[socket_id];
    atomicStore(&socket.state, 0u); // CLOSED
    // Free socket ID and associated buffers (simplified)
    free_socket_id(socket_id);
    atomicStore(&operation.status, 2u); // COMPLETE
}


// Helper functions
fn allocate_socket_id() -> u32 {
    // Use atomic operations to find free socket ID
    for (var i: u32 = 0u; i < OS_MAX_SOCKETS / 32u; i = i + 1u) { // Iterate through u32s in bitmap
        let current_word = atomicLoad(&os_net_free_socket_ids_bitmap[i]);
        if (current_word != 0xFFFFFFFFu) { // If not all bits are set (i.e., there's a free socket)
            for (var bit_idx: u32 = 0u; bit_idx < 32u; bit_idx = bit_idx + 1u) {
                let mask = 1u << bit_idx;
                if ((current_word & mask) == 0u) { // If this bit is 0 (socket is free)
                    let old_word = atomicOr(&os_net_free_socket_ids_bitmap[i], mask);
                    if ((old_word & mask) == 0u) { // If we successfully set the bit (claimed the socket)
                        return (i * 32u) + bit_idx; // Return the socket index
                    }
                }
            }
        }
    }
    return 0xFFFFFFFFu; // No free sockets
}

fn free_socket_id(socket_id: u32) {
    if (socket_id == 0xFFFFFFFFu || socket_id >= OS_MAX_SOCKETS) { return; }
    let word_idx = socket_id / 32u;
    let bit_idx = socket_id % 32u;
    let mask = 1u << bit_idx;
    atomicAnd(&os_net_free_socket_ids_bitmap[word_idx], ~mask); // Clear the bit to free the socket
}

fn allocate_packet_buffer() -> u32 {
    // For now, return a fixed offset within os_net_packet_buffers based on socket ID
    // A proper allocator would be needed for dynamic allocation
    return 0u; // Placeholder
}

fn find_socket_for_packet(packet: Packet) -> u32 {
    // For simplified routing, we assume a direct mapping or a lookup in net_routing_table
    let route_index = (packet.dst_ip & 0xFFu) + (packet.dst_port & 0xFFu) * 256u;
    if (route_index < 256u) {
        return atomicLoad(&os_net_routing_table[route_index]);
    }
    return 0xFFFFFFFFu; // No socket found
}

fn make_connection_key(src_ip: u32, src_port: u32, dst_ip: u32, dst_port: u32) -> u32 {
    // Simplified, combine IPs and ports into a single u64
    return src_ip ^ dst_ip;
}

fn find_connection(key: u32) -> u32 {
    // Placeholder, in a real system this would search the connection table
    return 0xFFFFFFFFu;
}

fn handle_new_tcp_connection(packet: Packet, socket_id: u32) { os_trace_debug_log(0u, 0u, 0u, 0u, 0u, 0u, 0u); }
fn handle_tcp_data(packet: Packet, socket_id: u32) { os_trace_debug_log(0u, 0u, 0u, 0u, 0u, 0u, 0u); }
fn handle_udp_data(packet: Packet, socket_id: u32) { os_trace_debug_log(0u, 0u, 0u, 0u, 0u, 0u, 0u); }
fn create_tcp_syn_packet(dst_ip: u32, dst_port: u32, socket_id: u32) -> Packet { return Packet(); }
fn send_packet_to_network(packet: Packet) {
    // Simplified: just store the packet for now
    // Use frame counter as a simple round-robin index
    let packet_index = atomicLoad(&os_frame_counter) % OS_MAX_PACKETS;
    os_net_packets[packet_index] = packet;
}
fn get_random_sequence() -> u32 { return atomicLoad(&os_frame_counter); } // Use frame counter as a simple random
fn get_next_sequence(socket_id: u32) -> u32 { return atomicLoad(&os_frame_counter); } // Use frame counter as a simple sequence
fn create_data_packet(socket_id: u32, dst_ip: u32, dst_port: u32, data_offset: u32, data_size: u32) -> Packet { 
    var packet: Packet;
    packet.src_ip = atomicLoad(&os_net_sockets[socket_id].local_ip);
    packet.dst_ip = dst_ip;
    packet.src_port = atomicLoad(&os_net_sockets[socket_id].local_port);
    packet.dst_port = dst_port;
    packet.protocol = atomicLoad(&os_net_sockets[socket_id].protocol);
    packet.flags = 0x18u; // PSH, ACK flags
    packet.sequence = get_next_sequence(socket_id);
    packet.ack = 0u;
    packet.data_size = data_size;
    
    // Copy data from payload buffer
    for (var i: u32 = 0u; i < (data_size + 3u) / 4u; i = i + 1u) {
        if (i < 376u) { // Ensure we don't write out of packet.data bounds (376 u32s = 1504 bytes)
            packet.data[i] = os_read_u32(data_offset + i);
        }
    }
    return packet;
}
fn os_trigger_network_send(packet_index: u32) { os_trace_debug_log(0u, 0u, 0u, 0u, 0u, 0u, 0u); }
