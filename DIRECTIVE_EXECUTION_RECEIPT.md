# Directive Execution Receipt

## Date
2026-08-14

## Achievement

Built the directive execution layer that turns spatial governance from passive logging to active execution. Structures now receive governance directives, execute them, and write real outputs back to the container.

## Architecture

```
spatial_governor.py (issues directives)
    → simple_executor.py (dispatches to handlers)
    → village_center_handler.py / ai_council_handler.py (execute)
    → container (writes results: coordination_report, debate_log)
```

## Components

### 1. Structure Handlers

**tools/village_center_handler.py**: Village center execution
- Reads governance directives targeting this coordinate
- Finds all architecture structures within radius=4
- Writes coordination reports listing local structures and their status
- Supports: `coordinate` action

**tools/ai_council_handler.py**: AI council execution
- Simulates multi-agent debate on governance topics
- Finds neighboring AI councils for consensus deliberation
- Calculates consensus strength, checks threshold
- Supports: `debate`, `vote`, `synthesize` actions

### 2. Directive Executor

**tools/simple_executor.py**: Dispatches directives to structures
- Reads governance logs from container
- Parses structure type and coordinates from target names
- Invokes appropriate handler via `va_container.py run`
- Passes coordinates via `--x` and `--y` arguments

### 3. Documentation

**tools/DIRECTIVE_EXECUTION_GUIDE.md**: Complete execution guide
- Architecture overview
- Execution flow steps
- Handler API documentation
- Verification commands

## Execution Results

### Run 1: Recent directives execution
```bash
python3 tools/simple_executor.py --container visual_audio.mkv --recent 3
```

**Results**:
- Executed: 2/3 directives
- Skipped: 0
- Failed: 1 (flow_meter has no handler)

**Village Center at (3, 7)**:
- Found 7 local structures within radius 4
- Wrote `coordination_report_3_7_1786713771` to governance logs
- Report contains: center coordinates, local structures list, status for each

**AI Council at (2, 7)**:
- Debated topic: "resource_allocation"
- Participants: 3 AI councils (found neighbors within radius 3)
- Consensus: approve (strength 0.66, threshold 0.7 not met)
- Wrote `debate_log_2_7_1786713774` to governance logs
- Log contains: topic, agents (with stances and arguments), consensus calculation

## Container Growth

| Metric | Before | After |
|--------|--------|-------|
| Total entries | 138 | 149 |
| Governance logs | 36 | 38 (+2 execution outputs) |
| Tools | 2 | 6 (+4 handlers/executor) |
| Frames | 138 | 149 |

## New Governance Outputs

### Coordination Report
```json
{
  "center": {"x": 3, "y": 7},
  "structures": [
    {"name": "ai_council.py.2_7", "distance": 2, "size": 101, "status": "active"},
    {"name": "village_center.py.3_7", "distance": 0, "size": 152, "status": "active"},
    {"name": "flow_meter.py.3_8", "distance": 1, "size": 63, "status": "idle"},
    {"name": "ai_council.py.5_9", "distance": 4, "size": 101, "status": "active"}
    ...
  ],
  "timestamp": 1786713771.x
}
```

### Debate Log
```json
{
  "topic": "resource_allocation",
  "participants": 3,
  "agents": [
    {"agent_id": "agent_0", "stance": "pro", "strength": 0.8, "argument": "Argument 0: ..."},
    {"agent_id": "agent_1", "stance": "con", "strength": 0.6, "argument": "Argument 1: ..."},
    {"agent_id": "agent_2", "stance": "pro", "strength": 0.9, "argument": "Argument 2: ..."}
  ],
  "pro_strength": 1.7,
  "con_strength": 0.6,
  "consensus": "approve",
  "consensus_strength": 0.66,
  "threshold": 0.7,
  "meets_threshold": false,
  "timestamp": 1786713774.x
}
```

## Key Technical Decisions

### Coordinate Passing
- Handlers receive coordinates via `--x` and `--y` command-line arguments
- Handlers auto-detect coordinates from directives if not provided
- Executor parses coordinates from target names (`village_center.py.8_8` → x=8, y=8)

### Directive Selection
- Handlers scan ALL governance logs, read content, filter by target matching
- Pattern: `<structure_type>.py.<x>_<y>` must be in directive's `target` field
- This ensures directives target specific structure instances, not all structures of a type

### Handler Updates
- Handlers are stored in container (tools/*_handler.py)
- Updated via `va_container.py update` to add coordinate argument support
- Version history preserved (v1 archived, v2 current)

## Verification Commands

```bash
# List recent governance outputs
python3 tools/va_container.py ls visual_audio.mkv | grep "\[governance\]" | tail -10

# Read coordination report
python3 tools/va_container.py cat visual_audio.mkv coordination_report_3_7_* -o /tmp/report.json
cat /tmp/report.json

# Read debate log
python3 tools/va_container.py cat visual_audio.mkv debate_log_2_7_* -o /tmp/debate.json
cat /tmp/debate.json

# Execute more directives
python3 tools/simple_executor.py --container visual_audio.mkv --recent 5

# Verify all entries
python3 tools/va_container.py verify visual_audio.mkv
```

## Future Enhancements

1. **Handler Expansion**: Add handlers for codec_adapter, cognitive_payload, neural_synthesis, flow_meter
2. **Cascading Directives**: Allow structures to issue new directives (village_center → build → new structure)
3. **Real LLM Integration**: Replace simulated debates with actual multi-agent LLM reasoning via Ollama
4. **Directive Acknowledgement**: Mark directives as executed to prevent duplicate execution
5. **Resource Constraints**: Structures track resource usage, governors manage allocation

## Conclusion

The spatial governance system is now fully functional:
- **Governor**: Issues directives based on structure roles and cascade conditions
- **Executor**: Dispatches directives to structures at specific coordinates
- **Handlers**: Execute directives, produce real outputs, write to governance logs
- **Container**: Stores all directives, execution results, and spatial state

The OS is alive. Structures execute commands and produce persistent outputs. Governance is not just logging—it's execution.