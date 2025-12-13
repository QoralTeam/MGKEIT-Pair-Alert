# Authentication System Documentation

## Overview

Password-based authentication for admin and curator roles with enforced password policies, 2-minute sudo-style sessions, and TOTP-based 2FA with QR + one-time backup codes.

## Components

- **Password management** (`src/bot/utils/password_manager.py`): bcrypt hashing; validation (8-128 chars, upper/lower/digit, allowed symbols `~!?@#$%^&*_-+()[]{}<>/\|"'.,;:`, no spaces); history check (last 8); default passwords (`admin`, `curator`) on role change; forced first change.
- **Session management** (`src/bot/utils/session_manager.py`): 2-minute inactivity window stored in DB; refreshed by `SessionActivityMiddleware`; reset on password change.
- **2FA** (`src/bot/utils/two_fa.py`, `src/bot/handlers/two_fa.py`): TOTP secret + QR; 6-digit verification; 10 hashed backup codes (one-time); QR/backup messages auto-delete after 2 minutes; disable flow requires password + current code/backup.
- **Auth handlers** (`src/bot/handlers/auth.py`): login = password -> 2FA (if enabled) -> forced password change when default detected; `/changepassword` validates current password and 2FA when enabled.
- **DB schema** (`src/bot/db/db.py`): `hashed_password`, `password_changed`, `password_history`, `two_fa_enabled`, `two_fa_secret`, `backup_codes`, `last_auth_time`; migrations run on startup and are additive/safe.

## Flows

### Login / Re-auth
1) User taps protected action (e.g., `/admin`).
2) If session active (<2 minutes idle) -> proceed; otherwise prompt for password.
3) Password accepted -> if `two_fa_enabled=1`, prompt for TOTP/backup code (backup removal persisted).
4) If default password is still stored, user must change it before any action.
5) On success, session timestamp updates; 2-minute window applies to all protected actions.

### First-time password change
- Triggered automatically when a default password is detected during login.
- Validates requirements, confirms twice, then stores hash and updates history (last 8).

### `/changepassword`
- Requires active session; asks current password, then new + confirm.
- If 2FA is enabled, final step requires TOTP or backup code before applying change.

### Enable 2FA (admins/curators)
1) Settings -> `Настройка 2FA` -> `Включить 2FA`.
2) Secret generated, QR shown (with plaintext secret); message scheduled for deletion in 2 minutes.
3) User enters 6-digit code to confirm.
4) Bot saves `two_fa_secret`, `backup_codes` (hashed), flags `two_fa_enabled=1`.
5) Backup codes message sent and auto-deleted after 2 minutes; codes are one-time.

### Disable 2FA
- Requires password, then current TOTP or backup code; clears secret/codes and `two_fa_enabled`.

## Protected Areas

- Admin panel, role change, roles listing, sync, broadcasts, replacements, pair links, lunch time changes, stats, direct messaging, and other admin buttons are guarded by `require_authentication` (password/2FA + active session).
- Curator settings/actions use the same session guard.

## Installation

```powershell
pip install -r requirements/prod.txt
```

Installs bcrypt, pyotp, qrcode, pillow, and other bot dependencies.

## Configuration

- Session timeout is hardcoded to `SESSION_TIMEOUT = 120` seconds (`src/bot/utils/session_manager.py`).
- No env vars are needed for auth/2FA; admins/curators parsed from `.env` get default passwords on startup.

## Troubleshooting

- **Import bcrypt/pyotp/qrcode/pillow issues:** reinstall deps with `pip install -r requirements/prod.txt`.
- **Session expires too fast:** increase `SESSION_TIMEOUT`.
- **Forgot password:** currently requires manual DB reset; password reset command is a future item.
- **2FA messages gone:** QR/backup messages auto-delete after 2 minutes by design; restart setup to regenerate.

## Testing Checklist

- [ ] Run migrations implicitly by starting the bot; ensure ALTER statements log once.
- [ ] First-time login: default password -> force change -> session active 2 minutes.
- [ ] Session timeout: wait >2 minutes, confirm re-auth prompt; within 2 minutes no prompt.
- [ ] Password validation rejects weak inputs and prevents reuse of last 8.
- [ ] `/changepassword` succeeds with correct current password; rejects wrong current.
- [ ] Enable 2FA: QR displayed, code required, backup codes shown then auto-deleted; backup count decrements on use.
- [ ] Login with 2FA: password -> TOTP -> access; backup code works once and is removed.
- [ ] Disable 2FA: password + code/backup required; flags cleared.
- [ ] Admin/curator buttons require active session; students remain unaffected.

## Ready Status / Next Steps

- Ready: strong passwords + history, 2-minute sessions, TOTP 2FA with QR/backup codes, guarded admin/curator flows, safe DB migrations.
- Next: admin-triggered password reset flow (not yet implemented).
