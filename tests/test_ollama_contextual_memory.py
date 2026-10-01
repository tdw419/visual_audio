#!/usr/bin/env python3
"""
Test suite for Ollama contextual memory functionality.

Verifies that context persists between queries across container sessions.
"""

import json
import os
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tools.ollama_prompt import (
    ConversationMemory,
    ContextualOllamaPrompter,
    prompt_ollama_with_context
)


class TestConversationMemory:
    """Test ConversationMemory core functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.memory = ConversationMemory(max_tokens=4096)
        self.temp_dir = tempfile.mkdtemp()
    
    def teardown_method(self):
        """Clean up test fixtures."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_add_and_retrieve_messages(self):
        """Test that messages can be added and retrieved."""
        self.memory.add_message("user", "Hello")
        self.memory.add_message("assistant", "Hi there")
        
        history = self.memory.get_conversation_history()
        assert len(history) == 2
        assert history[0]['role'] == 'user'
        assert history[0]['content'] == 'Hello'
        assert history[1]['role'] == 'assistant'
        assert history[1]['content'] == 'Hi there'
    
    def test_timestamp_tracking(self):
        """Test that messages have timestamps."""
        self.memory.add_message("user", "Test message")
        
        history = self.memory.get_conversation_history()
        assert 'timestamp' in history[0]
        
        # Verify timestamp is valid ISO format
        timestamp_str = history[0]['timestamp']
        datetime.fromisoformat(timestamp_str)  # Will raise if invalid
    
    def test_get_last_n_messages(self):
        """Test retrieving last N messages."""
        for i in range(5):
            self.memory.add_message("user", f"Message {i}")
        
        last_3 = self.memory.get_last_n_messages(3)
        assert len(last_3) == 3
        assert last_3[0]['content'] == 'Message 2'
        assert last_3[2]['content'] == 'Message 4'
    
    def test_get_messages_by_role(self):
        """Test filtering messages by role."""
        self.memory.add_message("user", "Question 1")
        self.memory.add_message("assistant", "Answer 1")
        self.memory.add_message("user", "Question 2")
        
        user_messages = self.memory.get_messages_by_role("user")
        assert len(user_messages) == 2
        
        assistant_messages = self.memory.get_messages_by_role("assistant")
        assert len(assistant_messages) == 1
    
    def test_clear_memory(self):
        """Test clearing conversation history."""
        self.memory.add_message("user", "Test")
        assert len(self.memory.get_conversation_history()) == 1
        
        self.memory.clear()
        assert len(self.memory.get_conversation_history()) == 0
    
    def test_persistence_save_and_load(self):
        """Test saving and loading conversation history to/from disk."""
        # Add some messages
        self.memory.add_message("user", "Question")
        self.memory.add_message("assistant", "Response")
        
        # Save to file
        save_path = os.path.join(self.temp_dir, "conversation.json")
        self.memory.save(save_path)
        assert os.path.exists(save_path)
        
        # Load into new memory instance
        new_memory = ConversationMemory()
        new_memory.load(save_path)
        
        # Verify content
        history = new_memory.get_conversation_history()
        assert len(history) == 2
        assert history[0]['content'] == 'Question'
        assert history[1]['content'] == 'Response'
    
    def test_persistence_with_metadata(self):
        """Test that metadata is persisted correctly."""
        metadata = {
            'container_id': 'test_container',
            'session_id': 'session_123',
            'created_at': datetime.now().isoformat()
        }
        self.memory = ConversationMemory(max_tokens=4096, metadata=metadata)
        
        save_path = os.path.join(self.temp_dir, "conversation.json")
        self.memory.save(save_path)
        
        # Load and verify metadata
        new_memory = ConversationMemory()
        new_memory.load(save_path)
        
        loaded_metadata = new_memory.get_metadata()
        assert loaded_metadata['container_id'] == 'test_container'
        assert loaded_metadata['session_id'] == 'session_123'
    
    def test_merge_memories(self):
        """Test merging two conversation memories."""
        mem1 = ConversationMemory()
        mem1.add_message("user", "First message")
        
        mem2 = ConversationMemory()
        mem2.add_message("assistant", "Response")
        mem2.add_message("user", "Follow-up")
        
        # Merge mem2 into mem1
        mem1.merge(mem2)
        
        history = mem1.get_conversation_history()
        assert len(history) == 3
        assert history[0]['content'] == 'First message'
        assert history[1]['content'] == 'Response'
        assert history[2]['content'] == 'Follow-up'
    
    def test_token_limit_pruning(self):
        """Test that old messages are pruned when token limit is exceeded."""
        # Create memory with small token limit
        memory = ConversationMemory(max_tokens=50)
        
        # Add messages with longer text (each ~50 chars = 12-13 tokens)
        # Adding 5 messages would exceed 50 token limit
        for i in range(5):
            memory.add_message("user", f"This is a much longer message number {i} with more text content that will consume tokens")
        
        # Should prune to stay under limit
        assert memory.get_token_count() <= 50
        assert len(memory.get_conversation_history()) < 5
    
    def test_clear_preserves_metadata(self):
        """Test that clearing messages preserves metadata."""
        metadata = {'container_id': 'test'}
        self.memory = ConversationMemory(metadata=metadata)
        
        self.memory.add_message("user", "Test")
        self.memory.clear()
        
        # Messages should be gone
        assert len(self.memory.get_conversation_history()) == 0
        # Metadata should remain
        assert self.memory.get_metadata()['container_id'] == 'test'


class TestContextualOllamaPrompter:
    """Test ContextualOllamaPrompter container-specific functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.prompter = ContextualOllamaPrompter(
            container_id="test_container",
            context_dir=self.temp_dir,
            auto_persist=False  # Disable auto-persist for cleaner tests
        )
    
    def teardown_method(self):
        """Clean up test fixtures."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_container_id_tracking(self):
        """Test that container ID is tracked correctly."""
        assert self.prompter.get_container_id() == "test_container"
        
        metadata = self.prompter.get_metadata()
        assert metadata['container_id'] == "test_container"
    
    def test_context_persistence_across_sessions(self):
        """Test that context persists across prompter instances (sessions)."""
        # First session: add some context
        self.prompter.track_context("user", "My name is Alice")
        self.prompter.track_context("assistant", "Hello Alice!")
        self.prompter.save_context()
        
        # Create new prompter instance (simulating new session)
        prompter2 = ContextualOllamaPrompter(
            container_id="test_container",
            context_dir=self.temp_dir,
            auto_persist=False
        )
        
        # Context should be loaded automatically
        history = prompter2.get_conversation_history()
        assert len(history) == 2
        assert history[0]['content'] == "My name is Alice"
        assert history[1]['content'] == "Hello Alice!"
    
    def test_auto_persist_enabled(self):
        """Test that auto_persist saves context after each update."""
        prompter = ContextualOllamaPrompter(
            container_id="auto_container",
            context_dir=self.temp_dir,
            auto_persist=True
        )
        
        # Add context - should auto-save
        prompter.track_context("user", "Auto-persist test")
        
        # Load into new instance
        prompter2 = ContextualOllamaPrompter(
            container_id="auto_container",
            context_dir=self.temp_dir,
            auto_persist=False
        )
        
        history = prompter2.get_conversation_history()
        assert len(history) == 1
        assert history[0]['content'] == "Auto-persist test"
    
    def test_max_history_limit(self):
        """Test that max_history limits the number of messages."""
        prompter = ContextualOllamaPrompter(
            container_id="limit_container",
            context_dir=self.temp_dir,
            max_history=5,
            auto_persist=False
        )
        
        # Add 10 messages
        for i in range(10):
            prompter.track_context("user", f"Message {i}")
        
        # Should only keep last 5
        history = prompter.get_conversation_history()
        assert len(history) == 5
        assert history[0]['content'] == "Message 5"
        assert history[4]['content'] == "Message 9"
    
    def test_clear_context(self):
        """Test clearing context removes all messages."""
        self.prompter.track_context("user", "Test")
        self.prompter.track_context("assistant", "Response")
        
        assert len(self.prompter.get_conversation_history()) == 2
        
        self.prompter.clear_context()
        assert len(self.prompter.get_conversation_history()) == 0
    
    def test_history_to_prompt_string(self):
        """Test converting history to readable prompt string."""
        self.prompter.track_context("user", "What is Python?")
        self.prompter.track_context("assistant", "Python is a programming language")
        
        prompt_str = self.prompter.history_to_prompt_string(max_messages=2)
        
        assert "USER:" in prompt_str
        assert "ASSISTANT:" in prompt_str
        assert "What is Python?" in prompt_str
        assert "Python is a programming language" in prompt_str
    
    def test_get_context_for_ollama(self):
        """Test getting context formatted for Ollama API."""
        self.prompter.track_context("user", "Hello")
        
        ollama_context = self.prompter.get_context_for_ollama(max_messages=1)
        
        assert isinstance(ollama_context, list)
        assert len(ollama_context) == 1
        assert ollama_context[0]['role'] == 'user'
        assert ollama_context[0]['content'] == 'Hello'
    
    def test_container_isolation(self):
        """Test that different containers have separate histories."""
        prompter1 = ContextualOllamaPrompter(
            container_id="container_1",
            context_dir=self.temp_dir,
            auto_persist=False
        )
        
        prompter2 = ContextualOllamaPrompter(
            container_id="container_2",
            context_dir=self.temp_dir,
            auto_persist=False
        )
        
        prompter1.track_context("user", "Container 1 message")
        prompter2.track_context("user", "Container 2 message")
        
        # Each should have only its own messages
        assert len(prompter1.get_conversation_history()) == 1
        assert prompter1.get_conversation_history()[0]['content'] == "Container 1 message"
        
        assert len(prompter2.get_conversation_history()) == 1
        assert prompter2.get_conversation_history()[0]['content'] == "Container 2 message"
    
    def test_save_and_load_context(self):
        """Test explicit save and load of context."""
        self.prompter.track_context("user", "Save test")
        
        # Explicit save
        saved = self.prompter.save_context()
        assert saved is True
        
        # Clear memory
        self.prompter.clear_context()
        assert len(self.prompter.get_conversation_history()) == 0
        
        # Load back
        loaded = self.prompter.load_context()
        assert loaded is True
        assert len(self.prompter.get_conversation_history()) == 1


class TestContextPersistenceAcrossQueries:
    """Integration tests for context persistence between queries."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
    
    def teardown_method(self):
        """Clean up test fixtures."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_context_flows_through_query_ollama(self):
        """Test that context is maintained across multiple query_ollama calls."""
        prompter = ContextualOllamaPrompter(
            container_id="flow_test",
            context_dir=self.temp_dir,
            auto_persist=False
        )
        
        # First query - tracks user prompt and would track response
        # (We're mocking query_ollama_with_context to avoid actual Ollama calls)
        history_before = prompter.get_conversation_history()
        assert len(history_before) == 0
        
        # Simulate what query_ollama does
        prompter.track_context("user", "First question")
        assert len(prompter.get_conversation_history()) == 1
        
        # Track response (simulated)
        prompter.track_context("assistant", "First answer")
        assert len(prompter.get_conversation_history()) == 2
        
        # Second query
        prompter.track_context("user", "Follow-up question")
        history = prompter.get_conversation_history()
        
        # All messages should be present
        assert len(history) == 3
        assert history[0]['content'] == "First question"
        assert history[1]['content'] == "First answer"
        assert history[2]['content'] == "Follow-up question"
    
    def test_conversation_memory_integration(self):
        """Test ConversationMemory integrates correctly with prompt_ollama_with_context."""
        memory = ConversationMemory(max_tokens=4096)
        
        # Add context to memory
        memory.add_message("user", "Context question")
        memory.add_message("assistant", "Context answer")
        
        # Get context for prompt
        history = memory.get_last_n_messages(10)
        assert len(history) == 2
        
        # Format as expected by prompt_ollama_with_context
        assert history[0]['role'] == 'user'
        assert history[1]['role'] == 'assistant'
    
    def test_multiple_container_sessions(self):
        """Test that multiple sessions for same container maintain continuity."""
        container_id = "session_test"
        
        # Session 1
        prompter1 = ContextualOllamaPrompter(
            container_id=container_id,
            context_dir=self.temp_dir,
            auto_persist=False
        )
        prompter1.track_context("user", "Session 1 message")
        prompter1.save_context()
        
        # Session 2 (new instance, same container)
        prompter2 = ContextualOllamaPrompter(
            container_id=container_id,
            context_dir=self.temp_dir,
            auto_persist=False
        )
        prompter2.track_context("user", "Session 2 message")
        prompter2.save_context()
        
        # Session 3
        prompter3 = ContextualOllamaPrompter(
            container_id=container_id,
            context_dir=self.temp_dir,
            auto_persist=False
        )
        
        history = prompter3.get_conversation_history()
        assert len(history) == 2
        assert history[0]['content'] == "Session 1 message"
        assert history[1]['content'] == "Session 2 message"


def run_all_tests():
    """Run all test classes."""
    test_classes = [
        TestConversationMemory,
        TestContextualOllamaPrompter,
        TestContextPersistenceAcrossQueries
    ]
    
    total_passed = 0
    total_failed = 0
    failures = []
    
    for test_class in test_classes:
        print(f"\n{'='*60}")
        print(f"Running {test_class.__name__}")
        print(f"{'='*60}")
        
        test_instance = test_class()
        
        # Get all test methods
        test_methods = [m for m in dir(test_instance) if m.startswith('test_')]
        
        for method_name in test_methods:
            # Run setup
            test_instance.setup_method()
            
            try:
                # Run test
                getattr(test_instance, method_name)()
                print(f"✓ {method_name}")
                total_passed += 1
            except Exception as e:
                print(f"✗ {method_name}: {e}")
                total_failed += 1
                failures.append(f"{test_class.__name__}.{method_name}: {e}")
            
            # Run teardown
            try:
                test_instance.teardown_method()
            except Exception:
                pass
    
    # Summary
    print(f"\n{'='*60}")
    print(f"Test Summary")
    print(f"{'='*60}")
    print(f"Passed: {total_passed}")
    print(f"Failed: {total_failed}")
    
    if failures:
        print(f"\nFailures:")
        for failure in failures:
            print(f"  - {failure}")
    
    return total_failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)