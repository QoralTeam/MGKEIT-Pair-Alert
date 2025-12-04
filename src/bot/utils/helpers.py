from datetime import datetime


def is_even_week(date: datetime | None = None) -> bool:
    if date is None:
        date = datetime.now()
    return date.isocalendar().week % 2 == 0


def format_pair_reminder(pair: dict, minutes_before: int) -> str:
    return (
        f"Через {minutes_before} мин — {pair['pair_number']} пара\n"
        f"{pair['subject']}\n"
        f"{pair.get('teacher', '—')} • {pair.get('room', '—')}"
    )
