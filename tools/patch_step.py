with open("tools/spatial_rv64i_cpu.py", "r") as f:
    code = f.read()

import re
old_step = '''    def step(self, steps: int = 1):
        """Execute `steps` instructions in a single WGSL dispatch"""
        # First, read the current state to preserve PC and halted status
        state = self.get_state()

        # Write state with the requested number of steps
        # Preserve: pc_low, pc_high, halted, mode, trap_pending, reservation fields, uart_tx_len, ram_base
        state_data = np.array([
            state['pc_low'],
            state['pc_high'],
            state['halted'],
            steps,  # steps_remaining
            state['mode'],
            state['trap_pending'],
            state['reservation_valid'],
            state['reservation_addr_low'],
            state['reservation_addr_high'],
            state['uart_tx_len'],
            state['mtime_low'],
            state['mtime_high'],
            state['mtimecmp_low'],
            state['mtimecmp_high'],
            state['ram_base_low'],
            state['ram_base_high'],
            state['uart_rx_data_pending'],
            state['uart_rx_byte'],
            # _pad[5]
        ], dtype=np.uint32).tobytes()
        self.queue.write_buffer(self.state_buffer, 0, state_data)

        encoder = self.device.create_command_encoder()
        compute_pass = encoder.begin_compute_pass()
        compute_pass.set_pipeline(self.pipeline)
        compute_pass.set_bind_group(0, self.bind_group)
        compute_pass.dispatch_workgroups(1)
        compute_pass.end()
        self.queue.submit([encoder.finish()])

        # Trace the new state after execution
        new_state = self.get_state()
        self._trace_state(new_state['pc'], new_state['regs'])'''

new_step = '''    def step(self, steps: int = 1):
        """Execute `steps` instructions in a single WGSL dispatch"""
        # We only need to overwrite steps_remaining, which is at offset 12 (3rd u32).
        self.queue.write_buffer(self.state_buffer, 12, np.array([steps], dtype=np.uint32).tobytes())

        encoder = self.device.create_command_encoder()
        compute_pass = encoder.begin_compute_pass()
        compute_pass.set_pipeline(self.pipeline)
        compute_pass.set_bind_group(0, self.bind_group)
        compute_pass.dispatch_workgroups(1)
        compute_pass.end()
        self.queue.submit([encoder.finish()])
        self.device.poll(True)'''

code = code.replace(old_step, new_step)
with open("tools/spatial_rv64i_cpu.py", "w") as f:
    f.write(code)
