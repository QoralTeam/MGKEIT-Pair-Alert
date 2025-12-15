import asyncio

from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import date as _date

import aiosqlite

from bot.db.db import (
    DB_PATH,
    list_users_by_role,
    get_users_in_group,
    get_user_role,
    get_all_pair_links,
    clear_pair_links,
    upsert_schedule_entry,
    add_replacement,
    add_pair_link,
    set_user_role,
    add_lunch,
)
from bot.scheduler import tasks as scheduler_tasks
from bot.config import settings
from bot.utils.logger import logger
from bot.db.db import (
    DB_PATH as _DB_PATH_dummy
)
from bot.utils.keyboards import admin_keyboard, admin_panel_keyboard
from bot.utils.helpers import get_campus_selection_keyboard, get_group_selection_keyboard, ALL_GROUPS

router = Router(name="admin")


class BroadcastStates(StatesGroup):
    text = State()
    confirm = State()
    target = State()  # For curator selection


class DirectMessageStates(StatesGroup):
    """FSM for direct messages to curator."""
    waiting_curator_query = State()  # Search by ID or name
    waiting_text = State()
    waiting_confirm = State()


class AdminScheduleStates(StatesGroup):
    waiting_group = State()
    waiting_date = State()
    waiting_pair = State()
    waiting_subject = State()
    waiting_teacher = State()
    waiting_start = State()
    waiting_end = State()
    waiting_room = State()


class AdminReplacementStates(StatesGroup):
    waiting_group = State()
    waiting_date = State()
    waiting_pair = State()
    waiting_subject = State()
    waiting_teacher = State()
    waiting_room = State()


class AdminLinkStates(StatesGroup):
    waiting_group = State()
    waiting_date = State()
    waiting_pair = State()
    waiting_url = State()


class AdminRoleStates(StatesGroup):
    waiting_user_id = State()
    waiting_role_choice = State()


class AdminUnblockStates(StatesGroup):
    waiting_user_id = State()


class AdminLunchStates(StatesGroup):
    waiting_group = State()
    waiting_start_time = State()
    waiting_end_time = State()


class ShowRolesDetailedStates(StatesGroup):
    """FSM for password verification before showing detailed roles."""
    waiting_password = State()


async def _delete_after(message: Message, delay_seconds: int) -> None:
    """Delete a message after a delay; ignore failures (e.g., perms)."""
    try:
        await asyncio.sleep(delay_seconds)
        await message.delete()
    except Exception:
        return


async def _ensure_admin(user_id: int) -> bool:
    # Check both settings.ADMINS and database role
    if user_id in settings.ADMINS:
        return True
    role = await get_user_role(user_id)
    return role == "admin"


@router.message(F.text == "Админ-панель")
async def msg_admin_panel_button(message: Message):
    """Reply-keyboard button to open the admin panel."""
    user_id = message.from_user.id
    if not await _ensure_admin(user_id):
        return await message.answer("Только для админов.")
    
    await message.answer("Админ-панель:", reply_markup=admin_panel_keyboard)


@router.message(F.text == "Добавить замену")
async def msg_admin_add_replacement(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if not await _ensure_admin(user_id):
        return await message.answer("Только для админов.")
    
    await state.clear()
    await state.set_state(AdminReplacementStates.waiting_group)
    kb = get_campus_selection_keyboard()
    await message.answer("Выбор кампуса:", reply_markup=kb)


@router.message(F.text == "Добавить ссылку на занятия")
async def msg_admin_add_link_msg(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if not await _ensure_admin(user_id):
        return await message.answer("Только для админов.")
    
    await state.clear()
    await state.set_state(AdminLinkStates.waiting_group)
    kb = get_campus_selection_keyboard()
    await message.answer("Выбор кампуса:", reply_markup=kb)


@router.message(F.text == "Изменение времени обедов")
async def msg_admin_change_lunch_time(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if not await _ensure_admin(user_id):
        return await message.answer("Только для админов.")
    
    await state.clear()
    await state.set_state(AdminLunchStates.waiting_group)
    kb = get_campus_selection_keyboard()
    await message.answer("Выбор кампуса:", reply_markup=kb)


@router.message(F.text == "Статистика")
async def msg_admin_stats(message: Message):
    user_id = message.from_user.id
    if not await _ensure_admin(user_id):
        return await message.answer("Только для админов.")
    
    # Build and show stats
    stats_text = await _build_stats_text()
    await message.answer(f"<b>Статистика</b>\n{stats_text}")


@router.message(F.text == "Синхронизация")
async def msg_admin_sync(message: Message):
    user_id = message.from_user.id
    if not await _ensure_admin(user_id):
        return await message.answer("Только для админов.")
    
    # Respect synchronization flag from settings
    if not getattr(settings, "SYNCHRONIZATION", True):
        return await message.answer("Синхронизация временно не доступна.")

    await message.answer("Запускаю синхронизацию расписаний...")
    try:
        import asyncio

        asyncio.create_task(scheduler_tasks.sync_all_groups(message.bot))
        await message.answer("Синхронизация запущена.")
    except Exception as exc:
        await message.answer(f"Ошибка при запуске синхронизации: {exc}")


@router.message(F.text == "Управление доступом")
async def msg_admin_manage_access(message: Message):
    """Show locked and blocked users, allow admin to unblock them."""
    if not await _ensure_admin(message.from_user.id):
        return await message.answer("Только для админов.")
    
    from bot.db.db import get_locked_users, set_user_blocked
    import time
    
    locked_users = await get_locked_users()
    
    if not locked_users:
        await message.answer(
            "✅ Заблокированных или временно запрещённых пользователей нет.",
            reply_markup=admin_panel_keyboard
        )
        return
    
    # Build list of locked users
    text = "<b>🔒 Заблокированные пользователи:</b>\n\n"
    
    for user_id, first_name, locked_until, blocked_by_admin in locked_users:
        status = ""
        if blocked_by_admin:
            status = "🔴 Заблокирован админом (требует разблокировки)"
        elif locked_until and locked_until > time.time():
            remaining_min = int((locked_until - time.time()) / 60) + 1
            status = f"🟡 Временно заблокирован (~{remaining_min} мин)"
        
        text += f"ID: <code>{user_id}</code>\n"
        text += f"Имя: {first_name or 'N/A'}\n"
        text += f"Статус: {status}\n\n"
    
    # Create inline keyboard for unblocking
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    inline_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔓 Разблокировать пользователя", callback_data="admin:unblock_user")]
        ]
    )
    
    await message.answer(text, reply_markup=inline_kb)


@router.callback_query(lambda c: c.data == "admin:unblock_user")
async def cb_unblock_user_start(callback: CallbackQuery, state: FSMContext):
    """Start unblock user process."""
    if not await _ensure_admin(callback.from_user.id):
        return await callback.answer("Только для админов.", show_alert=True)
    
    await callback.answer()
    await state.set_state(AdminUnblockStates.waiting_user_id)
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отмена")]],
        resize_keyboard=True,
    )
    await callback.message.answer(
        "Введите ID пользователя для разблокировки:",
        reply_markup=cancel_kb
    )


@router.message(AdminUnblockStates.waiting_user_id)
async def admin_unblock_user_id(message: Message, state: FSMContext):
    """Handle user ID for unblocking."""
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=admin_panel_keyboard)
        return
    
    if not await _ensure_admin(message.from_user.id):
        return await message.answer("Только для админов.")
    
    try:
        user_id = int(message.text.strip())
    except ValueError:
        return await message.answer("ID должен быть числом. Попробуйте снова.")
    
    # Unblock user
    from bot.db.db import set_user_blocked
    await set_user_blocked(user_id, False)
    
    # Also reset temporary lock
    import aiosqlite
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET locked_until = 0, failed_login_attempts = 0 WHERE user_id = ?",
            (user_id,)
        )
        await db.commit()
    
    await state.clear()
    await message.answer(
        f"✅ Пользователь {user_id} разблокирован.",
        reply_markup=admin_panel_keyboard
    )
    logger.info(f"Admin {message.from_user.id} unblocked user {user_id}")


@router.message(F.text == "Назад")
async def msg_admin_back(message: Message):
    if not await _ensure_admin(message.from_user.id):
        return await message.answer("Только для админов.")
    await message.answer("Возвращаюсь в меню.", reply_markup=admin_keyboard)


@router.message(F.text == "Сменить роль")
async def msg_admin_change_role(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if not await _ensure_admin(user_id):
        return await message.answer("Только для админов.")
    
    await state.clear()
    await state.set_state(AdminRoleStates.waiting_user_id)
    await message.answer(
        "Введите ID пользователя для изменения роли:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Отмена")]],
            resize_keyboard=True,
        ),
    )


@router.message(AdminRoleStates.waiting_user_id)
async def admin_role_user_id(message: Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Отменено. Возвращаюсь в админ-панель.", reply_markup=admin_panel_keyboard)
        return
    
    try:
        user_id = int(message.text.strip())
    except ValueError:
        return await message.answer("ID должен быть числом. Попробуйте снова.")
    
    await state.update_data(user_id=user_id)
    await state.set_state(AdminRoleStates.waiting_role_choice)
    
    # Show role selection keyboard
    role_kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="student"), KeyboardButton(text="curator")],
            [KeyboardButton(text="admin"), KeyboardButton(text="Отмена")],
        ],
        resize_keyboard=True,
    )
    await message.answer(
        f"Выберите новую роль для пользователя {user_id}:",
        reply_markup=role_kb,
    )


@router.message(AdminRoleStates.waiting_role_choice)
async def admin_role_choice(message: Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Отменено. Возвращаюсь в админ-панель.", reply_markup=admin_panel_keyboard)
        return
    
    role = message.text.strip().lower()
    if role not in ("student", "curator", "admin"):
        return await message.answer("Выберите одну из доступных ролей: student, curator, admin")
    
    data = await state.get_data()
    user_id = data.get("user_id")
    
    try:
        await set_user_role(user_id, role)
        await state.clear()
        await message.answer(
            f"✓ Роль пользователя {user_id} изменена на: {role}",
            reply_markup=admin_panel_keyboard,
        )
        logger.info(f"Admin {message.from_user.id} changed role for user {user_id} to {role}")
    except Exception as exc:
        await message.answer(f"Ошибка при изменении роли: {exc}")
        logger.error(f"Error changing role for user {user_id}: {exc}")


@router.message(F.text == "Рассылка всем")
async def msg_admin_broadcast_all(message: Message, state: FSMContext):
    """Handle 'Broadcast to all' button from admin keyboard."""
    if not await _ensure_admin(message.from_user.id):
        return await message.answer("Только для админов.")
    await state.clear()
    await state.update_data(target="all")
    await state.set_state(BroadcastStates.text)
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отмена")]],
        resize_keyboard=True,
    )
    await message.answer("Напишите текст сообщения для рассылки всем:", reply_markup=cancel_kb)


@router.message(F.text == "Кураторам")
async def msg_admin_broadcast_curators(message: Message, state: FSMContext):
    """Handle 'Broadcast to curators' button from admin keyboard."""
    if not await _ensure_admin(message.from_user.id):
        return await message.answer("Только для админов.")
    await state.clear()
    await state.update_data(target="curators")
    await state.set_state(BroadcastStates.text)
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отмена")]],
        resize_keyboard=True,
    )
    await message.answer("Напишите текст сообщения для рассылки кураторам:", reply_markup=cancel_kb)


@router.message(F.text == "Конкретной группе")
async def msg_admin_broadcast_group(message: Message, state: FSMContext):
    """Handle 'Broadcast to specific group' button from admin keyboard."""
    if not await _ensure_admin(message.from_user.id):
        return await message.answer("Только для админов.")
    await state.clear()
    await state.update_data(target="group")
    await state.set_state(BroadcastStates.text)
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отмена")]],
        resize_keyboard=True,
    )
    await message.answer(
        "Введите группу в первой строке, затем текст сообщения во второй строке:\n\n"
        "Пример:\n"
        "1ОЗИП-1-11-25\n"
        "Важное сообщение для группы",
        reply_markup=cancel_kb
    )


@router.message(F.text == "Показать роли")
async def msg_admin_show_roles(message: Message):
    user_id = message.from_user.id
    if not await _ensure_admin(user_id):
        return await message.answer("Только для админов.")
    
    # Show masked roles list with button to reveal details
    await _show_masked_roles_list(message)


async def _show_masked_roles_list(message: Message):
    """Display masked roles list with hidden IDs, usernames, and names."""
    if not await _ensure_admin(message.from_user.id):
        return await message.answer("Только для админов.")
    
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT user_id, role FROM users ORDER BY role") as cur:
                rows = await cur.fetchall()
        
        # Count users by role
        from collections import Counter
        role_counts = Counter(row[1] for row in rows)
        
        # Add from env
        env_admins = settings.ADMINS or []
        env_curators = settings.CURATORS or []
        for aid in env_admins:
            if aid not in [row[0] for row in rows]:
                role_counts["admin"] += 1
        for cid in env_curators:
            if cid not in [row[0] for row in rows]:
                role_counts["curator"] += 1
        
        # Build summary
        lines = ["<b>📊 Статистика пользователей:</b>\n"]
        
        role_names = {
            "admin": "👑 Администраторы",
            "curator": "📋 Кураторы",
            "student": "👤 Студенты",
        }
        
        for role in ["admin", "curator", "student"]:
            count = role_counts.get(role, 0)
            if count > 0:
                lines.append(f"\n{role_names.get(role, role)}: {count}")
        
        if not any(role_counts.values()):
            lines = ["Нет пользователей в системе."]
        
        # Add button to show full details
        ikb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Показать подробнее", callback_data="show_roles_detailed")]
        ])
        
        await message.answer("\n".join(lines), reply_markup=ikb)
    except Exception as exc:
        await message.answer(f"Ошибка при получении ролей: {exc}")
        logger.error(f"Error fetching roles: {exc}")


async def _show_full_roles_list(message: Message):
    """Display the full roles list with all user IDs."""
    if not await _ensure_admin(message.from_user.id):
        return await message.answer("Только для админов.")
    
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT user_id, role, first_name, username FROM users ORDER BY role, user_id") as cur:
                rows = await cur.fetchall()
        
        # Build role summary
        lines = ["<b>Роли пользователей:</b>\n"]
        
        # Group by role with user info
        roles_dict = {}
        for user_id, role, first_name, username in rows:
            if role not in roles_dict:
                roles_dict[role] = []
            # Format name: "First Name (@username) [ID]" or just "ID" if no name
            name_str = ""
            if first_name:
                name_str = first_name
            if username:
                name_str += f" (@{username})" if name_str else f"@{username}"
            if not name_str:
                name_str = str(user_id)
            else:
                name_str += f" [{user_id}]"
            
            roles_dict[role].append((user_id, name_str))
        
        # Add from env for admins and curators (no name info for env users)
        env_admins = settings.ADMINS or []
        env_curators = settings.CURATORS or []
        
        if "admin" not in roles_dict:
            roles_dict["admin"] = []
        if "curator" not in roles_dict:
            roles_dict["curator"] = []
        
        for aid in env_admins:
            if aid not in [uid for uid, _ in roles_dict["admin"]]:
                roles_dict["admin"].append((aid, str(aid)))
        
        for cid in env_curators:
            if cid not in [uid for uid, _ in roles_dict["curator"]]:
                roles_dict["curator"].append((cid, str(cid)))
        
        # Format output
        role_names = {
            "admin": "👑 Админ",
            "curator": "📋 Куратор",
            "student": "👤 Студент",
        }
        
        for role in ["admin", "curator", "student"]:
            if role in roles_dict and roles_dict[role]:
                users = sorted(set(roles_dict[role]), key=lambda x: x[0])
                lines.append(f"\n{role_names.get(role, role)}:")
                for uid, name_str in users:
                    lines.append(f"  • {name_str}")
        
        if not any(roles_dict.values()):
            lines = ["Нет пользователей в системе."]
        
        return await message.answer("\n".join(lines))
    except Exception as exc:
        await message.answer(f"Ошибка при получении ролей: {exc}")
        logger.error(f"Error fetching roles: {exc}")
    return None


@router.callback_query(F.data == "show_roles_detailed")
async def callback_show_roles_detailed(callback: CallbackQuery, state: FSMContext):
    """Handle 'Show detailed' button - request password."""
    user_id = callback.from_user.id
    if not await _ensure_admin(user_id):
        return await callback.answer("Только для админов.", show_alert=True)
    
    await callback.answer()
    await state.set_state(ShowRolesDetailedStates.waiting_password)
    
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отмена")]],
        resize_keyboard=True
    )
    
    await callback.message.answer(
        "🔐 Для просмотра подробной информации введите ваш пароль:",
        reply_markup=cancel_kb
    )


@router.message(ShowRolesDetailedStates.waiting_password)
async def process_show_roles_password(message: Message, state: FSMContext):
    """Verify password and show detailed roles list."""
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=admin_panel_keyboard)
        return
    
    user_id = message.from_user.id
    
    # Verify password
    from bot.utils.password_manager import verify_user_password
    if not await verify_user_password(user_id, message.text):
        try:
            await message.delete()
        except Exception:
            pass
        await message.answer("❌ Неверный пароль. Попробуйте снова или нажмите Отмена.")
        return
    
    # Password correct - show full roles list
    await state.clear()
    detailed_msg = await _show_full_roles_list(message)
    # Delete the password message for safety
    try:
        await message.delete()
    except Exception:
        pass
    # Auto-delete the detailed output after 2 minutes
    if detailed_msg:
        asyncio.create_task(_delete_after(detailed_msg, 120))
    
    # Return to admin panel keyboard
    await message.answer("✅ Данные отображены.", reply_markup=admin_panel_keyboard)


async def _build_stats_text() -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            total = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM users WHERE role = 'student'") as cur:
            students = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM users WHERE role = 'curator'") as cur:
            curators = (await cur.fetchone())[0]
    admins_env = 0
    try:
        admins_env = len(settings.ADMINS or [])
    except Exception:
        admins_env = 0
    return f"Пользователей всего: {total}\nСтудентов: {students}\nКураторов (в БД): {curators}\nАдминов (env): {admins_env}"


@router.callback_query(F.data == "admin:stats")
async def cb_admin_stats(query: CallbackQuery):
    if not await _ensure_admin(query.from_user.id):
        return await query.answer("Только для админов.", show_alert=True)
    await query.answer("Раздел в разработке", show_alert=True)


@router.callback_query(F.data == "admin:sync")
async def cb_admin_sync(query: CallbackQuery):
    if not await _ensure_admin(query.from_user.id):
        return await query.answer("Только для админов.", show_alert=True)
    await query.answer("Синхронизация в разработке", show_alert=True)


@router.callback_query(F.data == "admin:add_schedule")
async def cb_admin_add_schedule(query: CallbackQuery, state: FSMContext):
    if not await _ensure_admin(query.from_user.id):
        return await query.answer("Только для админов.", show_alert=True)
    await query.answer("Раздел в разработке", show_alert=True)


@router.message(F.text == "Добавить расписание")
async def msg_admin_add_schedule(message: Message, state: FSMContext):
    if not await _ensure_admin(message.from_user.id):
        return await message.answer("Только для админов.")
    await state.clear()
    await state.set_state(AdminScheduleStates.waiting_group)
    kb = get_campus_selection_keyboard()
    await message.answer("Выбор кампуса:", reply_markup=kb)


@router.message(F.text == "Изменить расписание")
async def msg_admin_edit_schedule(message: Message, state: FSMContext):
    if not await _ensure_admin(message.from_user.id):
        return await message.answer("Только для админов.")
    await state.clear()
    await state.set_state(AdminScheduleStates.waiting_group)
    kb = get_campus_selection_keyboard()
    await message.answer("Выбор кампуса:", reply_markup=kb)


@router.message(AdminScheduleStates.waiting_group)
async def admin_schedule_group(message: Message, state: FSMContext):
    # This handler is now for backwards compatibility / error handling
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Отменено. Возвращаюсь в админ-панель.", reply_markup=admin_panel_keyboard)
        return
    group = message.text.strip()
    if not group:
        return await message.answer("Группа не может быть пустой. Попробуйте снова или отмените.")
    await state.update_data(group=group)
    await state.set_state(AdminScheduleStates.waiting_date)
    await message.answer(
        "Введите дату в формате ГГГГ-ММ-ДД:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Отмена")]],
            resize_keyboard=True,
        ),
    )


@router.message(AdminScheduleStates.waiting_date)
async def admin_schedule_date(message: Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Отменено. Возвращаюсь в админ-панель.", reply_markup=admin_panel_keyboard)
        return
    date_s = message.text.strip()
    try:
        # validate date format
        _ = _date.fromisoformat(date_s)
    except Exception:
        return await message.answer("Неверный формат даты. Используй ГГГГ-ММ-ДД.")
    await state.update_data(date=date_s)
    await state.set_state(AdminScheduleStates.waiting_pair)
    await message.answer(
        "Введите номер пары (целое число):",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Отмена")]],
            resize_keyboard=True,
        ),
    )


@router.message(AdminScheduleStates.waiting_pair)
async def admin_schedule_pair(message: Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Отменено. Возвращаюсь в админ-панель.", reply_markup=admin_panel_keyboard)
        return
    try:
        pair_number = int(message.text.strip())
    except Exception:
        return await message.answer("Номер пары должен быть числом. Попробуйте снова.")
    await state.update_data(pair=pair_number)
    await state.set_state(AdminScheduleStates.waiting_subject)
    await message.answer(
        "Введите название предмета:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Отмена")]],
            resize_keyboard=True,
        ),
    )


@router.message(AdminScheduleStates.waiting_subject)
async def admin_schedule_subject(message: Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Отменено. Возвращаюсь в админ-панель.", reply_markup=admin_panel_keyboard)
        return
    subject = message.text.strip()
    await state.update_data(subject=subject)
    await state.set_state(AdminScheduleStates.waiting_teacher)
    await message.answer(
        "Введите имя преподавателя:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Отмена")]],
            resize_keyboard=True,
        ),
    )


@router.message(AdminScheduleStates.waiting_teacher)
async def admin_schedule_teacher(message: Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Отменено. Возвращаюсь в админ-панель.", reply_markup=admin_panel_keyboard)
        return
    teacher = message.text.strip()
    await state.update_data(teacher=teacher)
    await state.set_state(AdminScheduleStates.waiting_start)
    await message.answer(
        "Введите время начала пары в формате HH:MM (например, 09:30):",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Отмена")]],
            resize_keyboard=True,
        ),
    )


@router.message(AdminScheduleStates.waiting_start)
async def admin_schedule_start(message: Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Отменено. Возвращаюсь в админ-панель.", reply_markup=admin_panel_keyboard)
        return
    tstart = message.text.strip()
    # basic validation HH:MM
    parts = tstart.split(":")
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        return await message.answer("Неверный формат времени. Используй HH:MM.")
    hh, mm = int(parts[0]), int(parts[1])
    if not (0 <= hh < 24 and 0 <= mm < 60):
        return await message.answer("Неверное время. Часы 0-23, минуты 0-59.")
    await state.update_data(time_start=tstart)
    await state.set_state(AdminScheduleStates.waiting_end)
    await message.answer(
        "Введите время окончания пары в формате HH:MM (например, 10:15):",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Отмена")]],
            resize_keyboard=True,
        ),
    )


@router.message(AdminScheduleStates.waiting_end)
async def admin_schedule_end(message: Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Отменено. Возвращаюсь в админ-панель.", reply_markup=admin_panel_keyboard)
        return
    tend = message.text.strip()
    parts = tend.split(":")
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        return await message.answer("Неверный формат времени. Используй HH:MM.")
    hh, mm = int(parts[0]), int(parts[1])
    if not (0 <= hh < 24 and 0 <= mm < 60):
        return await message.answer("Неверное время. Часы 0-23, минуты 0-59.")
    await state.update_data(time_end=tend)
    await state.set_state(AdminScheduleStates.waiting_room)
    await message.answer(
        "Введите номер кабинета:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Отмена")]],
            resize_keyboard=True,
        ),
    )


@router.message(AdminScheduleStates.waiting_room)
async def admin_schedule_room(message: Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Отменено. Возвращаюсь в админ-панель.", reply_markup=admin_panel_keyboard)
        return
    room = message.text.strip()
    data = await state.get_data()
    group = data.get("group")
    date_s = data.get("date")
    pair_number = data.get("pair")
    subject = data.get("subject") or ""
    teacher = data.get("teacher") or ""
    time_start = data.get("time_start") or ""
    time_end = data.get("time_end") or ""
    week_type = "both"
    try:
        await upsert_schedule_entry(group, date_s, pair_number, time_start, time_end, subject, teacher, room, week_type)
        await state.clear()
        await message.answer("Расписание добавлено.", reply_markup=admin_panel_keyboard)
    except Exception as exc:
        await message.answer(f"Ошибка при сохранении расписания: {exc}")


@router.message(AdminReplacementStates.waiting_group)
async def admin_replacement_group(message: Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Отменено. Возвращаюсь в админ-панель.", reply_markup=admin_panel_keyboard)
        return
    group = message.text.strip()
    if not group:
        return await message.answer("Группа не может быть пустой. Попробуйте снова или отмените.")
    await state.update_data(group=group)
    await state.set_state(AdminReplacementStates.waiting_date)
    await message.answer(
        "Введите дату замены в формате ГГГГ-ММ-ДД:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Отмена")]],
            resize_keyboard=True,
        ),
    )


@router.message(AdminReplacementStates.waiting_date)
async def admin_replacement_date(message: Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Отменено. Возвращаюсь в админ-панель.", reply_markup=admin_panel_keyboard)
        return
    date_s = message.text.strip()
    try:
        _ = _date.fromisoformat(date_s)
    except Exception:
        return await message.answer("Неверный формат даты. Используйте ГГГГ-ММ-ДД.")
    await state.update_data(date=date_s)
    await state.set_state(AdminReplacementStates.waiting_pair)
    await message.answer(
        "Введите номер пары (целое число):",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Отмена")]],
            resize_keyboard=True,
        ),
    )


@router.message(AdminReplacementStates.waiting_pair)
async def admin_replacement_pair(message: Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Отменено. Возвращаюсь в админ-панель.", reply_markup=admin_panel_keyboard)
        return
    try:
        pair_number = int(message.text.strip())
    except Exception:
        return await message.answer("Номер пары должен быть числом. Попробуйте снова.")
    await state.update_data(pair=pair_number)
    await state.set_state(AdminReplacementStates.waiting_subject)
    await message.answer(
        "Введите название предмета:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Отмена")]],
            resize_keyboard=True,
        ),
    )


@router.message(AdminReplacementStates.waiting_subject)
async def admin_replacement_subject(message: Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Отменено. Возвращаюсь в админ-панель.", reply_markup=admin_panel_keyboard)
        return
    subject = message.text.strip()
    await state.update_data(subject=subject)
    await state.set_state(AdminReplacementStates.waiting_teacher)
    await message.answer(
        "Введите имя преподавателя:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Отмена")]],
            resize_keyboard=True,
        ),
    )


@router.message(AdminReplacementStates.waiting_teacher)
async def admin_replacement_teacher(message: Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Отменено. Возвращаюсь в админ-панель.", reply_markup=admin_panel_keyboard)
        return
    teacher = message.text.strip()
    await state.update_data(teacher=teacher)
    await state.set_state(AdminReplacementStates.waiting_room)
    await message.answer(
        "Введите номер кабинета:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Отмена")]],
            resize_keyboard=True,
        ),
    )


@router.message(AdminReplacementStates.waiting_room)
async def admin_replacement_room(message: Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Отменено. Возвращаюсь в админ-панель.", reply_markup=admin_panel_keyboard)
        return
    room = message.text.strip()
    data = await state.get_data()
    group = data.get("group")
    date_s = data.get("date")
    pair_number = data.get("pair")
    subject = data.get("subject") or ""
    teacher = data.get("teacher") or ""
    
    try:
        await add_replacement(group, date_s, pair_number, subject, teacher, room, message.from_user.id)
        await state.clear()
        await message.answer(
            f"✓ Замена добавлена:\n"
            f"Группа: {group}\n"
            f"Дата: {date_s}\n"
            f"Пара: {pair_number}\n"
            f"Предмет: {subject}\n"
            f"Преподаватель: {teacher}\n"
            f"Кабинет: {room}",
            reply_markup=admin_panel_keyboard,
        )
    except Exception as e:
        await message.answer(f"Ошибка при добавлении замены: {e}")


@router.message(AdminLinkStates.waiting_group)
async def admin_link_group(message: Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Отменено. Возвращаюсь в админ-панель.", reply_markup=admin_panel_keyboard)
        return
    group = message.text.strip()
    if not group:
        return await message.answer("Группа не может быть пустой. Попробуйте снова или отмените.")
    await state.update_data(group=group)
    await state.set_state(AdminLinkStates.waiting_date)
    await message.answer(
        "Введите дату в формате ГГГГ-ММ-ДД:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Отмена")]],
            resize_keyboard=True,
        ),
    )


@router.message(AdminLinkStates.waiting_date)
async def admin_link_date(message: Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Отменено. Возвращаюсь в админ-панель.", reply_markup=admin_panel_keyboard)
        return
    date_s = message.text.strip()
    try:
        # validate date format
        from datetime import date as _date
        _ = _date.fromisoformat(date_s)
    except Exception:
        return await message.answer("Неверный формат даты. Используй ГГГГ-ММ-ДД.")
    await state.update_data(date=date_s)
    await state.set_state(AdminLinkStates.waiting_pair)
    await message.answer(
        "Введите номер пары (целое число):",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Отмена")]],
            resize_keyboard=True,
        ),
    )


@router.message(AdminLinkStates.waiting_pair)
async def admin_link_pair(message: Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Отменено. Возвращаюсь в админ-панель.", reply_markup=admin_panel_keyboard)
        return
    try:
        pair_number = int(message.text.strip())
    except Exception:
        return await message.answer("Номер пары должен быть числом. Попробуйте снова.")
    await state.update_data(pair=pair_number)
    await state.set_state(AdminLinkStates.waiting_url)
    await message.answer(
        "Введите URL ссылки на занятие (например: https://meet.google.com/xxx-yyyy-zzz):",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Отмена")]],
            resize_keyboard=True,
        ),
    )


@router.message(AdminLinkStates.waiting_url)
async def admin_link_url(message: Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Отменено. Возвращаюсь в админ-панель.", reply_markup=admin_panel_keyboard)
        return
    url = message.text.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        return await message.answer("URL должен начинаться с http:// или https://. Попробуйте снова.")
    
    data = await state.get_data()
    group = data.get("group")
    date_s = data.get("date")
    pair_number = data.get("pair")
    
    try:
        await add_pair_link(group, date_s, pair_number, url, message.from_user.id)
        await state.clear()
        await message.answer(
            f"✓ Ссылка на пару добавлена:\n"
            f"Группа: {group}\n"
            f"Дата: {date_s}\n"
            f"Номер пары: {pair_number}\n"
            f"URL: {url}",
            reply_markup=admin_panel_keyboard,
        )
    except Exception as e:
        await message.answer(f"Ошибка при добавлении ссылки: {e}")


@router.callback_query(F.data == "admin:manage_roles")
async def cb_admin_manage_roles(query: CallbackQuery, state: FSMContext):
    if not await _ensure_admin(query.from_user.id):
        return await query.answer("Только для админов.", show_alert=True)
    await query.answer("Раздел в разработке", show_alert=True)


@router.message(AdminLunchStates.waiting_group)
async def admin_lunch_group(message: Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Отменено. Возвращаюсь в админ-панель.", reply_markup=admin_panel_keyboard)
        return
    group = message.text.strip()
    if not group:
        return await message.answer("Группа не может быть пустой. Попробуйте снова или отмените.")
    await state.update_data(group=group)
    await state.set_state(AdminLunchStates.waiting_start_time)
    await message.answer(
        "Введите время начала обеда в формате HH:MM (например: 12:00):",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Отмена")]],
            resize_keyboard=True,
        ),
    )


@router.message(AdminLunchStates.waiting_start_time)
async def admin_lunch_start_time(message: Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Отменено. Возвращаюсь в админ-панель.", reply_markup=admin_panel_keyboard)
        return
    time_start = message.text.strip()
    parts = time_start.split(":")
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        return await message.answer("Неверный формат времени. Используйте HH:MM.")
    hh, mm = int(parts[0]), int(parts[1])
    if not (0 <= hh < 24 and 0 <= mm < 60):
        return await message.answer("Неверное время. Часы 0-23, минуты 0-59.")
    await state.update_data(time_start=time_start)
    await state.set_state(AdminLunchStates.waiting_end_time)
    await message.answer(
        "Введите время окончания обеда в формате HH:MM (например: 13:00):",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Отмена")]],
            resize_keyboard=True,
        ),
    )


@router.message(AdminLunchStates.waiting_end_time)
async def admin_lunch_end_time(message: Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Отменено. Возвращаюсь в админ-панель.", reply_markup=admin_panel_keyboard)
        return
    time_end = message.text.strip()
    parts = time_end.split(":")
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        return await message.answer("Неверный формат времени. Используйте HH:MM.")
    hh, mm = int(parts[0]), int(parts[1])
    if not (0 <= hh < 24 and 0 <= mm < 60):
        return await message.answer("Неверное время. Часы 0-23, минуты 0-59.")
    
    data = await state.get_data()
    group = data.get("group")
    time_start = data.get("time_start")
    
    try:
        # Save lunch time to database (you'll need to implement set_lunch_time in db.py)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO lunch_times (group_name, time_start, time_end, updated_by, updated_at)
                VALUES (?, ?, ?, ?, datetime('now'))
                """,
                (group, time_start, time_end, message.from_user.id),
            )
            await db.commit()
        
        await state.clear()
        await message.answer(
            f"✓ Время обедов установлено:\n"
            f"Группа: {group}\n"
            f"Начало: {time_start}\n"
            f"Конец: {time_end}",
            reply_markup=admin_panel_keyboard,
        )
    except Exception as e:
        await message.answer(f"Ошибка при установке времени обедов: {e}")


@router.callback_query(F.data == "admin:show_links")
async def cb_admin_show_links(query: CallbackQuery):
    if not await _ensure_admin(query.from_user.id):
        return await query.answer("Только для админов.", show_alert=True)
    await query.answer()
    links = await get_all_pair_links()
    if not links:
        return await query.message.answer("Ссылок не найдено.")
    lines = []
    for grp, num, url in links:
        lines.append(f"{grp} • {num} пара: {url}")
    # Send in one message (if too long, Telegram will trim; can paginate later)
    await query.message.answer("Все ссылки:\n" + "\n".join(lines))


@router.callback_query(F.data == "admin:broadcast")
async def cb_admin_broadcast(query: CallbackQuery, state: FSMContext):
    if not await _ensure_admin(query.from_user.id):
        return await query.answer("Только для админов.", show_alert=True)
    await query.answer()
    # Show target selection for broadcast
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Всем", callback_data="admin:broadcast:all")],
        [InlineKeyboardButton(text="Кураторам", callback_data="admin:broadcast:curators")],
        [InlineKeyboardButton(text="Конкретной группе", callback_data="admin:broadcast:group")],
    ])
    await query.message.answer("Кому отправить рассылку?", reply_markup=kb)


@router.message(BroadcastStates.text)
async def broadcast_text(message: Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Рассылка отменена.", reply_markup=admin_keyboard)
        return
    # Support group target: expect first line as group when target == 'group'
    data = await state.get_data()
    target = data.get("target")
    if target == "group":
        parts = message.text.splitlines()
        if len(parts) < 2:
            return await message.answer("Неверный формат. В первой строке — группа, во второй — текст сообщения.")
        group = parts[0].strip()
        text = "\n".join(parts[1:]).strip()
        await state.update_data(text=text, group=group)
    else:
        await state.update_data(text=message.text)
    await state.set_state(BroadcastStates.confirm)
    confirm_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Да"), KeyboardButton(text="Отмена")]],
        resize_keyboard=True,
    )
    await message.answer("Подтвердить рассылку?", reply_markup=confirm_kb)


@router.message(BroadcastStates.confirm)
async def broadcast_confirm(message: Message, state: FSMContext):
    if message.text.strip().lower() not in ("да", "yes", "y"):
        await state.clear()
        return await message.answer("Отмена рассылки.", reply_markup=admin_keyboard)
    data = await state.get_data()
    text = data.get("text")
    target = data.get("target") or "all"
    sent = 0
    if target == "all":
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT user_id FROM users") as cur:
                rows = await cur.fetchall()
        for r in rows:
            uid = int(r[0])
            try:
                broadcast_msg = f"📢 <b>Рассылка от администратора</b>\n\n{text}"
                await message.bot.send_message(uid, broadcast_msg)
                sent += 1
            except Exception:
                continue
    elif target == "curators":
        curators = await list_users_by_role("curator")
        for uid in curators:
            try:
                broadcast_msg = f"📢 <b>Рассылка для кураторов</b>\n\n{text}"
                await message.bot.send_message(uid, broadcast_msg)
                sent += 1
            except Exception:
                continue
    elif target == "group":
        group = data.get("group")
        if not group:
            await state.clear()
            return await message.answer("Группа не указана, рассылка отменена.")
        users = await get_users_in_group(group)
        for uid in users:
            try:
                broadcast_msg = f"📢 <b>Рассылка для группы {group}</b>\n\n{text}"
                await message.bot.send_message(uid, broadcast_msg)
                sent += 1
            except Exception:
                continue
    await state.clear()
    await message.answer(f"✅ Рассылка завершена, отправлено: {sent} сообщений.", reply_markup=admin_keyboard)


@router.callback_query(F.data == "admin:broadcast:all")
async def cb_broadcast_all(query: CallbackQuery, state: FSMContext):
    if not await _ensure_admin(query.from_user.id):
        return await query.answer("Только для админов.", show_alert=True)
    await query.answer()
    await state.clear()
    await state.update_data(target="all")
    await state.set_state(BroadcastStates.text)
    await query.message.answer("Введи текст рассылки (всем):")


@router.callback_query(F.data == "admin:broadcast:curators")
async def cb_broadcast_curators(query: CallbackQuery, state: FSMContext):
    if not await _ensure_admin(query.from_user.id):
        return await query.answer("Только для админов.", show_alert=True)
    await query.answer()
    await state.clear()
    await state.update_data(target="curators")
    await state.set_state(BroadcastStates.text)
    await query.message.answer("Введи текст рассылки (кураторам):")


@router.callback_query(F.data == "admin:broadcast:group")
async def cb_broadcast_group(query: CallbackQuery, state: FSMContext):
    if not await _ensure_admin(query.from_user.id):
        return await query.answer("Только для админов.", show_alert=True)
    await query.answer()
    await state.clear()
    await state.update_data(target="group")
    await state.set_state(BroadcastStates.text)
    await query.message.answer("Введите группу и текст через перевод строки: в первой строке — группа, во второй — сообщение.")


@router.callback_query(F.data == "admin:clear_links")
async def cb_admin_clear_links(query: CallbackQuery, state: FSMContext):
    if not await _ensure_admin(query.from_user.id):
        return await query.answer("Только для админов.", show_alert=True)
    await query.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Очистить все ссылки", callback_data="admin:clear_links:all")],
        [InlineKeyboardButton(text="Отмена", callback_data="admin:cancel")],
    ])
    await query.message.answer("Подтвердите очистку всех ссылок:", reply_markup=kb)


@router.callback_query(F.data == "admin:clear_links:all")
async def cb_admin_clear_links_all(query: CallbackQuery):
    if not await _ensure_admin(query.from_user.id):
        return await query.answer("Только для админов.", show_alert=True)
    await query.answer()
    try:
        links = await get_all_pair_links()
        groups = sorted(set([g for g, _, _ in links]))
        for g in groups:
            await clear_pair_links(g)
        await query.message.answer("Все ссылки удалены.")
    except Exception as exc:
        await query.message.answer(f"Ошибка при очистке: {exc}")


@router.message(Command("to_curators"))
async def cmd_to_curators(message: Message):
    if not await _ensure_admin(message.from_user.id):
        return await message.answer("Только для админов.")
    await message.answer("Пришли текст — я отправлю кураторам.")


@router.message(F.text == "Написать куратору")
async def msg_admin_direct_to_curator(message: Message, state: FSMContext):
    """Handle 'Write to curator' button - show list of curators."""
    if not await _ensure_admin(message.from_user.id):
        return await message.answer("Только для админов.")
    
    try:
        # Get all curators from DB
        curators = await list_users_by_role("curator")
        
        # Also add curators from .env settings
        env_curators = settings.CURATORS or []
        all_curator_ids = set(curators) | set(env_curators)
        
        if not all_curator_ids:
            return await message.answer("В системе нет кураторов.")
        
        # Fetch curator info from DB
        curator_info = []
        async with aiosqlite.connect(DB_PATH) as db:
            for cid in sorted(all_curator_ids):
                async with db.execute(
                    "SELECT user_id, first_name, username FROM users WHERE user_id = ?",
                    (cid,)
                ) as cur:
                    row = await cur.fetchone()
                    if row:
                        curator_info.append({
                            "id": row[0],
                            "name": row[1] or "Без имени",
                            "username": row[2],
                        })
                    else:
                        # Curator not in DB yet, add placeholder
                        curator_info.append({
                            "id": cid,
                            "name": "Без имени",
                            "username": None,
                        })
        
        # Build curator list message
        lines = ["<b>Выберите куратора для отправки сообщения:</b>\n"]
        for info in curator_info:
            username_str = f" (@{info['username']})" if info['username'] else ""
            lines.append(f"ID: <code>{info['id']}</code> — {info['name']}{username_str}")
        
        lines.append("\n\nВы можете поиск по ID или имени. Напишите ID или имя куратора:")
        
        cancel_kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Отмена")]],
            resize_keyboard=True,
        )
        
        await state.clear()
        await state.set_state(DirectMessageStates.waiting_curator_query)
        await state.update_data(curator_list=curator_info)
        await message.answer("\n".join(lines), reply_markup=cancel_kb)
    
    except Exception as exc:
        await message.answer(f"Ошибка: {exc}")
        logger.error(f"Error showing curator list: {exc}")


@router.message(DirectMessageStates.waiting_curator_query)
async def direct_message_curator_query(message: Message, state: FSMContext):
    """Handle curator search by ID or name."""
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=admin_keyboard)
        return
    
    query = message.text.strip()
    data = await state.get_data()
    curator_list = data.get("curator_list", [])
    
    # Search by ID (exact match)
    matches = [c for c in curator_list if str(c["id"]) == query]
    
    # Search by name (partial match)
    if not matches:
        matches = [c for c in curator_list if query.lower() in c["name"].lower()]
    
    # Search by username
    if not matches:
        matches = [c for c in curator_list if c["username"] and query.lower() in c["username"].lower()]
    
    if not matches:
        return await message.answer(f"Куратор с ID или именем '{query}' не найден. Попробуйте снова:")
    
    if len(matches) == 1:
        # Exact match found
        curator = matches[0]
        await state.update_data(target_curator_id=curator["id"], target_curator_name=curator["name"])
        await state.set_state(DirectMessageStates.waiting_text)
        
        username_str = f" (@{curator['username']})" if curator['username'] else ""
        await message.answer(
            f"Пишите сообщение для куратора {curator['name']}{username_str} (ID: {curator['id']}):",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="Отмена")]],
                resize_keyboard=True,
            ),
        )
    else:
        # Multiple matches, show list for selection
        lines = [f"Найдено {len(matches)} кураторов:\n"]
        for m in matches:
            username_str = f" (@{m['username']})" if m['username'] else ""
            lines.append(f"ID: <code>{m['id']}</code> — {m['name']}{username_str}")
        lines.append("\nВыберите точный ID:")
        
        await message.answer("\n".join(lines))


@router.message(DirectMessageStates.waiting_text)
async def direct_message_curator_text(message: Message, state: FSMContext):
    """Handle message text to curator."""
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=admin_keyboard)
        return
    
    msg_text = message.text.strip()
    await state.update_data(message_text=msg_text)
    await state.set_state(DirectMessageStates.waiting_confirm)
    
    data = await state.get_data()
    curator_name = data.get("target_curator_name", "куратор")
    
    # Show preview
    preview = (
        f"<b>Предпросмотр сообщения для {curator_name}:</b>\n\n"
        f"{msg_text}\n\n"
        f"Отправить?"
    )
    
    confirm_kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Отправить"), KeyboardButton(text="Отмена")],
        ],
        resize_keyboard=True,
    )
    
    await message.answer(preview, reply_markup=confirm_kb)


@router.message(DirectMessageStates.waiting_confirm)
async def direct_message_curator_confirm(message: Message, state: FSMContext):
    """Confirm and send direct message to curator."""
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=admin_keyboard)
        return
    
    if message.text != "Отправить":
        return await message.answer("Выберите 'Отправить' или 'Отмена'.")
    
    data = await state.get_data()
    target_curator_id = data.get("target_curator_id")
    msg_text = data.get("message_text")
    admin_id = message.from_user.id
    admin_name = message.from_user.first_name or f"Администратор {admin_id}"
    
    if not target_curator_id:
        await state.clear()
        return await message.answer("Ошибка: куратор не выбран. Попробуйте еще раз.", reply_markup=admin_keyboard)
    
    try:
        # Ensure target_curator_id is int
        target_curator_id = int(target_curator_id)
        
        # Format message with sender info
        formatted_msg = (
            f"<b>📨 От администратора:</b>\n"
            f"<b>ID:</b> <code>{admin_id}</code>\n"
            f"<b>Имя:</b> {admin_name}\n\n"
            f"{msg_text}"
        )
        
        await message.bot.send_message(target_curator_id, formatted_msg)
        await state.clear()
        await message.answer("✓ Сообщение отправлено куратору.", reply_markup=admin_keyboard)
        
        logger.info(f"Admin {admin_id} sent direct message to curator {target_curator_id}")
    except Exception as exc:
        await state.clear()
        await message.answer(f"Ошибка при отправке сообщения: {exc}", reply_markup=admin_keyboard)
        logger.error(f"Error sending direct message to curator {target_curator_id}: {exc}")


@router.message()
async def fallback_admin_text(message: Message):
    # If admin requested to send to curators recently, naive: if message starts with @curators marker
    if message.text and message.text.startswith("@curators ") and await _ensure_admin(message.from_user.id):
        text = message.text[len("@curators "):]
        curators = await list_users_by_role("curator")
        sent = 0
        for uid in curators:
            try:
                await message.bot.send_message(uid, text)
                sent += 1
            except Exception:
                continue
        return await message.answer(f"Отправлено кураторам: {sent}")


@router.message(Command("to_group"))
async def cmd_to_group_admin(message: Message):
    # usage: /to_group <group>
    if not await _ensure_admin(message.from_user.id):
        return await message.answer("Только для админов.")
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.answer("Использование: /to_group <group> — после команды пришли текст с префиксом 'group:<имя>' например:\n/group:9A Текст")
    # fallback: admin can send 'group:<name> message'
    if parts[1].startswith("group:"):
        try:
            g, msg = parts[1].split(None, 1)
        except Exception:
            return await message.answer("Неверный формат. Пример: /to_group group:9A Текст")
        group = g.split(":", 1)[1]
        users = await get_users_in_group(group)
        sent = 0
        for uid in users:
            try:
                await message.bot.send_message(uid, msg)
                sent += 1
            except Exception:
                continue
        return await message.answer(f"Отправлено {sent} сообщений в группу {group}.")
    return await message.answer("Не распознан формат команды.")


# Callback handlers for group selection in admin operations
@router.callback_query(
    StateFilter(
        AdminScheduleStates.waiting_group,
        AdminReplacementStates.waiting_group,
        AdminLinkStates.waiting_group,
        AdminLunchStates.waiting_group,
    ),
    F.data.startswith("campus:"),
)
async def cb_campus_admin(callback: CallbackQuery, state: FSMContext):
    """Handle campus selection in admin group selection flows."""
    campus = callback.data.split(":", 1)[1]
    await callback.answer()
    await state.update_data(selected_campus=campus)
    kb = get_group_selection_keyboard(campus, page=0)
    await callback.message.edit_text(f"Выберите группу в кампусе {campus}:", reply_markup=kb)


@router.callback_query(
    StateFilter(
        AdminScheduleStates.waiting_group,
        AdminReplacementStates.waiting_group,
        AdminLinkStates.waiting_group,
        AdminLunchStates.waiting_group,
    ),
    F.data.startswith("page:"),
)
async def cb_pagination_admin(callback: CallbackQuery, state: FSMContext):
    """Handle pagination in admin group selection."""
    parts = callback.data.split(":")
    campus = parts[1]
    page = int(parts[2])
    await callback.answer()
    kb = get_group_selection_keyboard(campus, page=page)
    await callback.message.edit_reply_markup(reply_markup=kb)


@router.callback_query(
    StateFilter(
        AdminScheduleStates.waiting_group,
        AdminReplacementStates.waiting_group,
        AdminLinkStates.waiting_group,
        AdminLunchStates.waiting_group,
    ),
    F.data == "select_campus",
)
async def cb_back_campus_admin(callback: CallbackQuery, state: FSMContext):
    """Back to campus selection in admin flow."""
    await callback.answer()
    kb = get_campus_selection_keyboard()
    await callback.message.edit_text("Выбор кампуса:", reply_markup=kb)


@router.callback_query(
    StateFilter(
        AdminScheduleStates.waiting_group,
        AdminReplacementStates.waiting_group,
        AdminLinkStates.waiting_group,
        AdminLunchStates.waiting_group,
    ),
    F.data.startswith("group:"),
)
async def cb_group_admin(callback: CallbackQuery, state: FSMContext):
    """Handle group selection in admin operations (schedule, replacement, etc)."""
    group = callback.data.split(":", 1)[1]
    await callback.answer()
    
    # Update FSM data with selected group
    await state.update_data(group=group)
    
    # Get current FSM state to determine what flow we're in
    current_state = await state.get_state()
    
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отмена")]],
        resize_keyboard=True,
    )
    
    if current_state == AdminScheduleStates.waiting_group:
        await state.set_state(AdminScheduleStates.waiting_date)
        await callback.message.answer(
            f"Группа: {group}\n\nВведите дату в формате ГГГГ-ММ-ДД:",
            reply_markup=cancel_kb
        )
    elif current_state == AdminReplacementStates.waiting_group:
        await state.set_state(AdminReplacementStates.waiting_date)
        await callback.message.answer(
            f"Группа: {group}\n\nВведите дату замены в формате ГГГГ-ММ-ДД:",
            reply_markup=cancel_kb
        )
    elif current_state == AdminLinkStates.waiting_group:
        await state.set_state(AdminLinkStates.waiting_date)
        await callback.message.answer(
            f"Группа: {group}\n\nВведите дату в формате ГГГГ-ММ-ДД:",
            reply_markup=cancel_kb
        )
    elif current_state == AdminLunchStates.waiting_group:
        await state.set_state(AdminLunchStates.waiting_start_time)
        await callback.message.answer(
            f"Группа: {group}\n\nВведите время начала обеда в формате HH:MM (например: 12:00):",
            reply_markup=cancel_kb
        )
    else:
        # Unknown flow, just show the group
        await callback.message.answer(f"Выбрана группа: {group}")

