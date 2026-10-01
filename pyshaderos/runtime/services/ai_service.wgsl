#include "../core/os_abi.wgsl"

// runtime/services/ai_service.wgsl - Phase 1 Implementation
// Note: AI constants (AI_OP_*, AI_STATUS_*) are defined in os_abi.wgsl

// Main AI service entry point
 @compute @workgroup_size(64, 1, 1)
fn main( @builtin(global_invocation_id) global_id: vec3<u32>) {
    let request_id = global_id.x;
    if (request_id >= MAX_AI_REQUESTS) { return; } // Use MAX_AI_REQUESTS from os_abi
    
    let request = os_ai_requests[request_id]; // Correct global buffer name
    if (request.request_type != AI_OP_INFERENCE) { return; }

    // Mark as processing - access directly from array
    atomicStore(&os_ai_requests[request_id].status, AI_STATUS_PENDING);

    // Execute forward pass
    handle_ai_inference(request_id, request.model_id, request.input_buffer_offset, request.output_buffer_offset, request.batch_size);
    
    // Mark as complete
    atomicStore(&os_ai_results[request_id].status, AI_STATUS_SUCCESS); // Update status in os_ai_results
    atomicStore(&os_ai_results[request_id].request_id, request_id); // Update request_id in os_ai_results
    atomicStore(&os_ai_results[request_id].execution_time, 42u); // Placeholder timing in os_ai_results
    atomicStore(&os_ai_results[request_id].model_id, request.model_id); // Set model_id
    atomicStore(&os_ai_results[request_id].output_buffer_offset, request.output_buffer_offset); // Set output_buffer_offset
}

// Helper functions
fn handle_ai_inference(
    request_id: u32,
    model_id: u32,
    input_buffer_offset: u32,
    output_buffer_offset: u32,
    batch_size: u32
) {
    let model = os_ai_models[model_id]; // Access model directly

    // Load input data
    var activations: array<f32, MAX_LAYER_SIZE>; // MAX_LAYER_SIZE is from os_abi now
    for (var i: u32 = 0u; i < batch_size; i++) {
        activations[i] = bitcast<f32>(os_payload_buffer[input_buffer_offset + i]); // Cast u32 to f32
    }
    
    // Process each layer
    var current_size = model.input_size; // Corrected from model.input_count
    for (var layer_idx: u32 = 0u; layer_idx < model.layer_count; layer_idx++) {
        let layer = os_ai_layers[model.layers_offset + layer_idx]; // Correct global buffer name and indexing
        
        // Process each neuron in parallel
        for (var neuron: u32 = 0u; neuron < layer.output_count; neuron++) {
            var sum: f32 = 0.0;
            
            // Compute weighted sum
            for (var input: u32 = 0u; input < current_size; input++) {
                let weight = os_ai_weights[layer.weights_offset + neuron * current_size + input]; // Correct global buffer name
                let activation = activations[input];
                sum = sum + weight * activation;
            }
            
            // Add bias
            let bias = os_ai_weights[layer.bias_offset + neuron]; // Correct global buffer name
            sum = sum + bias;
            
            // Apply activation function
            let output = activate(sum, layer.activation_type);
            activations[neuron] = output; // This line still looks suspicious, check later
        }
        
        // Prepare for next layer
        current_size = layer.output_count;
    }
    
    // Write output
    for (var i: u32 = 0u; i < model.output_size; i++) { // Corrected from model.output_count
        os_payload_buffer[output_buffer_offset + i] = bitcast<u32>(activations[i]); // Cast f32 to u32
    }
}

// Activation functions (GPU-optimized)
fn activate(x: f32, activation_type: u32) -> f32 {
    switch (activation_type) {
        case 0u: { return max(x, 0.0); }  // ReLU
        case 1u: { return 1.0 / (1.0 + exp(-x)); }  // Sigmoid
        case 2u: { return tanh(x); }  // Tanh
        default: { return x; }  // Linear
    }
}