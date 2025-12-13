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


async def get_users_in_group(group_name: str) -> list:
    """Return list of user_ids belonging to a group."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id FROM users WHERE group_name = ?", (group_name,)
        ) as cur:
            rows = await cur.fetchall()
    return [r[0] for r in rows]


async def get_user_group(user_id: int) -> str | None:
    """Return stored group for a user or None."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT group_name FROM users WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
    return row[0] if row and row[0] else None


async def set_user_group(user_id: int, group_name: str) -> None:
    """Set or update user's group."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO users (user_id, group_name)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET group_name = excluded.group_name
            """,
            (user_id, group_name),
        )
        await db.commit()


async def set_user_name(user_id: int, first_name: str = "", username: str = "") -> None:
    """Set or update user's name info. Only updates if user exists."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Check if user exists first
        cursor = await db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        exists = await cursor.fetchone()
        
        if exists:
            # Update existing user
            await db.execute(
                """
                UPDATE users 
                SET first_name = ?, username = ?
                WHERE user_id = ?
                """,
                (first_name, username, user_id),
            )
        else:
            # For new users, insert with default group_name
            await db.execute(
                """
                INSERT INTO users (user_id, first_name, username, group_name)
                VALUES (?, ?, ?, '')
                """,
                (user_id, first_name, username),
            )
        await db.commit()

async def add_lunch(group_name: str, date: str, time_start: str, item: str, price: str, added_by: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO lunches (group_name, date, time_start, item, price, added_by, added_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (group_name, date, time_start, item, price, added_by),
        )
        await db.commit()


async def get_lunches_for_date(group_name: str, date: str) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT time_start, item, price FROM lunches WHERE group_name = ? AND date = ? ORDER BY time_start",
            (group_name, date),
        ) as cur:
            rows = await cur.fetchall()
    return [(r[0], r[1], r[2]) for r in rows]


async def add_pair_link(group_name: str, pair_number: int, url: str, added_by: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO pair_links (group_name, pair_number, url, added_by, added_at)
            VALUES (?, ?, ?, ?, datetime('now'))
            ON CONFLICT(group_name, pair_number) DO UPDATE SET
                url=excluded.url,
                added_by=excluded.added_by,
                added_at=excluded.added_at
            """,
            (group_name, pair_number, url, added_by),
        )
        await db.commit()


async def get_pair_links(group_name: str) -> list:
    """Return list of (pair_number, url) for a group, ordered by pair_number."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT pair_number, url FROM pair_links WHERE group_name = ? ORDER BY pair_number",
            (group_name,),
        ) as cur:
            rows = await cur.fetchall()
    return [(int(r[0]), r[1]) for r in rows]


async def clear_pair_links(group_name: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM pair_links WHERE group_name = ?", (group_name,))
        await db.commit()


async def get_all_pair_links() -> list:
    """Return list of (group_name, pair_number, url) for all stored links."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT group_name, pair_number, url FROM pair_links ORDER BY group_name, pair_number"
        ) as cur:
            rows = await cur.fetchall()
    return [(r[0], int(r[1]), r[2]) for r in rows]


async def upsert_schedule_entry(
    group_name: str,
    date: str,
    pair_number: int,
    time_start: str,
    time_end: str,
    subject: str,
    teacher: str | None,
    room: str | None,
    week_type: str = "both",
) -> None:
    """Insert or update an entry into `schedule_cache` (used by admins)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO schedule_cache (
                group_name, date, pair_number, time_start, time_end, subject, teacher, room, week_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(group_name, date, pair_number) DO UPDATE SET
                time_start=excluded.time_start,
                time_end=excluded.time_end,
                subject=excluded.subject,
                teacher=excluded.teacher,
                room=excluded.room,
                week_type=excluded.week_type
            """,
            (
                group_name,
                date,
                pair_number,
                time_start,
                time_end,
                subject,
                teacher or "",
                room or "",
                week_type,
            ),
        )
        await db.commit()


async def add_replacement(
    group_name: str,
    date: str,
    pair_number: int,
    subject: str,
    teacher: str | None,
    room: str | None,
    created_by: int,
) -> None:
    """Add or replace a substitution for a specific group/date/pair."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO replacements (
                group_name, date, pair_number, subject, teacher, room, created_by, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(group_name, date, pair_number) DO UPDATE SET
                subject=excluded.subject,
                teacher=excluded.teacher,
                room=excluded.room,
                created_by=excluded.created_by,
                created_at=excluded.created_at
            """,
            (
                group_name,
                date,
                pair_number,
                subject,
                teacher or "",
                room or "",
                created_by,
            ),
        )
        await db.commit()


async def list_schedule_for_group(group_name: str, date: str) -> list:
    """Return schedule_cache rows for group/date ordered by pair_number."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT pair_number, time_start, time_end, subject, teacher, room, week_type FROM schedule_cache WHERE group_name = ? AND date = ? ORDER BY pair_number",
            (group_name, date),
        ) as cur:
            rows = await cur.fetchall()
            return rows


async def get_replacements_for_group_date(group_name: str, date: str) -> dict:
    """Return a mapping pair_number -> (subject, teacher, room) for replacements on a date."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT pair_number, subject, teacher, room FROM replacements WHERE group_name = ? AND date = ?",
            (group_name, date),
        ) as cur:
            rows = await cur.fetchall()
    return {int(r[0]): (r[1], r[2] or "", r[3] or "") for r in rows}
