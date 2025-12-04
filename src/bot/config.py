"""
main.py

2025 (C) Dmitrii Kudlenkov

Config bot file
"""

import os
from pathlib import Path

from dotenv import load_dotenv

env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)


class Settings:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN")
    API_KEY: str = os.getenv("API_KEY")
    BASE_URL: str = "https://api.mgkeit.space/api/v1"
    DB_PATH: str = os.getenv("DB_PATH", "instance/bot.db")
    SYNC_INTERVAL_MINUTES: int = int(os.getenv("SYNC_INTERVAL_MINUTES", "60"))
    REMINDER_DEFAULT_MINUTES: int = int(
        os.getenv("REMINDER_DEFAULT_MINUTES", "10")
    )
    # Comma-separated lists of user IDs in environment, e.g. "12345,67890"
    ADMINS: list = []
    CURATORS: list = []

    def __init__(self):
        admins_raw = os.getenv("ADMINS", "")
        curators_raw = os.getenv("CURATORS", "")
        try:
            self.ADMINS = [int(x) for x in admins_raw.split(",") if x.strip()]
        except Exception:
            self.ADMINS = []
        try:
            self.CURATORS = [
                int(x) for x in curators_raw.split(",") if x.strip()
            ]
        except Exception:
            self.CURATORS = []


settings = Settings()

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_KEY = os.getenv("API_KEY")
BASE_URL = os.getenv("BASE_URL")
SYNC_INTERVAL_MINUTES = int(os.getenv("SYNC_INTERVAL_MINUTES", 10))
