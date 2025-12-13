"""Session management for admin and curator authentication.

Tracks active sessions with 2-minute inactivity timeout (like sudo in Linux).
Sessions are identified by user_id and stored in memory with last_auth_time.
"""

import time
import aiosqlite
from bot.db.db import DB_PATH

# Session timeout: 2 minutes = 120 seconds
SESSION_TIMEOUT = 120


async def authenticate_user(user_id: int) -> None:
    """Mark user as authenticated by updating last_auth_time in database."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET last_auth_time = ? WHERE user_id = ?",
            (time.time(), user_id),
        )
        await db.commit()


async def update_activity(user_id: int) -> None:
    """Update user activity timestamp to keep session alive."""
    await authenticate_user(user_id)  # Same implementation - update last_auth_time


async def is_session_active(user_id: int) -> bool:
    """
    Check if user's session is still active.
    
    Returns True if authenticated and within 2-minute window, False otherwise.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT last_auth_time FROM users WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
    
    if not row:
        return False
    
    last_auth = row[0] or 0
    current_time = time.time()
    
    # Check if within timeout window
    return (current_time - last_auth) < SESSION_TIMEOUT


async def invalidate_session(user_id: int) -> None:
    """Invalidate user session (timeout or explicit logout)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET last_auth_time = 0 WHERE user_id = ?",
            (user_id,),
        )
        await db.commit()


async def get_session_remaining_time(user_id: int) -> int:
    """
    Get remaining session time in seconds.
    
    Returns: remaining seconds, or 0 if expired or never authenticated.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT last_auth_time FROM users WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
    
    if not row:
        return 0
    
    last_auth = row[0] or 0
    current_time = time.time()
    elapsed = current_time - last_auth
    remaining = max(0, SESSION_TIMEOUT - int(elapsed))
    
    return remaining
