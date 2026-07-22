# TASK_A001 DRAFT SUMMARY

## Task Information
- **Task ID**: TASK_A001
- **Title**: Ollama contextual memory for container self-awareness
- **Priority**: HIGH
- **Phase**: Container Self-Awareness & Enhanced Security

## Description
Enhanced tools/ollama_prompt.py with conversation history tracking across container sessions so that containers can maintain context between queries.

## Implementation Drafted

### 1. New Class: `ContextualOllamaPrompter`

Added a new high-level class that provides container-isolated conversation memory:

**Key Features:**
- **Container-isolated histories**: Each container gets its own conversation context stored in `~/.hermes/container_context/<container_id>.json`
- **Automatic persistence**: Context is automatically saved to disk after each update (configurable via `auto_persist`)
- **History limits**: Configurable `max_history` parameter to limit the number of messages kept (oldest are pruned)
- **Token-based limits**: Integrated with existing `ConversationMemory` for token-aware context pruning
- **Metadata tracking**: Tracks container_id, timestamps, and other metadata

**API Methods:**
- `__init__(container_id, context_dir=None, auto_persist=True, max_history=None, max_tokens=4096)`: Initialize with configuration
- `track_context(role, content)`: Add a message to the conversation history
- `get_conversation_history()`: Get full conversation history
- `clear_context()`: Clear conversation history
- `history_to_prompt_string(max_messages=20)`: Convert history to formatted string
- `get_context_for_ollama(max_messages=20)`: Get history formatted for Ollama API
- `save_context()`: Manually save context to disk
- `load_context()`: Manually load context from disk
- `query_ollama(prompt, model, system_prompt)`: Query Ollama with full context (automatically tracks query/response)
- `get_container_id()`: Get container ID
- `get_metadata()`: Get conversation metadata

### 2. Integration with Existing Code

The implementation leverages the existing `ConversationMemory` class which provides:
- Token-based context management
- JSON serialization/deserialization
- Conversation history tracking with timestamps
- Message pruning when over token limit

### 3. Test File Created

Created `tests/test_ollama_contextual_memory.py` with comprehensive test coverage:

**Test Suites:**
- `TestContextualMemoryBasic`: Basic functionality tests
  - Context isolation between containers
  - Context persistence across queries
  - Context clearing

- `TestContextualMemoryFormatting`: Output formatting tests
  - History to prompt string conversion
  - Context formatting for Ollama API

- `TestContextualMemoryPersistence`: Disk persistence tests
  - Context saves to disk
  - Context loads from disk
  - Auto-persistence on track

- `TestContextualMemoryMetadata`: Metadata handling tests
  - Metadata tracking (timestamps, container_id)
  - Max history limit enforcement

- `TestEdgeCases`: Edge case handling tests
  - Empty container ID handling
  - Special characters in messages (quotes, newlines, emoji, unicode)

## Verification

All 12 tests passed successfully:

```
============================================================
All 12 tests PASSED!
============================================================

[Test 1] Context isolation between containers  ✓ PASS
[Test 2] Context persistence across queries     ✓ PASS
[Test 3] Context clear                          ✓ PASS
[Test 4] History to prompt string               ✓ PASS
[Test 5] Context for Ollama                     ✓ PASS
[Test 6] Context saves to disk                  ✓ PASS
[Test 7] Context loads from disk                ✓ PASS
[Test 8] Auto persistence                       ✓ PASS
[Test 9] Metadata tracking                      ✓ PASS
[Test 10] Max history limit                     ✓ PASS
[Test 11] Empty container ID                    ✓ PASS
[Test 12] Special characters in messages        ✓ PASS
```

## Files Modified

1. **tools/ollama_prompt.py**
   - Added `import os` for path expansion
   - Added `ContextualOllamaPrompter` class (~230 lines)
   - Leverages existing `ConversationMemory` class

2. **tests/test_ollama_contextual_memory.py**
   - Created comprehensive test suite (~300 lines)
   - 5 test classes with 12 total test methods

## Usage Example

```python
from tools.ollama_prompt import ContextualOllamaPrompter

# Create prompter for a specific container
prompter = ContextualOllamaPrompter(
    container_id="my_container",
    auto_persist=True,
    max_history=20
)

# Track context (automatically persisted)
prompter.track_context("user", "What is the capital of France?")

# Query Ollama with full context
response = prompter.query_ollama("Please answer.")

# Follow-up question maintains context
followup = prompter.query_ollama("And what about Germany?")

# Context persists across sessions
# (if another process creates prompter with same container_id)
```

## Receipt Criteria Met

✓ Enhanced `tools/ollama_prompt.py` with `ContextualOllamaPrompter` class
✓ Conversation history tracking across container sessions
✓ Container-isolated contexts (no cross-contamination)
✓ Automatic persistence to disk for session resilience
✓ Configurable history limits and token management
✓ Comprehensive test suite with all tests passing

## Next Steps

This implementation is ready for the autonomous gate to:
1. Verify the test command runs successfully
2. Review the code changes
3. Commit if verification passes
4. Mark TASK_A001 as COMPLETE in ROADMAP.md

---

**Drafted by**: Visual Audio Eager Drafter
**Date**: 2026-07-21
**Status**: Draft complete, awaiting autonomous gate verification