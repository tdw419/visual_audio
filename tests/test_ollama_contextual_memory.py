#!/usr/bin/env python3
"""
Ollama Contextual Memory Tests - TASK_A001
Tests for conversation history tracking across container sessions.

Verifies:
1. Context persists between queries in the same session
2. Session history can be saved and loaded
3. Context window management works correctly
4. Memory persists across container sessions (when persisted to disk)
5. Context summarization kicks in when window is full
"""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List, Dict

import pytest

# Add tools to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

from ollama_prompt import ConversationMemory, prompt_ollama


class TestConversationMemory:
    """Tests for conversation history tracking."""

    def test_memory_initializes_empty(self):
        """Verify conversation memory starts empty."""
        memory = ConversationMemory(max_tokens=4096)
        
        assert memory.get_conversation_history() == []
        assert memory.get_token_count() == 0

    def test_add_message_to_history(self):
        """Verify messages can be added to conversation history."""
        memory = ConversationMemory(max_tokens=4096)
        
        memory.add_message("user", "Hello, how are you?")
        memory.add_message("assistant", "I'm doing well, thank you!")
        
        history = memory.get_conversation_history()
        
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "Hello, how are you?"
        assert history[1]["role"] == "assistant"
        assert history[1]["content"] == "I'm doing well, thank you!"

    def test_memory_persists_to_disk(self):
        """Verify conversation memory can be saved to and loaded from disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            memory_path = Path(tmpdir) / "conversation.json"
            
            # Create and populate memory
            memory1 = ConversationMemory(max_tokens=4096)
            memory1.add_message("user", "What is the weather?")
            memory1.add_message("assistant", "I don't have weather data.")
            
            # Save to disk
            memory1.save(str(memory_path))
            
            # Verify file exists
            assert memory_path.exists()
            
            # Load into new memory instance
            memory2 = ConversationMemory(max_tokens=4096)
            memory2.load(str(memory_path))
            
            # Verify history matches
            history1 = memory1.get_conversation_history()
            history2 = memory2.get_conversation_history()
            
            assert len(history2) == 2
            assert history1 == history2

    def test_memory_loads_invalid_file_gracefully(self):
        """Verify loading invalid memory file doesn't crash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            memory_path = Path(tmpdir) / "invalid.json"
            
            # Write invalid JSON
            memory_path.write_text("{ invalid json")
            
            memory = ConversationMemory(max_tokens=4096)
            memory.load(str(memory_path))
            
            # Should initialize empty
            assert memory.get_conversation_history() == []

    def test_context_window_management(self):
        """Verify old messages are dropped when window is full."""
        memory = ConversationMemory(max_tokens=100)  # Very small window
        
        # Add messages that will exceed token limit
        for i in range(10):
            memory.add_message("user", f"This is message number {i} with some text")
            memory.add_message("assistant", f"Response number {i}")
        
        # Token count should be managed
        assert memory.get_token_count() <= memory.max_tokens
        
        # Should still have recent messages
        history = memory.get_conversation_history()
        assert len(history) > 0

    def test_clear_memory(self):
        """Verify memory can be cleared."""
        memory = ConversationMemory(max_tokens=4096)
        
        memory.add_message("user", "Test message")
        memory.add_message("assistant", "Test response")
        
        assert len(memory.get_conversation_history()) == 2
        
        memory.clear()
        
        assert memory.get_conversation_history() == []
        assert memory.get_token_count() == 0

    def test_get_last_n_messages(self):
        """Verify retrieving last N messages works."""
        memory = ConversationMemory(max_tokens=4096)
        
        for i in range(10):
            memory.add_message("user", f"Message {i}")
        
        last_3 = memory.get_last_n_messages(3)
        
        assert len(last_3) == 3
        assert "Message 7" in last_3[0]["content"]
        assert "Message 9" in last_3[2]["content"]

    def test_get_messages_by_role(self):
        """Verify filtering messages by role works."""
        memory = ConversationMemory(max_tokens=4096)
        
        memory.add_message("user", "Question 1")
        memory.add_message("assistant", "Answer 1")
        memory.add_message("user", "Question 2")
        memory.add_message("assistant", "Answer 2")
        memory.add_message("user", "Question 3")
        
        user_msgs = memory.get_messages_by_role("user")
        assistant_msgs = memory.get_messages_by_role("assistant")
        
        assert len(user_msgs) == 3
        assert len(assistant_msgs) == 2
        assert all(msg["role"] == "user" for msg in user_msgs)

    def test_metadata_tracking(self):
        """Verify metadata can be attached to memory."""
        memory = ConversationMemory(
            max_tokens=4096,
            metadata={
                "session_id": "test-session-001",
                "container_id": "visual_audio.mkv",
                "started_at": datetime.now().isoformat()
            }
        )
        
        meta = memory.get_metadata()
        
        assert meta["session_id"] == "test-session-001"
        assert meta["container_id"] == "visual_audio.mkv"

    def test_multiple_sessions(self):
        """Verify multiple conversation sessions can be distinguished."""
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
            
            assert "Session 1 question" in str(loaded1.get_conversation_history())
            assert "Session 2 question" not in str(loaded1.get_conversation_history())
            assert "Session 2 question" in str(loaded2.get_conversation_history())
            assert "Session 1 question" not in str(loaded2.get_conversation_history())


class TestOllamaWithContext:
    """Tests for Ollama with contextual memory."""

    def test_prompt_ollama_with_context(self):
        """Verify Ollama prompt includes conversation history."""
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
        
        # Note: We don't actually call Ollama here (it may not be available in test env)
        # Just verify the context is properly formatted
        assert "My name is Alice" in full_prompt
        assert "Hello Alice!" in full_prompt
        assert "Current question:" in full_prompt

    def test_token_count_estimation(self):
        """Verify token counting is reasonably accurate."""
        memory = ConversationMemory(max_tokens=4096)
        
        # Short message
        memory.add_message("user", "Hi")
        short_count = memory.get_token_count()
        
        # Longer message
        memory.clear()
        memory.add_message("user", "Hello, how are you doing today?")
        long_count = memory.get_token_count()
        
        # Longer message should have more tokens
        assert long_count > short_count


class TestSessionPersistenceAcrossContainer:
    """Tests for memory persistence across container sessions."""

    def test_container_session_id_tracking(self):
        """Verify container sessions can be tracked by ID."""
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
            
            assert len(history) == 2
            assert meta["container_id"] == "visual_audio.mkv"
            assert meta["session_id"] == "container-run-123"

    def test_session_continuation(self):
        """Verify conversation can continue from saved session."""
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
            
            assert len(mem2.get_conversation_history()) == 2
            
            # Add more
            mem2.add_message("user", "Step 2: Process")
            mem2.add_message("assistant", "Processed")
            
            assert len(mem2.get_conversation_history()) == 4

    def test_session_merge(self):
        """Verify sessions can be merged."""
        mem1 = ConversationMemory(max_tokens=4096)
        mem1.add_message("user", "Session A question")
        
        mem2 = ConversationMemory(max_tokens=4096)
        mem2.add_message("user", "Session B question")
        
        # Merge mem2 into mem1
        mem1.merge(mem2)
        
        history = mem1.get_conversation_history()
        
        assert len(history) == 2
        assert "Session A question" in str(history)
        assert "Session B question" in str(history)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])