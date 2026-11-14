from aiogram import Router, Bot
from aiogram.types import Message
from bot.config import CHAT_TRAINEE, LOG_CHAT_ID, role_level, role_label
from bot.models import (get_user, add_warn, count_warns_chat, add_log,
                         set_user_role, clear_warns)
from bot.texts import *
from bot.utils import seconds_to_text

router = Router()

# Только варн в чате стажёров
@router.message(lambda m: m.chat.id == CHAT_TRAINEE and m.text and
                m.text.split()[0].lower().lstrip("./") in ("мут", "mute", "кик", "kick",
                                                           "бан", "ban", "размут", "unmute"))
async def trainee_chat_block(message: Message):
    await message.reply(ERR_TRAINEE_CHAT_ONLY_WARN)

@router.message(lambda m: m.chat.id == CHAT_TRAINEE and m.text and
                m.text.split()[0].lower().lstrip("./") in ("варн", "warn"))
async def trainee_warn(message: Message, bot: Bot, db_user):
    if role_level(db_user["role"]) < role_level("manager"):
        return await message.reply(ERR_NO_RIGHTS)
    args = message.text.split()[1:]
    if not args:
        return await message.reply(ERR_ARGS)
    
    # ФИКС: Если это реплай, берем ID из реплая, а аргументы — это причина
    if message.reply_to_message and message.reply_to_message.from_user:
        u = message.reply_to_message.from_user
        target_id, target_username, rest = u.id, u.username or str(u.id), args
    elif args[0].startswith("@"):
        try:
            m = await bot.get_chat_member(message.chat.id, args[0])
            target_id, target_username, rest = m.user.id, m.user.username or str(m.user.id), args[1:]
        except Exception:
            return await message.reply(ERR_TARGET)
    else:
        return await message.reply(ERR_TARGET)

    target = await get_user(target_id)
    if target["role"] != "trainee":
        return await message.reply("❌ Этот пользователь не является стажёром.")

    reason = " ".join(rest) if rest else "—"
    await add_warn(target_id, db_user["telegram_id"], reason, chat_id=CHAT_TRAINEE)
    count = await count_warns_chat(target_id, CHAT_TRAINEE)
    text = warn_report(target_username, count, 3, db_user["username"], reason)
    await message.answer(text)
    await bot.send_message(LOG_CHAT_ID,
        f"⚖️ ВАРН СТАЖЁРУ\nКто: @{db_user['username']}\nКого: @{target_username}\n"
        f"Счёт: {count}/3\nПричина: {reason}")

    if count >= 3:
        # провал стажировки
        await message.answer(TRAINEE_FAILED.format(username=target_username))
        try:
            await bot.send_message(target_id, TRAINEE_FAILED.format(username=target_username))
        except Exception:
            pass
        try:
            await bot.ban_chat_member(CHAT_TRAINEE, target_id)
            await bot.unban_chat_member(CHAT_TRAINEE, target_id)
        except Exception:
            pass
        # снятие с должности (вернёт статус по флагу)
        await set_user_role(target_id, "member")
        await clear_warns(target_id)
        user_after = await get_user(target_id)
        await bot.send_message(LOG_CHAT_ID,
            f"❌ СТАЖИРОВКА ПРОВАЛЕНА\nСтажёр: @{target_username}\n"
            f"3/3 варна → кик из чата стажёров.\n"
            f"Новая роль: {role_label(user_after['role'])}")
        await add_log(db_user["telegram_id"], target_id, "trainee_fail", None, None, None, CHAT_TRAINEE)
