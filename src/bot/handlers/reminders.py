from datetime import datetime

from aiogram import Router
from aiogram.types import Message

router = Router()


@router.message()
async def handle_reminder(message: Message):
    # Example logic for recurring reminders
    current_week = datetime.now().isocalendar()[1] % 2  # 0 for even, 1 for odd
    if current_week == 0:
        await message.answer(
            "Напоминание: чётная неделя, проверьте расписание!"
        )
    else:
        await message.answer(
            "Напоминание: нечётная неделя, проверьте расписание!"
        )


import aiohttp

from bot.config import settings

HEADERS = {"Authorization": f"Bearer {settings.API_KEY}"}


async def fetch_timetable(group: str, week: str = "current"):
    url = f"{settings.BASE_URL}/timetable"
    params = {"group": group, "week": week}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=HEADERS, params=params) as resp:
            if resp.status == 200:
                return await resp.json()
            return None
