# Quick Start: Authentication System

## Installation

```powershell
pip install -r requirements/prod.txt
```

## First Admin Login

1. Start bot: `python src/bot/main.py`
2. Send `/admin` command
3. Enter default password: `admin`
4. System forces password change
5. Enter new secure password (8+ chars, uppercase, lowercase, digit, symbols)
6. Confirm new password
7. (Optional) Enable 2FA in settings → scan QR, confirm code, save backup codes (message auto-deletes after 2 minutes)
8. ✅ Session active for 2 minutes of inactivity

## Key Commands

- `/admin` - Open admin panel (requires password)
- `/changepassword` - Change your password (asks 2FA code if enabled)
- `/start` - Register/update your profile

## Password Requirements

✅ 8-128 characters
✅ Uppercase + lowercase + digit
✅ Allowed symbols: `~!?@#$%^&*_-+()[]{}<>/\|"'.,;:`
✅ No spaces
✅ Cannot reuse last 8 passwords

## Default Passwords

- **Admin**: `admin`
- **Curator**: `curator`

Automatically set when role is assigned; must be changed on first login.

## Session Behavior

- Like `sudo` on Linux
- **Timeout**: 2 minutes of inactivity (enforced by middleware)
- After timeout, password required again (keyboard removed)
- Multiple actions within 2 minutes don't require re-authentication
- Session resets after password change

## Protected Admin Functions

All require active session:
- Админ-панель (Admin panel)
- Сменить роль (Change role)
- Показать роли (Show roles)
- Синхронизация (Sync)
- Добавить замену (Add replacement)
- Статистика (Statistics)
- And all other admin functions

## Troubleshooting

**"Import bcrypt could not be resolved"**
```powershell
pip install -r requirements/prod.txt
```

**Session expires too fast?**
Edit `SESSION_TIMEOUT_SECONDS` in `src/bot/utils/session_manager.py`

**Forgot password?**
Contact another admin to reset via database or wait for password reset command implementation.

## Files Modified/Created

**New Files:**
- `src/bot/utils/password_manager.py` - Password validation and hashing
- `src/bot/utils/session_manager.py` - Session timeout tracking
- `src/bot/utils/two_fa.py` - TOTP + backup codes utilities
- `src/bot/handlers/auth.py` - Authentication FSM handlers
- `src/bot/handlers/two_fa.py` - 2FA enable/disable flow
- `AUTHENTICATION.md` - Full documentation

**Modified Files:**
- `src/bot/db/db.py` - Database schema + migrations (2FA columns, lunch times)
- `src/bot/handlers/admin.py` - Auth/session checks, direct messaging, broadcasts
- `src/bot/handlers/curator.py` - Direct messaging, group broadcast, links
- `src/bot/handlers/settings.py` - Reminder/time settings
- `src/bot/main.py` - Registered two_fa_router and middleware
- `src/bot/utils/keyboards.py` - Buttons for 2FA, direct messaging
- `requirements/prod.txt` - Added bcrypt, pyotp, qrcode, pillow

## Testing Quick List

```powershell
# 1. Install dependencies
pip install -r requirements/prod.txt

# 2. Start bot
python src/bot/main.py

# 3. Test authentication + 2FA flow
# - Send /admin
# - Enter "admin"
# - Change password
# - Enable 2FA: scan QR, enter code, save backup codes (message auto-deletes in 2 minutes)
# - Re-login: password → TOTP/backup code when 2FA enabled
# - Verify session timeout after 2 minutes of inactivity
# - Test /changepassword (prompts 2FA if enabled)

# 4. Check logs
# Look for "ALTER TABLE" migrations on first startup
```

## What's Next?

**Pending Implementation:**
- Password reset command for admins

**Ready for Production:**
✅ Password protection
✅ Session management
✅ Mandatory password changes
✅ Password history tracking
✅ TOTP 2FA with QR + backup codes (auto-deleted messages)
✅ All admin/curator functions protected by session/2FA

See `AUTHENTICATION.md` for full documentation.
