#!/usr/bin/env python3
"""
Simple verification script for Ollama contextual memory.
Tests that conversation history persists across multiple queries.
"""

import sys
import tempfile
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from tools.ollama_memory_manager import OllamaMemoryManager, MessageRole

def test_context_persists_across_multiple_queries():
    """Test that context persists between multiple queries in the same conversation."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        db_path = tmp.name
    
    try:
        # Create manager
        manager = OllamaMemoryManager(db_path=db_path)
        
        # Create conversation
        conv_id = "context_persistence_conv"
        session = manager.create_session(session_id=conv_id)
        
        # Turn 1: Initial Q&A
        session.add_message(MessageRole.USER, "What is the capital of France?")
        session.add_message(MessageRole.ASSISTANT, "The capital of France is Paris.")
        
        # Verify Turn 1 was stored
        history_after_turn1 = manager.get_session(conv_id).get_conversation_history()
        assert len(history_after_turn1) == 2, f"Expected 2 messages, got {len(history_after_turn1)}"
        assert "France" in history_after_turn1[0].content, "User message not stored correctly"
        print(f"✓ Turn 1 verified: {history_after_turn1[0].content}")
        print(f"✓ Response 1 verified: {history_after_turn1[1].content}")
        
        # Turn 3: Follow-up question
        session.add_message(MessageRole.USER, "And what about Germany?")
        session.add_message(MessageRole.ASSISTANT, "The capital of Germany is Berlin.")
        
        # Verify all context is preserved
        history_final = manager.get_session(conv_id).get_conversation_history()
        assert len(history_final) == 4, f"Expected 4 messages, got {len(history_final)}"
        
        # Verify conversation flow is intact
        assert history_final[0].content == "What is the capital of France?"
        assert history_final[1].content == "The capital of France is Paris."
        assert history_final[2].content == "And what about Germany?"
        assert history_final[3].content == "The capital of Germany is Berlin."
        
        print(f"✓ Turn 2 verified: {history_final[2].content}")
        print(f"✓ Response 2 verified: {history_final[3].content}")
        print(f"✓ All {len(history_final)} messages preserved across turns")
        
        return True
        
    finally:
        # Cleanup
        Path(db_path).unlink(missing_ok=True)

def test_database_persistence_across_reopen():
    """Test that data persists across manager re-instantiation."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        db_path = tmp.name
    
    try:
        conv_id = "persistence_test_conv"
        
        # First instance: create and populate
        manager1 = OllamaMemoryManager(db_path=db_path)
        session1 = manager1.create_session(session_id=conv_id)
        session1.add_message(MessageRole.USER, "Persistent message")
        
        # Second instance: should retrieve persisted data
        manager2 = OllamaMemoryManager(db_path=db_path)
        session = manager2.get_session(conv_id)
        
        assert session is not None, "Session not found after reopen"
        history = session.get_conversation_history()
        assert len(history) == 1, f"Expected 1 message, got {len(history)}"
        assert history[0].content == "Persistent message", "Message content mismatch"
        assert history[0].role.lower() == MessageRole.USER, "Message role mismatch"
        
        print(f"✓ Message persisted across manager reinstantiation: {history[0].content}")
        
        return True
        
    finally:
        # Cleanup
        Path(db_path).unlink(missing_ok=True)

if __name__ == "__main__":
    print("Testing Ollama contextual memory for container self-awareness...\n")
    
    try:
        # Test 1: Context persistence within a conversation
        print("Test 1: Context persists across multiple queries")
        test_context_persists_across_multiple_queries()
        print()
        
        # Test 2: Database persistence across reopen
        print("Test 2: Database persistence across manager reopen")
        test_database_persistence_across_reopen()
        print()
        
        print("✅ All tests passed! Ollama contextual memory works correctly.")
        sys.exit(0)
        
    except AssertionError as e:
        print(f"❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)