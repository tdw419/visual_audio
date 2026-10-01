# Directive Execution Layer

## Overview

The directive execution layer turns spatial governance from logging to actual execution. Structures (village_center, ai_council) now receive and execute governance directives, producing real outputs that persist to the container.

## Architecture

```
spatial_governor.py → issues directives → directive_executor.py → invokes handlers → structures execute → results written to governance logs
```

## Components

### 1. Directive Generators

**tools/spatial_governor.py**: Issues governance directives
- Reads structures from container
- Detects cascade conditions (consensus, coordination, synthesis)
- Generates JSON directives: `{target, action, params, timestamp, governor_id}`

### 2. Directive Executor

**tools/directive_executor.py**: Dispatches directives to structures
- Reads governance logs from container
- Parses target structure type and coordinates
- Invokes appropriate handler via `va_container.py run`
- Passes coordinates via `--x` and `--y` flags

**tools/simple_executor.py**: Streamlined executor (recommended)
- Same flow as directive_executor.py
- Passes directive content via `--directive-json` flag
- Cleaner separation between discovery and execution

### 3. Structure Handlers

**tools/village_center_handler.py**: Village center execution
- `coordinate`: Gathers status from local structures (radius=4 tiles)
- `build`: Places new structure at specified location
- `report`: Writes coordination report to governance logs

**tools/ai_council_handler.py**: AI council execution
- `debate`: Simulates multi-agent debate, calculates consensus
- `vote`: Casts vote on a proposal
- `synthesize`: Generates new proposal from recent debates

## Execution Flow

### Step 1: Governor issues directive
```json
{
  "target": "village_center.py.8_8",
  "action": "coordinate",
  "params": {"mode": "gather_status", "targets": ["post_office", "utility_shed"]},
  "timestamp": 1786712687.11,
  "governor_id": "spatial_governor_v1"
}
```

### Step 2: Executor invokes handler
```bash
python3 tools/va_container.py run visual_audio.mkv tools/village_center_handler.py \
  --directives --x 8 --y 8
```

### Step 3: Handler executes directive
- village_center_handler.py reads container
- Finds local structures within radius 4
- Writes coordination report to governance logs

### Step 4: Results persist
```
[governance] coordination_report_8_8_1786712687117335
  Contains: local structures list, status for each, timestamp
```

## Running the Execution Layer

### Execute recent directives
```bash
# Execute 10 most recent directives
python3 tools/simple_executor.py --container visual_audio.mkv --recent 10

# Execute all directives
python3 tools/simple_executor.py --container visual_audio.mkv --all
```

### Execute specific directive (for testing)
```bash
# Manually invoke village center handler
python3 tools/va_container.py run visual_audio.mkv tools/village_center_handler.py \
  --directives --x 8 --y 8

# Manually invoke AI council handler
python3 tools/va_container.py run visual_audio.mkv tools/ai_council_handler.py \
  --directives --x 2 --y 7
```

### Check execution results
```bash
# View recent governance logs
python3 tools/va_container.py ls visual_audio.mkv | grep "\[governance\]" | tail -20

# Read a coordination report
python3 tools/va_container.py cat visual_audio.mkv coordination_report_8_8_* -o report.json
cat report.json

# Read a debate log
python3 tools/va_container.py cat visual_audio.mkv debate_log_2_7_* -o debate.json
cat debate.json
```

## Structure Handler API

### Village Center

**Actions**:
- `coordinate`: Gather status from local structures
  - `params.mode`: "gather_status", "coordinate"
  - `params.targets`: List of structure types to query
  - Output: coordination_report with local structures and their status

- `build`: Place new structure at location
  - `params.x`: Target X coordinate
  - `params.y`: Target Y coordinate
  - `params.type`: Structure type ("utility_shed", "watchtower", "marketplace")
  - Output: New architecture entry in container

### AI Council

**Actions**:
- `debate`: Run multi-agent consensus process
  - `params.topic`: Topic to debate
  - `params.consensus_threshold`: Required consensus ratio (0.0-1.0)
  - Output: debate_log with agents, arguments, consensus, threshold met boolean

- `vote`: Cast vote on proposal
  - `params.proposal_id`: Proposal identifier
  - `params.vote`: Vote value ("approve", "reject", "abstain")
  - Output: vote record in governance logs

- `synthesize`: Generate proposal from deliberations
  - `params.source`: Topic/context for synthesis
  - Output: synthesis proposal in governance logs

## Handler Development Pattern

To add a new structure handler:

1. Create handler script: `tools/<structure>_handler.py`
2. Parse coordinates from `--x` and `--y` arguments
3. Read directives targeting this structure from governance logs
4. Execute directive actions
5. Write results to governance logs
6. Add handler mapping to `simple_executor.py`'s `get_handler_for_structure()`
7. Add handler to container: `va_container.py add visual_audio.mkv tools/<structure>_handler.py`

## Future Enhancements

1. **Directive Acknowledgement**: Mark directives as executed to prevent duplicate execution
2. **Cascading Execution**: Allow structures to issue new directives (e.g., village_center → build → new structure receives directive)
3. **Real LLM Integration**: Replace simulated debates with actual multi-agent LLM reasoning
4. **Resource Constraints**: Structures track resource usage, governors manage allocation
5. **Inter-Biome Communication**: Cross-biome directives for coordinated actions

## Verification

```bash
# Full autonomous loop with execution
bash tools/self_hosted_autonomy.sh
python3 tools/simple_executor.py --container visual_audio.mkv --recent 20

# Check container state
python3 tools/va_container.py ls visual_audio.mkv
python3 tools/va_container.py verify visual_audio.mkv
```

Expected results:
- Governance logs include coordination reports, debate logs, vote records
- Village centers report on local structures
- AI councils produce consensus calculations
- New structures may appear (if build directives issued)
- All entries verify (CRC + sha256)