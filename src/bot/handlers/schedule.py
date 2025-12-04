from datetime import datetime, timedelta

import aiosqlite
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import Message

from bot.db.db import DB_PATH, init_db

router = Router(name="schedule")


async def get_today_schedule(group: str, offset: int = 0) -> str:
    target = (datetime.now() + timedelta(days=offset)).strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT pair_number, time_start, subject, teacher, room
               FROM schedule_cache WHERE group_name = ? AND date = ?
               ORDER BY pair_number""",
            (group, target),
        ) as cur:
            rows = await cur.fetchall()

    if not rows:
        return "Пар нет" if offset == 0 else "Пар нет"

    lines = []
    for n, t, subj, teacher, room in rows:
        lines.append(
            f"{n} пара • {t} • {subj}\n   {teacher or '—'} • {room or '—'}"
        )
    return "\n\n".join(lines)


@router.message(Command("today"))
async def cmd_today(message: Message):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT group_name FROM users WHERE user_id = ?",
            (message.from_user.id,),
        ) as cur:
            row = await cur.fetchone()
    if not row:
        return await message.answer("Укажи группу: /setgroup ...")

    text = await get_today_schedule(row[0])
    day = "Сегодня" if datetime.now().weekday() < 6 else "Воскресенье"
    await message.answer(f"{day}\n\n{text}")


@router.message(Command("tomorrow"))
async def cmd_tomorrow(message: Message):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT group_name FROM users WHERE user_id = ?",
            (message.from_user.id,),
        ) as cur:
            row = await cur.fetchone()
    if not row:
        return await message.answer("Укажи группу: /setgroup ...")

    text = await get_today_schedule(row[0], offset=1)
    await message.answer(f"Завтра\n\n{text}")


@router.message(Command("schedule"))
async def schedule_command(message: types.Message):
    args = message.get_args()
    day_of_week = datetime.now().weekday()  # Default to today

    if args == "tomorrow":
        day_of_week = (day_of_week + 1) % 7
    elif args.isdigit():
        day_of_week = int(args) % 7

    group = "Example Group"  # Replace with user-specific group

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT class_name, start_time FROM schedule WHERE group_name = ? AND day_of_week = ?",
        (group, day_of_week),
    )
    rows = cursor.fetchall()
    conn.close()

    if rows:
        schedule = "\n".join([f"{row[1]} - {row[0]}" for row in rows])
        await message.answer(f"Расписание:\n{schedule}")
    else:
        await message.answer("На выбранный день занятий нет.")
