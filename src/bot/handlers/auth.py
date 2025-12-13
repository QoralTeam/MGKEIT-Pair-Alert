"""Authentication handlers for admin and curator roles.

Handles:
- Password authentication on first access
- First-time password change requirement
- Password change with validation
- Session management
"""

from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.db.db import DB_PATH, get_user_role
from bot.utils.password_manager import (
    verify_user_password,
    change_password,
    is_password_changed,
    validate_password,
)
from bot.utils.session_manager import authenticate_user, is_session_active
from bot.config import settings
from bot.utils.logger import logger
from bot.utils.keyboards import admin_keyboard, curator_keyboard, student_keyboard
from bot.utils.two_fa import verify_totp_code, verify_backup_code
import aiosqlite

router = Router(name="auth")


class AuthStates(StatesGroup):
    """FSM states for authentication flow."""
    waiting_password = State()  # Initial password entry
    waiting_2fa_code = State()  # TOTP code verification
    waiting_new_password = State()  # First-time password change
    waiting_confirm_password = State()  # Confirm new password


class ChangePasswordStates(StatesGroup):
    """FSM states for password change."""
    waiting_current_password = State()
    waiting_new_password = State()
    waiting_confirm_password = State()
    waiting_2fa_code = State()  # TOTP verification before finalizing password change


async def require_authentication(
    user_id: int,
    message: Message,
    state: FSMContext,
    context_action: str = "access this",
    force: bool = False,
) -> bool:
    """Ensure the user is authenticated; start password flow if not.

    When force=True, skip the active-session check (used to enforce
    first-time password change even if a session timestamp exists).
    """
    # If not forcing, allow active session to pass
    if not force and await is_session_active(user_id):
        logger.info(f"User {user_id} has active session")
        return True
    
    logger.info(f"User {user_id} requires authentication (force={force}), starting auth flow")
    await state.set_state(AuthStates.waiting_password)
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отмена")]],
        resize_keyboard=True
    )
    await message.answer(
        "🔒 Требуется аутентификация для доступа.\n\n"
        "Пожалуйста, введите ваш пароль:",
        reply_markup=cancel_kb
    )
    return False


@router.message(AuthStates.waiting_password)
async def process_initial_password(message: Message, state: FSMContext):
    """Handle initial password entry for authentication."""
    user_id = message.from_user.id
    message_id = message.message_id
    
    if message.text in ("Отмена", "Назад", "Назад в настройки"):
        await state.clear()
        await message.answer("Отменено.")
        return
    
    password = message.text
    logger.info(f"User {user_id} attempting password authentication")
    
    # Delete user's password message for security
    try:
        await message.delete()
    except Exception as e:
        logger.warning(f"Could not delete password message for user {user_id}: {e}")
    
    # Verify password
    if not await verify_user_password(user_id, password):
        logger.warning(f"User {user_id} entered incorrect password")
        await message.answer("❌ Неверный пароль. Попробуйте снова или нажмите Отмена.")
        return
    
    # Password correct, check if 2FA is enabled
    import aiosqlite
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT two_fa_enabled, two_fa_secret FROM users WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
    
    two_fa_enabled = bool(row[0]) if row else False
    
    if two_fa_enabled:
        # Require 2FA code
        await state.set_state(AuthStates.waiting_2fa_code)
        cancel_kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Отмена")]],
            resize_keyboard=True
        )
        await message.answer(
            "✅ Пароль верный.\n\n"
            "🔐 Введите 6-значный код из приложения-аутентификатора\n"
            "или один из резервных кодов:",
            reply_markup=cancel_kb
        )
        logger.info(f"User {user_id} passed password check, waiting for 2FA code")
        return
    
    # No 2FA, check if user changed default password
    password_changed = await is_password_changed(user_id)
    logger.info(f"User {user_id} password verified. password_changed={password_changed}")
    
    if not password_changed:
        # Force password change on first authentication
        await state.set_state(AuthStates.waiting_new_password)
        logger.info(f"User {user_id} must change default password")
        cancel_kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Отмена")]],
            resize_keyboard=True
        )
        await message.answer(
            "✅ Пароль верный.\n\n"
            "⚠️ Вы должны сменить пароль по умолчанию перед использованием функций.\n"
            "Это требуется для безопасности.\n\n"
            "Введите новый пароль (8-128 символов, заглавные и строчные буквы, цифры, без пробелов):",
            reply_markup=cancel_kb
        )
        logger.info(f"User {user_id} prompted for password change")
        return
    
    # Password changed, authenticate session
    await authenticate_user(user_id)
    await state.clear()
    # Show appropriate keyboard based on role
    role = await get_user_role(user_id)
    if role == "admin" or user_id in settings.ADMINS:
        kb = admin_keyboard
        greet = "Привет, администратор!"
    elif role == "curator" or user_id in settings.CURATORS:
        kb = curator_keyboard
        greet = "Привет, куратор!"
    else:
        kb = student_keyboard
        greet = "Привет!"
    await message.answer(f"✅ Аутентификация успешна!\n\n{greet}\n\nНиже выберите действие:", reply_markup=kb)
    logger.info(f"User {user_id} authenticated successfully")


@router.message(AuthStates.waiting_2fa_code)
async def process_2fa_code(message: Message, state: FSMContext):
    """Verify 2FA code (TOTP or backup code) after password."""
    user_id = message.from_user.id
    
    if message.text in ("Отмена", "Назад", "Назад в настройки"):
        await state.clear()
        await message.answer("Отменено.")
        return
    
    code = message.text.strip()
    logger.info(f"User {user_id} attempting 2FA verification")
    
    # Get 2FA data
    import aiosqlite
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT two_fa_secret, backup_codes FROM users WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
    
    if not row or not row[0]:
        await state.clear()
        return await message.answer("Ошибка: 2FA данные не найдены. Обратитесь к администратору.")
    
    secret = row[0]
    backup_codes_json = row[1] or "[]"
    
    # Try TOTP code first
    from bot.utils.two_fa import verify_totp_code, verify_backup_code
    is_valid = verify_totp_code(secret, code)
    used_backup = False
    
    # If TOTP failed, try backup code
    if not is_valid:
        is_valid, updated_codes = verify_backup_code(code, backup_codes_json)
        if is_valid:
            used_backup = True
            # Update backup codes in DB (remove used code)
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "UPDATE users SET backup_codes = ? WHERE user_id = ?",
                    (updated_codes, user_id),
                )
                await db.commit()
            logger.info(f"User {user_id} used backup code for 2FA")
    
    if not is_valid:
        logger.warning(f"User {user_id} entered invalid 2FA code")
        await message.answer("❌ Неверный код. Попробуйте снова или нажмите Отмена.")
        return
    
    # 2FA passed, check if password needs to be changed
    password_changed = await is_password_changed(user_id)
    
    if not password_changed:
        # Force password change on first authentication
        await state.set_state(AuthStates.waiting_new_password)
        logger.info(f"User {user_id} passed 2FA, must change default password")
        cancel_kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Отмена")]],
            resize_keyboard=True
        )
        await message.answer(
            "✅ Код верный.\n\n"
            "⚠️ Вы должны сменить пароль по умолчанию перед использованием функций.\n"
            "Это требуется для безопасности.\n\n"
            "Введите новый пароль (8-128 символов, заглавные и строчные буквы, цифры, без пробелов):",
            reply_markup=cancel_kb
        )
        return
    
    # Authenticate session
    await authenticate_user(user_id)
    await state.clear()
    
    # Show appropriate keyboard based on role
    role = await get_user_role(user_id)
    if role == "admin" or user_id in settings.ADMINS:
        kb = admin_keyboard
        greet = "Привет, администратор!"
    elif role == "curator" or user_id in settings.CURATORS:
        kb = curator_keyboard
        greet = "Привет, куратор!"
    else:
        kb = student_keyboard
        greet = "Привет!"
    
    backup_msg = "\n\n⚠️ Вы использовали резервный код. Осталось кодов: см. Настройки → 2FA" if used_backup else ""
    await message.answer(
        f"✅ Аутентификация успешна!{backup_msg}\n\n{greet}\n\nНиже выберите действие:",
        reply_markup=kb
    )
    logger.info(f"User {user_id} authenticated successfully with 2FA")


@router.message(AuthStates.waiting_new_password)
async def process_new_password(message: Message, state: FSMContext):
    """Handle new password entry during first-time password change."""
    user_id = message.from_user.id
    
    if message.text in ("Отмена", "Назад", "Назад в настройки"):
        await state.clear()
        await message.answer("Смена пароля отменена.")
        return
    
    new_password = message.text
    logger.info(f"User {user_id} entering new password during first-time change")
    
    # Delete user's password message for security
    try:
        await message.delete()
    except Exception as e:
        logger.warning(f"Could not delete password message for user {user_id}: {e}")
    
    # Validate password
    is_valid, error = validate_password(new_password)
    if not is_valid:
        logger.warning(f"User {user_id} entered invalid password: {error}")
        cancel_kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Отмена")]],
            resize_keyboard=True
        )
        await message.answer(f"❌ {error}\n\nПопробуйте снова:", reply_markup=cancel_kb)
        return
    
    # Store new password in state and ask for confirmation
    await state.update_data(new_password=new_password)
    await state.set_state(AuthStates.waiting_confirm_password)
    logger.info(f"User {user_id} entered valid password, waiting for confirmation")
    await message.answer(
        f"Пароль: {new_password}\n\n"
        "Подтвердите новый пароль (введите его ещё раз):"
    )


@router.message(AuthStates.waiting_confirm_password)
async def process_confirm_password(message: Message, state: FSMContext):
    """Handle confirmation of new password."""
    user_id = message.from_user.id
    
    if message.text in ("Отмена", "Назад", "Назад в настройки"):
        await state.clear()
        await message.answer("Смена пароля отменена.")
        return
    
    # Delete user's password message for security
    try:
        await message.delete()
    except Exception as e:
        logger.warning(f"Could not delete password message for user {user_id}: {e}")
    
    data = await state.get_data()
    new_password = data.get("new_password")
    confirm = message.text
    logger.info(f"User {user_id} confirming password")
    
    if new_password != confirm:
        logger.warning(f"User {user_id} password confirmation mismatch")
        cancel_kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Отмена")]],
            resize_keyboard=True
        )
        await message.answer("❌ Пароли не совпадают. Попробуйте снова:", reply_markup=cancel_kb)
        await state.set_state(AuthStates.waiting_new_password)
        return
    
    # Change password
    logger.info(f"User {user_id} changing password now")
    success, msg = await change_password(user_id, new_password)
    
    if not success:
        logger.error(f"User {user_id} password change failed: {msg}")
        cancel_kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Отмена")]],
            resize_keyboard=True
        )
        await message.answer(f"❌ {msg}\n\nПопробуйте другой пароль:", reply_markup=cancel_kb)
        await state.set_state(AuthStates.waiting_new_password)
        return
    
    # Password changed successfully
    await authenticate_user(user_id)
    await state.clear()
    # Show appropriate keyboard based on role
    role = await get_user_role(user_id)
    if role == "admin" or user_id in settings.ADMINS:
        kb = admin_keyboard
        greet = "Пароль изменен. Админ-панель доступна."
    elif role == "curator" or user_id in settings.CURATORS:
        kb = curator_keyboard
        greet = "Пароль изменен. Панель куратора доступна."
    else:
        kb = student_keyboard
        greet = "Пароль изменен."
    logger.info(f"User {user_id} password changed successfully, sending keyboard")
    await message.answer(
        f"✅ {greet}\n\nНиже выберите действие:",
        reply_markup=kb
    )
    logger.info(f"User {user_id} changed password for first time, keyboard sent")


# Handler to start password change flow via menu buttons
# Supports both English and Russian button labels
@router.message(F.text == "Change Password")
@router.message(F.text == "Сменить пароль")
async def msg_change_password(message: Message, state: FSMContext):
    """Start password change flow (for users already authenticated)."""
    user_id = message.from_user.id
    
    # Check if authenticated
    if not await is_session_active(user_id):
        await require_authentication(user_id, message, state, "change password")
        return
    
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отмена")]],
        resize_keyboard=True
    )
    await state.set_state(ChangePasswordStates.waiting_current_password)
    await message.answer(
        "Введите ваш текущий пароль:",
        reply_markup=cancel_kb
    )


@router.message(ChangePasswordStates.waiting_current_password)
async def process_current_password(message: Message, state: FSMContext):
    """Verify current password before allowing change."""
    user_id = message.from_user.id
    
    if message.text in ("Отмена", "Назад", "Назад в настройки"):
        await state.clear()
        # Return to settings keyboard
        role = await get_user_role(user_id)
        if role == "admin" or user_id in settings.ADMINS:
            from bot.utils.keyboards import admin_settings_keyboard
            kb = admin_settings_keyboard
        else:
            from bot.utils.keyboards import curator_settings_keyboard
            kb = curator_settings_keyboard
        await message.answer("Отменено.", reply_markup=kb)
        return
    
    # Delete user's password message for security
    try:
        await message.delete()
    except Exception as e:
        logger.warning(f"Could not delete password message for user {user_id}: {e}")
    
    if not await verify_user_password(user_id, message.text):
        cancel_kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Отмена")]],
            resize_keyboard=True
        )
        await message.answer("❌ Неверный пароль. Попробуйте снова:", reply_markup=cancel_kb)
        return
    
    await state.set_state(ChangePasswordStates.waiting_new_password)
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отмена")]],
        resize_keyboard=True
    )
    await message.answer(
        "Введите новый пароль (8-128 символов, заглавные и строчные буквы, цифры, без пробелов):",
        reply_markup=cancel_kb
    )


@router.message(ChangePasswordStates.waiting_new_password)
async def process_password_change_new(message: Message, state: FSMContext):
    """Handle new password entry."""
    user_id = message.from_user.id
    
    if message.text in ("Отмена", "Назад", "Назад в настройки"):
        await state.clear()
        # Return to settings keyboard
        role = await get_user_role(user_id)
        if role == "admin" or user_id in settings.ADMINS:
            from bot.utils.keyboards import admin_settings_keyboard
            kb = admin_settings_keyboard
        else:
            from bot.utils.keyboards import curator_settings_keyboard
            kb = curator_settings_keyboard
        await message.answer("Отменено.", reply_markup=kb)
        return
    
    new_password = message.text
    
    # Delete user's password message for security
    try:
        await message.delete()
    except Exception as e:
        logger.warning(f"Could not delete password message for user {user_id}: {e}")
    
    # Validate password
    is_valid, error = validate_password(new_password)
    if not is_valid:
        cancel_kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Отмена")]],
            resize_keyboard=True
        )
        await message.answer(f"❌ {error}\n\nПопробуйте снова:", reply_markup=cancel_kb)
        return
    
    await state.update_data(new_password=new_password)
    await state.set_state(ChangePasswordStates.waiting_confirm_password)
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отмена")]],
        resize_keyboard=True
    )
    await message.answer(
        f"Пароль: {new_password}\n\n"
        "Подтвердите новый пароль:",
        reply_markup=cancel_kb
    )


@router.message(ChangePasswordStates.waiting_confirm_password)
async def process_password_change_confirm(message: Message, state: FSMContext):
    """Confirm and apply password change."""
    user_id = message.from_user.id
    
    if message.text in ("Отмена", "Назад", "Назад в настройки"):
        await state.clear()
        # Return to settings keyboard
        role = await get_user_role(user_id)
        if role == "admin" or user_id in settings.ADMINS:
            from bot.utils.keyboards import admin_settings_keyboard
            kb = admin_settings_keyboard
        else:
            from bot.utils.keyboards import curator_settings_keyboard
            kb = curator_settings_keyboard
        await message.answer("Отменено.", reply_markup=kb)
        return
    
    # Delete user's password message for security
    try:
        await message.delete()
    except Exception as e:
        logger.warning(f"Could not delete password message for user {user_id}: {e}")
    
    data = await state.get_data()
    new_password = data.get("new_password")
    
    if message.text != new_password:
        cancel_kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Отмена")]],
            resize_keyboard=True
        )
        await message.answer("❌ Пароли не совпадают. Попробуйте снова:", reply_markup=cancel_kb)
        await state.set_state(ChangePasswordStates.waiting_new_password)
        return
    
    # Check if user has 2FA enabled
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT two_fa_enabled, two_fa_secret FROM users WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
    
    if row and row[0]:  # 2FA is enabled
        # Store new password in FSM, request 2FA code
        await state.update_data(new_password=new_password)
        await state.set_state(ChangePasswordStates.waiting_2fa_code)
        cancel_kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Отмена")]],
            resize_keyboard=True
        )
        await message.answer(
            "🔐 У вас включена двухфакторная аутентификация.\n\n"
            "Введите 6-значный код из приложения-аутентификатора или резервный код для подтверждения смены пароля:",
            reply_markup=cancel_kb
        )
        return
    
    # No 2FA - proceed with password change
    success, msg = await change_password(user_id, new_password)
    
    if not success:
        cancel_kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Отмена")]],
            resize_keyboard=True
        )
        await message.answer(f"❌ {msg}\n\nПопробуйте другой пароль:", reply_markup=cancel_kb)
        await state.set_state(ChangePasswordStates.waiting_new_password)
        return
    
    await state.clear()
    
    # Return to settings keyboard
    role = await get_user_role(user_id)
    if role == "admin" or user_id in settings.ADMINS:
        from bot.utils.keyboards import admin_settings_keyboard
        kb = admin_settings_keyboard
    else:
        from bot.utils.keyboards import curator_settings_keyboard
        kb = curator_settings_keyboard
    
    await message.answer("✅ Пароль успешно изменен!", reply_markup=kb)
    logger.info(f"User {user_id} changed password")


@router.message(ChangePasswordStates.waiting_2fa_code)
async def process_password_change_2fa(message: Message, state: FSMContext):
    """Verify 2FA code before finalizing password change."""
    user_id = message.from_user.id
    
    if message.text in ("Отмена", "Назад", "Назад в настройки"):
        await state.clear()
        # Return to settings keyboard
        role = await get_user_role(user_id)
        if role == "admin" or user_id in settings.ADMINS:
            from bot.utils.keyboards import admin_settings_keyboard
            kb = admin_settings_keyboard
        else:
            from bot.utils.keyboards import curator_settings_keyboard
            kb = curator_settings_keyboard
        await message.answer("Отменено.", reply_markup=kb)
        return
    
    code = message.text.strip().replace(' ', '').replace('-', '')
    
    # Get user's 2FA secret and backup codes from DB
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT two_fa_secret, backup_codes FROM users WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
    
    if not row or not row[0]:
        await state.clear()
        return await message.answer("❌ Ошибка: 2FA не настроена. Попробуйте снова.")
    
    secret = row[0]
    backup_codes_json = row[1] or "[]"
    
    # Try to verify TOTP code
    is_valid_totp = verify_totp_code(secret, code)
    
    # Try to verify backup code
    is_valid_backup, remaining_codes = False, backup_codes_json
    if not is_valid_totp:
        is_valid_backup, remaining_codes = await verify_backup_code(user_id, code)
    
    if not is_valid_totp and not is_valid_backup:
        cancel_kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Отмена")]],
            resize_keyboard=True
        )
        await message.answer(
            "❌ Неверный код. Попробуйте ещё раз или используйте резервный код:",
            reply_markup=cancel_kb
        )
        return
    
    # 2FA verified - proceed with password change
    data = await state.get_data()
    new_password = data.get("new_password")
    
    success, msg = await change_password(user_id, new_password)
    
    if not success:
        cancel_kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Отмена")]],
            resize_keyboard=True
        )
        await message.answer(f"❌ {msg}\n\nПопробуйте другой пароль:", reply_markup=cancel_kb)
        await state.set_state(ChangePasswordStates.waiting_new_password)
        return
    
    await state.clear()
    
    # Return to settings keyboard
    role = await get_user_role(user_id)
    if role == "admin" or user_id in settings.ADMINS:
        from bot.utils.keyboards import admin_settings_keyboard
        kb = admin_settings_keyboard
    else:
        from bot.utils.keyboards import curator_settings_keyboard
        kb = curator_settings_keyboard
    
    await message.answer("✅ Пароль успешно изменен!", reply_markup=kb)
    logger.info(f"User {user_id} changed password with 2FA verification")
