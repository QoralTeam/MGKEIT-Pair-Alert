import aiosqlite
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.db.db import DB_PATH

router = Router(name="settings")


@router.message(Command("settings"))
async def cmd_settings(message: Message):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT reminder_minutes, "
            "week_parity FROM users WHERE user_id = ?",
            (message.from_user.id,),
        ) as cur:
            row = await cur.fetchone()

    if not row:
        return await message.answer("Сначала установи группу: /setgroup ...")

    mins, parity = row
    kb = InlineKeyboardBuilder()
    kb.button(text="Изменить время напоминания", callback_data="set_time")
    kb.button(text="Чётность недели", callback_data=f"parity_{parity}")
    kb.button(text="Дни недели", callback_data="set_days")
    kb.adjust(1)

    await message.answer(
        f"Текущие настройки:\n"
        f"• Напоминание: за {mins} мин\n"
        f"• Чётность: {parity}\n\n"
        "Что изменить?",
        reply_markup=kb.as_markup(),
    )


@router.message(Command("set_reminder"))
async def set_reminder_command(message: Message):
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("За 10 минут"))
    keyboard.add(KeyboardButton("За 30 минут"))
    keyboard.add(KeyboardButton("За 1 час"))

    await message.answer(
        "Выберите время, за которое напоминать о занятии:",
        reply_markup=keyboard,
    )


# Здесь можно добавить FSM для изменения времени/дней — пока просто заглушка
@router.callback_query(F.data.startswith("set_"))
async def stub(callback: CallbackQuery):
    await callback.answer("Скоро будет =)", show_alert=True)
