import json
from datetime import datetime, timedelta
from aiogram import Router, Bot
from aiogram.types import Message, ChatPermissions
from bot.config import (LOG_CHAT_ID, CHAT_TRAINEE, CHAT_BRATSK, CHAT_VIHOREVKA,
                        role_level, role_label)
from bot.models import (get_user, get_rule, add_warn, count_warns, get_warns,
                        add_log, count_recurrence, create_application, schedule_delete,
                        save_pending_fsm, get_expired_fsm, delete_fsm, set_user_role, get_top)
from bot.texts import *
from bot.utils import seconds_to_text, apply_vip

router = Router()

def full_mute_permissions():
    return ChatPermissions(
        can_send_messages=False, can_send_audios=False, can_send_documents=False,
        can_send_photos=False, can_send_videos=False, can_send_video_notes=False,
        can_send_voice_notes=False, can_send_polls=False, can_send_other_messages=False,
        can_add_web_page_previews=False, can_change_info=False, can_invite_users=False, can_pin_messages=False)

async def get_target(message: Message, bot: Bot, target_str: str):
    # Только ID! По @username больше не ищем.
    if target_str.isdigit():
        tid = int(target_str)
        row = await get_user(tid)
        return tid, str(tid), row["role"]
    return None, None, None

def check_chat_access(user, chat_id):
    if role_level(user["role"]) >= role_level("deputy_head"): return True
    if chat_id == CHAT_BRATSK and user["is_bratsk"]: return True
    if chat_id == CHAT_VIHOREVKA and user["is_vihorevka"]: return True
    return False

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

@router.message(lambda m: m.text and m.text.startswith((".наказать", "/наказать")))
async def cmd_punish(message: Message, bot: Bot, db_user):
    if message.chat.id == CHAT_TRAINEE: return await message.reply(ERR_TRAINEE_CHAT_ONLY_WARN)
    if not check_chat_access(db_user, message.chat.id): return await message.reply("❌ Вы не относитесь к администрации этого чата.")
        
    if message.reply_to_message and message.reply_to_message.from_user:
        u = message.reply_to_message.from_user
        target_id, target_username, target_role = u.id, u.username or str(u.id), (await get_user(u.id))["role"]
        args = message.text.split()[1:]
    else:
        parts = message.text.split(maxsplit=2)
        if len(parts) < 3: return await message.reply("❌ Формат: `.наказать 123456789 1.1` или реплаем `.наказать 1.1`")
        target_id, target_username, target_role = await get_target(message, bot, parts[1])
        if target_id is None: return await message.reply("❌ Используйте реплай или ID (цифры).")
        args = [parts[2]]

    if not args: return await message.reply("❌ Укажите номер правила.")
    rule_code = args[0]
    if target_role == "owner": return await message.reply(ERR_OWNER_IMMUNE)
        
    rule = await get_rule(rule_code)
    if not rule: return await message.reply(ERR_RULE_NOT_FOUND.format(code=rule_code))
    if not rule["active"]: return await message.reply(ERR_RULE_INACTIVE.format(code=rule_code))

    if target_role in ("blat", "partner"):
        app_id = await create_application(db_user["telegram_id"], target_id, message.chat.id, "mute", rule_code, None)
        await send_appeal(bot, app_id, "⚠️ ЗАЯВКА НА МУТ (иммунитет)", f"👤 @{db_user['username']}\n🎯 {target_username}\n📜 Правило: {rule_code}", appeal_kb_safe(app_id))
        return

    count = await count_recurrence(target_id, rule_code, message.chat.id)
    
    act_type = rule["special"]
    duration_sec = rule["duration_sec"]
    
    is_ban = False; is_kick = False; is_warn = False; remind_post = False; remind_bot = False

    if count == 0: pass
    elif count == 1:
        if rule["recurrence_action"] == "ban": is_ban = True
        elif rule["recurrence_action"] == "mute": act_type = "mute"
        elif rule["recurrence_sec"]: duration_sec = rule["recurrence_sec"]
    elif count >= 2:
        if rule["recurrence_2_action"] == "ban": is_ban = True
        elif rule["recurrence_2_action"] == "mute": act_type = "mute"
    
    if act_type == "warn" or act_type == "warn_post":
        is_warn = True
        if act_type == "warn_post": remind_post = True
    elif act_type == "kick" or act_type == "kick_bot":
        is_kick = True
        if act_type == "kick_bot": remind_bot = True
    elif act_type == "ban": is_ban = True

    if target_role == "vip" and duration_sec and not is_warn and not is_ban:
        duration_sec = apply_vip(duration_sec)

    header = f"⚖️ <b>Правило {rule_code} — {rule['text']}</b>"
    result_text = ""
    
    if is_warn:
        await add_warn(target_id, db_user["telegram_id"], f"Правило {rule_code}", chat_id=message.chat.id)
        warn_count = await count_warns(target_id)
        result_text = f"❗️ @{target_username} получает предупреждение ({warn_count}/3)."
        await add_log(db_user["telegram_id"], target_id, "warn", rule_code, None, None, message.chat.id)
    elif is_ban:
        try: await bot.ban_chat_member(message.chat.id, target_id)
        except Exception as e: return await message.reply(f"❌ Ошибка: {e}")
        result_text = f"🔨 @{target_username} забанен навсегда."
        await add_log(db_user["telegram_id"], target_id, "ban", rule_code, None, None, message.chat.id)
    elif is_kick:
        try:
            await bot.ban_chat_member(message.chat.id, target_id)
            await bot.unban_chat_member(message.chat.id, target_id)
        except Exception as e: return await message.reply(f"❌ Ошибка: {e}")
        result_text = f"👢 @{target_username} удалён из чата (кик)."
        await add_log(db_user["telegram_id"], target_id, "kick", rule_code, None, None, message.chat.id)
    else: # Mute
        until = None if duration_sec is None else datetime.now() + timedelta(seconds=duration_sec)
        try: await bot.restrict_chat_member(message.chat.id, target_id, full_mute_permissions(), until_date=until)
        except Exception as e: return await message.reply(f"❌ Ошибка: {e}")
        dur = "навсегда" if duration_sec is None else seconds_to_text(duration_sec)
        result_text = f"🔇 @{target_username} лишается права слова на {dur}."
        await add_log(db_user["telegram_id"], target_id, "mute", rule_code, None, duration_sec, message.chat.id)

    report = f"{header}\n{result_text}\n👮‍ Модератор: @{db_user['username']}"
    sent = await message.answer(report)
    delete_at = (datetime.utcnow() + timedelta(seconds=86400)).strftime("%Y-%m-%d %H:%M:%S")
    await schedule_delete(message.chat.id, sent.message_id, delete_at)

    if remind_post:
        try: await bot.send_message(db_user["telegram_id"], MSG_POST_DELETE_REMINDER.format(username=target_username, rule=rule_code))
        except Exception: pass
    if remind_bot:
        try: await bot.send_message(db_user["telegram_id"], MSG_BOT_DELETE_REMINDER.format(username=target_username))
        except Exception: pass

    await bot.send_message(LOG_CHAT_ID, f"🔨 ДЕЙСТВИЕ\nКто: @{db_user['username']}\nКого: {target_username}\nПравило: {rule_code}\nДействие: {act_type}")

# --- .мут и .размут теперь снимают наказание ---
@router.message(lambda m: m.text and m.text.startswith((".размут", "/размут", ".unmute", "/unmute", ".мут", "/мут", ".mute", "/mute")))
async def cmd_unmute(message: Message, bot: Bot, db_user):
    if message.chat.id == CHAT_TRAINEE: return await message.reply(ERR_TRAINEE_CHAT_ONLY_WARN)
    if role_level(db_user["role"]) < role_level("senior_mod"): return await message.reply(ERR_NO_RIGHTS)
    if not check_chat_access(db_user, message.chat.id): return await message.reply("❌ Вы не относитесь к администрации этого чата.")
        
    if message.reply_to_message and message.reply_to_message.from_user:
        target_id = message.reply_to_message.from_user.id
        target_username = message.reply_to_message.from_user.username or str(target_id)
    else:
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2: return await message.reply(ERR_ARGS)
        target_id, target_username, _ = await get_target(message, bot, parts[1])
        
    if target_id is None: return await message.reply("❌ Используйте реплай или ID.")
    
    try:
        await bot.restrict_chat_member(message.chat.id, target_id, ChatPermissions(can_send_messages=True))
        await message.answer(unmute_report(target_username, db_user["username"]))
        await add_log(db_user["telegram_id"], target_id, "unmute", None, None, None, message.chat.id)
    except Exception as e:
        await message.reply(f"❌ Ошибка: {e}")

@router.message(lambda m: m.text and m.text.startswith((".кик", "/кик", ".kick", "/kick")))
async def cmd_kick(message: Message, bot: Bot, db_user):
    if role_level(db_user["role"]) < role_level("deputy_head"):
