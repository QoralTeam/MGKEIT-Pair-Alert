import aiosqlite
from aiogram import F, Router, types
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from aiogram.utils.markdown import hbold
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.config import settings
from bot.db.db import (
    DB_PATH,
    get_user_role,
    list_users_by_role,
    set_user_role,
    set_user_name,
    upsert_schedule_entry,
    add_replacement,
)
from bot.utils.keyboards import (
    admin_keyboard,
    curator_keyboard,
    student_keyboard,
)
from bot.utils.password_manager import set_default_password, is_password_changed
from bot.handlers.auth import require_authentication
from bot.utils.session_manager import is_session_active
from bot.utils.logger import logger

router = Router(name="start")


class SetGroupStates(StatesGroup):
    waiting_group = State()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    # Save user's name info
    first_name = message.from_user.first_name or ""
    username = message.from_user.username or ""
    await set_user_name(message.from_user.id, first_name, username)
    
    user_id = message.from_user.id
    logger.info(f"User {user_id} started bot with /start")
    
    # Greet user and show keyboard appropriate for their role
    role = await get_user_role(user_id)
    logger.info(f"User {user_id} role from DB: {role}")
    
    # Check if user is admin or curator (from DB or .env)
    is_admin = role == "admin" or user_id in settings.ADMINS
    is_curator = role == "curator" or user_id in settings.CURATORS
    logger.info(f"User {user_id} is_admin={is_admin}, is_curator={is_curator}")
    
    if is_admin or is_curator:
        # Determine role for password creation
        actual_role = "admin" if is_admin else "curator"
        logger.info(f"User {user_id} is {actual_role}, checking auth status")
        
        # Ensure admin/curator role is set in DB
        if role != actual_role:
            await set_user_role(user_id, actual_role)
        # If a legacy curator/admin has no password yet, ensure the row exists and seed the default
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                cursor = await db.execute(
                    "SELECT hashed_password FROM users WHERE user_id = ?",
                    (user_id,),
                )
                row = await cursor.fetchone()
                hashed = row[0] if row else ""
            if not hashed:
                await set_user_role(user_id, actual_role)  # upsert and set default password
                logger.info(f"Seeded default password for {actual_role} {user_id} because it was missing")
        except Exception as exc:
            logger.error(f"Failed to seed default password for {actual_role} {user_id}: {exc}")
        
        # Check if password is set and changed from default
        password_changed = await is_password_changed(user_id)
        session_active = await is_session_active(user_id)
        logger.info(f"User {user_id} password_changed={password_changed}, session_active={session_active}")
        
        if not password_changed or not session_active:
            # Need authentication
            logger.info(f"User {user_id} needs authentication, starting auth flow")
            await message.answer(
                f"🔐 {hbold('MGKEIT Pair Alert')}\n\n"
                f"Привет, {'администратор' if is_admin else 'куратор'}!\n\n"
                f"Для доступа к панели необходимо ввести пароль."
            )
            # If password not changed, force auth even if session timestamp exists
            force_auth = not password_changed
            await require_authentication(user_id, message, state, "получить доступ к панели", force=force_auth)
            return
        
        # Authenticated - show keyboard
        logger.info(f"User {user_id} authenticated, showing keyboard")
        kb = admin_keyboard if is_admin else curator_keyboard
        await message.answer(
            f"{hbold('MGKEIT Pair Alert')}\n\n"
            f"Привет, {'администратор' if is_admin else 'куратор'}!\n\n"
            "Ниже выберите действие:",
            reply_markup=kb
        )
        return

    # Check if user (student or curator) has a group set
    group = None
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT group_name FROM users WHERE user_id = ?", (message.from_user.id,)) as cur:
                row = await cur.fetchone()
                group = row[0] if row and row[0] else None
    except Exception:
        group = None

    # This point is only reached for students (non-admin, non-curator)
    # Curators are handled above with authentication

    # Student flow
    kb = student_keyboard
    if group:
        # Student with group: show greeting and settings advice
        await message.answer(
            f"{hbold('MGKEIT Pair Alert')}\n\nПривет! Вы уже добавили группу: {group}\n\nЕсли хотите изменить группу, нажмите кнопку Настройки.",
            reply_markup=kb,
        )
    else:
        # Student without group: inline button to add group + reply keyboard
        ikb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Добавить группу", callback_data="set_group")]])
        await message.answer(
            f"{hbold('MGKEIT Pair Alert')}\n\nПривет! Добавьте группу, чтобы получать расписание.",
            reply_markup=ikb,
        )
        await message.answer("Выбери действие:", reply_markup=kb)





async def _is_admin(user_id: int) -> bool:
    # First check static admins from settings, then DB role
    if user_id in settings.ADMINS:
        return True
    role = await get_user_role(user_id)
    return role == "admin"


# Inline callback: start set-group flow
@router.callback_query(lambda c: c.data == "set_group")
async def cb_set_group(callback: types.CallbackQuery, state: FSMContext):
    # If admin pressed it somehow, ignore
    role = await get_user_role(callback.from_user.id)
    if role == "admin" or callback.from_user.id in settings.ADMINS:
        await callback.answer("Администратор: установка группы не требуется.", show_alert=True)
        return
    await callback.answer()
    await state.set_state(SetGroupStates.waiting_group)
    await callback.message.answer("Введите вашу группу (пример: 1ОЗИП-1-11-25):")


@router.message(SetGroupStates.waiting_group)
async def state_set_group(message: Message, state: FSMContext):
    group = message.text.strip().upper()
    if not group:
        return await message.answer("Пустое значение. Введите корректную группу:")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO users (user_id, group_name, reminder_minutes)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET group_name = excluded.group_name
            """,
            (message.from_user.id, group, settings.REMINDER_DEFAULT_MINUTES),
        )
        await db.commit()
    await state.clear()
    await message.answer(f"Группа {group} сохранена!")
    # show student keyboard
    await message.answer("Выберите действие:", reply_markup=student_keyboard)
