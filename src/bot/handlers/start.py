import aiosqlite
from aiogram import F, Router, types
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from aiogram.utils.markdown import hbold

from bot.config import settings
from bot.db.db import DB_PATH
from bot.db.db import set_user_role, get_user_role, list_users_by_role
from bot.utils.keyboards import (
    admin_keyboard,
    curator_keyboard,
    student_keyboard,
)

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        f"{hbold('MGKEIT Pair Alert')}\n\n"
        "Привет! Я буду напоминать тебе о парах заранее.\n\n"
        "Чтобы начать — пришли свою группу:\n"
        "/setgroup 1ОЗИП-1-11-25"
    )


@router.message(Command("setgroup"))
async def cmd_setgroup(message: Message):
    args = message.text.strip().split(maxsplit=1)
    if len(args) < 2 or not args[1].strip():
        return await message.answer(
            "Ошибка! Укажи группу правильно:\n/setgroup 1ОЗИП-1-11-25"
        )

    group = args[1].strip().upper()

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO users (user_id, group_name, reminder_minutes)
               VALUES (?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET group_name = excluded.group_name""",
            (message.from_user.id, group, settings.REMINDER_DEFAULT_MINUTES),
        )
        await db.commit()

    await message.answer(
        f"Группа {hbold(group)} сохранена!\n"
        f"Напоминания будут приходить за {hbold(settings.REMINDER_DEFAULT_MINUTES)} мин до пары.\n\n"
        "Настройки: /settings\nРасписание: /today /tomorrow"
    )


@router.message(Command("start"))
async def start_command(message: types.Message):
    print("Команда /start вызвана")  # Log to verify the handler is triggered
    await message.answer(
        "Добро пожаловать! Выберите действие:",
        reply_markup=student_keyboard,
    )


async def _is_admin(user_id: int) -> bool:
    # First check static admins from settings, then DB role
    if user_id in settings.ADMINS:
        return True
    role = await get_user_role(user_id)
    return role == 'admin'


@router.message(Command("setrole"))
async def setrole_command(message: types.Message):
    """Usage: /setrole <user_id> <student|curator|admin>
    Only users with admin role (or listed in settings.ADMINS) can run this.
    """
    caller_id = message.from_user.id
    if not await _is_admin(caller_id):
        return await message.answer("Ошибка: только администратор может менять роли.")

    parts = message.text.strip().split(maxsplit=2)
    if len(parts) < 3:
        return await message.answer("Использование: /setrole <user_id> <student|curator|admin>")

    try:
        target_id = int(parts[1])
    except ValueError:
        return await message.answer("Ошибка: user_id должен быть числом.")

    role = parts[2].lower()
    if role not in ("student", "curator", "admin"):
        return await message.answer("Роль должна быть одной из: student, curator, admin")

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
        return await message.answer("Ошибка: только администратор может просматривать список ролей.")

    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        return await message.answer("Использование: /listrole <student|curator|admin>")

    role = parts[1].lower()
    if role not in ("student", "curator", "admin"):
        return await message.answer("Роль должна быть одной из: student, curator, admin")

    users = await list_users_by_role(role)
    if not users:
        return await message.answer(f"Пользователи с ролью {role} не найдены.")

    await message.answer(f"Пользователи с ролью {role}:\n" + "\n".join(str(u) for u in users))


@router.message(Command("settings"))
async def settings_command(message: types.Message):
    await message.answer(
        "Настройки бота:",
        reply_markup=admin_keyboard if message.from_user.id in settings.ADMINS else curator_keyboard,
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
    await message.answer("Вы можете отправить свои отзывы и предложения сюда: feedback@example.com")


@router.message(Command("about"))
async def about_command(message: types.Message):
    await message.answer(
        "MGKEIT Pair Alert - бот для напоминаний о парах.\n"
        "Разработчик: QoralTeam\n"
        "Версия: 1.0.0"
    )
