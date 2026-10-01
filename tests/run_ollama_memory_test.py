#!/usr/bin/env python3
"""
Simple test runner for Ollama contextual memory functionality (no pytest required).
"""

import os
import sys
import json
import tempfile
from pathlib import Path

# Import the module under test
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from tools.ollama_prompt import ContextualOllamaPrompter

def test_context_isolation_between_containers():
    """Verify that different containers have separate conversation histories."""
    print("Test: context_isolation_between_containers...", end=" ")

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create prompters for two different containers
        prompter_a = ContextualOllamaPrompter(container_id="container_a", context_dir=tmpdir)
        prompter_b = ContextualOllamaPrompter(container_id="container_b", context_dir=tmpdir)

        # Track context for container_a
        prompter_a.track_context("user", "Hello from A")
        prompter_a.track_context("assistant", "Hi A!")

        # Track context for container_b
        prompter_b.track_context("user", "Hello from B")
        prompter_b.track_context("assistant", "Hi B!")

        # Verify histories are separate
        history_a = prompter_a.get_conversation_history()
        history_b = prompter_b.get_conversation_history()

        assert len(history_a) == 2
        assert len(history_b) == 2

        # Container A should have A's messages only
        assert any("from A" in msg.get("content", "") for msg in history_a)
        assert not any("from B" in msg.get("content", "") for msg in history_a)

        # Container B should have B's messages only
        assert any("from B" in msg.get("content", "") for msg in history_b)
        assert not any("from A" in msg.get("content", "") for msg in history_b)

    print("PASS")
    return True

def test_context_persistence_across_queries():
    """Verify that context persists across multiple queries."""
    print("Test: context_persistence_across_queries...", end=" ")

    with tempfile.TemporaryDirectory() as tmpdir:
        prompter = ContextualOllamaPrompter(container_id="test_container", context_dir=tmpdir)

        # Simulate multiple query cycles
        queries = [
            ("user", "First question"),
            ("assistant", "First answer"),
            ("user", "Follow-up question"),
            ("assistant", "Follow-up answer"),
            ("user", "Third question"),
            ("assistant", "Third answer"),
        ]

        for role, content in queries:
            prompter.track_context(role, content)

        history = prompter.get_conversation_history()
        assert len(history) == 6

        # Verify sequence is maintained
        assert history[0]["role"] == "user"
        assert "First question" in history[0]["content"]
        assert history[1]["role"] == "assistant"
        assert "First answer" in history[1]["content"]

    print("PASS")
    return True

def test_context_clear():
    """Verify that context can be cleared."""
    print("Test: context_clear...", end=" ")

    with tempfile.TemporaryDirectory() as tmpdir:
        prompter = ContextualOllamaPrompter(container_id="test_container", context_dir=tmpdir)

        # Add some context
        prompter.track_context("user", "Initial message")
        prompter.track_context("assistant", "Response")

        assert len(prompter.get_conversation_history()) == 2

        # Clear context
        prompter.clear_context()

        # Verify cleared
        assert len(prompter.get_conversation_history()) == 0

    print("PASS")
    return True

def test_history_to_prompt_string():
    """Verify conversation history converts to readable prompt format."""
    print("Test: history_to_prompt_string...", end=" ")

    with tempfile.TemporaryDirectory() as tmpdir:
        prompter = ContextualOllamaPrompter(container_id="test_container", context_dir=tmpdir)

        prompter.track_context("user", "What is the capital of France?")
        prompter.track_context("assistant", "The capital of France is Paris.")

        prompt_string = prompter.history_to_prompt_string()

        assert "capital of France" in prompt_string
        assert "Paris" in prompt_string
        assert "User:" in prompt_string or "user" in prompt_string.lower()

    print("PASS")
    return True

def test_context_for_ollama():
    """Verify context is formatted correctly for Ollama API."""
    print("Test: context_for_ollama...", end=" ")

    with tempfile.TemporaryDirectory() as tmpdir:
        prompter = ContextualOllamaPrompter(container_id="test_container", context_dir=tmpdir)

        prompter.track_context("user", "Question 1")
        prompter.track_context("assistant", "Answer 1")

        context = prompter.get_context_for_ollama()

        # Should be a list of message dictionaries
        assert isinstance(context, list)
        assert len(context) >= 2

        # Check structure
        assert all("role" in msg and "content" in msg for msg in context)

        # Verify roles
        assert context[0]["role"] == "user"
        assert context[1]["role"] == "assistant"

    print("PASS")
    return True

def test_context_saves_to_disk():
    """Verify that conversation history is saved to disk."""
    print("Test: context_saves_to_disk...", end=" ")

    with tempfile.TemporaryDirectory() as tmpdir:
        prompter = ContextualOllamaPrompter(
            container_id="persist_test",
            context_dir=tmpdir
        )

        # Add context
        prompter.track_context("user", "Test message")
        prompter.save_context()

        # Check that file was created
        context_file = Path(tmpdir) / "persist_test.json"
        assert context_file.exists()

        # Load and verify content
        with open(context_file, 'r') as f:
            data = json.load(f)
            # Check both 'history' (backward compat) and 'messages' keys
            messages = data.get('history') or data.get('messages', [])
            assert len(messages) == 1
            assert "Test message" in messages[0]["content"]

    print("PASS")
    return True

def test_context_loads_from_disk():
    """Verify that conversation history loads from disk."""
    print("Test: context_loads_from_disk...", end=" ")

    with tempfile.TemporaryDirectory() as tmpdir:
        # First session: create and save context
        prompter1 = ContextualOllamaPrompter(
            container_id="load_test",
            context_dir=tmpdir
        )
        prompter1.track_context("user", "First session message")
        prompter1.save_context()

        # Second session: load context
        prompter2 = ContextualOllamaPrompter(
            container_id="load_test",
            context_dir=tmpdir
        )
        prompter2.load_context()

        history = prompter2.get_conversation_history()
        assert len(history) == 1
        assert "First session message" in history[0]["content"]

    print("PASS")
    return True

def test_context_auto_persistence():
    """Verify that context is automatically persisted on track."""
    print("Test: context_auto_persistence...", end=" ")

    with tempfile.TemporaryDirectory() as tmpdir:
        prompter = ContextualOllamaPrompter(
            container_id="auto_test",
            context_dir=tmpdir,
            auto_persist=True
        )

        # Add context (should auto-save)
        prompter.track_context("user", "Auto-save test")

        # Verify file exists immediately
        context_file = Path(tmpdir) / "auto_test.json"
        assert context_file.exists()

        # Verify content
        with open(context_file, 'r') as f:
            data = json.load(f)
            messages = data.get('history') or data.get('messages', [])
            assert len(messages) == 1

    print("PASS")
    return True

def test_metadata_tracking():
    """Verify that metadata (timestamps, container_id) is tracked."""
    print("Test: metadata_tracking...", end=" ")

    with tempfile.TemporaryDirectory() as tmpdir:
        prompter = ContextualOllamaPrompter(container_id="meta_test", context_dir=tmpdir)

        prompter.track_context("user", "Metadata test")

        history = prompter.get_conversation_history()

        # Check that first message has metadata
        assert len(history) > 0
        msg = history[0]

        # Should have timestamp if implemented
        if "timestamp" in msg:
            assert isinstance(msg["timestamp"], str)

        # Check prompter metadata
        metadata = prompter.get_metadata()
        assert "container_id" in metadata
        assert metadata["container_id"] == "meta_test"

    print("PASS")
    return True

def test_max_history_limit():
    """Verify that conversation history can be limited."""
    print("Test: max_history_limit...", end=" ")

    with tempfile.TemporaryDirectory() as tmpdir:
        prompter = ContextualOllamaPrompter(
            container_id="limit_test",
            context_dir=tmpdir,
            max_history=3
        )

        # Add 5 messages
        for i in range(5):
            prompter.track_context("user", f"Message {i+1}")

        history = prompter.get_conversation_history()

        # Should only keep last 3
        assert len(history) == 3
        # The expected messages are 3, 4, 5 (oldest messages are pruned)
        assert "Message 3" in history[0]["content"]
        assert "Message 4" in history[1]["content"]
        assert "Message 5" in history[2]["content"]

    print("PASS")
    return True

def test_empty_container_id():
    """Verify behavior with empty container ID."""
    print("Test: empty_container_id...", end=" ")

    with tempfile.TemporaryDirectory() as tmpdir:
        prompter = ContextualOllamaPrompter(container_id="", context_dir=tmpdir)

        prompter.track_context("user", "Test")

        # Should still work, using default/fallback ID
        history = prompter.get_conversation_history()
        assert len(history) == 1

    print("PASS")
    return True

def test_special_characters_in_messages():
    """Verify handling of special characters."""
    print("Test: special_characters_in_messages...", end=" ")

    with tempfile.TemporaryDirectory() as tmpdir:
        prompter = ContextualOllamaPrompter(container_id="special_test", context_dir=tmpdir)

        special_messages = [
            "Message with quotes 'single' and \"double\"",
            "Message with newlines\nand\ttabs",
            "Message with emoji 🎉",
            "Message with unicode: 你好, مرحبا",
        ]

        for msg in special_messages:
            prompter.track_context("user", msg)

        history = prompter.get_conversation_history()

        # All messages should be preserved
        assert len(history) == len(special_messages)

        # Verify content is preserved (after JSON roundtrip)
        for original, saved in zip(special_messages, history):
            assert original in saved["content"]

    print("PASS")
    return True

def run_all_tests():
    """Run all tests."""
    tests = [
        test_context_isolation_between_containers,
        test_context_persistence_across_queries,
        test_context_clear,
        test_history_to_prompt_string,
        test_context_for_ollama,
        test_context_saves_to_disk,
        test_context_loads_from_disk,
        test_context_auto_persistence,
        test_metadata_tracking,
        test_max_history_limit,
        test_empty_container_id,
        test_special_characters_in_messages,
    ]

    passed = 0
    failed = 0

    print("\nRunning Ollama Contextual Memory Tests")
    print("=" * 50)

    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("=" * 50)
    print(f"Results: {passed} passed, {failed} failed")

    if failed > 0:
        sys.exit(1)

if __name__ == "__main__":
    run_all_tests()