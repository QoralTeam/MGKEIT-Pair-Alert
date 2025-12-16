"""Password management for admin and curator authentication.

Features:
- Bcrypt hashing for security
- Comprehensive validation (8-128 chars, uppercase, lowercase, digit, no spaces, allowed symbols)
- Password history (last 8 passwords) to prevent reuse
- Default passwords for new roles (admin/curator)
"""

import re
import json
import bcrypt
import aiosqlite
from bot.db.db import DB_PATH

# Password requirements
MIN_LENGTH = 8
MAX_LENGTH = 128
ALLOWED_SYMBOLS = r"~!?@#$%^&*_\-+\(\)\[\]{}<>/\\|\"'.,;:"

# Default passwords for new roles
DEFAULT_PASSWORDS = {
    "admin": "admin",
    "curator": "curator",
}


def validate_password(password: str) -> tuple[bool, str]:
    """
    Validate password against requirements.
    
    Returns: (is_valid, error_message)
    """
    if not password:
        return False, "Password cannot be empty"
    
    if len(password) < MIN_LENGTH:
        return False, f"Пароль должен быть минимум {MIN_LENGTH} символов"
    
    if len(password) > MAX_LENGTH:
        return False, f"Пароль должен быть не более {MAX_LENGTH} символов"
    
    if " " in password:
        return False, "Пароль не может содержать пробелы"
    
    if not re.search(r"[a-z]", password):
        return False, "Пароль должен содержать хотя бы одну строчную букву"
    
    if not re.search(r"[A-Z]", password):
        return False, "Пароль должен содержать хотя бы одну заглавную букву"
    
    if not re.search(r"\d", password):
        return False, "Пароль должен содержать хотя бы одну цифру"
    
    # Check for only allowed characters (letters, digits, symbols)
    allowed_pattern = rf"^[a-zA-Z0-9{re.escape(ALLOWED_SYMBOLS)}]+$"
    if not re.match(allowed_pattern, password):
        return False, "Пароль содержит недопустимые символы"
    
    return True, ""


def hash_password(password: str) -> str:
    """Hash password using bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Verify password against hash."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


async def set_default_password(user_id: int, role: str) -> None:
    """Set default password when role changes to admin or curator."""
    if role not in DEFAULT_PASSWORDS:
        return
    
    default_pwd = DEFAULT_PASSWORDS[role]
    hashed = hash_password(default_pwd)
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE users 
            SET hashed_password = ?, password_changed = 0, password_history = ''
            WHERE user_id = ?
            """,
            (hashed, user_id),
        )
        await db.commit()


async def verify_user_password(user_id: int, password: str) -> bool:
    """Verify user password (no session side-effects)."""
    
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT hashed_password FROM users WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
    
    if not row or not row[0]:
        return False
    
    hashed = row[0]
    if not verify_password(password, hashed):
        return False
    return True


async def change_password(user_id: int, new_password: str) -> tuple[bool, str]:
    """
    Change user password with history check.
    
    Returns: (success, message)
    """
    # Validate new password
    is_valid, error = validate_password(new_password)
    if not is_valid:
        return False, error
    
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT hashed_password, password_history FROM users WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
    
    if not row:
        return False, "Пользователь не найден"
    
    current_hashed = row[0]
    history_json = row[1] or "[]"
    
    try:
        history = json.loads(history_json)
    except:
        history = []
    
    # Check if new password matches any of last 8 passwords
    new_hashed = hash_password(new_password)
    for old_hash in history[-8:]:  # Last 8 passwords
        if verify_password(new_password, old_hash):
            return False, "Новый пароль не может совпадать с последними 8 паролями"
    
    # Add current password to history
    if current_hashed:
        history.append(current_hashed)
    
    # Keep only last 8
    history = history[-8:]
    
    # Update database
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE users 
            SET hashed_password = ?, password_changed = 1, password_history = ?
            WHERE user_id = ?
            """,
            (new_hashed, json.dumps(history), user_id),
        )
        await db.commit()
    
    return True, "Пароль успешно изменен"


async def is_password_changed(user_id: int) -> bool:
    """Check if user has changed their default password."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT password_changed FROM users WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
    
    if not row:
        return False
    
    return bool(row[0])
