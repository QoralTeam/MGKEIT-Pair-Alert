import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.bot import DefaultBotProperties
from aiogram.enums import ParseMode

# ВСЁ ИМЕННО ТАК — с префиксом bot.
from bot.config import settings
from bot.db.db import init_db
from bot.handlers.reminders import router as reminders_router
from bot.handlers.schedule import router as schedule_router
from bot.handlers.settings import router as settings_router

# Роутеры — тоже с bot.
from bot.handlers.start import router as start_router
from bot.scheduler.tasks import setup_scheduler


async def main() -> None:
    await init_db()

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    # Подключаем роутеры
    dp.include_router(start_router)
    dp.include_router(schedule_router)
    dp.include_router(settings_router)
    dp.include_router(reminders_router)

    # Запускаем планировщик
    setup_scheduler(bot)

    print("MGKEIT Pair Alert успешно запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
