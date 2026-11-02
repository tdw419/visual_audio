#!/usr/bin/env python3
"""
Demo script showing Ollama contextual memory for container self-awareness.

This demonstrates how containers can maintain conversation context across queries,
enabling self-awareness of their own interaction history.
"""

import os
import sys
import tempfile
from pathlib import Path

# Import the module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from tools.ollama_prompt import ContextualOllamaPrompter


def demo_container_isolation():
    """Show how different containers have separate histories."""
    print("\n" + "="*60)
    print("DEMO: Container Isolation")
    print("="*60)

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create two containers
        container_a = ContextualOllamaPrompter(
            container_id="security_audit",
            context_dir=tmpdir
        )
        container_b = ContextualOllamaPrompter(
            container_id="code_review",
            context_dir=tmpdir
        )

        # Track interactions for security audit container
        container_a.track_context("user", "Audit container security policies")
        container_a.track_context("assistant", "I'll check RBAC and isolation settings")

        # Track interactions for code review container
        container_b.track_context("user", "Review PR #123")
        container_b.track_context("assistant", "I found 2 issues with error handling")

        # Show histories are separate
        print("\nContainer A (security_audit) history:")
        for msg in container_a.get_conversation_history():
            print(f"  {msg['role']}: {msg['content']}")

        print("\nContainer B (code_review) history:")
        for msg in container_b.get_conversation_history():
            print(f"  {msg['role']}: {msg['content']}")

        print("\n✓ Containers maintain separate contexts")


def demo_context_persistence():
    """Show how context persists across queries."""
    print("\n" + "="*60)
    print("DEMO: Context Persistence Across Queries")
    print("="*60)

    with tempfile.TemporaryDirectory() as tmpdir:
        container = ContextualOllamaPrompter(
            container_id="persistent_demo",
            context_dir=tmpdir
        )

        # Simulate a conversation
        queries = [
            ("user", "What files were modified?"),
            ("assistant", "Based on git status: main.py, codec.py, tests/"),
            ("user", "Are there tests for codec.py?"),
            ("assistant", "Yes, test_codec_roundtrip.py exists"),
            ("user", "Show me the codec test structure"),
        ]

        print("\nConversation flow:")
        for role, content in queries:
            print(f"{role}: {content}")
            container.track_context(role, content)

        # Show accumulated context
        print("\nAccumulated context (ready for Ollama):")
        context_for_ollama = container.get_context_for_ollama()
        for i, msg in enumerate(context_for_ollama, 1):
            print(f"  {i}. [{msg['role']}]: {msg['content']}")

        print("\n✓ Context persists across queries")


def demo_session_continuity():
    """Show how context survives container restart."""
    print("\n" + "="*60)
    print("DEMO: Session Continuity (Container Restart)")
    print("="*60)

    with tempfile.TemporaryDirectory() as tmpdir:
        # Session 1: Start working
        print("\n--- Session 1: Initial work ---")
        session1 = ContextualOllamaPrompter(
            container_id="build_container",
            context_dir=tmpdir
        )
        session1.track_context("user", "Build the project")
        session1.track_context("assistant", "Building... completed in 45s")
        session1.save_context()

        print("Work tracked:")
        for msg in session1.get_conversation_history():
            print(f"  {msg['role']}: {msg['content']}")

        # Session 2: Resume work
        print("\n--- Session 2: After restart ---")
        session2 = ContextualOllamaPrompter(
            container_id="build_container",
            context_dir=tmpdir
        )
        session2.load_context()

        print("Context restored:")
        for msg in session2.get_conversation_history():
            print(f"  {msg['role']}: {msg['content']}")

        # Continue working
        print("\nContinuing conversation:")
        session2.track_context("user", "Now run the tests")
        session2.track_context("assistant", "Running tests... all 12 passed")

        print("\nFinal history:")
        for msg in session2.get_conversation_history():
            print(f"  {msg['role']}: {msg['content']}")

        print("\n✓ Context survives container restart")


def demo_metadata_tracking():
    """Show metadata tracking for self-awareness."""
    print("\n" + "="*60)
    print("DEMO: Metadata Tracking")
    print("="*60)

    with tempfile.TemporaryDirectory() as tmpdir:
        container = ContextualOllamaPrompter(
            container_id="metadata_demo",
            context_dir=tmpdir
        )

        container.track_context("user", "Track my request")

        # Show metadata
        metadata = container.get_metadata()
        print("\nContainer metadata:")
        print(f"  Container ID: {metadata.get('container_id')}")
        print(f"  Created at: {metadata.get('created_at')}")

        # Show message metadata
        history = container.get_conversation_history()
        print(f"\nMessage metadata:")
        print(f"  Timestamp: {history[0].get('timestamp')}")
        print(f"  Role: {history[0].get('role')}")

        print("\n✓ Metadata provides container self-awareness")


def main():
    """Run all demos."""
    print("\n" + "="*60)
    print("Ollama Contextual Memory - Container Self-Awareness Demo")
    print("="*60)

    demo_container_isolation()
    demo_context_persistence()
    demo_session_continuity()
    demo_metadata_tracking()

    print("\n" + "="*60)
    print("All demos completed!")
    print("="*60)
    print("\nKey capabilities demonstrated:")
    print("1. Container-isolated conversation histories")
    print("2. Context persistence across queries")
    print("3. Session continuity across restarts")
    print("4. Metadata tracking for self-awareness")
    print("\nContainers can now maintain awareness of their own")
    print("interaction history, enabling more autonomous behavior.")


if __name__ == "__main__":
    main()