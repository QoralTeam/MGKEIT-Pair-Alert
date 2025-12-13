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


@router.message(Command("setgroup"))
async def cmd_setgroup(message: Message):
    """Deprecated: use inline 'Добавить группу' button or Настройки instead."""
    await message.answer("Используйте кнопку 'Добавить группу' или 'Настройки' на клавиатуре.")


@router.message(Command("start"))
async def start_command(message: types.Message):
    # Deprecated: CommandStart() decorator handles /start now.
    # This duplicate handler is kept for backwards compatibility but should not be needed.
    await cmd_start(message)


async def _is_admin(user_id: int) -> bool:
    # First check static admins from settings, then DB role
    if user_id in settings.ADMINS:
        return True
    role = await get_user_role(user_id)
    return role == "admin"


@router.message(Command("setrole"))
async def setrole_command(message: types.Message):
    """Usage: /setrole <user_id> <student|curator|admin>
    Only users with admin role (or listed in settings.ADMINS) can run this.
    """
    caller_id = message.from_user.id
    if not await _is_admin(caller_id):
        return await message.answer(
            "Ошибка: только администратор может менять роли."
        )

    parts = message.text.strip().split(maxsplit=2)
    if len(parts) < 3:
        return await message.answer(
            "Использование: /setrole <user_id> <student|curator|admin>"
        )

    try:
        target_id = int(parts[1])
    except ValueError:
        return await message.answer("Ошибка: user_id должен быть числом.")

    role = parts[2].lower()
    if role not in ("student", "curator", "admin"):
        return await message.answer(
            "Роль должна быть одной из: student, curator, admin"
        )

    await set_user_role(target_id, role)
    await message.answer(f"Роль пользователя {target_id} установлена: {role}")


@router.message(Command("role"))
async def role_command(message: types.Message):
    """Show the role of the calling user or of given user_id: /role [user_id]"""
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) == 1:
        user_id = message.from_user.id
    else:
        try:
            user_id = int(parts[1])
        except ValueError:
            return await message.answer("Ошибка: user_id должен быть числом.")

    role = await get_user_role(user_id)
    await message.answer(f"Роль пользователя {user_id}: {role}")


@router.message(Command("listrole"))
async def listrole_command(message: types.Message):
    """List users by role. Usage: /listrole <student|curator|admin> (admin only)"""
    caller_id = message.from_user.id
    if not await _is_admin(caller_id):
        return await message.answer(
            "Ошибка: только администратор может просматривать список ролей."
        )

    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        return await message.answer(
            "Использование: /listrole <student|curator|admin>"
        )

    role = parts[1].lower()
    if role not in ("student", "curator", "admin"):
        return await message.answer(
            "Роль должна быть одной из: student, curator, admin"
        )

    users = await list_users_by_role(role)
    if not users:
        return await message.answer(f"Пользователи с ролью {role} не найдены.")

    await message.answer(
        f"Пользователи с ролью {role}:\n" + "\n".join(str(u) for u in users)
    )


@router.message(Command("settings"))
async def settings_command(message: types.Message):
    await message.answer(
        "Настройки бота:",
        reply_markup=(
            admin_keyboard
            if message.from_user.id in settings.ADMINS
            else curator_keyboard
        ),
    )


@router.message(Command("today"))
async def today_command(message: types.Message):
    await message.answer("Сегодняшнее расписание: ...")


@router.message(Command("tomorrow"))
async def tomorrow_command(message: types.Message):
    await message.answer("Завтрашнее расписание: ...")


@router.message(Command("help"))
async def help_command(message: types.Message):
    await message.answer(
        "Список доступных команд:\n"
        "/start - Начало работы\n"
        "/setgroup - Установить группу\n"
        "/settings - Настройки\n"
        "/today - Расписание на сегодня\n"
        "/tomorrow - Расписание на завтра\n"
        "/help - Помощь"
    )


@router.message(Command("feedback"))
async def feedback_command(message: types.Message):
    await message.answer(
        "Вы можете отправить свои отзывы и предложения сюда: feedback@example.com"
    )


@router.message(Command("about"))
async def about_command(message: types.Message):
    await message.answer(
        "MGKEIT Pair Alert - бот для напоминаний о парах.\n"
        "Разработчик: QoralTeam\n"
        "Версия: 1.0.0"
    )
