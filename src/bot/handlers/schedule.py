from datetime import datetime, timedelta

import aiosqlite
from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup

from bot.db.db import DB_PATH, list_schedule_for_group, get_replacements_for_group_date

router = Router(name="schedule")


async def get_today_schedule(group: str, offset: int = 0) -> str:
    target = (datetime.now() + timedelta(days=offset)).strftime("%Y-%m-%d")
    rows = await list_schedule_for_group(group, target)

    # Fetch replacements and override schedule where present
    replacements = await get_replacements_for_group_date(group, target)

    if not rows and not replacements:
        return "Пар нет"

    # Build map of pair_number -> row (pair_number, time_start, time_end, subject, teacher, room, week_type)
    schedule_map = {
        int(r[0]): (r[1], r[2], r[3] or "", r[4] or "", r[5] or "") for r in rows
    }

    # Merge replacements (they override existing entries)
    for pnum, (subj, teacher, room) in replacements.items():
        schedule_map[int(pnum)] = ("", subj or "", teacher or "", room or "")

    lines = []
    for n in sorted(schedule_map.keys()):
        time_start, time_end, subj, teacher, room = schedule_map[n]
        time_label = f"{time_start}–{time_end}" if time_end else (time_start or '—')
        # mark if this pair has replacement
        rep_mark = " (замена)" if n in replacements else ""
        lines.append(
            f"{n} пара{rep_mark} • {time_label} • {subj or '—'}\n   {teacher or '—'} • {room or '—'}"
        )
    return "\n\n".join(lines)


async def _parse_time(date_s: str, time_s: str):
    try:
        return datetime.strptime(f"{date_s} {time_s}", "%Y-%m-%d %H:%M")
    except Exception:
        return None


async def get_current_and_next_pair(group: str):
    """Return (current_pair_dict|None, next_pair_dict|None).
    pair dict: {pair_number, time_start(datetime), subject, teacher, room, is_replacement}
    """
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    rows = await list_schedule_for_group(group, today)
    replacements = await get_replacements_for_group_date(group, today)

    candidates = []
    for r in rows:
        pnum = int(r[0])
        t_start = r[1]
        t_end = r[2]
        subj = r[3] or ""
        teacher = r[4] or ""
        room = r[5] or ""
        dt = await _parse_time(today, t_start)
        if not dt:
            continue
        is_rep = pnum in replacements
        if is_rep:
            subj, teacher, room = replacements[pnum]
        candidates.append((pnum, dt, subj, teacher, room, is_rep))

    # sort by start time
    candidates.sort(key=lambda x: x[1])

    current = None
    next_pair = None
    for pnum, dt, subj, teacher, room, is_rep in candidates:
        # prefer parsed t_end if available, otherwise assume 90 minutes
        end_dt = dt + timedelta(minutes=90)
        if dt <= now < end_dt:
            current = {
                "pair_number": pnum,
                "time_start": dt,
                "subject": subj,
                "teacher": teacher,
                "room": room,
                "is_replacement": is_rep,
            }
        elif dt >= now and next_pair is None:
            next_pair = {
                "pair_number": pnum,
                "time_start": dt,
                "subject": subj,
                "teacher": teacher,
                "room": room,
                "is_replacement": is_rep,
            }

    return current, next_pair





async def _get_user_group(user_id: int) -> str | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT group_name FROM users WHERE user_id = ?",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
    return row[0] if row else None


def _get_week_start_date(date: datetime = None) -> datetime:
    """Return the Monday of the week containing the given date (or today if not specified).
    weekday() returns 0 = Monday, 6 = Sunday.
    """
    if date is None:
        date = datetime.now()
    # Calculate days back to Monday (0)
    days_since_monday = date.weekday()
    return date - timedelta(days=days_since_monday)


async def cmd_today(message: Message):
    """Get today's schedule."""
    group = await _get_user_group(message.from_user.id)
    if not group:
        return await message.answer("Укажи группу: /setgroup ...")

    today = datetime.now()
    date_s = today.strftime("%Y-%m-%d")
    day_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    day_name = day_names[today.weekday()]
    
    text = await get_today_schedule(group)
    await message.answer(f"<b>{day_name} {date_s} (Сегодня)</b>\n\n{text}")


async def cmd_tomorrow(message: Message):
    """Get tomorrow's schedule."""
    group = await _get_user_group(message.from_user.id)
    if not group:
        return await message.answer("Укажи группу: /setgroup ...")

    tomorrow = datetime.now() + timedelta(days=1)
    date_s = tomorrow.strftime("%Y-%m-%d")
    day_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    day_name = day_names[tomorrow.weekday()]
    
    text = await get_today_schedule(group, offset=1)
    await message.answer(f"<b>{day_name} {date_s} (Завтра)</b>\n\n{text}")


# Handlers for reply-keyboard buttons (text messages)
@router.message(F.text == "Сегодня")
async def msg_today(message: Message):
    await cmd_today(message)


@router.message(F.text == "Завтра")
async def msg_tomorrow(message: Message):
    await cmd_tomorrow(message)


@router.message(F.text == "Неделя")
async def msg_week(message: Message):
    group = await _get_user_group(message.from_user.id)
    if not group:
        return await message.answer("Укажи группу: /setgroup ...")

    # Build week overview starting from Monday of this week
    week_start = _get_week_start_date()
    texts = []
    day_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    
    for d in range(7):
        current_date = week_start + timedelta(days=d)
        date_s = current_date.strftime("%Y-%m-%d")
        day_name = day_names[d]
        
        sched = await get_today_schedule(group, offset=0)
        # Manually fetch schedule for the specific date instead of using offset
        rows = await list_schedule_for_group(group, date_s)
        replacements = await get_replacements_for_group_date(group, date_s)
        
        if not rows and not replacements:
            sched_text = "Пар нет"
        else:
            schedule_map = {int(r[0]): (r[1], r[2], r[3] or "", r[4] or "", r[5] or "") for r in rows}
            for pnum, (subj, teacher, room) in replacements.items():
                schedule_map[int(pnum)] = ("", "", subj or "", teacher or "", room or "")

            lines = []
            for n in sorted(schedule_map.keys()):
                time_start, time_end, subj, teacher, room = schedule_map[n]
                time_label = f"{time_start}–{time_end}" if time_end else (time_start or '—')
                rep_mark = " (замена)" if n in replacements else ""
                lines.append(
                    f"{n} пара{rep_mark} • {time_label} • {subj or '—'}\n   {teacher or '—'} • {room or '—'}"
                )
            sched_text = "\n\n".join(lines)
        
        texts.append(f"<b>{day_name} {date_s}</b>\n{sched_text}")
    
    await message.answer("Неделя:\n\n" + "\n\n".join(texts))


@router.message(F.text == "Сейчас")
async def msg_current_pair(message: Message):
    """Show current pair."""
    group = await _get_user_group(message.from_user.id)
    if not group:
        return await message.answer("Укажи группу: /setgroup ...")
    
    current, next_pair = await get_current_and_next_pair(group)
    
    if current:
        msg = (
            f"<b>📚 Текущая пара:</b>\n"
            f"{current['pair_number']} пара • {current['time_start'].strftime('%H:%M')}\n"
            f"{current['subject']}\n"
            f"{current['teacher']} • {current['room']}"
        )
    else:
        msg = "<b>📚 Текущая пара:</b>\nПар нет или день закончился."
    
    await message.answer(msg)


@router.message(F.text == "Следующая пара")
async def msg_next_pair(message: Message):
    """Show next pair."""
    group = await _get_user_group(message.from_user.id)
    if not group:
        return await message.answer("Укажи группу: /setgroup ...")
    
    current, next_pair = await get_current_and_next_pair(group)
    
    if next_pair:
        msg = (
            f"<b>🔵 Следующая пара:</b>\n"
            f"{next_pair['pair_number']} пара • {next_pair['time_start'].strftime('%H:%M')}\n"
            f"{next_pair['subject']}\n"
            f"{next_pair['teacher']} • {next_pair['room']}"
        )
    else:
        msg = "<b>🔵 Следующая пара:</b>\nПар нет."
    
    await message.answer(msg)
