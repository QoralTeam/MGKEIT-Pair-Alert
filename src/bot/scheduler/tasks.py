import asyncio
from datetime import datetime, timedelta

import aiosqlite
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.config import settings
from bot.db.db import DB_PATH
from bot.services.api_client import fetch_timetable
from bot.utils.helpers import format_pair_reminder, is_even_week
from bot.utils.keyboards import reminder_disable_kb

scheduler = AsyncIOScheduler()


async def sync_all_groups():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT DISTINCT group_name FROM users") as cur:
            groups = [row[0] async for row in cur]

    for group in groups:
        data = await fetch_timetable(group)
        if not data or "data" not in data:
            continue

        entries = []
        for day in data["data"]:
            date = day["date"]
            week_type = (
                "even" if is_even_week(datetime.fromisoformat(date)) else "odd"
            )
            for unit in day["units"]:
                entries.append(
                    (
                        group,
                        date,
                        unit["number"],
                        unit["start"],
                        unit["subject"],
                        unit["teacher"] or "",
                        unit["room"] or "",
                        week_type,
                    )
                )

        async with aiosqlite.connect(DB_PATH) as db:
            await db.executemany(
                """
                INSERT INTO schedule_cache VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(group_name, date, pair_number) DO UPDATE SET
                    time_start=excluded.time_start,
                    subject=excluded.subject,
                    teacher=excluded.teacher,
                    room=excluded.room
            """,
                entries,
            )
            await db.commit()


async def check_and_send_reminders(bot):
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM users") as cur:
            users = await cur.fetchall()

    for user in users:
        user_id, group, mins, reps, days_csv, parity = user
        if mins <= 0 or str(now.weekday()) not in days_csv:
            continue
        if parity != "both" and parity != (
            "even" if is_even_week() else "odd"
        ):
            continue

        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                """
                SELECT pair_number, time_start, subject, teacher, room
                FROM schedule_cache
                WHERE group_name = ? AND date = ?
                ORDER BY time_start
            """,
                (group, today),
            ) as cur:
                rows = await cur.fetchall()

        for num, t_start, subj, teacher, room in rows:
            class_time = datetime.strptime(
                f"{today} {t_start}", "%Y-%m-%d %H:%M"
            )
            remind_at = class_time - timedelta(minutes=mins)
            if remind_at <= now < class_time:
                text = format_pair_reminder(
                    {
                        "pair_number": num,
                        "subject": subj,
                        "teacher": teacher,
                        "room": room,
                    },
                    mins,
                )

                await bot.send_message(
                    user_id, text, reply_markup=reminder_disable_kb()
                )
                # Можно добавить таблицу sent_reminders, чтобы не дублировать


def setup_scheduler(bot):
    scheduler.add_job(
        sync_all_groups,
        "interval",
        minutes=settings.SYNC_INTERVAL_MINUTES,
        id="sync",
    )
    scheduler.add_job(
        lambda: asyncio.run_coroutine_threadsafe(
            check_and_send_reminders(bot), asyncio.get_event_loop()
        ),
        "interval",
        minutes=1,
        id="remind",
    )
    scheduler.start()
