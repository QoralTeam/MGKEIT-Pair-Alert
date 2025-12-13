"""Logging configuration for the bot.

Setup logging with both file and console handlers.
File logs are rotated by size (10MB) and up to 7 backups are kept.
Console output goes to stdout (supervisor-friendly).
"""

import logging
import logging.handlers
import os
import time
from collections import deque
from pathlib import Path

# Ensure logs directory exists
# Use absolute path from project root
LOGS_DIR = Path(__file__).parent.parent.parent / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Main application logger
logger = logging.getLogger("mgkeit_bot")
logger.setLevel(logging.DEBUG)

# Remove any existing handlers to avoid duplicates
logger.handlers.clear()

# Formatter
formatter = logging.Formatter(
    "[%(asctime)s] %(levelname)-8s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# File handler with rotation (daily, 7 days retention)
log_file = LOGS_DIR / "bot.log"
file_handler = logging.handlers.RotatingFileHandler(
    log_file,
    maxBytes=10 * 1024 * 1024,  # 10 MB per file
    backupCount=7,  # Keep up to 7 backup files
)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Console handler for supervisor output
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# Log startup
logger.info("=" * 60)
logger.info("MGKEIT Pair Alert Bot - Logging initialized")
logger.info(f"Log file: {log_file}")
logger.info("=" * 60)
