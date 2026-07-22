#!/usr/bin/env python3
"""
Quick verification test for Ollama contextual memory.
Runs without pytest dependency.
"""

import sys
import tempfile
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from tools.ollama_memory_manager import (
    OllamaMemoryManager,
    MessageRole,
)


def test_basic_functionality():
    """Test basic conversation memory functionality."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        manager = OllamaMemoryManager(db_path=str(db_path))

        # Test 1: Create session
        conv_id = "test_conv_001"
        manager.create_session(session_id=conv_id)
        print("✓ Test 1: Session created")

        # Test 2: Add messages
        manager.add_message(conv_id, MessageRole.USER, "Hello")
        manager.add_message(conv_id, MessageRole.ASSISTANT, "Hi there!")
        print("✓ Test 2: Messages added")

        # Test 3: Retrieve session
        session = manager.get_session(conv_id)
        assert session is not None
        assert len(session.messages) == 2
        print("✓ Test 3: Session retrieved with messages")

        # Test 4: Context persists
        manager.add_message(conv_id, MessageRole.USER, "Follow-up question")
        session = manager.get_session(conv_id)
        assert len(session.messages) == 3
        print("✓ Test 4: Context persists across queries")

        # Test 5: Multiple conversations independent
        conv2_id = "test_conv_002"
        manager.create_session(session_id=conv2_id)
        manager.add_message(conv2_id, MessageRole.USER, "Different conversation")
        
        session1 = manager.get_session(conv_id)
        session2 = manager.get_session(conv2_id)
        assert len(session1.messages) == 3
        assert len(session2.messages) == 1
        print("✓ Test 5: Multiple conversations are independent")

        # Test 6: Role tracking
        roles = [msg.role for msg in session1.messages]
        assert roles[0] == MessageRole.USER
        assert roles[1] == MessageRole.ASSISTANT
        assert roles[2] == MessageRole.USER
        print("✓ Test 6: Roles tracked correctly")

        # Test 7: Delete conversation
        success = manager.delete_session(conv_id)
        assert success is True
        session = manager.get_session(conv_id)
        assert session is None
        print("✓ Test 7: Conversation deletion works")

        # Test 8: Database persistence across reopen
        manager2 = OllamaMemoryManager(db_path=str(db_path))
        session = manager2.get_session(conv2_id)
        assert session is not None
        assert len(session.messages) == 1
        print("✓ Test 8: Data persists across manager reopen")

        print("\n🎉 All tests passed!")


if __name__ == "__main__":
    test_basic_functionality()