from datetime import datetime

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router(name="reminders")


@router.message(Command("reminder_debug"))
async def handle_reminder_debug(message: Message):
    """Debug-only endpoint.

    Real reminders are sent by the scheduler; this handler must not intercept user messages.
    """
    current_week = datetime.now().isocalendar()[1] % 2  # 0 for even, 1 for odd
    parity = "чётная" if current_week == 0 else "нечётная"
    await message.answer(f"reminder_debug: сейчас {parity} неделя")


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
