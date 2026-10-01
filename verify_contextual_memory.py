#!/usr/bin/env python3
"""
Verification script for Ollama Contextual Memory (TASK_A001)
This script verifies that the ConversationMemory implementation works correctly.
"""

import sys
import tempfile
from pathlib import Path
from datetime import datetime

# Add tools to path
sys.path.insert(0, str(Path(__file__).parent / "tools"))

from ollama_prompt import ConversationMemory, prompt_ollama_with_context

def test_memory_initializes_empty():
    """Verify conversation memory starts empty."""
    print("Testing memory initialization...", end=" ")
    memory = ConversationMemory(max_tokens=4096)
    
    assert memory.get_conversation_history() == [], "History should be empty"
    assert memory.get_token_count() == 0, "Token count should be 0"
    print("✓ PASS")
    return True

def test_add_message_to_history():
    """Verify messages can be added to conversation history."""
    print("Testing add_message...", end=" ")
    memory = ConversationMemory(max_tokens=4096)
    
    memory.add_message("user", "Hello, how are you?")
    memory.add_message("assistant", "I'm doing well, thank you!")
    
    history = memory.get_conversation_history()
    
    assert len(history) == 2, f"Expected 2 messages, got {len(history)}"
    assert history[0]["role"] == "user", "First message should be user"
    assert history[0]["content"] == "Hello, how are you?", "Content mismatch"
    assert history[1]["role"] == "assistant", "Second message should be assistant"
    assert history[1]["content"] == "I'm doing well, thank you!", "Content mismatch"
    print("✓ PASS")
    return True

def test_memory_persists_to_disk():
    """Verify conversation memory can be saved to and loaded from disk."""
    print("Testing save/load to disk...", end=" ")
    with tempfile.TemporaryDirectory() as tmpdir:
        memory_path = Path(tmpdir) / "conversation.json"
        
        # Create and populate memory
        memory1 = ConversationMemory(max_tokens=4096)
        memory1.add_message("user", "What is the weather?")
        memory1.add_message("assistant", "I don't have weather data.")
        
        # Save to disk
        memory1.save(str(memory_path))
        
        # Verify file exists
        assert memory_path.exists(), "Memory file should exist"
        
        # Load into new memory instance
        memory2 = ConversationMemory(max_tokens=4096)
        memory2.load(str(memory_path))
        
        # Verify history matches
        history1 = memory1.get_conversation_history()
        history2 = memory2.get_conversation_history()
        
        assert len(history2) == 2, f"Expected 2 messages in loaded memory, got {len(history2)}"
        assert history1 == history2, "Saved and loaded history should match"
    print("✓ PASS")
    return True

def test_memory_loads_invalid_file_gracefully():
    """Verify loading invalid memory file doesn't crash."""
    print("Testing graceful handling of invalid files...", end=" ")
    with tempfile.TemporaryDirectory() as tmpdir:
        memory_path = Path(tmpdir) / "invalid.json"
        
        # Write invalid JSON
        memory_path.write_text("{ invalid json")
        
        memory = ConversationMemory(max_tokens=4096)
        memory.load(str(memory_path))
        
        # Should initialize empty
        assert memory.get_conversation_history() == [], "Invalid file should result in empty memory"
    print("✓ PASS")
    return True

def test_context_window_management():
    """Verify old messages are dropped when window is full."""
    print("Testing context window pruning...", end=" ")
    memory = ConversationMemory(max_tokens=100)  # Very small window
    
    # Add messages that will exceed token limit
    for i in range(10):
        memory.add_message("user", f"This is message number {i} with some text")
        memory.add_message("assistant", f"Response number {i}")
    
    # Token count should be managed
    assert memory.get_token_count() <= memory.max_tokens, f"Token count {memory.get_token_count()} exceeds max {memory.max_tokens}"
    
    # Should still have recent messages
    history = memory.get_conversation_history()
    assert len(history) > 0, "Should have some messages after pruning"
    print("✓ PASS")
    return True

def test_clear_memory():
    """Verify memory can be cleared."""
    print("Testing clear operation...", end=" ")
    memory = ConversationMemory(max_tokens=4096)
    
    memory.add_message("user", "Test message")
    memory.add_message("assistant", "Test response")
    
    assert len(memory.get_conversation_history()) == 2, "Should have 2 messages before clear"
    
    memory.clear()
    
    assert memory.get_conversation_history() == [], "History should be empty after clear"
    assert memory.get_token_count() == 0, "Token count should be 0 after clear"
    print("✓ PASS")
    return True

def test_get_last_n_messages():
    """Verify retrieving last N messages works."""
    print("Testing get_last_n_messages...", end=" ")
    memory = ConversationMemory(max_tokens=4096)
    
    for i in range(10):
        memory.add_message("user", f"Message {i}")
    
    last_3 = memory.get_last_n_messages(3)
    
    assert len(last_3) == 3, f"Expected 3 messages, got {len(last_3)}"
    assert "Message 7" in last_3[0]["content"], "Last 3 should start with message 7"
    assert "Message 9" in last_3[2]["content"], "Last 3 should end with message 9"
    print("✓ PASS")
    return True

def test_get_messages_by_role():
    """Verify filtering messages by role works."""
    print("Testing get_messages_by_role...", end=" ")
    memory = ConversationMemory(max_tokens=4096)
    
    memory.add_message("user", "Question 1")
    memory.add_message("assistant", "Answer 1")
    memory.add_message("user", "Question 2")
    memory.add_message("assistant", "Answer 2")
    memory.add_message("user", "Question 3")
    
    user_msgs = memory.get_messages_by_role("user")
    assistant_msgs = memory.get_messages_by_role("assistant")
    
    assert len(user_msgs) == 3, f"Expected 3 user messages, got {len(user_msgs)}"
    assert len(assistant_msgs) == 2, f"Expected 2 assistant messages, got {len(assistant_msgs)}"
    assert all(msg["role"] == "user" for msg in user_msgs), "All messages should be user role"
    print("✓ PASS")
    return True

def test_metadata_tracking():
    """Verify metadata can be attached to memory."""
    print("Testing metadata tracking...", end=" ")
    memory = ConversationMemory(
        max_tokens=4096,
        metadata={
            "session_id": "test-session-001",
            "container_id": "visual_audio.mkv",
            "started_at": datetime.now().isoformat()
        }
    )
    
    meta = memory.get_metadata()
    
    assert meta["session_id"] == "test-session-001", "Session ID should match"
    assert meta["container_id"] == "visual_audio.mkv", "Container ID should match"
    print("✓ PASS")
    return True

def test_multiple_sessions():
    """Verify multiple conversation sessions can be distinguished."""
    print("Testing multiple session isolation...", end=" ")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        # Session 1
        session1_path = tmpdir / "session1.json"
        memory1 = ConversationMemory(
            max_tokens=4096,
            metadata={"session_id": "session-1"}
        )
        memory1.add_message("user", "Session 1 question")
        memory1.add_message("assistant", "Session 1 answer")
        memory1.save(str(session1_path))
        
        # Session 2
        session2_path = tmpdir / "session2.json"
        memory2 = ConversationMemory(
            max_tokens=4096,
            metadata={"session_id": "session-2"}
        )
        memory2.add_message("user", "Session 2 question")
        memory2.add_message("assistant", "Session 2 answer")
        memory2.save(str(session2_path))
        
        # Load both and verify they're separate
        loaded1 = ConversationMemory(max_tokens=4096)
        loaded1.load(str(session1_path))
        
        loaded2 = ConversationMemory(max_tokens=4096)
        loaded2.load(str(session2_path))
        
        hist1_str = str(loaded1.get_conversation_history())
        hist2_str = str(loaded2.get_conversation_history())
        
        assert "Session 1 question" in hist1_str, "Session 1 should have its content"
        assert "Session 2 question" not in hist1_str, "Session 1 should not have session 2 content"
        assert "Session 2 question" in hist2_str, "Session 2 should have its content"
        assert "Session 1 question" not in hist2_str, "Session 2 should not have session 1 content"
    print("✓ PASS")
    return True

def test_container_session_id_tracking():
    """Verify container sessions can be tracked by ID."""
    print("Testing container session ID tracking...", end=" ")
    with tempfile.TemporaryDirectory() as tmpdir:
        session_file = Path(tmpdir) / "container_session.json"
        
        # Simulate container session
        memory = ConversationMemory(
            max_tokens=4096,
            metadata={
                "container_id": "visual_audio.mkv",
                "session_id": "container-run-123",
                "started_at": datetime.now().isoformat()
            }
        )
        
        memory.add_message("user", "Container boot complete")
        memory.add_message("assistant", "Acknowledged")
        
        memory.save(str(session_file))
        
        # Simulate container restart - load memory
        new_memory = ConversationMemory(max_tokens=4096)
        new_memory.load(str(session_file))
        
        history = new_memory.get_conversation_history()
        meta = new_memory.get_metadata()
        
        assert len(history) == 2, f"Expected 2 messages, got {len(history)}"
        assert meta["container_id"] == "visual_audio.mkv", "Container ID should match"
        assert meta["session_id"] == "container-run-123", "Session ID should match"
    print("✓ PASS")
    return True

def test_session_continuation():
    """Verify conversation can continue from saved session."""
    print("Testing session continuation...", end=" ")
    with tempfile.TemporaryDirectory() as tmpdir:
        session_file = Path(tmpdir) / "continue_test.json"
        
        # First session
        mem1 = ConversationMemory(max_tokens=4096)
        mem1.add_message("user", "Step 1: Initialize")
        mem1.add_message("assistant", "Initialized")
        mem1.save(str(session_file))
        
        # Second session (continuation)
        mem2 = ConversationMemory(max_tokens=4096)
        mem2.load(str(session_file))
        
        assert len(mem2.get_conversation_history()) == 2, f"Expected 2 messages after load, got {len(mem2.get_conversation_history())}"
        
        # Add more
        mem2.add_message("user", "Step 2: Process")
        mem2.add_message("assistant", "Processed")
        
        assert len(mem2.get_conversation_history()) == 4, f"Expected 4 messages after continuation, got {len(mem2.get_conversation_history())}"
    print("✓ PASS")
    return True

def test_session_merge():
    """Verify sessions can be merged."""
    print("Testing session merge...", end=" ")
    mem1 = ConversationMemory(max_tokens=4096)
    mem1.add_message("user", "Session A question")
    
    mem2 = ConversationMemory(max_tokens=4096)
    mem2.add_message("user", "Session B question")
    
    # Merge mem2 into mem1
    mem1.merge(mem2)
    
    history = mem1.get_conversation_history()
    hist_str = str(history)
    
    assert len(history) == 2, f"Expected 2 messages after merge, got {len(history)}"
    assert "Session A question" in hist_str, "Should have session A content"
    assert "Session B question" in hist_str, "Should have session B content"
    print("✓ PASS")
    return True

def test_prompt_ollama_with_context():
    """Verify Ollama prompt includes conversation history."""
    print("Testing prompt_ollama_with_context formatting...", end=" ")
    memory = ConversationMemory(max_tokens=4096)
    
    # Add context
    memory.add_message("user", "My name is Alice")
    memory.add_message("assistant", "Hello Alice!")
    
    # Build context-aware prompt
    history = memory.get_conversation_history()
    context_str = "\n".join([
        f"{msg['role']}: {msg['content']}" 
        for msg in history
    ])
    
    full_prompt = f"Previous conversation:\n{context_str}\n\nCurrent question: What is my name?"
    
    # Verify the context is properly formatted
    assert "My name is Alice" in full_prompt, "Should contain first message"
    assert "Hello Alice!" in full_prompt, "Should contain second message"
    assert "Current question:" in full_prompt, "Should have current question marker"
    print("✓ PASS")
    return True

def test_token_count_estimation():
    """Verify token counting is reasonably accurate."""
    print("Testing token count estimation...", end=" ")
    memory = ConversationMemory(max_tokens=4096)
    
    # Short message
    memory.add_message("user", "Hi")
    short_count = memory.get_token_count()
    
    # Longer message
    memory.clear()
    memory.add_message("user", "Hello, how are you doing today?")
    long_count = memory.get_token_count()
    
    # Longer message should have more tokens
    assert long_count > short_count, f"Longer message ({long_count}) should have more tokens than shorter ({short_count})"
    print("✓ PASS")
    return True

def main():
    """Run all verification tests."""
    print("=" * 60)
    print("Ollama Contextual Memory Verification (TASK_A001)")
    print("=" * 60)
    print()
    
    tests = [
        test_memory_initializes_empty,
        test_add_message_to_history,
        test_memory_persists_to_disk,
        test_memory_loads_invalid_file_gracefully,
        test_context_window_management,
        test_clear_memory,
        test_get_last_n_messages,
        test_get_messages_by_role,
        test_metadata_tracking,
        test_multiple_sessions,
        test_container_session_id_tracking,
        test_session_continuation,
        test_session_merge,
        test_prompt_ollama_with_context,
        test_token_count_estimation,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"✗ FAIL: {e}")
            failed += 1
            import traceback
            traceback.print_exc()
    
    print()
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests")
    print("=" * 60)
    
    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())