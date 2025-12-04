from pathlib import Path

import aiosqlite

from bot.config import settings

DB_PATH = Path(settings.DB_PATH)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                group_name TEXT NOT NULL,
                reminder_minutes INTEGER DEFAULT 10,
                repetitions INTEGER DEFAULT 1,
                days TEXT DEFAULT '0,1,2,3,4,5',        -- weekday numbers
                week_parity TEXT DEFAULT 'both'       -- odd/even/both
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


async def set_user_role(user_id: int, role: str) -> None:
    """Set or update a user's role. Inserts user with empty group if missing."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO users (user_id, group_name, reminder_minutes, role)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET role = excluded.role
            """,
            (user_id, "", settings.REMINDER_DEFAULT_MINUTES, role),
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
