from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, KeyboardButton, ReplyKeyboardMarkup, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.db.db import (
    add_replacement,
    add_pair_link,
    get_pair_links,
    clear_pair_links,
    get_users_in_group,
    get_user_role,
)
from bot.utils.logger import logger
from bot.utils.helpers import get_campus_selection_keyboard, get_group_selection_keyboard, ALL_GROUPS
from bot.utils.keyboards import curator_keyboard
from bot.config import settings

router = Router(name="curator")


class ToGroupStates(StatesGroup):
    group = State()
    text = State()
    confirm = State()


class DirectMessageStates(StatesGroup):
    """FSM for direct messages to admin."""
    waiting_admin_id = State()
    waiting_text = State()
    waiting_confirm = State()


class LinkAddStates(StatesGroup):
    group = State()
    date = State()
    pair = State()
    url = State()
    confirm = State()


class ReplaceStates(StatesGroup):
    group = State()
    date = State()
    pair = State()
    subject = State()
    teacher = State()
    room = State()
    confirm = State()


class ClearLinksStates(StatesGroup):
    waiting_group = State()


async def _ensure_curator(user_id: int) -> bool:
    role = await get_user_role(user_id)
    return role in ("curator", "admin")


@router.message(F.text == "Написать группе")
async def msg_to_group_button(message: Message, state: FSMContext):
    """Handle 'Write to group' button or /to_group command."""
    if not await _ensure_curator(message.from_user.id):
        return await message.answer("Доступ только для кураторов и админов.")
    await state.clear()
    await state.set_state(ToGroupStates.group)
    kb = get_campus_selection_keyboard()
    await message.answer("Выберите кампус:", reply_markup=kb)


@router.message(ToGroupStates.group)
async def to_group_enter_group(message: Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        from bot.utils.keyboards import curator_keyboard
        await message.answer("Отменено.", reply_markup=curator_keyboard)
        return
    await state.update_data(group=message.text.strip())
    await state.set_state(ToGroupStates.text)
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отмена")]],
        resize_keyboard=True,
    )
    await message.answer("Напишите сообщение для отправки группе:", reply_markup=cancel_kb)


@router.message(ToGroupStates.text)
async def to_group_enter_text(message: Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        from bot.utils.keyboards import curator_keyboard
        await message.answer("Отменено.", reply_markup=curator_keyboard)
        return
    await state.update_data(text=message.text)
    data = await state.get_data()
    await state.set_state(ToGroupStates.confirm)
    confirm_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Да"), KeyboardButton(text="Отмена")]],
        resize_keyboard=True,
    )
    await message.answer(
        f"<b>Отправить группе {data['group']}?</b>\n\n{data['text']}",
        reply_markup=confirm_kb,
    )


@router.message(ToGroupStates.confirm)
async def to_group_confirm(message: Message, state: FSMContext):
    txt = message.text.strip().lower()
    if txt not in ("да", "yes", "y"):
        await state.clear()
        from bot.utils.keyboards import curator_keyboard
        return await message.answer("Отправка отменена.", reply_markup=curator_keyboard)
    data = await state.get_data()
    group = data.get("group")
    text = data.get("text")
    users = await get_users_in_group(group)
    sent = 0
    for uid in users:
        try:
            broadcast_msg = f"📢 <b>Рассылка от куратора для группы {group}</b>\n\n{text}"
            await message.bot.send_message(uid, broadcast_msg)
            sent += 1
        except Exception:
            continue
    await state.clear()
    from bot.utils.keyboards import curator_keyboard
    await message.answer(
        f"✅ Отправлено {sent} пользователям группы {group}.",
        reply_markup=curator_keyboard,
    )
    logger.info(f"Curator {message.from_user.id} sent broadcast to group {group}, reached {sent} users")


@router.message(F.text == "Ссылки на пары")
async def cmd_link_start(message: Message, state: FSMContext):
    if not await _ensure_curator(message.from_user.id):
        return await message.answer("Доступ только для кураторов/админов.")
    await state.clear()
    await state.set_state(LinkAddStates.group)
    kb = get_campus_selection_keyboard()
    await message.answer("Выберите кампус:", reply_markup=kb)


@router.message(LinkAddStates.group)
async def link_group(message: Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        from bot.utils.keyboards import curator_keyboard
        await message.answer("Отменено.", reply_markup=curator_keyboard)
        return
    await state.update_data(group=message.text.strip())
    await state.set_state(LinkAddStates.date)
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отмена")]],
        resize_keyboard=True,
    )
    await message.answer("Введите дату в формате ГГГГ-ММ-ДД:", reply_markup=cancel_kb)


@router.message(LinkAddStates.date)
async def link_date(message: Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        from bot.utils.keyboards import curator_keyboard
        await message.answer("Отменено.", reply_markup=curator_keyboard)
        return
    date_s = message.text.strip()
    try:
        # validate date format
        from datetime import date as _date
        _ = _date.fromisoformat(date_s)
    except Exception:
        return await message.answer("Неверный формат даты. Используй ГГГГ-ММ-ДД.")
    await state.update_data(date=date_s)
    await state.set_state(LinkAddStates.pair)
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отмена")]],
        resize_keyboard=True,
    )
    await message.answer("Введите номер пары (целое число):", reply_markup=cancel_kb)


@router.message(LinkAddStates.pair)
async def link_pair(message: Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        from bot.utils.keyboards import curator_keyboard
        await message.answer("Отменено.", reply_markup=curator_keyboard)
        return
    try:
        pair = int(message.text.strip())
    except Exception:
        return await message.answer("Неверный номер пары. Попробуйте снова.")
    await state.update_data(pair=pair)
    await state.set_state(LinkAddStates.url)
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отмена")]],
        resize_keyboard=True,
    )
    await message.answer("Введите URL ссылки на занятие (например: https://meet.google.com/xxx-yyyy-zzz):", reply_markup=cancel_kb)


@router.message(LinkAddStates.url)
async def link_url(message: Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        from bot.utils.keyboards import curator_keyboard
        await message.answer("Отменено.", reply_markup=curator_keyboard)
        return
    url = message.text.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        return await message.answer("URL должен начинаться с http:// или https://. Попробуйте снова.")
    await state.update_data(url=url)
    data = await state.get_data()
    await state.set_state(LinkAddStates.confirm)
    confirm_kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Да"), KeyboardButton(text="Отмена")],
        ],
        resize_keyboard=True,
    )
    await message.answer(
        f"Добавить ссылку для группы {data['group']} на дату {data['date']} на {data['pair']} пару?\n{data['url']}\n\nНажмите 'Да' для подтверждения.",
        reply_markup=confirm_kb
    )


@router.message(LinkAddStates.confirm)
async def link_confirm(message: Message, state: FSMContext):
    from bot.utils.keyboards import curator_keyboard
    
    if message.text.strip().lower() not in ("да", "yes", "y"):
        await state.clear()
        return await message.answer("Отменено.", reply_markup=curator_keyboard)
    
    data = await state.get_data()
    try:
        await add_pair_link(data["group"], data["date"], int(data["pair"]), data["url"], message.from_user.id)
        await state.clear()
        await message.answer(
            f"✓ Ссылка на пару добавлена:\n"
            f"Группа: {data['group']}\n"
            f"Дата: {data['date']}\n"
            f"Номер пары: {data['pair']}\n"
            f"URL: {data['url']}",
            reply_markup=curator_keyboard
        )
    except Exception as e:
        await message.answer(f"Ошибка при добавлении ссылки: {e}", reply_markup=curator_keyboard)


@router.message(F.text == "Добавить замену")
async def cmd_replace_start(message: Message, state: FSMContext):
    """Initiate replacement addition with group dropdown."""
    if not await _ensure_curator(message.from_user.id):
        return await message.answer("Доступ только для кураторов/админов.")
    await state.clear()
    await state.set_state(ReplaceStates.group)
    kb = get_campus_selection_keyboard()
    await message.answer("Выберите кампус:", reply_markup=kb)


@router.message(F.text == "Очистить ссылки")
async def cmd_clear_links_start(message: Message, state: FSMContext):
    """Initiate link clearing with group dropdown."""
    if not await _ensure_curator(message.from_user.id):
        return await message.answer("Доступ только для кураторов/админов.")
    await state.clear()
    await state.set_state(ClearLinksStates.waiting_group)
    kb = get_campus_selection_keyboard()
    await message.answer("Выберите кампус:", reply_markup=kb)


@router.message(ClearLinksStates.waiting_group)
async def clear_links_group(message: Message, state: FSMContext):
    group = message.text.strip()
    if not group:
        await state.clear()
        return await message.answer("Пустая группа. Отмена.")
    try:
        await clear_pair_links(group)
        await state.clear()
        await message.answer(f"Ссылки для группы {group} удалены (если были).")
    except Exception as exc:
        await state.clear()
        await message.answer(f"Ошибка при удалении ссылок для {group}: {exc}")


@router.message(ReplaceStates.group)
async def replace_group(message: Message, state: FSMContext):
    await state.update_data(group=message.text.strip())
    await state.set_state(ReplaceStates.date)
    await message.answer("Укажи дату замены в формате YYYY-MM-DD:")


@router.message(ReplaceStates.date)
async def replace_date(message: Message, state: FSMContext):
    await state.update_data(date=message.text.strip())
    await state.set_state(ReplaceStates.pair)
    await message.answer("Номер пары (число):")


@router.message(ReplaceStates.pair)
async def replace_pair(message: Message, state: FSMContext):
    try:
        p = int(message.text.strip())
    except Exception:
        return await message.answer("Неверный номер пары")
    await state.update_data(pair=p)
    await state.set_state(ReplaceStates.subject)
    await message.answer("Предмет (название):")


@router.message(ReplaceStates.subject)
async def replace_subject(message: Message, state: FSMContext):
    await state.update_data(subject=message.text.strip())
    await state.set_state(ReplaceStates.teacher)
    await message.answer("Преподаватель (или '-' если нет):")


@router.message(ReplaceStates.teacher)
async def replace_teacher(message: Message, state: FSMContext):
    await state.update_data(teacher=message.text.strip())
    await state.set_state(ReplaceStates.room)
    await message.answer("Аудитория (или '-' если нет):")


@router.message(ReplaceStates.room)
async def replace_room(message: Message, state: FSMContext):
    await state.update_data(room=message.text.strip())
    data = await state.get_data()
    await state.set_state(ReplaceStates.confirm)
    await message.answer(
        f"Добавить замену для {data['group']} {data['date']} {data['pair']} пары?\n{data['subject']} • {data['teacher']} • {data['room']}\n\nНапиши 'да' для подтверждения."
    )


@router.message(ReplaceStates.confirm)
async def replace_confirm(message: Message, state: FSMContext):
    if message.text.strip().lower() not in ("да", "yes", "y"):
        await state.clear()
        return await message.answer("Отмена.")
    data = await state.get_data()
    await add_replacement(
        data["group"], data["date"], int(data["pair"]), data["subject"], data.get("teacher"), data.get("room"), message.from_user.id
    )
    await state.clear()
    await message.answer("Замена сохранена.")


@router.message(F.text == "Ответить администратору")
async def msg_direct_to_admin(message: Message, state: FSMContext):
    """Handle 'Reply to admin' button."""
    if not await _ensure_curator(message.from_user.id):
        return await message.answer("Доступ только для кураторов.")
    
    await state.clear()
    await state.set_state(DirectMessageStates.waiting_admin_id)
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отмена")]],
        resize_keyboard=True,
    )
    await message.answer(
        "Введите ID администратора или команду /admin_list для просмотра списка:",
        reply_markup=cancel_kb
    )


@router.message(DirectMessageStates.waiting_admin_id)
async def direct_message_admin_id(message: Message, state: FSMContext):
    """Handle admin ID input from curator."""
    if message.text == "Отмена":
        await state.clear()
        from bot.utils.keyboards import curator_keyboard
        await message.answer("Отменено.", reply_markup=curator_keyboard)
        return
    
    try:
        admin_id = int(message.text.strip())
    except ValueError:
        return await message.answer("ID должен быть числом. Попробуйте снова:")
    
    # Verify admin exists in .env
    if admin_id not in (settings.ADMINS or []):
        return await message.answer(f"Администратор с ID {admin_id} не найден. Попробуйте снова:")
    
    await state.update_data(target_admin_id=admin_id)
    await state.set_state(DirectMessageStates.waiting_text)
    
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отмена")]],
        resize_keyboard=True,
    )
    await message.answer(f"Пишите сообщение для администратора (ID: {admin_id}):", reply_markup=cancel_kb)


@router.message(DirectMessageStates.waiting_text)
async def direct_message_admin_text(message: Message, state: FSMContext):
    """Handle message text to admin."""
    if message.text == "Отмена":
        await state.clear()
        from bot.utils.keyboards import curator_keyboard
        await message.answer("Отменено.", reply_markup=curator_keyboard)
        return
    
    msg_text = message.text.strip()
    await state.update_data(message_text=msg_text)
    await state.set_state(DirectMessageStates.waiting_confirm)
    
    # Show preview
    preview = (
        f"<b>Предпросмотр сообщения для администратора:</b>\n\n"
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
async def direct_message_admin_confirm(message: Message, state: FSMContext):
    """Confirm and send direct message to admin."""
    if message.text == "Отмена":
        await state.clear()
        role = await get_user_role(message.from_user.id)
        is_admin = role == "admin" or message.from_user.id in settings.ADMINS
        from bot.utils.keyboards import curator_keyboard, admin_keyboard
        kb = admin_keyboard if is_admin else curator_keyboard
        await message.answer("Отменено.", reply_markup=kb)
        return
    
    if message.text != "Отправить":
        return await message.answer("Выберите 'Отправить' или 'Отмена'.")
    
    data = await state.get_data()
    target_admin_id = data.get("target_admin_id")
    msg_text = data.get("message_text")
    curator_id = message.from_user.id
    curator_name = message.from_user.first_name or f"Куратор {curator_id}"
    
    # Validate target_admin_id
    if not target_admin_id or target_admin_id not in (settings.ADMINS or []):
        await state.clear()
        from bot.utils.keyboards import curator_keyboard
        return await message.answer(f"Ошибка: администратор не найден или сессия истекла. Попробуйте снова.", reply_markup=curator_keyboard)
    
    try:
        # Format message with sender info
        formatted_msg = (
            f"<b>📨 От куратора:</b>\n"
            f"<b>ID:</b> <code>{curator_id}</code>\n"
            f"<b>Имя:</b> {curator_name}\n\n"
            f"{msg_text}"
        )
        
        await message.bot.send_message(target_admin_id, formatted_msg)
        await state.clear()
        from bot.utils.keyboards import curator_keyboard
        await message.answer("✓ Сообщение отправлено администратору.", reply_markup=curator_keyboard)
        
        logger.info(f"Curator {curator_id} sent direct message to admin {target_admin_id}")
    except Exception as exc:
        await message.answer(f"Ошибка при отправке сообщения: {exc}")
        logger.error(f"Error sending direct message to admin {target_admin_id}: {exc}")


# Callback handlers for group selection in curator operations
@router.callback_query(lambda c: c.data.startswith("campus:") and c.message.text and "выбор" in c.message.text.lower())
async def cb_campus_curator(callback: CallbackQuery, state: FSMContext):
    """Handle campus selection in curator group selection flows."""
    campus = callback.data.split(":", 1)[1]
    await callback.answer()
    await state.update_data(selected_campus=campus)
    kb = get_group_selection_keyboard(campus, page=0)
    await callback.message.edit_text(f"Выберите группу в кампусе {campus}:", reply_markup=kb)


@router.callback_query(lambda c: c.data.startswith("page:") and c.message.text and "выбор" in c.message.text.lower())
async def cb_pagination_curator(callback: CallbackQuery, state: FSMContext):
    """Handle pagination in curator group selection."""
    parts = callback.data.split(":")
    campus = parts[1]
    page = int(parts[2])
    await callback.answer()
    kb = get_group_selection_keyboard(campus, page=page)
    await callback.message.edit_reply_markup(reply_markup=kb)


@router.callback_query(lambda c: c.data == "select_campus" and c.message.text and "выбор" in c.message.text.lower())
async def cb_back_campus_curator(callback: CallbackQuery, state: FSMContext):
    """Back to campus selection in curator flow."""
    await callback.answer()
    kb = get_campus_selection_keyboard()
    await callback.message.edit_text("Выберите кампус:", reply_markup=kb)


@router.callback_query(lambda c: c.data.startswith("group:") and c.message.text and "выбор" in c.message.text.lower())
async def cb_group_curator(callback: CallbackQuery, state: FSMContext):
    """Handle group selection in curator operations (links, replacements)."""
    group = callback.data.split(":", 1)[1]
    await callback.answer()
    
    # Update FSM data with selected group
    await state.update_data(group=group)
    
    # Get current FSM state to determine what flow we're in
    current_state = await state.get_state()
    
    if current_state == LinkAddStates.group:
        await state.set_state(LinkAddStates.pair)
        await callback.message.edit_text(f"Группа: {group}\n\nВведите номер пары (число):")
    elif current_state == ReplaceStates.group:
        await state.set_state(ReplaceStates.date)
        await callback.message.edit_text(f"Группа: {group}\n\nВведите дату (YYYY-MM-DD):")
    elif current_state == ClearLinksStates.waiting_group:
        await callback.message.edit_text(f"Группа: {group}\n\nОчищаю ссылки...")
        try:
            await clear_pair_links(group)
            await state.clear()
            await callback.message.edit_text(f"✓ Ссылки для группы {group} удалены (если были).")
        except Exception as exc:
            await state.clear()
            await callback.message.edit_text(f"Ошибка при удалении ссылок для {group}: {exc}")
    elif current_state == ToGroupStates.group:
        await state.set_state(ToGroupStates.text)
        await callback.message.edit_text(f"Группа: {group}\n\nНапишите сообщение для отправки группе:")
    else:
        # Unknown flow, just show the group
        await callback.message.edit_text(f"Выбрана группа: {group}")
