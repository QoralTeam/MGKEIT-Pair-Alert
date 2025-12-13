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
        # Support both singular and plural env var names for convenience.
        admins_raw = os.getenv("ADMINS") or os.getenv("ADMIN") or ""
        curators_raw = os.getenv("CURATORS") or os.getenv("CURATOR") or ""

        def _parse_ids(raw: str) -> list:
            if not raw:
                return []
            # normalize separators to commas, accept spaces/semicolons/newlines
            cleaned = raw.replace("\n", ",").replace(";", ",").replace(" ", ",")
            parts = [p.strip() for p in cleaned.split(",")]
            res = []
            for p in parts:
                if not p:
                    continue
                try:
                    res.append(int(p))
                except Exception:
                    # ignore non-integer values
                    continue
            return res

        self.ADMINS = _parse_ids(admins_raw)
        self.CURATORS = _parse_ids(curators_raw)
        # Synchronization enabled flag (accepts 'True'/'False', case-insensitive)
        sync_raw = os.getenv("SYNCHRONIZATION") or os.getenv("synchronization")
        if sync_raw is None:
            self.SYNCHRONIZATION = True
        else:
            self.SYNCHRONIZATION = str(sync_raw).strip().lower() in ("1", "true", "yes", "on")


settings = Settings()

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_KEY = os.getenv("API_KEY")
BASE_URL = os.getenv("BASE_URL")
SYNC_INTERVAL_MINUTES = int(os.getenv("SYNC_INTERVAL_MINUTES", 10))
