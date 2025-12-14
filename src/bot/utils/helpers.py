from datetime import datetime

# All existing groups organized by campus
ALL_GROUPS = {
    "Миллионщикова": [
        "1ВР-1-25", "1ВР-2-25", "1И-1-11-25", "1ИП-1-25 (п)", "1ИП-2-25 (п)", "1ИП-3-25 (п)", 
        "1ИП-4-25 (п)", "1ИП-5-25 (п)", "1ИП-6-25 (п)", "1ИП-7-25 (п)", "1ИП-8-25 (п)", 
        "1ИП-9-25 (п)", "1ИП-19-25 (п)", "1ИП-1-11-25 (п)", "1РКИ-1-25", "1РКИ-2-25", "1РКИ-3-25",
        "2И-1-24", "2И-2-24", "2И-3-24", "2И-4-24", "2И-5-24", "2И-6-24", "2И-7-24", "2И-8-24", 
        "2И-11-24", "2ИП-1-24 (пр)", "2ИП-2-24 (пр)", "2ИП-3-24 (сис)", "2ИП-4-24 (сис)", 
        "2ИП-5-24 (веб)", "2ИП-6-24 (веб)", "2ИП-7-24 (пр)", "2ИП-8-24 (пр)", "2ИП-9-24 (пр)", 
        "2ИП-10-24 (пр)", "2ИП-11-24 (пр)", "2ИП-12-24 (пр)", "2ИП-13-24 (пр)", "2ИП-1-11-24", 
        "2ИП-2-11-24", "3И-1-23", "3И-2-23", "3И-3-23", "3И-4-23", "3И-11-23", "3ИП-1-23 (пр)", 
        "3ИП-2-23 (пр)", "3ИП-3-23 (сис)", "3ИП-4-23 (веб)", "3ИП-5-23 (веб)", "3ИП-1-11-23 (пр)", 
        "3ИП-2-11-23 (веб)", "3ИП-3-11-23 (сис)", "4И-1-22", "4И-2-22", "4И-3-22", "4ИП-1-22", 
        "4ИП-2-22", "4ИП-3-22"
    ],
    "Коломенская": [
        "1ГД-1-11-25", "1ГД-2-11-25", "2ГД-1-24", "2ГД-2-24", "2ГД-3-24", "2ГД-4-24", "2ГД-5-24", 
        "2ГД-6-24", "2ГД-7-24", "2ГД-8-24", "2ГД-9-24", "2ГД-10-24", "2ГД-11-24", "2ГД-12-24", 
        "2ГД-13-24", "2ГД-14-24", "2ГД-1-11-24", "2ГД-2-11-24", "2ГД-3-11-24", "3ГД-1-23", 
        "3ГД-2-23", "3ГД-3-23", "3ГД-4-23", "4ГД-1-22", "4ГД-2-22", "4ГД-3-22"
    ],
    "Судостроительная": [
        "1ИС-1-25", "1КС-1-25", "1КС-2-25", "1КС-1-11-25", "1МТ-1-25", "1МТ-2-25", "1СА-1-25", 
        "1СА-2-25", "1СА-3-25", "1СА-4-25", "1СА-5-25", "2КС-1-24", "2КС-2-24", "2КС-3-24", 
        "2КС-11-24", "2СА-1-24", "2СА-2-24", "2СА-3-24", "2СА-11-24", "2ЭМ-24", "2ЭО-1-24", 
        "2ЭО-2-24", "2ЭО-3-24", "3КС-1-23", "3КС-2-23", "3Р-1-23", "3Р-2-23", "3Р-3-23", 
        "3Р-4-23", "3СА-1-23", "3СА-2-23", "3СА-11-23", "3ЭМ-1-23", "3ЭМ-2-23", "4КС-22", 
        "4Р-1-22", "4Р-2-22", "4СА-1-22", "4СА-2-22", "4ЭК-22"
    ],
    "Бирюлёво": [
        "1ГД-1-25", "1ГД-2-25", "1ГД-3-25", "1ГД-4-25", "1ГД-5-25", "1ГД-6-25", "1ГД-7-25", 
        "1ГД-8-25", "1ГД-9-25", "1ГД-10-25", "1ГД-11-25", "1ГД-12-25", "1ГД-13-25", "1ГД-14-25", 
        "1И-1-25", "1И-2-25", "1И-3-25", "1И-4-25", "1И-5-25", "1И-6-25", "1ИП-10-25 (п)", 
        "1ИП-11-25 (п)", "1ИП-12-25 (п)", "1ИП-13-25 (п)", "1ИП-14-25 (п)", "1ИП-15-25 (п)", 
        "1ИП-16-25 (п)", "1ИП-17-25 (п)", "1ИП-18-25 (п)"
    ],
    "Очно-заочные": [
        "1ОЗИП-1-11-25", "4ЗКС-22", "5ЗКС-21,4ЗКС-11-22"
    ],
    "ЭВМ": [
        "1-ЭВМ-1-25", "1-ЭВМ-2-25"
    ]
}


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


def get_campus_selection_keyboard():
    """Generate inline keyboard for campus selection."""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    
    buttons = []
    for campus in ALL_GROUPS.keys():
        buttons.append([InlineKeyboardButton(text=campus, callback_data=f"campus:{campus}")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_group_selection_keyboard(campus: str, page: int = 0, page_size: int = 10):
    """Generate inline keyboard for group selection with pagination."""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    
    groups = ALL_GROUPS.get(campus, [])
    total = len(groups)
    start = page * page_size
    end = min(start + page_size, total)
    
    buttons = []
    for group in groups[start:end]:
        buttons.append([InlineKeyboardButton(text=group, callback_data=f"group:{group}")])
    
    # Pagination buttons
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"page:{campus}:{page-1}"))
    if end < total:
        nav.append(InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"page:{campus}:{page+1}"))
    
    if nav:
        buttons.append(nav)
    
    # Back to campus selection
    buttons.append([InlineKeyboardButton(text="↩️ К выбору кампуса", callback_data="select_campus")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)
