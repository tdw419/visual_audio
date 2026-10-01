# GeOS Region Executor - TASK_G001

## Overview

The GeOS Region Executor enables dense cartridge execution via Geometry OS spatial syscalls. This integration allows Visual Audio cartridges to run in GeOS's spatial computing environment through the MMIO-based spatial syscall interface (0x8009_0000-0x8009_FFFF).

## Architecture

### Spatial Syscall Interface

The executor uses GeOS's spatial syscall layer:

- **Spatial Registry**: 0x8009_0000-0x8009_1FFF (8KB) - Syscall ID → offset/len mappings
- **Bytecode Corridor**: 0x8009_2000-0x8009_FFFF (56KB) - Spatial VM bytecode
- **VM Opcode Set**: 29-op virtual machine for spatial execution

### Execution Flow

1. **Decode**: Dense PNG cartridge is decoded to payload bytes
2. **Encode**: Payload is encoded as spatial VM bytecode
3. **Dispatch**: Spatial syscall request is created and dispatched to GeOS
4. **Execute**: GeOS executes the bytecode in the specified region

### Components

- `src/geos/region_executor.py`: Main executor implementation
- `src/geos/__init__.py`: Module exports
- `tests/test_geos_region_executor.py`: Unit tests
- `tests/test_geos_integration.py`: Integration tests

## Usage

### Command Line

Execute a cartridge via GeOS:

```bash
python3 tools/dense_encoder.py run cartridge.png --geos --region my_region
```

### Python API

```python
from src.geos.region_executor import GeOSRegionExecutor, run_cartridge_with_geos

# Convenience function
success = run_cartridge_with_geos("cartridge.png", region_id="default")

# Full API
executor = GeOSRegionExecutor()
result = executor.execute_cartridge_region("cartridge.png", region_id="my_region")

# Get execution history
history = executor.get_execution_history()
```

## Receipt Criteria

The receipt for TASK_G001 is satisfied by:

1. **Command Works**: `python3 tools/dense_encoder.py run cartridge.png --geos` executes successfully
2. **Spatial Syscall Interface**: Executor uses GeOS MMIO addresses (0x8009_0000, 0x8009_2000)
3. **Bytecode Generation**: Payload is encoded as spatial VM bytecode
4. **Region Support**: Multiple regions can be executed independently

## Testing

### Unit Tests

```bash
python3 tests/test_geos_region_executor.py
```

Tests:
- Cartridge decoding
- Bytecode generation
- Spatial syscall request creation
- Multiple region execution
- Invalid cartridge handling

### Integration Tests

```bash
python3 tests/test_geos_integration.py
```

Tests:
- Cartridge decode
- Bytecode generation
- Spatial syscall request
- Full execution pipeline
- Multiple regions
- GeOS socket connection (when available)

## Status

**Phase**: Geometry OS Integration
**Priority**: HIGH
**Status**: ✅ COMPLETE (Draft)

The implementation provides the interface layer for GeOS spatial execution. Full integration with running GeOS hypervisor requires:
1. GeOS hypervisor running with spatial syscall support
2. Real bytecode execution in spatial VM
3. Region management in GeOS spatial grid

Current implementation validates the interface and prepares for live GeOS integration.

## Dependencies

- `dense_encoder.py`: Cartridge encoding/decoding
- GeOS spatial syscall architecture (TASK_C030 complete)
- TASK_X001: Sandboxed cartridge executor (complete)

## Future Work

- [ ] Live GeOS hypervisor socket integration
- [ ] Real bytecode execution in spatial VM
- [ ] Region lifecycle management
- [ ] Spatial memory mapping
- [ ] Error recovery and rollback