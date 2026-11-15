import json
import logging
from datetime import datetime, timedelta
from aiogram import Router, Bot
from aiogram.types import Message, ChatPermissions
from bot.config import LOG_CHAT_ID, CHAT_TRAINEE, role_level, role_label
from bot.models import (get_user, get_rule, add_warn, count_warns, add_log,
                        has_recurrence, create_application, schedule_delete,
                        save_pending_fsm, get_expired_fsm, delete_fsm, set_user_role)
from bot.texts import *
from bot.utils import seconds_to_text, apply_vip, apply_recurrence

router = Router()
logger = logging.getLogger(__name__)

def full_mute_permissions():
    return ChatPermissions(
        can_send_messages=False,
        can_send_audios=False, can_send_documents=False,
        can_send_photos=False, can_send_videos=False,
        can_send_video_notes=False, can_send_voice_notes=False,
        can_send_polls=False, can_send_other_messages=False,
        can_add_web_page_previews=False,
        can_change_info=False, can_invite_users=False, can_pin_messages=False)

async def get_target(message: Message, bot: Bot, target_str: str):
    if target_str.isdigit():
        tid = int(target_str)
        row = await get_user(tid)
        return tid, str(tid), row["role"]
    if target_str.startswith("@"):
        uname = target_str.lstrip("@")
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

def calc_duration(rule, target_role, recurrent):
    if rule["special"] == "ban": return None, True
    if recurrent and rule["recurrence_action"] == "ban": return None, True
    if recurrent:
        if rule["recurrence_sec"]: return rule["recurrence_sec"], False
        if rule["recurrence_action"] == "mute": return (rule["duration_sec"] or 3600), False
        if rule["duration_sec"]: return apply_recurrence(rule["duration_sec"]), False
    base = rule["duration_sec"] or 3600
    if target_role == "vip": base = apply_vip(base)
    return base, False

async def ping_admins(bot: Bot):
    try:
        admins = await bot.get_chat_administrators(LOG_CHAT_ID)
        mentions = [f"@{a.user.username}" for a in admins if not a.user.is_bot and a.user.username]
        if mentions: return "📢 Подъём, посмотрите логи!\n" + " ".join(mentions)
    except Exception: pass
    return "📢 Подъём, посмотрите логи!"

async def send_appeal(bot: Bot, app_id: int, header: str, text: str, kb):
    ping = await ping_admins(bot)
    await bot.send_message(LOG_CHAT_ID, ping)
    await bot.send_message(LOG_CHAT_ID, f"<b>{header}</b>\n{text}", reply_markup=kb)

def appeal_kb_safe(app_id):
    from bot.keyboards import appeal_kb
    return appeal_kb(app_id)

@router.message(lambda m: m.text and m.text.split()[0].lower().lstrip("./") in ("мут", "mute"))
async def cmd_mute(message: Message, bot: Bot, db_user):
    if message.chat.id == CHAT_TRAINEE:
        return await message.reply(ERR_TRAINEE_CHAT_ONLY_WARN)
    
    # 1. Если это реплай
    if message.reply_to_message and message.reply_to_message.from_user:
        u = message.reply_to_message.from_user
        target_id, target_username, target_role = u.id, u.username or str(u.id), (await get_user(u.id))["role"]
        args = message.text.split()[1:]
    else:
        # 2. Если написан @username или ID
        parts = message.text.split(maxsplit=2)
        if len(parts) < 3:
            return await message.reply("❌ Укажите, кого мутить (реплаем или @username) и правило. Пример: `.мут @user 1`")
        
        target_id, target_username, target_role = await get_target(message, bot, parts[1])
        if target_id is None:
            return await message.reply("❌ Пользователь не найден.")
        args = [parts[2]]

    # Логика
    if target_role == "owner":
        return await message.reply(ERR_OWNER_IMMUNE)
        
    raw_rule = args[0].lower()
    forever = raw_rule in ("навсегда", "forever")
    rule_code = args[1] if forever and len(args) > 1 else (None if forever else raw_rule)

    if rule_code:
        if role_level(db_user["role"]) < role_level("moderator"):
            return await message.reply(MSG_APPEAL_SENT)
        rule = await get_rule(rule_code)
        if not rule:
            return await message.reply(ERR_RULE_NOT_FOUND.format(code=rule_code))
        if not rule["active"]:
            return await message.reply(ERR_RULE_INACTIVE.format(code=rule_code))
            
        if target_role in ("blat", "partner"):
            app_id = await create_application(db_user["telegram_id"], target_id, message.chat.id, "mute", rule_code, None)
            await send_appeal(bot, app_id, "⚠️ ЗАЯВКА НА МУТ (иммунитет)", f"👤 @{db_user['username']}\n🎯 {target_username}\n📜 Правило: {rule_code}", appeal_kb_safe(app_id))
            return

        recurrent = await has_recurrence(target_id, rule_code, message.chat.id)
        duration, is_ban = calc_duration(rule, target_role, recurrent)
        
        if is_ban:
            await bot.ban_chat_member(message.chat.id, target_id)
            text = ban_report(target_username, rule_code, rule["text"], db_user["username"])
            await add_log(db_user["telegram_id"], target_id, "ban", rule_code, None, None, message.chat.id)
        else:
            until = None if duration is None else datetime.now() + timedelta(seconds=duration)
            await bot.restrict_chat_member(message.chat.id, target_id, full_mute_permissions(), until_date=until)
            duration_text = "навсегда" if duration is None else seconds_to_text(duration)
            text = mute_report(target_username, duration_text, rule_code, rule["text"], db_user["username"])
            await add_log(db_user["telegram_id"], target_id, "mute", rule_code, None, duration, message.chat.id)
            
        sent = await message.answer(text)
        delete_at = (datetime.utcnow() + timedelta(seconds=86400)).strftime("%Y-%m-%d %H:%M:%S")
        await schedule_delete(message.chat.id, sent.message_id, delete_at)
        await bot.send_message(LOG_CHAT_ID, f"🔨 ДЕЙСТВИЕ\nКто: @{db_user['username']}\nКого: {target_username}\nПравило: {rule_code}")
        return

    # Если правила нет — заявка
    await message.reply(MSG_APPEAL_SENT)
    app_id = await create_application(db_user["telegram_id"], target_id, message.chat.id, "mute", None, " ".join(args))
    await send_appeal(bot, app_id, "⚠️ НОВАЯ ЗАЯВКА НА МУТ", f"👤 @{db_user['username']}\n🎯 {target_username}\n📝 {' '.join(args)}", appeal_kb_safe(app_id))

@router.message(lambda m: m.text and m.text.split()[0].lower().lstrip("./") in ("размут", "unmute"))
async def cmd_unmute(message: Message, bot: Bot, db_user):
    if role_level(db_user["role"]) < role_level("senior_mod"):
        return await message.reply(ERR_NO_RIGHTS)
        
    if message.reply_to_message and message.reply_to_message.from_user:
        target_id = message.reply_to_message.from_user.id
        target_username = message.reply_to_message.from_user.username or str(target_id)
    else:
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2: return await message.reply(ERR_ARGS)
        target_id, target_username, _ = await get_target(message, bot, parts[1])
        
    if target_id is None: return await message.reply(ERR_TARGET)
    
    try:
        await bot.restrict_chat_member(message.chat.id, target_id, ChatPermissions(can_send_messages=True))
        await message.answer(unmute_report(target_username, db_user["username"]))
        await add_log(db_user["telegram_id"], target_id, "unmute", None, None, None, message.chat.id)
    except Exception as e:
        await message.reply(f"❌ Ошибка: {e}")

@router.message(lambda m: m.text and m.text.split()[0].lower().lstrip("./") in ("кик", "kick"))
async def cmd_kick(message: Message, bot: Bot, db_user):
    if role_level(db_user["role"]) < role_level("deputy_head"):
        return await message.reply(ERR_NO_RIGHTS)
        
    if message.reply_to_message and message.reply_to_message.from_user:
        target_id = message.reply_to_message.from_user.id
        target_username = message.reply_to_message.from_user.username or str(target_id)
        args = message.text.split()[1:]
    else:
        parts = message.text.split(maxsplit=2)
        if len(parts) < 2: return await message.reply(ERR_ARGS)
        target_id, target_username, _ = await get_target(message, bot, parts[1])
        args = [parts[2]] if len(parts) > 2 else []
        
    if target_id is None: return await message.reply(ERR_TARGET)
    reason = " ".join(args) if args else "—"
    
    try:
        await bot.ban_chat_member(message.chat.id, target_id)
        await bot.unban_chat_member(message.chat.id, target_id)
        await message.answer(kick_report(target_username, reason, db_user["username"]))
        await add_log(db_user["telegram_id"], target_id, "kick", None, reason, None, message.chat.id)
    except Exception as e:
        await message.reply(f"❌ Ошибка: {e}")

@router.message(lambda m: m.text and m.text.split()[0].lower().lstrip("./") in ("варн", "warn") and m.chat.id != CHAT_TRAINEE)
async def cmd_warn(message: Message, bot: Bot, db_user):
    if role_level(db_user["role"]) < role_level("senior_mod"):
        return await message.reply(ERR_NO_RIGHTS)
        
    if message.reply_to_message and message.reply_to_message.from_user:
        target_id = message.reply_to_message.from_user.id
        target_username = message.reply_to_message.from_user.username or str(target_id)
        args = message.text.split()[1:]
    else:
        parts = message.text.split(maxsplit=2)
        if len(parts) < 2: return await message.reply(ERR_ARGS)
        target_id, target_username, _ = await get_target(message, bot, parts[1])
        args = [parts[2]] if len(parts) > 2 else []
        
    if target_id is None: return await message.reply(ERR_TARGET)
    reason = " ".join(args) if args else "—"
    
    await add_warn(target_id, db_user["telegram_id"], reason, chat_id=message.chat.id)
    count = await count_warns(target_id)
    await message.answer(warn_report(target_username, count, 3, db_user["username"], reason))
    await add_log(db_user["telegram_id"], target_id, "warn", None, reason, None, message.chat.id)

    # Логика авто-понижения
    user = await get_user(target_id)
    current = user["role"]
    if current == "moderator" and user["demoted_before"] and count >= 2:
        await set_user_role(target_id, "member")
        await message.answer(f"⬇️ @{target_username} снят с роли полностью (2/2 варна).")
        return
    if count >= 3:
        if current == "moderator":
            await set_user_role(target_id, "trainee")
            from bot.db import execute
            await execute("UPDATE users SET demoted_before=1 WHERE telegram_id=?", (target_id,))
            await message.answer(f"⬇️ @{target_username} понижен до Стажёра (3 варна).")
        elif current == "trainee":
            await set_user_role(target_id, "member")
            await message.answer(f"⬇️ @{target_username} снят с роли (3 варна).")

@router.message(lambda m: m.text and m.text.split()[0].lower().lstrip("./") in ("варны", "warns"))
async def cmd_warns(message: Message, bot: Bot, db_user):
    if role_level(db_user["role"]) < role_level("senior_mod"):
        return await message.reply(ERR_NO_RIGHTS)
        
    if message.reply_to_message and message.reply_to_message.from_user:
        target_id = message.reply_to_message.from_user.id
        target_username = message.reply_to_message.from_user.username or str(target_id)
    else:
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2: return await message.reply(ERR_ARGS)
        target_id, target_username, _ = await get_target(message, bot, parts[1])
        
    if target_id is None: return await message.reply(ERR_TARGET)
    
    warns = await get_warns(target_id)
    if not warns:
        return await message.answer(f"📋 У @{target_username} нет активных варнов.")
    lines = [f"📋 <b>Варны @{target_username}</b>\n"]
    for i, w in enumerate(warns, 1):
        lines.append(f"{i}. {w['created_at'][:10]} — {w['reason'] or '—'}")
    lines.append(f"\nВсего активных: <b>{len(warns)}/3</b>")
    await message.answer("\n".join(lines))

@router.message(lambda m: m.chat.type == "private" and m.text and m.text.strip() in ("24", "48", "72"))
async def cmd_mute20_reply(message: Message, bot: Bot):
    from bot.models import get_active_fsm
    fsm = await get_active_fsm("mute20", message.from_user.id)
    if not fsm:
        return
    payload = json.loads(fsm["payload"])
    hours = int(message.text.strip())
    await _apply_mute20(bot, payload, hours * 3600)
    await delete_fsm(fsm["id"])
    await message.answer(f"✅ Мут на {hours} часов применён.")

async def _apply_mute20(bot, payload, duration_sec):
    rule = await get_rule(payload["rule_code"])
    until = datetime.now() + timedelta(seconds=duration_sec)
    try:
        await bot.restrict_chat_member(payload["chat_id"], payload["target_id"],
                                        full_mute_permissions(), until_date=until)
    except Exception:
        return
    dur_text = seconds_to_text(duration_sec)
    await bot.send_message(payload["chat_id"],
        f"🔇 @{payload['target_username']} лишается права слова на {dur_text}\n"
        f"💬 Причина: Правило 20 — {rule['text']}\n"
        f"👮‍ Модератор: @{payload['actor_username']}")
    await add_log(payload["actor_id"], payload["target_id"], "mute", "20", None, duration_sec, payload["chat_id"])

async def check_fsm_timeouts(bot: Bot):
    expired = await get_expired_fsm("mute20")
    for row in expired:
        payload = json.loads(row["payload"])
        await _apply_mute20(bot, payload, 24 * 3600)
        try:
            await bot.send_message(payload["actor_id"], "⏳ Время вышло — применён мут 24 часа.")
        except Exception:
            pass
        await delete_fsm(row["id"])
