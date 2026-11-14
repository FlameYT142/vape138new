from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def rules_kb(page, total_pages):
    row = []
    if page > 0:
        row.append(InlineKeyboardButton(text="◀️", callback_data=f"rules_page:{page-1}"))
    row.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        row.append(InlineKeyboardButton(text="▶️", callback_data=f"rules_page:{page+1}"))
    return InlineKeyboardMarkup(inline_keyboard=[row])

def appeal_kb(app_id):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Разрешить", callback_data=f"app_approve:{app_id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"app_reject:{app_id}"),
    ]])

def start_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📋 Правила", callback_data="show_rules")
    ]])