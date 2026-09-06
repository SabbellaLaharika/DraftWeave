import sqlite3
import hashlib
from typing import Optional
from datetime import datetime, timezone
from app.config import settings


def get_db_connection() -> sqlite3.Connection:
    """Establish connection to SQLite database."""
    db_path = settings.db_path
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Initialize database schema if it doesn't exist."""
    conn = get_db_connection()
    try:
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_styles (
                    user_id INTEGER PRIMARY KEY,
                    style_prompt TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
    finally:
        conn.close()


def set_user_style(user_id: int, style_prompt: str) -> None:
    """Insert or update user style preference."""
    conn = get_db_connection()
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        with conn:
            conn.execute("""
                INSERT INTO user_styles (user_id, style_prompt, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    style_prompt = excluded.style_prompt,
                    updated_at = excluded.updated_at
            """, (user_id, style_prompt.strip(), now_iso))
    finally:
        conn.close()


def get_user_style(user_id: int) -> Optional[str]:
    """Retrieve user style prompt if present, otherwise return None."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT style_prompt FROM user_styles WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        return row["style_prompt"] if row else None
    finally:
        conn.close()


def get_user_style_hash(user_id: int) -> str:
    """
    Get a hash of user style prompt.
    Returns empty string hash if user has no custom style.
    """
    style = get_user_style(user_id) or ""
    return hashlib.sha256(style.encode("utf-8")).hexdigest()[:12]
