import asyncio

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from bot.config import settings
from bot.db.db import init_db

# Example keyboard for disabling reminders
reminder_disable_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(
                text="Отключить напоминание", callback_data="disable_reminder"
            )
        ]
    ]
)

# Keyboard for students
student_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="Сегодня"),
            KeyboardButton(text="Завтра"),
            KeyboardButton(text="Неделя"),
        ],
        [KeyboardButton(text="Сейчас"), KeyboardButton(text="Следующая пара")],
        [KeyboardButton(text="Обед"), KeyboardButton(text="Настройки")],
    ],
    resize_keyboard=True,
)

# Keyboard for settings (reply buttons) - for students only (no password change)
student_settings_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Установить напоминание")],
        [KeyboardButton(text="Снять напоминание")],
        [KeyboardButton(text="Чётность недели")],
        [KeyboardButton(text="Дни недели")],
        [KeyboardButton(text="Изменить группу")],
        [KeyboardButton(text="Изменить ФИО")],
        [KeyboardButton(text="Назад")],
    ],
    resize_keyboard=True,
)

# Keyboard for settings (reply buttons) - for curators (with password change)
curator_settings_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Установить напоминание")],
        [KeyboardButton(text="Снять напоминание")],
        [KeyboardButton(text="Чётность недели")],
        [KeyboardButton(text="Дни недели")],
        [KeyboardButton(text="Изменить группу")],
        [KeyboardButton(text="Изменить ФИО")],
        [KeyboardButton(text="Настройка 2FA")],
        [KeyboardButton(text="Сменить пароль")],
        [KeyboardButton(text="Назад")],
    ],
    resize_keyboard=True,
)

# Legacy alias for backwards compatibility
settings_keyboard = curator_settings_keyboard

# Keyboard for settings (reply buttons) - for admins only
admin_settings_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Изменить ФИО")],
        [KeyboardButton(text="Сменить пароль")],
        [KeyboardButton(text="Настройка 2FA")],
        [KeyboardButton(text="Назад")],
    ],
    resize_keyboard=True,
)

# Keyboard for curators
curator_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="Сегодня"),
            KeyboardButton(text="Завтра"),
            KeyboardButton(text="Неделя"),
        ],
        [KeyboardButton(text="Сейчас"), KeyboardButton(text="Следующая пара")],
        [
            KeyboardButton(text="Обед"),
            KeyboardButton(text="Написать группе"),
            KeyboardButton(text="Ссылки на пары"),
        ],
        [KeyboardButton(text="Ответить администратору")],
        [KeyboardButton(text="Настройки"), KeyboardButton(text="Админу")],
    ],
    resize_keyboard=True,
)

# Keyboard for admins
admin_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [
                KeyboardButton(text="Рассылка всем"),
                KeyboardButton(text="Кураторам"),
                KeyboardButton(text="Конкретной группе"),
        ],
        [
            KeyboardButton(text="Написать куратору"),
        ],
        [
            KeyboardButton(text="Админ-панель"),
            KeyboardButton(text="Настройки"),
        ],
    ],
    resize_keyboard=True,
)


# Reply keyboard shown when admin opens the Admin Panel (under input line)
admin_panel_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="Статистика"),
            KeyboardButton(text="Синхронизация"),
        ],
        [
            KeyboardButton(text="Изменить расписание"),
            KeyboardButton(text="Добавить ссылку на занятия"),
        ],
        [
            KeyboardButton(text="Добавить замену"),
            KeyboardButton(text="Изменение времени обедов"),
        ],
        [
            KeyboardButton(text="Сменить роль"),
            KeyboardButton(text="Показать роли"),
        ],
        [
            KeyboardButton(text="Управление доступом"),
            KeyboardButton(text="Назад"),
        ],
    ],
    resize_keyboard=True,
)


async def main():
    await init_db()

    bot = Bot(token=settings.BOT_TOKEN, parse_mode=ParseMode.HTML)
    dp = Dispatcher()

    print("MGKEIT Pair Alert запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
