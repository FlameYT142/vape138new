from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from bot.texts import START_TEXT
from bot.keyboards import start_kb
from bot.models import count_warns
from bot.config import role_label, role_level

router = Router()

@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(START_TEXT, reply_markup=start_kb())

@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "📋 <b>Команды:</b>\n"
        ".мут @user 1.1 — мут по правилу\n"
        ".мут @user навсегда 1.1 — вечный мут\n"
        ".мут @user причина — заявка\n"
        ".размут @user — снять ограничения\n"
        ".кик @user причина — кик\n"
        ".варн @user причина — варн\n"
        ".варны @user — варны пользователя\n"
        ".профиль — мой статус"
    )

@router.message(lambda m: m.text and m.text.split()[0].lower().lstrip("./") in ("профиль", "me"))
async def cmd_profile(message: Message, db_user):
    warns = await count_warns(message.from_user.id)
    role = db_user["role"]
    await message.answer(
        f"👤 <b>@{message.from_user.username or message.from_user.id}</b>\n"
        f"🏷 Статус: {role_label(role)} [{role_level(role)}]\n"
        f"⚠️ Активных варнов: {warns}/3"
    )