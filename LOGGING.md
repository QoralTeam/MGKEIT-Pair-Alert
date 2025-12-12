# Logging Configuration

## Overview
The bot uses Python's built-in `logging` module for comprehensive logging that works with **supervisor** for process management and auto-restart on failure.

### Log Files
- **Application logs:** `logs/bot.log` - Full debug information, rotated when reaches 10MB
- **Supervisor logs:** Configured via supervisor.conf for stdout/stderr capture

### Logging Features
- ✅ **Console output** - Visible during direct runs and supervisor
- ✅ **File rotation** - Automatic daily rotation, keeps 7 backups
- ✅ **Structured format** - `[TIMESTAMP] LEVEL MODULE: MESSAGE`
- ✅ **Error tracking** - Full stack traces for exceptions
- ✅ **Job logging** - Sync, reminders, and scheduler events logged

### Log Levels
| Level | Color | Usage |
|-------|-------|-------|
| DEBUG | - | Detailed diagnostic info (low frequency) |
| INFO | - | General informational messages (normal operation) |
| WARNING | - | Warning messages (potential issues) |
| ERROR | - | Error events with stack trace (failures) |

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
[2025-12-12 15:50:26] INFO     mgkeit_bot: MGKEIT Pair Alert успешно запущен!
```

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

## Logger Module

The logger is implemented in `src/bot/utils/logger.py`:
- Configured at startup automatically
- Console output at INFO level for visibility
- File output at DEBUG level for troubleshooting
- Handlers: FileHandler (RotatingFileHandler) + StreamHandler

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
