# Logging Configuration

## Overview
The bot uses Python's built-in `logging` module for comprehensive logging that works with **supervisor** for process management and auto-restart on failure.

### Log Files
- **Application logs:** `logs/bot.log` - Full debug information, rotated when reaches 10MB
- **Supervisor logs:** Configured via supervisor.conf for stdout/stderr capture

### Logging Features
- ✅ **Console output** — Visible during direct runs and under supervisor
- ✅ **File rotation** — Size-based rotation (10MB per file), keeps 7 backups
- ✅ **Structured format** — `[TIMESTAMP] LEVEL MODULE: MESSAGE`
- ✅ **Error tracking** — Full stack traces for exceptions
- ✅ **Job logging** — Sync, reminders, and scheduler events logged
- ✅ **Global error handler** — Catches unhandled handler errors, logs stack trace, sends user-friendly notice

### Log Levels & Policy
| Level | Meaning | Bot behavior |
|-------|---------|--------------|
| DEBUG | Diagnostic, detailed internals | Written to file only (`bot.log`). No impact on runtime. |
| INFO | Normal operation events | Printed to console and written to file. No impact on runtime. |
| WARNING | Potential issues, degraded state | Bot keeps running. No restart by default. Optional auto-restart on frequent warnings (see below). |
| ERROR | Errors handled by code | Global error handler logs stack trace and continues. Process does not crash. |
| CRITICAL | Fatal conditions | Logged as critical. May exit process to trigger supervisor restart. |

### Sample Log Output
```
[2025-12-12 15:50:26] INFO     mgkeit_bot: ============================================================
[2025-12-12 15:50:26] INFO     mgkeit_bot: MGKEIT Pair Alert Bot - Logging initialized
[2025-12-12 15:50:26] INFO     mgkeit_bot: Log file: ./logs/bot.log
[2025-12-12 15:50:26] INFO     mgkeit_bot: Database initialized successfully
[2025-12-12 15:50:26] INFO     mgkeit_bot: Bot initialized: 1234567890...
[2025-12-12 15:50:26] INFO     mgkeit_bot: All routers included
[2025-12-12 15:50:26] INFO     mgkeit_bot: Setting up scheduler jobs...
[2025-12-12 15:50:26] INFO     mgkeit_bot: Added sync job (interval: 60 minutes)
[2025-12-12 15:50:26] INFO     mgkeit_bot: Added reminder job (interval: 1 minute)
[2025-12-12 15:50:26] INFO     mgkeit_bot: Scheduler started
[2025-12-12 15:50:26] INFO     mgkeit_bot: MGKEIT Pair Alert started successfully!
```

## Error Handling

- `global_error_handler` (`src/bot/main.py`) logs any unhandled exception from handlers with a stack trace and sends a generic error message back to the user/callback.
- Scheduler jobs in `src/bot/scheduler/tasks.py` log start/end, warnings for missing data, and network failures; failures still keep the process alive (supervisor handles restarts on crash).

## Supervisor Integration

### Installation
```bash
sudo apt-get install supervisor
```

### Configuration
1. Copy `supervisor.conf` to supervisor directory:
   ```bash
   sudo cp supervisor.conf /etc/supervisor/conf.d/mgkeit-bot.conf
   ```

2. Edit the paths in the config:
   - Replace `/path/to/venv/bin/python` with actual venv path
   - Replace `/path/to/MGKEIT-Pair-Alert` with actual project path

3. Reload supervisor:
   ```bash
   sudo supervisorctl reread
   sudo supervisorctl update
   ```

4. Start the bot:
   ```bash
   sudo supervisorctl start mgkeit-bot
   ```

### Monitor the Bot
```bash
# Check status
sudo supervisorctl status mgkeit-bot

# View logs
tail -f /path/to/MGKEIT-Pair-Alert/logs/bot.log
tail -f /path/to/MGKEIT-Pair-Alert/logs/supervisor_stdout.log

# Restart manually if needed
sudo supervisorctl restart mgkeit-bot
```

### Auto-Restart on Failure
When configured with supervisor, the bot will:
- ✅ Automatically restart if the process crashes
- ✅ Wait 10 seconds before restart to avoid rapid restart loops
- ✅ Keep running indefinitely with auto-restart enabled
- ✅ Log all activity to files with rotation

### Optional: Restart on Frequent Warnings
You can enable an automatic restart if too many WARNING events occur in a short time window (useful when warnings indicate a degraded state).

Enable via environment variables:

```bash
# Enable warning watchdog
WARNING_RESTART_ENABLED=1

# Number of WARNINGs within the window to trigger restart
WARNING_RESTART_THRESHOLD=20

# Sliding window duration in seconds (default 600 = 10 minutes)
WARNING_RESTART_WINDOW_SECONDS=600
```

How it works:
- The logger tracks WARNING events within the configured sliding window.
- If the count exceeds the threshold, it logs a CRITICAL message and exits with code 70.
- Supervisor with `autorestart=true` will restart the bot.

Note: a single WARNING does not trigger a restart. Only sustained bursts of warnings do.

## Logger Module

The logger is implemented in `src/bot/utils/logger.py`:
- Configured at startup automatically
- Console output at INFO level for visibility
- File output at DEBUG level for troubleshooting
- Handlers: FileHandler (RotatingFileHandler) + StreamHandler
- Optional handler: Warning‑restart watchdog (controlled by env vars, see above)

## Troubleshooting

### Logs not appearing
1. Check permissions on `logs/` directory
2. Verify logger is imported: `from bot.utils.logger import logger`
3. Check file system has space

### Supervisor not restarting the bot
1. Check `autostart=true` and `autorestart=true` in config
2. Verify command path is correct
3. Check supervisor logs: `/var/log/supervisor/supervisord.log`

### Log files growing too large
- File rotation is automatic at 10MB
- Keeps last 7 backups
- Adjust `maxBytes` and `backupCount` in `logger.py` if needed
