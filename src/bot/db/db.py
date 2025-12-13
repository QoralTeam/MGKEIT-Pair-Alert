from pathlib import Path

import aiosqlite

from bot.config import settings
from bot.utils.logger import logger

DB_PATH = Path(settings.DB_PATH)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


async def init_db() -> None:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    first_name TEXT DEFAULT '',
                    username TEXT DEFAULT '',
                    group_name TEXT NOT NULL DEFAULT '',
                    reminder_minutes INTEGER DEFAULT 10,
                    repetitions INTEGER DEFAULT 1,
                    days TEXT DEFAULT '0,1,2,3,4,5',        -- weekday numbers
                    week_parity TEXT DEFAULT 'both',        -- odd/even/both
                    role TEXT DEFAULT 'student',
                    hashed_password TEXT DEFAULT '',         -- bcrypt hashed password
                    password_changed INTEGER DEFAULT 0,      -- 1 if user changed default password
                    password_history TEXT DEFAULT '',        -- JSON list of last 8 hashed passwords
                    two_fa_enabled INTEGER DEFAULT 0,        -- 1 if TOTP 2FA enabled
                    two_fa_secret TEXT DEFAULT '',           -- TOTP secret key
                    last_auth_time REAL DEFAULT 0            -- Unix timestamp of last auth
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS schedule_cache (
                    group_name TEXT,
                    date TEXT,
                    pair_number INTEGER,
                    time_start TEXT,
                    time_end TEXT,
                    subject TEXT,
                    teacher TEXT,
                    room TEXT,
                    week_type TEXT,
                    PRIMARY KEY (group_name, date, pair_number)
                )
                """
            )
            await db.commit()

            # Ensure `role` column exists on `users` table. If not, add it with default 'student'.
            cursor = await db.execute("PRAGMA table_info('users')")
            cols = await cursor.fetchall()
            col_names = [row[1] for row in cols]
            if "role" not in col_names:
                await db.execute(
                    "ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'student'"
                )
                await db.commit()

            # Ensure replacements table exists for admin-managed substitutions
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS replacements (
                    group_name TEXT,
                    date TEXT,
                    pair_number INTEGER,
                    subject TEXT,
                    teacher TEXT,
                    room TEXT,
                    created_by INTEGER,
                    created_at TEXT,
                    PRIMARY KEY (group_name, date, pair_number)
                )
                """
            )
            await db.commit()

            # Ensure schedule_cache has `time_end` column (migration)
            cursor = await db.execute("PRAGMA table_info('schedule_cache')")
            cols = await cursor.fetchall()
            col_names = [row[1] for row in cols]
            if "time_end" not in col_names:
                await db.execute("ALTER TABLE schedule_cache ADD COLUMN time_end TEXT DEFAULT ''")
                await db.commit()

            # Ensure users table has `first_name` and `username` columns (migration)
            cursor = await db.execute("PRAGMA table_info('users')")
            cols = await cursor.fetchall()
            col_names = [row[1] for row in cols]
            if "first_name" not in col_names:
                await db.execute("ALTER TABLE users ADD COLUMN first_name TEXT DEFAULT ''")
                await db.commit()
            if "username" not in col_names:
                await db.execute("ALTER TABLE users ADD COLUMN username TEXT DEFAULT ''")
                await db.commit()

            # Ensure pair_links table exists for storing links per group/pair
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS pair_links (
                    group_name TEXT,
                    pair_number INTEGER,
                    url TEXT,
                    added_by INTEGER,
                    added_at TEXT,
                    PRIMARY KEY (group_name, pair_number)
                )
                """
            )
            await db.commit()

            # Ensure lunches table exists for canteen items and reminders
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS lunches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_name TEXT,
                    date TEXT,
                    time_start TEXT,
                    item TEXT,
                    price TEXT,
                    added_by INTEGER,
                    added_at TEXT
                )
                """
            )
            await db.commit()

            # Ensure lunch_times table exists for storing lunch time ranges per group
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS lunch_times (
                    group_name TEXT PRIMARY KEY,
                    time_start TEXT NOT NULL,
                    time_end TEXT NOT NULL,
                    updated_by INTEGER,
                    updated_at TEXT
                )
                """
            )
            await db.commit()

            # Migrations for password and 2FA columns
            cursor = await db.execute("PRAGMA table_info('users')")
            cols = await cursor.fetchall()
            col_names = [row[1] for row in cols]
            
            if "hashed_password" not in col_names:
                await db.execute("ALTER TABLE users ADD COLUMN hashed_password TEXT DEFAULT ''")
                await db.commit()
            if "password_changed" not in col_names:
                await db.execute("ALTER TABLE users ADD COLUMN password_changed INTEGER DEFAULT 0")
                await db.commit()
            if "password_history" not in col_names:
                await db.execute("ALTER TABLE users ADD COLUMN password_history TEXT DEFAULT ''")
                await db.commit()
            if "two_fa_enabled" not in col_names:
                await db.execute("ALTER TABLE users ADD COLUMN two_fa_enabled INTEGER DEFAULT 0")
                await db.commit()
            if "two_fa_secret" not in col_names:
                await db.execute("ALTER TABLE users ADD COLUMN two_fa_secret TEXT DEFAULT ''")
                await db.commit()
            if "backup_codes" not in col_names:
                await db.execute("ALTER TABLE users ADD COLUMN backup_codes TEXT DEFAULT ''")
                await db.commit()
            if "last_auth_time" not in col_names:
                await db.execute("ALTER TABLE users ADD COLUMN last_auth_time REAL DEFAULT 0")
                await db.commit()
            
            # Initialize passwords for admins and curators from .env
            await _initialize_env_passwords(db)

        logger.info("Database initialized successfully")
        
    except Exception as exc:
        logger.error(f"Failed to initialize database: {exc}", exc_info=True)
        raise


async def _initialize_env_passwords(db) -> None:
    """Initialize default passwords for admins and curators from .env if they don't have passwords."""
    from bot.utils.password_manager import DEFAULT_PASSWORDS, hash_password
    
    try:
        # Get all admins and curators from .env
        admin_ids = settings.ADMINS or []
        curator_ids = settings.CURATORS or []
        
        for admin_id in admin_ids:
            # Check if admin exists and has password
            cursor = await db.execute(
                "SELECT hashed_password FROM users WHERE user_id = ?",
                (admin_id,)
            )
            row = await cursor.fetchone()
            
            if not row or not row[0]:
                # Create/update admin with default password
                hashed = hash_password(DEFAULT_PASSWORDS["admin"])
                await db.execute(
                    """
                    INSERT INTO users (user_id, group_name, reminder_minutes, role, hashed_password, password_changed)
                    VALUES (?, '', ?, 'admin', ?, 0)
                    ON CONFLICT(user_id) DO UPDATE SET 
                        role = 'admin',
                        hashed_password = excluded.hashed_password,
                        password_changed = 0
                    """,
                    (admin_id, settings.REMINDER_DEFAULT_MINUTES, hashed)
                )
                logger.info(f"Initialized default password for admin {admin_id} from .env")
        
        for curator_id in curator_ids:
            # Check if curator exists and has password
            cursor = await db.execute(
                "SELECT hashed_password FROM users WHERE user_id = ?",
                (curator_id,)
            )
            row = await cursor.fetchone()
            
            if not row or not row[0]:
                # Create/update curator with default password
                hashed = hash_password(DEFAULT_PASSWORDS["curator"])
                await db.execute(
                    """
                    INSERT INTO users (user_id, group_name, reminder_minutes, role, hashed_password, password_changed)
                    VALUES (?, '', ?, 'curator', ?, 0)
                    ON CONFLICT(user_id) DO UPDATE SET 
                        role = 'curator',
                        hashed_password = excluded.hashed_password,
                        password_changed = 0
                    """,
                    (curator_id, settings.REMINDER_DEFAULT_MINUTES, hashed)
                )
                logger.info(f"Initialized default password for curator {curator_id} from .env")
        
        await db.commit()
        
    except Exception as exc:
        logger.error(f"Failed to initialize .env passwords: {exc}", exc_info=True)


async def set_user_role(user_id: int, role: str) -> None:
    """Set or update a user's role. Inserts user with empty group if missing.
    
    When role changes to admin or curator, sets default password and marks password_changed=0
    to force first-time password change on next authentication.
    """
    from bot.utils.password_manager import DEFAULT_PASSWORDS, hash_password
    
    async with aiosqlite.connect(DB_PATH) as db:
        # Check if user exists and has password
        cursor = await db.execute(
            "SELECT hashed_password FROM users WHERE user_id = ?",
            (user_id,)
        )
        row = await cursor.fetchone()
        existing_password = row[0] if row else ""
        
        # If changing to admin or curator, set default password if not exists
        hashed_password = ""
        if role in DEFAULT_PASSWORDS:
            if not existing_password:  # Only set if no password exists
                hashed_password = hash_password(DEFAULT_PASSWORDS[role])
            else:
                hashed_password = existing_password  # Keep existing password
        
        await db.execute(
            """
            INSERT INTO users (user_id, group_name, reminder_minutes, role, hashed_password, password_changed)
            VALUES (?, ?, ?, ?, ?, 0)
            ON CONFLICT(user_id) DO UPDATE SET 
                role = excluded.role,
                hashed_password = CASE 
                    WHEN excluded.hashed_password != '' THEN excluded.hashed_password 
                    ELSE hashed_password 
                END,
                password_changed = CASE 
                    WHEN excluded.hashed_password != '' AND hashed_password = '' THEN 0 
                    ELSE password_changed 
                END
            """,
            (user_id, "", settings.REMINDER_DEFAULT_MINUTES, role, hashed_password),
        )
        await db.commit()


async def get_user_role(user_id: int) -> str:
    """Return the role for a user. Defaults to 'student' if not set or missing."""
    # First check static lists from settings
    try:
        if user_id in settings.ADMINS:
            return "admin"
        if user_id in settings.CURATORS:
            return "curator"
    except Exception:
        # if settings missing or malformed, fall back to DB
        pass

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT role FROM users WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        if not row or not row[0]:
            return "student"
        return row[0]


async def list_users_by_role(role: str) -> list:
    """Return list of user_ids for a given role."""
    results = []
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT user_id FROM users WHERE role = ?", (role,)
        )
        rows = await cursor.fetchall()
        results = [r[0] for r in rows]

    # Include static IDs from settings for admins/curators
    try:
        if role == "admin":
            results.extend([int(x) for x in settings.ADMINS if x])
        if role == "curator":
            results.extend([int(x) for x in settings.CURATORS if x])
    except Exception:
        pass

    # Deduplicate and sort
    results = sorted(set(results))
    return results
