#!/usr/bin/env python3
"""
Simple verification script for Ollama contextual memory.
Tests that conversation history persists across multiple queries.
"""

import sys
import tempfile
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent
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
        manager.create_session(session_id=conv_id)
        
        # Turn 1: Initial Q&A
        manager.add_message(conv_id, MessageRole.USER, "What is the capital of France?")
        manager.add_message(conv_id, MessageRole.ASSISTANT, "The capital of France is Paris.")
        
        # Verify Turn 1 was stored
        session_after_turn1 = manager.get_session(conv_id)
        assert len(session_after_turn1.messages) == 2, f"Expected 2 messages, got {len(session_after_turn1.messages)}"
        assert "France" in session_after_turn1.messages[0].content, "User message not stored correctly"
        print(f"✓ Turn 1 verified: {session_after_turn1.messages[0].content}")
        print(f"✓ Response 1 verified: {session_after_turn1.messages[1].content}")
        
        # Turn 3: Follow-up question
        manager.add_message(conv_id, MessageRole.USER, "And what about Germany?")
        manager.add_message(conv_id, MessageRole.ASSISTANT, "The capital of Germany is Berlin.")
        
        # Verify all context is preserved
        session_final = manager.get_session(conv_id)
        assert len(session_final.messages) == 4, f"Expected 4 messages, got {len(session_final.messages)}"
        
        # Verify conversation flow is intact
        assert session_final.messages[0].content == "What is the capital of France?"
        assert session_final.messages[1].content == "The capital of France is Paris."
        assert session_final.messages[2].content == "And what about Germany?"
        assert session_final.messages[3].content == "The capital of Germany is Berlin."
        
        print(f"✓ Turn 2 verified: {session_final.messages[2].content}")
        print(f"✓ Response 2 verified: {session_final.messages[3].content}")
        print(f"✓ All {len(session_final.messages)} messages preserved across turns")
        
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
        manager1.create_session(session_id=conv_id)
        manager1.add_message(conv_id, MessageRole.USER, "Persistent message")
        
        # Second instance: should retrieve persisted data
        manager2 = OllamaMemoryManager(db_path=db_path)
        session = manager2.get_session(conv_id)
        
        assert session is not None, "Session not found after reopen"
        assert len(session.messages) == 1, f"Expected 1 message, got {len(session.messages)}"
        assert session.messages[0].content == "Persistent message", "Message content mismatch"
        assert session.messages[0].role == MessageRole.USER, "Message role mismatch"
        
        print(f"✓ Message persisted across manager reinstantiation: {session.messages[0].content}")
        
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