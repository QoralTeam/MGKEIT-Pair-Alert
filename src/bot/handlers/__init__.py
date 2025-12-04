from .reminders import router as reminders_router
from .schedule import router as schedule_router
from .settings import router as settings_router
from .start import router as start_router

__all__ = [
    "start_router",
    "settings_router",
    "schedule_router",
    "reminders_router",
]
