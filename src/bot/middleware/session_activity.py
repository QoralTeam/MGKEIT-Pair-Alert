"""Middleware to update session activity and expire idle admin/curator sessions."""

from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove

from bot.db.db import get_user_role
from bot.utils.session_manager import (
    update_activity,
    is_session_active,
    invalidate_session,
)
from bot.config import settings
from bot.handlers.auth import AuthStates


class SessionActivityMiddleware(BaseMiddleware):
    """Update last_auth_time for admins/curators on every message to keep session alive."""
    
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        # Get user_id from event
        if isinstance(event, Message):
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
        else:
            return await handler(event, data)
        
        # Check if user is admin or curator
        role = await get_user_role(user_id)
        is_admin = role == "admin" or user_id in settings.ADMINS
        is_curator = role == "curator" or user_id in settings.CURATORS

        # Shortcut if not privileged user
        if not (is_admin or is_curator):
            return await handler(event, data)

        state = data.get("state")
        current_state = await state.get_state() if state else None

        # Allow ongoing auth flow to proceed without refreshing session
        auth_states = {
            AuthStates.waiting_password.state,
            AuthStates.waiting_2fa_code.state,
            AuthStates.waiting_new_password.state,
            AuthStates.waiting_confirm_password.state,
        }
        if current_state in auth_states:
            return await handler(event, data)

        # If session still active, refresh and continue
        if await is_session_active(user_id):
            await update_activity(user_id)
            return await handler(event, data)

        # Session expired: invalidate, remove keyboard, prompt re-auth
        await invalidate_session(user_id)

        # Send expiration notice and strip reply keyboard
        reply_kwargs = {"reply_markup": ReplyKeyboardRemove()}
        try:
            if isinstance(event, Message):
                await event.answer("Сессия окончена. Чтобы войти введите пароль:", **reply_kwargs)
            elif isinstance(event, CallbackQuery):
                if event.message:
                    await event.message.answer("Сессия окончена. Чтобы войти введите пароль:", **reply_kwargs)
                await event.answer()
        except Exception:
            # Best-effort; continue
            pass

        # Put user into auth waiting state so next message is treated as password
        if state:
            try:
                await state.set_state(AuthStates.waiting_password)
            except Exception:
                pass

        # Stop further handler processing while unauthenticated
        return None
