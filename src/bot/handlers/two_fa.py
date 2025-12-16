"""Two-Factor Authentication handlers for admin and curator roles.

Provides:
- Enable 2FA: Generate secret, show QR code, verify initial code, show backup codes
- Disable 2FA: Verify password + current TOTP code
- Status display: Show whether 2FA is enabled, remaining backup codes
"""

from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import aiosqlite

from bot.db.db import DB_PATH, get_user_role
from bot.utils.two_fa import (
    generate_totp_secret,
    generate_qr_code,
    verify_totp_code,
    generate_backup_codes,
    store_backup_codes,
    verify_backup_code,
)
from bot.utils.password_manager import verify_user_password
from bot.config import settings
from bot.utils.logger import logger
from bot.utils.keyboards import admin_settings_keyboard, curator_settings_keyboard

router = Router(name="two_fa")


async def _delete_backup_codes_message(message: Message, delay_seconds: int) -> None:
    """Delete backup codes message after a delay."""
    import asyncio
    try:
        await asyncio.sleep(delay_seconds)
        await message.delete()
        logger.info(f"Deleted backup codes message for user {message.chat.id}")
    except Exception as e:
        logger.warning(f"Failed to delete backup codes message: {e}")


class Enable2FAStates(StatesGroup):
    """FSM for enabling 2FA."""
    waiting_initial_code = State()  # Verify first TOTP code to confirm setup


class Disable2FAStates(StatesGroup):
    """FSM for disabling 2FA."""
    waiting_password = State()
    waiting_code = State()


async def _ensure_admin_or_curator(user_id: int) -> bool:
    """Check if user is admin or curator."""
    role = await get_user_role(user_id)
    return role in ("admin", "curator") or user_id in settings.ADMINS or user_id in settings.CURATORS


async def _get_2fa_status(user_id: int) -> tuple[bool, str, int]:
    """
    Get 2FA status for user.
    
    Returns:
        Tuple of (enabled, secret, backup_codes_remaining)
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT two_fa_enabled, two_fa_secret, backup_codes FROM users WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
    
    if not row:
        return False, "", 0
    
    enabled = bool(row[0])
    secret = row[1] or ""
    backup_codes_json = row[2] or "[]"
    
    import json
    try:
        backup_codes = json.loads(backup_codes_json)
        backup_count = len(backup_codes)
    except:
        backup_count = 0
    
    return enabled, secret, backup_count


@router.message(F.text == "Настройка 2FA")
async def msg_2fa_menu(message: Message, state: FSMContext):
    """Show 2FA settings menu with current status."""
    user_id = message.from_user.id
    
    if not await _ensure_admin_or_curator(user_id):
        return await message.answer("2FA доступно только для кураторов и админов.")
    
    await state.clear()
    
    enabled, secret, backup_count = await _get_2fa_status(user_id)
    
    if enabled:
        status_text = (
            f"🔐 Двухфакторная аутентификация: <b>включена</b>\n\n"
            f"📱 Используйте приложение-аутентификатор для входа\n"
            f"🔑 Резервных кодов осталось: {backup_count}\n\n"
            f"Чтобы отключить 2FA, нажмите кнопку ниже."
        )
        kb = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Отключить 2FA")],
                [KeyboardButton(text="Назад в настройки")],
            ],
            resize_keyboard=True,
        )
    else:
        status_text = (
            f"🔓 Двухфакторная аутентификация: <b>отключена</b>\n\n"
            f"Включите 2FA для дополнительной защиты аккаунта.\n"
            f"Вам понадобится приложение-аутентификатор:\n"
            f"• Google Authenticator\n"
            f"• Microsoft Authenticator\n"
            f"• 1Password\n"
            f"• Authy\n\n"
            f"Нажмите кнопку ниже для настройки."
        )
        kb = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Включить 2FA")],
                [KeyboardButton(text="Назад в настройки")],
            ],
            resize_keyboard=True,
        )
    
    await message.answer(status_text, reply_markup=kb)


@router.message(F.text == "Включить 2FA")
async def msg_enable_2fa_start(message: Message, state: FSMContext):
    """Start 2FA enrollment process."""
    user_id = message.from_user.id
    
    if not await _ensure_admin_or_curator(user_id):
        return await message.answer("2FA доступно только для кураторов и админов.")
    
    # Check if already enabled
    enabled, _, _ = await _get_2fa_status(user_id)
    if enabled:
        return await message.answer("2FA уже включена. Используйте 'Отключить 2FA' для изменения.")
    
    # Generate new secret
    secret = generate_totp_secret()
    
    # Store secret temporarily in FSM
    await state.update_data(secret=secret)
    await state.set_state(Enable2FAStates.waiting_initial_code)
    
    # Generate and send QR code
    username = f"user_{user_id}"
    qr_image = generate_qr_code(secret, username)
    
    qr_message = await message.answer_photo(
        photo=qr_image,
        caption=(
            f"📱 <b>Настройка 2FA</b>\n\n"
            f"1. Откройте приложение-аутентификатор\n"
            f"2. Отсканируйте QR-код выше\n"
            f"3. Введите 6-значный код из приложения\n\n"
            f"<b>Секретный ключ (для ручного ввода):</b>\n"
            f"<code>{secret}</code>\n\n"
            f"⚠️ <b>Это сообщение будет удалено через 2 минуты в целях безопасности.</b>\n\n"
            f"После проверки кода вы получите резервные коды для восстановления доступа."
        )
    )
    
    # Schedule QR code message deletion after 2 minutes (120 seconds)
    import asyncio
    asyncio.create_task(_delete_backup_codes_message(qr_message, 120))
    
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отмена")]],
        resize_keyboard=True,
    )
    await message.answer("Введите 6-значный код из приложения:", reply_markup=cancel_kb)
    
    logger.info(f"User {user_id} started 2FA enrollment")


@router.message(Enable2FAStates.waiting_initial_code)
async def process_enable_2fa_code(message: Message, state: FSMContext):
    """Verify initial TOTP code and complete 2FA setup."""
    user_id = message.from_user.id
    
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Настройка 2FA отменена.")
        return
    
    code = message.text.strip().replace(' ', '').replace('-', '')
    
    # Get secret from FSM
    data = await state.get_data()
    secret = data.get("secret")
    
    if not secret:
        await state.clear()
        return await message.answer("Ошибка: секретный ключ не найден. Начните настройку заново.")
    
    # Verify code
    if not verify_totp_code(secret, code):
        await message.answer("❌ Неверный код. Попробуйте ещё раз или нажмите Отмена.")
        return
    
    # Code valid - generate backup codes
    backup_codes = generate_backup_codes(10)
    backup_codes_hashed = store_backup_codes(backup_codes)
    
    # Save to database
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE users 
            SET two_fa_enabled = 1, two_fa_secret = ?, backup_codes = ?, last_auth_time = 0
            WHERE user_id = ?
            """,
            (secret, backup_codes_hashed, user_id),
        )
        await db.commit()
    
    await state.clear()
    
    # Show backup codes
    codes_text = "\n".join([f"<code>{code}</code>" for code in backup_codes])
    
    role = await get_user_role(user_id)
    is_admin = role == "admin" or user_id in settings.ADMINS
    kb = admin_settings_keyboard if is_admin else curator_settings_keyboard
    
    codes_message = await message.answer(
        f"✅ <b>2FA успешно включена!</b>\n\n"
        f"🔑 <b>Резервные коды для восстановления доступа:</b>\n\n"
        f"{codes_text}\n\n"
        f"⚠️ <b>ВАЖНО! ОБЯЗАТЕЛЬНО СОХРАНИТЕ ЭТИ КОДЫ!</b>\n"
        f"• Это сообщение будет удалено через 2 минуты\n"
        f"• Сохраните коды в надёжном месте СЕЙЧАС\n"
        f"• Каждый код можно использовать только один раз\n"
        f"• Используйте их, если потеряете доступ к приложению\n"
        f"• Без этих кодов восстановить доступ будет невозможно!\n\n"
        f"⏰ Сообщение удалится через 2 минуты",
        reply_markup=kb
    )
    
    # Schedule message deletion after 2 minutes (120 seconds)
    import asyncio
    asyncio.create_task(_delete_backup_codes_message(codes_message, 120))
    
    logger.info(f"User {user_id} successfully enabled 2FA")


@router.message(F.text == "Отключить 2FA")
async def msg_disable_2fa_start(message: Message, state: FSMContext):
    """Start 2FA disable process."""
    user_id = message.from_user.id
    
    if not await _ensure_admin_or_curator(user_id):
        return await message.answer("2FA доступно только для кураторов и админов.")
    
    # Check if enabled
    enabled, _, _ = await _get_2fa_status(user_id)
    if not enabled:
        return await message.answer("2FA не включена.")
    
    await state.set_state(Disable2FAStates.waiting_password)
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отмена")]],
        resize_keyboard=True,
    )
    await message.answer(
        "🔐 Для отключения 2FA необходимо подтверждение.\n\n"
        "Введите ваш пароль:",
        reply_markup=cancel_kb
    )


@router.message(Disable2FAStates.waiting_password)
async def process_disable_2fa_password(message: Message, state: FSMContext):
    """Verify password before requesting TOTP code."""
    user_id = message.from_user.id
    
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Отключение 2FA отменено.")
        return
    
    # Delete password message for security
    try:
        await message.delete()
    except Exception as e:
        logger.warning(f"Could not delete password message for user {user_id}: {e}")
    
    # Verify password
    if not await verify_user_password(user_id, message.text):
        await message.answer("❌ Неверный пароль. Попробуйте снова или нажмите Отмена.")
        return
    
    # Password correct - request TOTP code
    await state.set_state(Disable2FAStates.waiting_code)
    await message.answer(
        "✅ Пароль верный.\n\n"
        "Теперь введите текущий 6-значный код из приложения-аутентификатора\n"
        "или один из резервных кодов:"
    )


@router.message(Disable2FAStates.waiting_code)
async def process_disable_2fa_code(message: Message, state: FSMContext):
    """Verify TOTP code or backup code and disable 2FA."""
    user_id = message.from_user.id
    
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Отключение 2FA отменено.")
        return
    
    code = message.text.strip()
    
    # Get 2FA data
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT two_fa_secret, backup_codes FROM users WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
    
    if not row:
        await state.clear()
        return await message.answer("Ошибка: данные 2FA не найдены.")
    
    secret = row[0]
    backup_codes_json = row[1] or "[]"
    
    # Try TOTP code first
    is_valid = verify_totp_code(secret, code)
    
    # If TOTP failed, try backup code
    if not is_valid:
        is_valid, _ = verify_backup_code(code, backup_codes_json)
    
    if not is_valid:
        await message.answer("❌ Неверный код. Попробуйте ещё раз или нажмите Отмена.")
        return
    
    # Code valid - disable 2FA
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE users 
            SET two_fa_enabled = 0, two_fa_secret = '', backup_codes = '', last_auth_time = 0
            WHERE user_id = ?
            """,
            (user_id,),
        )
        await db.commit()
    
    await state.clear()
    
    role = await get_user_role(user_id)
    is_admin = role == "admin" or user_id in settings.ADMINS
    kb = admin_settings_keyboard if is_admin else curator_settings_keyboard
    
    await message.answer(
        "✅ 2FA успешно отключена.\n\n"
        "Вы можете включить её снова в любое время через Настройки.",
        reply_markup=kb
    )
    
    logger.info(f"User {user_id} disabled 2FA")
