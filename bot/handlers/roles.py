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

async def resolve_target_username(message: Message, bot: Bot, args):
    if message.reply_to_message and message.reply_to_message.from_user:
        u = message.reply_to_message.from_user
        return u.id, u.username or str(u.id), args
    if not args or not args[0].startswith("@"):
        return None, None, args
    uname = args[0].lstrip("@")
    try:
        m = await bot.get_chat_member(message.chat.id, f"@{uname}")
        return m.user.id, m.user.username or str(m.user.id), args[1:]
    except Exception:
        return None, None, args

@router.message(lambda m: m.text and m.text.split()[0].lower().lstrip("./") in ("выдать", "setrole"))
async def cmd_grant(message: Message, bot: Bot, db_user):
    if message.chat.type != "private":
        return await message.reply(ERR_DM_ONLY)
    args = message.text.split()[1:]
    target_id, target_username, rest = await resolve_target_username(message, bot, args)
    if target_id is None or not rest:
        return await message.reply(ERR_ARGS)
    role_key = find_role_key(" ".join(rest))
    if not role_key:
        return await message.reply("❌ Неизвестная роль.")
    actor = db_user
    actor_id = actor["telegram_id"]
    actor_role = actor["role"]
    tech = is_tech_admin(actor_id)
    if tech and role_key in OWNER_ONLY_TARGETS:
        return await message.reply(ERR_NO_RIGHTS)
    need_level = role_level(role_key)
    actor_lvl = role_level(actor_role)
    if not tech and actor_lvl <= need_level:
        return await message.reply(ERR_NO_RIGHTS)
    if role_key in ("blat", "partner"):
        if not tech and actor_role not in ("owner", "deputy_owner"):
            return await message.reply(ERR_NO_RIGHTS)
    if role_key == "vip":
        if not tech and actor_lvl < role_level("deputy_head"):
            return await message.reply(ERR_NO_RIGHTS)
    await set_user_role(target_id, role_key)
    await message.answer(role_grant(target_username, role_label(role_key), role_level(role_key), actor["username"]))
    await bot.send_message(LOG_CHAT_ID,
        f"👑 ВЫДАЧА РОЛИ\nКто: @{actor['username']}\nКому: @{target_username}\nРоль: {role_label(role_key)}")

@router.message(lambda m: m.text and m.text.split()[0].lower().lstrip("./") in ("разжаловать", "demote"))
async def cmd_demote(message: Message, bot: Bot, db_user):
    if message.chat.type != "private":
        return await message.reply(ERR_DM_ONLY)
    args = message.text.split()[1:]
    target_id, target_username, _ = await resolve_target_username(message, bot, args)
    if target_id is None:
        return await message.reply(ERR_ARGS)
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
        f"⬇️ РАЗЖАЛОВАНИЕ\nКто: @{actor['username']}\nКого: @{target_username}\nНовая роль: {role_label(user_after['role'])}")

@router.message(lambda m: m.text and m.text.split()[0].lower().lstrip("./") in ("разбан", "unban"))
async def cmd_unban(message: Message, bot: Bot, db_user):
    if role_level(db_user["role"]) < role_level("deputy_head") and not is_tech_admin(db_user["telegram_id"]):
        return await message.reply(ERR_NO_RIGHTS)
    args = message.text.split()[1:]
    target_id, target_username, _ = await resolve_target_username(message, bot, args)
    if target_id is None:
        return await message.reply(ERR_ARGS)
    try:
        await bot.unban_chat_member(message.chat.id, target_id)
        await message.answer(f"✅ @{target_username} разбанен. Может вернуться в чат.")
    except Exception as e:
        await message.reply(f"❌ Ошибка: {e}")