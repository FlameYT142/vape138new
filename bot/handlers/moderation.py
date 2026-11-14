import json
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

def full_mute_permissions():
    return ChatPermissions(
        can_send_messages=False,
        can_send_audios=False, can_send_documents=False,
        can_send_photos=False, can_send_videos=False,
        can_send_video_notes=False, can_send_voice_notes=False,
        can_send_polls=False, can_send_other_messages=False,
        can_add_web_page_previews=False,
        can_change_info=False, can_invite_users=False, can_pin_messages=False)

async def resolve_target(message: Message, bot: Bot, args):
    # 1. Реплай
    if message.reply_to_message and message.reply_to_message.from_user:
        u = message.reply_to_message.from_user
        row = await get_user(u.id)
        return u.id, u.username or str(u.id), row["role"], args
    
    if not args:
        return None, None, None, args
        
    target_raw = args[0]

    # 2. Прямой ID (цифры)
    if target_raw.isdigit():
        target_id = int(target_raw)
        row = await get_user(target_id)
        return target_id, str(target_id), row["role"], args[1:]

    # 3. @username
    if target_raw.startswith("@"):
        uname = target_raw.lstrip("@")
        try:
            m = await bot.get_chat_member(message.chat.id, f"@{uname}")
            u = m.user
            row = await get_user(u.id)
            return u.id, u.username or str(u.id), row["role"], args[1:]
        except Exception:
            try:
                async for msg in bot.get_chat_history(message.chat.id, limit=100):
                    if msg.from_user and msg.from_user.username and msg.from_user.username.lower() == uname.lower():
                        u = msg.from_user
                        row = await get_user(u.id)
                        return u.id, u.username, row["role"], args[1:]
            except Exception:
                pass
                
    return None, None, None, args

def calc_duration(rule, target_role, recurrent):
    if rule["special"] == "ban":
        return None, True
    if recurrent and rule["recurrence_action"] == "ban":
        return None, True
    if recurrent:
        if rule["recurrence_sec"]:
            return rule["recurrence_sec"], False
        if rule["recurrence_action"] == "mute":
            base = rule["duration_sec"] or 3600
            return base, False
        if rule["duration_sec"]:
            return apply_recurrence(rule["duration_sec"]), False
    base = rule["duration_sec"] or 3600
    if target_role == "vip":
        base = apply_vip(base)
    return base, False

async def ping_admins(bot: Bot):
    try:
        admins = await bot.get_chat_administrators(LOG_CHAT_ID)
        mentions = []
        for a in admins:
            if a.user.is_bot:
                continue
            if a.user.username:
                mentions.append(f"@{a.user.username}")
        if mentions:
            return "📢 Подъём, посмотрите логи!\n" + " ".join(mentions)
    except Exception:
        pass
    return "📢 Подъём, посмотрите логи!"

async def send_appeal(bot: Bot, app_id: int, header: str, text: str, kb):
    ping = await ping_admins(bot)
    await bot.send_message(LOG_CHAT_ID, ping)
    await bot.send_message(LOG_CHAT_ID, f"<b>{header}</b>\n{text}", reply_markup=kb)

async def apply_mute_and_report(bot, chat_id, target_id, target_username, target_role,
                                 rule_code, rule, actor_id, actor_username, duration, is_ban):
    if is_ban:
        try:
            await bot.ban_chat_member(chat_id, target_id)
        except Exception as e:
            return None, f"❌ Ошибка: {e}"
        text = ban_report(target_username, rule_code, rule["text"], actor_username)
        await add_log(actor_id, target_id, "ban", rule_code, None, None, chat_id)
    else:
        until = None if duration is None else datetime.now() + timedelta(seconds=duration)
        try:
            await bot.restrict_chat_member(chat_id, target_id, full_mute_permissions(), until_date=until)
        except Exception as e:
            return None, f"❌ Ошибка: {e}"
        duration_text = "навсегда" if duration is None else seconds_to_text(duration)
        text = mute_report(target_username, duration_text, rule_code, rule["text"], actor_username)
        if target_role == "vip" and duration is not None:
            base = rule["duration_sec"] or 3600
            text += f"\n\n💎 VIP-статус: срок уменьшен вдвое ({seconds_to_text(base)} → {duration_text})"
        await add_log(actor_id, target_id, "mute", rule_code, None, duration, chat_id)
    return text, None

def appeal_kb_safe(app_id):
    from bot.keyboards import appeal_kb
    return appeal_kb(app_id)

@router.message(lambda m: m.text and m.text.split()[0].lower().lstrip("./") in ("мут", "mute"))
async def cmd_mute(message: Message, bot: Bot, db_user):
    if message.chat.id == CHAT_TRAINEE:
        return await message.reply(ERR_TRAINEE_CHAT_ONLY_WARN)
    
    args = message.text.split()[1:]
    if not args:
        return await message.reply(ERR_ARGS)

    # ЖЕЛЕЗОБЕТОННАЯ ЛОГИКА РЕПЛАЯ
    if message.reply_to_message and message.reply_to_message.from_user:
        u = message.reply_to_message.from_user
        target_id = u.id
        target_username = u.username or str(u.id)
        row = await get_user(target_id)
        target_role = row["role"]
        rest = args  # Все аргументы (номер правила) идут сюда
    else:
        target_id, target_username, target_role, rest = await resolve_target(message, bot, args)
        if target_id is None:
            return await message.reply(ERR_TARGET)

    actor = db_user
    actor_level = role_level(actor["role"])
    
    if not rest:
        return await message.reply(ERR_ARGS)

    forever = False
    rule_code = None
    if rest[0].lower() in ("навсегда", "forever"):
        forever = True
        if len(rest) < 2:
            return await message.reply(ERR_ARGS)
        rule_code = rest[1]
    elif rest[0][0].isdigit() or "." in rest[0]:
        rule_code = rest[0]

    if target_role == "owner":
        return await message.reply(ERR_OWNER_IMMUNE)

    if rule_code:
        if actor_level < role_level("moderator"):
            return await message.reply(MSG_APPEAL_SENT)
        if target_role in ("blat", "partner"):
            await message.reply(ERR_IMMUNITY.format(status=role_label(target_role)))
            app_id = await create_application(actor["telegram_id"], target_id, message.chat.id, "mute", rule_code, None)
            await send_appeal(bot, app_id, "⚠️ ЗАЯВКА НА МУТ (иммунитет)",
                f"👤 @{actor['username']}\n🎯 @{target_username} ({role_label(target_role)})\n📜 Правило: {rule_code}",
                appeal_kb_safe(app_id))
            return

        rule = await get_rule(rule_code)
        if not rule:
            return await message.reply(ERR_RULE_NOT_FOUND.format(code=rule_code))
        if not rule["active"]:
            return await message.reply(ERR_RULE_INACTIVE.format(code=rule_code))

        if rule_code == "20" and not forever and actor_level >= role_level("moderator"):
            payload = {"chat_id": message.chat.id, "target_id": target_id,
                       "target_username": target_username, "rule_code": rule_code,
                       "actor_id": actor["telegram_id"], "actor_username": actor["username"]}
            expire_at = (datetime.utcnow() + timedelta(seconds=30)).strftime("%Y-%m-%d %H:%M:%S")
            await save_pending_fsm("mute20", actor["telegram_id"], message.chat.id, payload, expire_at)
            try:
                await bot.send_message(actor["telegram_id"],
                    "⏳ Укажите срок мута (24–72 часа): 24, 48 или 72.\n"
                    "Если не ответите за 30 сек — применится 24 часа.")
            except Exception:
                await message.reply("❌ Не могу написать вам в ЛС. Напишите боту /start.")
            return

        recurrent = await has_recurrence(target_id, rule_code, message.chat.id)
        duration, is_ban = calc_duration(rule, target_role, recurrent)

        text, err = await apply_mute_and_report(
            bot, message.chat.id, target_id, target_username, target_role,
            rule_code, rule, actor["telegram_id"], actor["username"], duration, is_ban)
        if err:
            return await message.reply(err)
        sent = await message.answer(text)
        delete_at = (datetime.utcnow() + timedelta(seconds=86400)).strftime("%Y-%m-%d %H:%M:%S")
        await schedule_delete(message.chat.id, sent.message_id, delete_at)
        if is_ban:
            await bot.send_message(LOG_CHAT_ID,
                f"🔨 БАН\nКто: @{actor['username']}\nКого: @{target_username}\nПравило: {rule_code}")
        else:
            dur_text = "навсегда" if duration is None else seconds_to_text(duration)
            await bot.send_message(LOG_CHAT_ID,
                f"🔨 МУТ\nКто: @{actor['username']}\nКого: @{target_username}\n"
                f"Правило: {rule_code}\nСрок: {dur_text}")
        if rule["special"] == "warn_post":
            try:
                await bot.send_message(actor["telegram_id"],
                    MSG_POST_DELETE_REMINDER.format(username=target_username, rule=rule_code))
            except Exception:
                pass
        if rule["special"] == "kick_bot":
            try:
                await bot.send_message(actor["telegram_id"],
                    MSG_BOT_DELETE_REMINDER.format(username=target_username))
            except Exception:
                pass
        return

    reason = " ".join(rest) if rest else None
    if actor_level < role_level("moderator"):
        if target_role in ("blat", "partner"):
            await message.reply(ERR_IMMUNITY.format(status=role_label(target_role)))
        else:
            await message.reply(MSG_APPEAL_SENT if target_role != "vip" else MSG_APPEAL_VIP)
        app_id = await create_application(actor["telegram_id"], target_id, message.chat.id, "mute", None, reason)
        await send_appeal(bot, app_id, "⚠️ НОВАЯ ЗАЯВКА НА МУТ",
            f"👤 @{actor['username']}\n🎯 @{target_username} ({role_label(target_role)})\n📝 {reason or '—'}",
            appeal_kb_safe(app_id))
        return

    if target_role in ("blat", "partner"):
        await message.reply(ERR_IMMUNITY.format(status=role_label(target_role)))
        app_id = await create_application(actor["telegram_id"], target_id, message.chat.id, "mute", None, reason)
        await send_appeal(bot, app_id, "⚠️ ЗАЯВКА НА МУТ (иммунитет)",
            f"👤 @{actor['username']} → @{target_username}\n📝 {reason or '—'}",
            appeal_kb_safe(app_id))
        return
    if target_role == "vip":
        await message.reply(MSG_APPEAL_VIP)
        app_id = await create_application(actor["telegram_id"], target_id, message.chat.id, "mute", None, reason)
        await send_appeal(bot, app_id, "⚠️ ЗАЯВКА НА МУТ (VIP)",
            f"👤 @{actor['username']} → @{target_username}\n📝 {reason or '—'}",
            appeal_kb_safe(app_id))
        return
    await message.reply(ERR_NEED_RULE)

@router.message(lambda m: m.text and m.text.split()[0].lower().lstrip("./") in ("размут", "unmute"))
async def cmd_unmute(message: Message, bot: Bot, db_user):
    if message.chat.id == CHAT_TRAINEE:
        return await message.reply(ERR_TRAINEE_CHAT_ONLY_WARN)
    if role_level(db_user["role"]) < role_level("senior_mod"):
        return await message.reply(ERR_NO_RIGHTS)
    args = message.text.split()[1:]
    if not args:
        return await message.reply(ERR_ARGS)
        
    if message.reply_to_message and message.reply_to_message.from_user:
        u = message.reply_to_message.from_user
        target_id, target_username = u.id, u.username or str(u.id)
    else:
        target_id, target_username, _, _ = await resolve_target(message, bot, args)
        
    if target_id is None:
        return await message.reply(ERR_TARGET)
    try:
        await bot.restrict_chat_member(message.chat.id, target_id,
            ChatPermissions(can_send_messages=True))
    except Exception as e:
        return await message.reply(f"❌ Ошибка: {e}")
    await message.answer(unmute_report(target_username, db_user["username"]))
    await add_log(db_user["telegram_id"], target_id, "unmute", None, None, None, message.chat.id)

@router.message(lambda m: m.text and m.text.split()[0].lower().lstrip("./") in ("кик", "kick"))
async def cmd_kick(message: Message, bot: Bot, db_user):
    if message.chat.id == CHAT_TRAINEE:
        return await message.reply(ERR_TRAINEE_CHAT_ONLY_WARN)
    args = message.text.split()[1:]
    if not args:
        return await message.reply(ERR_ARGS)
        
    if message.reply_to_message and message.reply_to_message.from_user:
        u = message.reply_to_message.from_user
        target_id, target_username, rest = u.id, u.username or str(u.id), args
    else:
        target_id, target_username, _, rest = await resolve_target(message, bot, args)

    if target_id is None:
        return await message.reply(ERR_TARGET)
    reason = " ".join(rest) if rest else "—"
    if role_level(db_user["role"]) < role_level("deputy_head"):
        app_id = await create_application(db_user["telegram_id"], target_id, message.chat.id, "kick", None, reason)
        await send_appeal(bot, app_id, "⚠️ ЗАЯВКА НА КИК",
            f"👤 @{db_user['username']} → @{target_username}\n📝 {reason}",
            appeal_kb_safe(app_id))
        return await message.reply(MSG_APPEAL_SENT)
    try:
        await bot.ban_chat_member(message.chat.id, target_id)
        await bot.unban_chat_member(message.chat.id, target_id)
    except Exception as e:
        return await message.reply(f"❌ Ошибка: {e}")
    await message.answer(kick_report(target_username, reason, db_user["username"]))
    await add_log(db_user["telegram_id"], target_id, "kick", None, reason, None, message.chat.id)
    try:
        await bot.send_message(db_user["telegram_id"],
            MSG_BOT_DELETE_REMINDER.format(username=target_username))
    except Exception:
        pass

@router.message(lambda m: m.text and m.text.split()[0].lower().lstrip("./") in ("варн", "warn") and m.chat.id != CHAT_TRAINEE)
async def cmd_warn(message: Message, bot: Bot, db_user):
    if role_level(db_user["role"]) < role_level("senior_mod"):
        return await message.reply(ERR_NO_RIGHTS)
    args = message.text.split()[1:]
    if not args:
        return await message.reply(ERR_ARGS)

    if message.reply_to_message and message.reply_to_message.from_user:
        u = message.reply_to_message.from_user
        target_id, target_username, rest = u.id, u.username or str(u.id), args
        row = await get_user(target_id)
        target_role = row["role"]
    else:
        target_id, target_username, target_role, rest = await resolve_target(message, bot, args)

    if target_id is None:
        return await message.reply(ERR_TARGET)
    reason = " ".join(rest) if rest else "—"
    
    if target_role == "owner":
        return await message.reply(ERR_OWNER_IMMUNE)
    if target_role in ("blat", "partner"):
        return await message.reply(ERR_IMMUNITY.format(status=role_label(target_role)))
    await add_warn(target_id, db_user["telegram_id"], reason, chat_id=message.chat.id)
    count = await count_warns(target_id)
    await message.answer(warn_report(target_username, count, 3, db_user["username"], reason))
    await add_log(db_user["telegram_id"], target_id, "warn", None, reason, None, message.chat.id)

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
    args = message.text.split()[1:]
    if not args:
        return await message.reply(ERR_ARGS)
    target_id, target_username, _, _ = await resolve_target(message, bot, args)
    if target_id is None:
        return await message.reply(ERR_TARGET)
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
