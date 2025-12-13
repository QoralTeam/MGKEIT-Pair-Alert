import asyncio
import aiohttp
from aiohttp import ClientTimeout
from aiogram.client.session.aiohttp import AiohttpSession

from aiogram import Bot, Dispatcher
from aiogram.client.bot import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Update, ErrorEvent

# ВСЁ ИМЕННО ТАК — с префиксом bot.
from bot.config import settings
from bot.db.db import init_db
from bot.utils.logger import logger
from bot.handlers.reminders import router as reminders_router
from bot.handlers.schedule import router as schedule_router
from bot.handlers.settings import router as settings_router
from bot.handlers.curator import router as curator_router
from bot.handlers.admin import router as admin_router
from bot.handlers.auth import router as auth_router
from bot.handlers.two_fa import router as two_fa_router

# Роутеры — тоже с bot.
from bot.handlers.start import router as start_router
from bot.scheduler.tasks import setup_scheduler
from bot.middleware import SessionActivityMiddleware


# Global error handler for all unhandled exceptions in handlers
async def global_error_handler(event: ErrorEvent) -> None:
    """
    Catches all unhandled exceptions in message/callback handlers.
    Logs the error and prevents bot from crashing.
    """
    logger.error(
        f"Unhandled error in update {event.update.update_id}: {event.exception}",
        exc_info=event.exception
    )
    
    # Try to notify user about error
    try:
        if event.update.message:
            await event.update.message.answer(
                "❌ Произошла ошибка при обработке команды. Попробуйте позже или обратитесь к администратору."
            )
        elif event.update.callback_query:
            await event.update.callback_query.answer(
                "❌ Произошла ошибка. Попробуйте позже.",
                show_alert=True
            )
    except Exception as notify_error:
        logger.error(f"Failed to notify user about error: {notify_error}")


async def main() -> None:
    await init_db()
    logger.info("Database initialized successfully")
    
    # Create aiohttp session with increased timeout and trust_env to respect proxy env vars
    # Use numeric timeout (seconds) rather than aiohttp.ClientTimeout instance
    session_timeout_seconds = 300
    # Use aiogram AiohttpSession which manages its own aiohttp.ClientSession
    # Pass a larger timeout to tolerate temporary network slowness
    session = AiohttpSession(timeout=session_timeout_seconds)

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=session,
    )
    logger.info(f"Bot initialized: {settings.BOT_TOKEN[:10]}...")
    
    dp = Dispatcher()
    
    # Register middleware to update activity on every action
    dp.message.middleware(SessionActivityMiddleware())
    dp.callback_query.middleware(SessionActivityMiddleware())
    logger.info("Session activity middleware registered")
    
    # Register global error handler
    dp.errors.register(global_error_handler)
    logger.info("Global error handler registered")

    # Debug: show parsed admin/curator IDs (helps diagnose role detection)
    logger.info(f"Parsed ADMINS from env/settings: {settings.ADMINS}")
    logger.info(f"Parsed CURATORS from env/settings: {settings.CURATORS}")

    # Подключаем роутеры
    dp.include_router(start_router)
    dp.include_router(auth_router)  # Auth must be before admin/curator to handle password
    dp.include_router(two_fa_router)  # 2FA settings and management
    dp.include_router(schedule_router)
    dp.include_router(settings_router)
    dp.include_router(curator_router)
    dp.include_router(admin_router)
    dp.include_router(reminders_router)
    logger.info("All routers included")

    # Запускаем планировщик
    setup_scheduler(bot)
    logger.info("Scheduler initialized")

    logger.info("MGKEIT Pair Alert успешно запущен!")
    # Run polling in a resilient loop: on transient network errors, wait and retry
    backoff = 1
    try:
        while True:
            try:
                await dp.start_polling(bot)
                # If polling finishes cleanly, break the loop
                break
            except Exception as exc:
                # Log exception and retry after backoff
                logger.error(f"Polling error: {exc!r}. Retrying in {backoff} seconds...", exc_info=True)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 300)
    finally:
        # ensure aiogram session is closed
        logger.info("Shutting down bot...")
        try:
            await session.close()
            logger.info("Session closed")
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
