import aiosqlite
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.db.db import DB_PATH, get_user_role, set_user_name
from bot.utils.keyboards import student_settings_keyboard, curator_settings_keyboard, admin_settings_keyboard, student_keyboard, curator_keyboard, admin_keyboard
from bot.config import settings


# Helper function to get the correct settings keyboard based on user role
async def get_settings_keyboard(user_id: int):
    """Return the appropriate settings keyboard based on user role."""
    role = await get_user_role(user_id)
    is_admin = role == "admin" or user_id in settings.ADMINS
    is_curator = role == "curator" or user_id in settings.CURATORS
    
    if is_admin:
        return admin_settings_keyboard
    elif is_curator:
        return curator_settings_keyboard
    else:
        return student_settings_keyboard


class SettingsChangeGroupStates(StatesGroup):
    waiting_group = State()


class SettingsRenameStates(StatesGroup):
    waiting_new_first_name = State()
    waiting_new_username = State()


router = Router(name="settings")


@router.message(Command("settings"))
async def cmd_settings(message: Message):
    """Deprecated: use 'Настройки' button from reply keyboard instead."""
    await message.answer("Используйте кнопку 'Настройки' на клавиатуре.")


@router.message(F.text == "Настройки")
async def msg_settings(message: Message):
    # Check if user is admin or curator
    role = await get_user_role(message.from_user.id)
    is_admin = role == "admin" or message.from_user.id in settings.ADMINS
    is_curator = role == "curator" or message.from_user.id in settings.CURATORS
    
    if is_admin:
        # Admins only see name change option
        await message.answer(
            "Настройки администратора:",
            reply_markup=admin_settings_keyboard,
        )
        return
    
    # For students and curators, show full settings
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT reminder_minutes, week_parity, group_name FROM users WHERE user_id = ?",
            (message.from_user.id,),
        ) as cur:
            row = await cur.fetchone()

    if not row:
        return await message.answer("Сначала установи группу.")

    mins, parity, group = row
    
    # Choose keyboard based on role
    if is_curator:
        kb = curator_settings_keyboard
    else:
        kb = student_settings_keyboard
    
    await message.answer(
        f"Текущие настройки:\n"
        f"• Группа: {group}\n"
        f"• Напоминание: за {mins} мин\n"
        f"• Чётность: {parity}\n\n"
        "Что изменить?",
        reply_markup=kb,
    )





# Button handler: select reminder time
@router.message(F.text == "Установить напоминание")
async def msg_set_time(message: Message):
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="За 10 минут")],
            [KeyboardButton(text="За 30 минут")],
            [KeyboardButton(text="За 1 час")],
            [KeyboardButton(text="Назад в настройки")],
        ],
        resize_keyboard=True,
    )
    await message.answer("Выберите время напоминания:", reply_markup=kb)


# Button handler: disable reminders
@router.message(F.text == "Снять напоминание")
async def msg_disable_reminder(message: Message):
    user_id = message.from_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET reminder_minutes = 0 WHERE user_id = ?",
            (user_id,),
        )
        await db.commit()
    
    # Show confirmation and return to settings menu
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT reminder_minutes, week_parity, group_name FROM users WHERE user_id = ?",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
    
    if row:
        mins, parity, group = row
        kb = await get_settings_keyboard(message.from_user.id)
        await message.answer(
            f"Напоминания отключены.\n\n"
            f"Текущие настройки:\n"
            f"• Группа: {group}\n"
            f"• Напоминание: за {mins} мин\n"
            f"• Чётность: {parity}\n\n"
            "Что ещё изменить?",
            reply_markup=kb,
        )


# Button handler: time chosen for reminder
@router.message(F.text.in_(("За 10 минут", "За 30 минут", "За 1 час")))
async def msg_set_time_chosen(message: Message):
    # parse minutes from button text
    text_to_mins = {
        "За 10 минут": 10,
        "За 30 минут": 30,
        "За 1 час": 60,
    }
    minutes = text_to_mins.get(message.text, 0)

    user_id = message.from_user.id
    # update DB
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET reminder_minutes = ? WHERE user_id = ?",
            (minutes, user_id),
        )
        await db.commit()

    # Show confirmation and return to settings menu
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT reminder_minutes, week_parity, group_name FROM users WHERE user_id = ?",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
    
    if row:
        mins, parity, group = row
        kb = await get_settings_keyboard(message.from_user.id)
        await message.answer(
            f"Напоминание установлено за {minutes} минут.\n\n"
            f"Текущие настройки:\n"
            f"• Группа: {group}\n"
            f"• Напоминание: за {mins} мин\n"
            f"• Чётность: {parity}\n\n"
            "Что ещё изменить?",
            reply_markup=kb,
        )


# Button handler: change parity
@router.message(F.text == "Чётность недели")
async def msg_parity(message: Message):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT week_parity FROM users WHERE user_id = ?",
            (message.from_user.id,),
        ) as cur:
            row = await cur.fetchone()
    
    current = row[0] if row else "чётная"
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Чётная")],
            [KeyboardButton(text="Нечётная")],
            [KeyboardButton(text="Обе")],
            [KeyboardButton(text="Назад в настройки")],
        ],
        resize_keyboard=True,
    )
    await message.answer(
        f"Текущая чётность: {current}\nВыберите новую:",
        reply_markup=kb,
    )


# Button handler: parity selected
@router.message(F.text.in_(("Чётная", "Нечётная", "Обе")))
async def msg_parity_chosen(message: Message):
    user_id = message.from_user.id
    parity = message.text.lower()
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET week_parity = ? WHERE user_id = ?",
            (parity, user_id),
        )
        await db.commit()
    
    # Show confirmation and return to settings menu
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT reminder_minutes, week_parity, group_name FROM users WHERE user_id = ?",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
    
    if row:
        mins, parity_val, group = row
        kb = await get_settings_keyboard(message.from_user.id)
        await message.answer(
            f"Чётность установлена: {parity}\n\n"
            f"Текущие настройки:\n"
            f"• Группа: {group}\n"
            f"• Напоминание: за {mins} мин\n"
            f"• Чётность: {parity_val}\n\n"
            "Что ещё изменить?",
            reply_markup=kb,
        )


# Button handler: change days
@router.message(F.text == "Дни недели")
async def msg_set_days(message: Message):
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Будни")],
            [KeyboardButton(text="Выходные")],
            [KeyboardButton(text="Все дни")],
            [KeyboardButton(text="Назад в настройки")],
        ],
        resize_keyboard=True,
    )
    await message.answer(
        "Выберите дни, в которые отправлять напоминания:",
        reply_markup=kb,
    )


# Button handler: days selected
@router.message(F.text.in_(("Будни", "Выходные", "Все дни")))
async def msg_set_days_chosen(message: Message):
    user_id = message.from_user.id
    days = message.text.lower()
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET days = ? WHERE user_id = ?",
            (days, user_id),
        )
        await db.commit()
    
    # Show confirmation and return to settings menu
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT reminder_minutes, week_parity, group_name FROM users WHERE user_id = ?",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
    
    if row:
        mins, parity, group = row
        kb = await get_settings_keyboard(message.from_user.id)
        await message.answer(
            f"Дни установлены: {days}\n\n"
            f"Текущие настройки:\n"
            f"• Группа: {group}\n"
            f"• Напоминание: за {mins} мин\n"
            f"• Чётность: {parity}\n\n"
            "Что ещё изменить?",
            reply_markup=kb,
        )


# Button handler: change group
@router.message(F.text == "Изменить группу")
async def msg_change_group(message: Message, state: FSMContext):
    await state.set_state(SettingsChangeGroupStates.waiting_group)
    await message.answer(
        "Введите новую группу (например: ПКС-24-1):",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Отмена")]],
            resize_keyboard=True,
        ),
    )


# FSM handler: new group entered
@router.message(SettingsChangeGroupStates.waiting_group)
async def state_change_group(message: Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT reminder_minutes, week_parity, group_name FROM users WHERE user_id = ?",
                (message.from_user.id,),
            ) as cur:
                row = await cur.fetchone()
        
        if not row:
            await message.answer("Сначала установи группу.")
            return
        
        mins, parity, group = row
        kb = await get_settings_keyboard(message.from_user.id)
        await message.answer(
            f"Текущие настройки:\n"
            f"• Группа: {group}\n"
            f"• Напоминание: за {mins} мин\n"
            f"• Чётность: {parity}\n\n"
            "Что изменить?",
            reply_markup=kb,
        )
        return
    
    group = message.text.strip()
    user_id = message.from_user.id
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET group_name = ? WHERE user_id = ?",
            (group, user_id),
        )
        await db.commit()
    
    await state.clear()
    
    kb = await get_settings_keyboard(message.from_user.id)
    await message.answer(
        f"Группа изменена на: {group}",
        reply_markup=kb,
    )


# Button handler: back to settings menu from submenu
@router.message(F.text == "Назад в настройки")
async def msg_back_to_settings(message: Message):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT reminder_minutes, week_parity, group_name FROM users WHERE user_id = ?",
            (message.from_user.id,),
        ) as cur:
            row = await cur.fetchone()
    
    if not row:
        await message.answer("Сначала установи группу.")
        return
    
    mins, parity, group = row
    kb = await get_settings_keyboard(message.from_user.id)
    await message.answer(
        f"Текущие настройки:\n"
        f"• Группа: {group}\n"
        f"• Напоминание: за {mins} мин\n"
        f"• Чётность: {parity}\n\n"
        "Что изменить?",
        reply_markup=kb,
    )


# Button handler: back to main menu
@router.message(F.text == "Назад")
async def msg_back(message: Message, state: FSMContext):
    await state.clear()
    
    # Determine user's role and return appropriate keyboard
    user_id = message.from_user.id
    role = await get_user_role(user_id)
    
    if role == "admin" or user_id in settings.ADMINS:
        kb = admin_keyboard
    elif role == "curator" or user_id in settings.CURATORS:
        kb = curator_keyboard
    else:
        kb = student_keyboard
    
    await message.answer(
        "Вернулись в главное меню.",
        reply_markup=kb,
    )


# Handler for "Изменить ФИО" button
@router.message(F.text == "Изменить ФИО")
async def msg_change_name(message: Message, state: FSMContext):
    """Start rename flow for user to change their own name"""
    
    # Get current name from database
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT first_name, username FROM users WHERE user_id=?",
            (message.from_user.id,)
        )
        row = await cursor.fetchone()
    
    current_first_name = row[0] if row and row[0] else "(не указано)"
    current_username = row[1] if row and row[1] else "(не указано)"
    
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отмена")]],
        resize_keyboard=True
    )
    
    await state.set_state(SettingsRenameStates.waiting_new_first_name)
    await message.answer(
        f"Текущее имя: {current_first_name}\n"
        f"Текущий username: {current_username}\n\n"
        f"Введите новое имя (First Name):",
        reply_markup=cancel_kb
    )


@router.message(SettingsRenameStates.waiting_new_first_name)
async def process_user_rename_first_name(message: Message, state: FSMContext):
    # Check user role for correct keyboard
    user_id = message.from_user.id
    kb = await get_settings_keyboard(user_id)
    
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=kb)
        return
    
    new_first_name = message.text.strip()
    if not new_first_name:
        await message.answer("Имя не может быть пустым. Введите имя или нажмите Отмена.")
        return
    
    await state.update_data(new_first_name=new_first_name)
    await state.set_state(SettingsRenameStates.waiting_new_username)
    
    await message.answer(
        f"Новое имя: {new_first_name}\n\n"
        f"Теперь введите новый username (без @, можно оставить пустым):"
    )


@router.message(SettingsRenameStates.waiting_new_username)
async def process_user_rename_username(message: Message, state: FSMContext):
    # Check user role for correct keyboard
    user_id = message.from_user.id
    kb = await get_settings_keyboard(user_id)
    
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=kb)
        return
    
    new_username = message.text.strip()
    # Remove @ if user included it
    if new_username.startswith("@"):
        new_username = new_username[1:]
    
    data = await state.get_data()
    new_first_name = data["new_first_name"]
    
    try:
        await set_user_name(message.from_user.id, new_first_name, new_username)
        await state.clear()
        
        username_display = f"@{new_username}" if new_username else "(не указано)"
        await message.answer(
            f"✅ ФИО обновлено!\n"
            f"Имя: {new_first_name}\n"
            f"Username: {username_display}",
            reply_markup=kb
        )
    except Exception as e:
        await message.answer(f"Ошибка при обновлении: {e}", reply_markup=kb)
        await state.clear()
