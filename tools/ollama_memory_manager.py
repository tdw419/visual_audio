#!/usr/bin/env python3
"""
Ollama Memory Manager - SQLite-backed conversation memory for Ollama queries.

This module provides persistent conversation history tracking that persists
across container restarts, enabling container self-awareness and multi-turn
conversations.

Key features:
- SQLite-based persistence with atomic writes and ACID guarantees
- Session isolation via unique session IDs
- LRU cleanup based on last_accessed timestamp
- Export/import for debugging
- Auto-truncation when sessions exceed message limits

Database schema:
- sessions table: session_id, created_at, last_accessed, metadata, access_count
- messages table: id, session_id, role, content, timestamp, metadata

Usage:
    manager = OllamaMemoryManager(db_path="~/.ollama_memory.db")
    session = manager.create_session("user_alice_20260720")
    session.add_message("user", "Hello, I need help with container self-awareness")
    session.add_message("assistant", "I can help you with that...")
    history = session.get_conversation_history()
"""

import json
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class MessageRole:
    """Role constants for conversation messages."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class ConversationMessage:
    """Represents a single message in a conversation."""
    
    def __init__(
        self,
        role: str,
        content: str,
        timestamp: Optional[str] = None,
        metadata: Optional[Dict] = None
    ):
        """
        Initialize a conversation message.
        
        Args:
            role: Message role (SYSTEM, USER, ASSISTANT)
            content: Message content
            timestamp: ISO timestamp (auto-generated if not provided)
            metadata: Optional metadata dict
        """
        self.role = role.upper()
        self.content = content
        self.timestamp = timestamp or datetime.now().isoformat()
        self.metadata = metadata or {}
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            'role': self.role,
            'content': self.content,
            'timestamp': self.timestamp,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'ConversationMessage':
        """Create from dictionary."""
        return cls(
            role=data['role'],
            content=data['content'],
            timestamp=data.get('timestamp'),
            metadata=data.get('metadata', {})
        )
    
    @classmethod
    def from_row(cls, row: Tuple) -> 'ConversationMessage':
        """Create from database row."""
        return cls(
            role=row[0],
            content=row[1],
            timestamp=row[2],
            metadata=json.loads(row[3]) if row[3] else {}
        )


class ConversationSession:
    """Represents a conversation session with message history."""
    
    def __init__(
        self,
        session_id: str,
        db_path: str,
        max_messages: int = 100,
        metadata: Optional[Dict] = None
    ):
        """
        Initialize a conversation session.
        
        Args:
            session_id: Unique session identifier
            db_path: Path to SQLite database
            max_messages: Maximum messages before auto-truncation
            metadata: Optional metadata dict
        """
        self.session_id = session_id
        self.db_path = db_path
        self.max_messages = max_messages
        self.metadata = metadata or {}
        
        # Get connection lazily
        self._conn: Optional[sqlite3.Connection] = None
    
    @property
    def conn(self) -> sqlite3.Connection:
        """Lazy database connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
        return self._conn
    
    def close(self):
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
    
    def add_message(
        self,
        role: str,
        content: str,
        metadata: Optional[Dict] = None
    ) -> ConversationMessage:
        """
        Add a message to the session.
        
        Args:
            role: Message role (SYSTEM, USER, ASSISTANT)
            content: Message content
            metadata: Optional metadata dict
            
        Returns:
            Created message object
        """
        msg = ConversationMessage(
            role=role,
            content=content,
            metadata=metadata
        )
        
        # Insert into database
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO messages (session_id, role, content, timestamp, metadata)
            VALUES (?, ?, ?, ?, ?)
        """, (
            self.session_id,
            msg.role,
            msg.content,
            msg.timestamp,
            json.dumps(msg.metadata)
        ))
        
        # Update session access
        cursor.execute("""
            UPDATE sessions
            SET last_accessed = ?, access_count = access_count + 1
            WHERE session_id = ?
        """, (datetime.now().isoformat(), self.session_id))
        
        self.conn.commit()
        
        # Check if we need to truncate
        self._auto_truncate()
        
        return msg
    
    def get_conversation_history(
        self,
        limit: Optional[int] = None
    ) -> List[ConversationMessage]:
        """
        Get conversation history.
        
        Args:
            limit: Optional limit on number of messages
            
        Returns:
            List of message objects
        """
        cursor = self.conn.cursor()
        
        query = """
            SELECT role, content, timestamp, metadata
            FROM messages
            WHERE session_id = ?
            ORDER BY timestamp ASC
        """
        
        if limit:
            query += f" LIMIT {limit}"
        
        cursor.execute(query, (self.session_id,))
        
        return [ConversationMessage.from_row(row) for row in cursor.fetchall()]
    
    def get_last_n_messages(self, n: int) -> List[ConversationMessage]:
        """
        Get last N messages from history.
        
        Args:
            n: Number of messages to retrieve
            
        Returns:
            List of last N message objects
        """
        cursor = self.conn.cursor()
        
        cursor.execute("""
            SELECT role, content, timestamp, metadata
            FROM messages
            WHERE session_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (self.session_id, n))
        
        # Reverse to get chronological order
        messages = [ConversationMessage.from_row(row) for row in cursor.fetchall()]
        messages.reverse()
        
        return messages
    
    def get_messages_by_role(self, role: str) -> List[ConversationMessage]:
        """
        Get all messages with a specific role.
        
        Args:
            role: Role to filter by (SYSTEM, USER, ASSISTANT)
            
        Returns:
            List of message objects with matching role
        """
        cursor = self.conn.cursor()
        
        cursor.execute("""
            SELECT role, content, timestamp, metadata
            FROM messages
            WHERE session_id = ? AND role = ?
            ORDER BY timestamp ASC
        """, (self.session_id, role.upper()))
        
        return [ConversationMessage.from_row(row) for row in cursor.fetchall()]
    
    def clear(self):
        """Clear all messages from the session."""
        cursor = self.conn.cursor()
        cursor.execute("""
            DELETE FROM messages WHERE session_id = ?
        """, (self.session_id,))
        self.conn.commit()
    
    def get_message_count(self) -> int:
        """Get total number of messages in session."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM messages WHERE session_id = ?
        """, (self.session_id,))
        return cursor.fetchone()[0]
    
    def _auto_truncate(self):
        """Auto-truncate if session exceeds max_messages."""
        count = self.get_message_count()
        
        if count > self.max_messages:
            # Keep 80% of limit (not 100%) to prevent edge cases
            keep_count = int(self.max_messages * 0.8)
            
            cursor = self.conn.cursor()
            cursor.execute("""
                DELETE FROM messages
                WHERE id IN (
                    SELECT id FROM messages
                    WHERE session_id = ?
                    ORDER BY timestamp ASC
                    LIMIT ?
                )
            """, (self.session_id, count - keep_count))
            self.conn.commit()


class OllamaMemoryManager:
    """
    Manages Ollama conversation memory with SQLite persistence.
    
    Provides session isolation, LRU cleanup, and persistent conversation
    history across container restarts.
    """
    
    def __init__(
        self,
        db_path: str = "~/.ollama_memory.db",
        max_messages_per_session: int = 100,
        max_sessions: int = 100
    ):
        """
        Initialize memory manager.
        
        Args:
            db_path: Path to SQLite database (expands ~)
            max_messages_per_session: Max messages per session before truncation
            max_sessions: Max total sessions for LRU eviction
        """
        self.db_path = Path(db_path).expanduser()
        self.max_messages_per_session = max_messages_per_session
        self.max_sessions = max_sessions
        
        # Initialize database
        self._init_db()
    
    def _init_db(self):
        """Initialize database schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Sessions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                last_accessed TEXT NOT NULL,
                metadata TEXT,
                access_count INTEGER DEFAULT 0
            )
        """)
        
        # Messages table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                metadata TEXT,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
            )
        """)
        
        # Indexes for performance
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_session
            ON messages(session_id)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_timestamp
            ON messages(timestamp)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sessions_accessed
            ON sessions(last_accessed)
        """)
        
        conn.commit()
        conn.close()
    
    def create_session(
        self,
        session_id: str,
        metadata: Optional[Dict] = None
    ) -> ConversationSession:
        """
        Create or get a conversation session.
        
        Args:
            session_id: Unique session identifier
            metadata: Optional metadata dict
            
        Returns:
            ConversationSession object
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        
        # Check if session exists
        cursor.execute("""
            SELECT session_id FROM sessions WHERE session_id = ?
        """, (session_id,))
        
        if not cursor.fetchone():
            # Create new session
            cursor.execute("""
                INSERT INTO sessions (session_id, created_at, last_accessed, metadata)
                VALUES (?, ?, ?, ?)
            """, (
                session_id,
                now,
                now,
                json.dumps(metadata) if metadata else None
            ))
        else:
            # Update access time
            cursor.execute("""
                UPDATE sessions
                SET last_accessed = ?, access_count = access_count + 1
                WHERE session_id = ?
            """, (now, session_id))
        
        conn.commit()
        conn.close()
        
        return ConversationSession(
            session_id=session_id,
            db_path=str(self.db_path),
            max_messages=self.max_messages_per_session,
            metadata=metadata
        )
    
    def get_session(self, session_id: str) -> Optional[ConversationSession]:
        """
        Get an existing session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            ConversationSession object or None if not found
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT session_id FROM sessions WHERE session_id = ?
        """, (session_id,))
        
        if not cursor.fetchone():
            conn.close()
            return None
        
        conn.close()
        
        return ConversationSession(
            session_id=session_id,
            db_path=str(self.db_path),
            max_messages=self.max_messages_per_session
        )
    
    def delete_session(self, session_id: str) -> bool:
        """
        Delete a session and all its messages.
        
        Args:
            session_id: Session identifier
            
        Returns:
            True if session was deleted, False if not found
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            DELETE FROM sessions WHERE session_id = ?
        """, (session_id,))
        
        deleted = cursor.rowcount > 0
        
        conn.commit()
        conn.close()
        
        return deleted
    
    def list_sessions(self) -> List[Dict]:
        """
        List all sessions with metadata.
        
        Returns:
            List of session info dicts
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                session_id,
                created_at,
                last_accessed,
                metadata,
                access_count,
                (SELECT COUNT(*) FROM messages WHERE session_id = sessions.session_id) as message_count
            FROM sessions
            ORDER BY last_accessed DESC
        """)
        
        sessions = []
        for row in cursor.fetchall():
            sessions.append({
                'session_id': row[0],
                'created_at': row[1],
                'last_accessed': row[2],
                'metadata': json.loads(row[3]) if row[3] else {},
                'access_count': row[4],
                'message_count': row[5]
            })
        
        conn.close()
        
        return sessions
    
    def cleanup_old_sessions(
        self,
        max_age_days: int = 7,
        max_count: Optional[int] = None
    ) -> int:
        """
        Clean up old sessions using LRU eviction.
        
        Args:
            max_age_days: Delete sessions older than this many days
            max_count: Also limit total sessions to this count
            
        Returns:
            Number of sessions deleted
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        deleted = 0
        
        # Delete by age
        cutoff = datetime.now() - timedelta(days=max_age_days)
        cursor.execute("""
            DELETE FROM sessions WHERE last_accessed < ?
        """, (cutoff.isoformat(),))
        deleted += cursor.rowcount
        
        # Delete by count (LRU - oldest accessed first)
        if max_count:
            cursor.execute("""
                DELETE FROM sessions
                WHERE session_id IN (
                    SELECT session_id FROM sessions
                    ORDER BY last_accessed ASC
                    LIMIT ?
                )
            """, (max_count,))
            deleted += cursor.rowcount
        
        conn.commit()
        conn.close()
        
        return deleted
    
    def export_session(
        self,
        session_id: str,
        output_path: str
    ) -> bool:
        """
        Export a session to JSON for debugging.
        
        Args:
            session_id: Session to export
            output_path: Path to write JSON file
            
        Returns:
            True if export successful, False if session not found
        """
        session = self.get_session(session_id)
        if not session:
            return False
        
        history = session.get_conversation_history()
        
        data = {
            'session_id': session_id,
            'metadata': session.metadata,
            'exported_at': datetime.now().isoformat(),
            'messages': [msg.to_dict() for msg in history]
        }
        
        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2)
        
        session.close()
        
        return True
    
    def import_session(
        self,
        input_path: str,
        session_id_override: Optional[str] = None
    ) -> bool:
        """
        Import a session from JSON.
        
        Args:
            input_path: Path to JSON file
            session_id_override: Optional override for session_id
            
        Returns:
            True if import successful
        """
        with open(input_path, 'r') as f:
            data = json.load(f)
        
        session_id = session_id_override or data.get('session_id')
        if not session_id:
            return False
        
        # Create session
        session = self.create_session(
            session_id=session_id,
            metadata=data.get('metadata', {})
        )
        
        # Import messages
        for msg_data in data.get('messages', []):
            session.add_message(
                role=msg_data['role'],
                content=msg_data['content'],
                metadata=msg_data.get('metadata')
            )
        
        session.close()
        
        return True
    
    def get_total_message_count(self) -> int:
        """Get total number of messages across all sessions."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM messages")
        count = cursor.fetchone()[0]
        
        conn.close()
        
        return count
    
    def get_stats(self) -> Dict:
        """Get database statistics."""
        sessions = self.list_sessions()
        
        return {
            'total_sessions': len(sessions),
            'total_messages': self.get_total_message_count(),
            'db_path': str(self.db_path),
            'max_messages_per_session': self.max_messages_per_session,
            'max_sessions': self.max_sessions
        }