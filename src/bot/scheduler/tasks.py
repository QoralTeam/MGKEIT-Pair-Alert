import asyncio
from datetime import datetime, timedelta

import aiosqlite
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiohttp.client_exceptions import ClientConnectorError

from bot.config import settings
from bot.db.db import DB_PATH
from bot.services.api_client import fetch_timetable
from bot.utils.helpers import format_pair_reminder, is_even_week
from bot.utils.keyboards import reminder_disable_kb
from bot.utils.logger import logger

scheduler = AsyncIOScheduler()


async def sync_all_groups(bot=None):
    """Fetch timetable for all groups and update schedule cache.

    If `bot` is provided, admin notifications will be sent on failures.
    """
    # Respect global synchronization flag
    if not getattr(settings, "SYNCHRONIZATION", True):
        # If called interactively (bot), notify that sync is disabled
        logger.info("Sync skipped: SYNCHRONIZATION is disabled")
        if bot and settings.ADMINS:
            for admin_id in settings.ADMINS:
                try:
                    await bot.send_message(admin_id, "Синхронизация отключена.")
                except Exception:
                    pass
        return

    logger.info("Starting schedule synchronization...")
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT DISTINCT group_name FROM users") as cur:
                groups = [row[0] async for row in cur]

        logger.info(f"Found {len(groups)} groups to sync")
        synced_count = 0

        for group in groups:
            # fetch remote timetable
            data = await fetch_timetable(group)
            if not data or "data" not in data:
                logger.warning(f"No schedule data for group {group}")
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
                            unit.get("start", ""),
                            unit.get("end", ""),
                            unit.get("subject", ""),
                            unit.get("teacher") or "",
                            unit.get("room") or "",
                            week_type,
                        )
                    )

            if not entries:
                logger.warning(f"No entries found for group {group}")
                continue

            async with aiosqlite.connect(DB_PATH) as db:
                await db.executemany(
                    """
                    INSERT INTO schedule_cache (group_name, date, pair_number, time_start, time_end, subject, teacher, room, week_type)
                    VALUES (?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(group_name, date, pair_number) DO UPDATE SET
                        time_start=excluded.time_start,
                        time_end=excluded.time_end,
                        subject=excluded.subject,
                        teacher=excluded.teacher,
                        room=excluded.room,
                        week_type=excluded.week_type
                """,
                    entries,
                )
                await db.commit()
            logger.info(f"Synced {len(entries)} entries for group {group}")
            synced_count += 1

        logger.info(f"Synchronization completed successfully. {synced_count} groups synced")

    except ClientConnectorError as exc:
        # Network error connecting to external API — notify admins if possible
        logger.error(f"Network error during sync: {exc}", exc_info=True)
        if bot and settings.ADMINS:
            for admin_id in settings.ADMINS:
                try:
                    await bot.send_message(admin_id, "Синхронизация не удалась. Попробуйте позже...")
                except Exception:
                    pass
        return
    except OSError as exc:
        logger.error(f"OS error during sync: {exc}", exc_info=True)
        if bot and settings.ADMINS:
            for admin_id in settings.ADMINS:
                try:
                    await bot.send_message(admin_id, "Синхронизация не удалась. Попробуйте позже...")
                except Exception:
                    pass
        return
    except Exception as exc:
        # General failure: notify admins with a short message
        logger.error(f"Unexpected error during sync: {exc}", exc_info=True)
        if bot and settings.ADMINS:
            for admin_id in settings.ADMINS:
                try:
                    await bot.send_message(admin_id, f"Синхронизация не удалась: {exc}")
                except Exception:
                    pass
        return


async def check_and_send_reminders(bot):
    try:
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")

        async with aiosqlite.connect(DB_PATH) as db:
            # Explicit column list prevents issues when schema gains new columns (e.g. role)
            async with db.execute(
                "SELECT user_id, group_name, reminder_minutes, repetitions, days, week_parity FROM users"
            ) as cur:
                users = await cur.fetchall()

        reminders_sent = 0
        for user in users:
            # `users` rows may contain an extra `role` column; unpack only first 6 fields
            try:
                user_id, group, mins, reps, days_csv, parity = user[:6]
            except Exception as exc:
                logger.warning(f"Invalid user row from DB, skipping: {user} -> {exc}")
                continue

            try:
                if mins <= 0 or str(now.weekday()) not in (days_csv or ""):
                    continue
            except Exception:
                # malformed mins or days_csv
                continue
            if parity != "both" and parity != (
                "even" if is_even_week() else "odd"
            ):
                continue

            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute(
                    """
                    SELECT pair_number, time_start, time_end, subject, teacher, room
                    FROM schedule_cache
                    WHERE group_name = ? AND date = ?
                    ORDER BY pair_number
                """,
                    (group, today),
                ) as cur:
                    rows = await cur.fetchall()

            for row in rows:
                # rows now: pair_number, time_start, time_end, subject, teacher, room
                try:
                    num, t_start, t_end, subj, teacher, room = row
                except Exception:
                    # unexpected row shape
                    continue
                if not t_start:
                    # skip entries without start time
                    continue
                try:
                    class_time = datetime.strptime(f"{today} {t_start}", "%Y-%m-%d %H:%M")
                except ValueError:
                    # malformed time string; skip
                    logger.debug(f"Skipped invalid time for user {user_id}: {t_start}")
                    continue
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

                    try:
                        await bot.send_message(
                            user_id, text, reply_markup=reminder_disable_kb()
                        )
                        reminders_sent += 1
                        logger.info(f"Reminder sent to user {user_id} for pair {num}")
                    except Exception as exc:
                        logger.warning(f"Failed to send reminder to user {user_id}: {exc}")
                    # Можно добавить таблицу sent_reminders, чтобы не дублировать
        
        if reminders_sent > 0:
            logger.info(f"Total reminders sent: {reminders_sent}")
    except Exception as exc:
        logger.error(f"Critical error in check_and_send_reminders: {exc}", exc_info=True)


def setup_scheduler(bot):
    try:
        logger.info("Setting up scheduler jobs...")
        scheduler.add_job(
            sync_all_groups,
            "interval",
            args=[bot],
            minutes=settings.SYNC_INTERVAL_MINUTES,
            id="sync",
        )
        logger.info(f"Added sync job (interval: {settings.SYNC_INTERVAL_MINUTES} minutes)")
        
        scheduler.add_job(
            check_and_send_reminders,
            "interval",
            args=[bot],
            minutes=1,
            id="remind",
        )
        logger.info("Added reminder job (interval: 1 minute)")
        
        scheduler.start()
        logger.info("Scheduler started")
    except Exception as exc:
        logger.error(f"Failed to setup scheduler: {exc}", exc_info=True)
        raise
