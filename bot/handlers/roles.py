from aiogram import Router, Bot
from aiogram.types import Message
from bot.config import (role_level, role_label, is_tech_admin,
                         OWNER_ONLY_TARGETS, LOG_CHAT_ID, ROLES)
from bot.models import set_user_role, get_user
from bot.texts import *

router = Router()

def find_role_key(name):
    name = name.lower().strip()
    for key, meta in ROLES.items():
        if key == name or meta["label"].lower() == name:
            return key
    return None

async def resolve_target(message: Message, bot: Bot, raw_target: str):
    if raw_target.isdigit():
        target_id = int(raw_target)
        row = await get_user(target_id)
        return target_id, str(target_id), row["role"]

    if raw_target.startswith("@"):
        uname = raw_target.lstrip("@")
        from bot.db import fetchone
        row = await fetchone("SELECT * FROM users WHERE username=?", (uname,))
        if row:
            return row["telegram_id"], row["username"], row["role"]
        try:
            m = await bot.get_chat_member(message.chat.id, f"@{uname}")
            return m.user.id, m.user.username or str(m.user.id), "member"
        except Exception:
            pass

    return None, None, None

@router.message(lambda m: m.text and m.text.split()[0].lower().lstrip("./") in ("выдать", "setrole"))
async def cmd_grant(message: Message, bot: Bot, db_user):
    if message.chat.type != "private":
        return await message.reply(ERR_DM_ONLY)
    
    # Разбиваем текст ровно на 3 части: команда, цель, роль
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        return await message.reply(ERR_ARGS)
    
    target_raw = parts[1]
    role_text = parts[2]
    
    target_id, target_username, target_role = await resolve_target(message, bot, target_raw)
    if target_id is None:
        return await message.reply("❌ Пользователь не найден. Введите его ID (цифры) или напишите ему /start в боте.")
        
    role_key = find_role_key(role_text)
    if not role_key:
        return await message.reply("❌ Неизвестная роль. Проверьте название.")
        
    actor = db_user
    actor_id = actor["telegram_id"]
    tech = is_tech_admin(actor_id)
    
    if tech and role_key in OWNER_ONLY_TARGETS:
        return await message.reply(ERR_NO_RIGHTS)
    if not tech and role_level(actor["role"]) <= role_level(role_key):
        return await message.reply(ERR_NO_RIGHTS)
    if role_key in ("blat", "partner") and not tech and actor["role"] not in ("owner", "deputy_owner"):
        return await message.reply(ERR_NO_RIGHTS)
    if role_key == "vip" and not tech and role_level(actor["role"]) < role_level("deputy_head"):
        return await message.reply(ERR_NO_RIGHTS)
            
    await set_user_role(target_id, role_key)
    await message.answer(role_grant(target_username, role_label(role_key), role_level(role_key), actor["username"]))
    await bot.send_message(LOG_CHAT_ID,
        f"👑 ВЫДАЧА РОЛИ\nКто: @{actor['username']}\nКому: {target_username}\nРоль: {role_label(role_key)}")

@router.message(lambda m: m.text and m.text.split()[0].lower().lstrip("./") in ("разжаловать", "demote"))
async def cmd_demote(message: Message, bot: Bot, db_user):
    if message.chat.type != "private":
        return await message.reply(ERR_DM_ONLY)
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.reply(ERR_ARGS)
        
    target_id, target_username, _ = await resolve_target(message, bot, parts[1])
    if target_id is None:
        return await message.reply("❌ Пользователь не найден.")
        
    target = await get_user(target_id)
    actor = db_user
    tech = is_tech_admin(actor["telegram_id"])
    if tech and target["role"] in OWNER_ONLY_TARGETS:
        return await message.reply(ERR_NO_RIGHTS)
    if not tech and role_level(actor["role"]) <= role_level(target["role"]):
        return await message.reply(ERR_NO_RIGHTS)
    if target["role"] == "owner":
        return await message.reply(ERR_OWNER_IMMUNE)
        
    await set_user_role(target_id, "member")
    user_after = await get_user(target_id)
    await message.answer(role_demote(target_username, role_label(user_after["role"]), role_level(user_after["role"])))
    await bot.send_message(LOG_CHAT_ID,
        f"⬇️ РАЗЖАЛОВАНИЕ\nКто: @{actor['username']}\nКого: {target_username}\nНовая роль: {role_label(user_after['role'])}")

@router.message(lambda m: m.text and m.text.split()[0].lower().lstrip("./") in ("админы", "staff"))
async def cmd_list_staff(message: Message, db_user):
    if role_level(db_user["role"]) < role_level("trainee"):
        return await message.reply(ERR_NO_RIGHTS)
        
    from bot.models import get_all_staff
    staff = await get_all_staff()
    
    if not staff:
        return await message.answer("📋 В базе нет администраторов.")
        
    lines = ["👑 <b>Администрация барахолки</b>\n"]
    current_role = None
    
    for user in staff:
        role = user["role"]
        if role != current_role:
            current_role = role
            lines.append(f"\n<b>{role_label(role)}:</b>")
            
        name = f"@{user['username']}" if user["username"] else f"ID: {user['telegram_id']}"
        lines.append(f"• {name}")
        
    text = "\n".join(lines)
    if len(text) > 4000:
        await message.answer(text[:4000])
        await message.answer(text[4000:])
    else:
        await message.answer(text)
