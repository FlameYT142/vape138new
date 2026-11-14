from aiogram import Router
from aiogram.types import Message
from bot.config import role_level, is_tech_admin
from bot.models import (get_rule, get_all_rules, add_rule, delete_rule,
                        set_rule_active, set_rule_critical)
from bot.texts import *
from bot.utils import parse_duration
from bot.keyboards import rules_kb

router = Router()

def has_tech_rights(user_id, db_user):
    return is_tech_admin(user_id) or role_level(db_user["role"]) >= role_level("head")

def is_dm(message):
    return message.chat.type == "private"

@router.message(lambda m: m.text and m.text.split()[0].lower().lstrip("./") in ("addrule", "добавитьправило"))
async def cmd_addrule(message: Message, db_user):
    if not is_dm(message):
        return await message.reply(ERR_DM_ONLY)
    if not has_tech_rights(message.from_user.id, db_user):
        return await message.reply(ERR_NO_RIGHTS)
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.reply(ERR_ARGS)
    rest = parts[1].split()
    if len(rest) < 3:
        return await message.reply(ERR_ARGS)
    code = rest[0]
    duration_raw = rest[-1]
    if not (duration_raw.endswith("!") or duration_raw.lower() in ("навсегда", "forever")
            or duration_raw[-1].lower() in ("м", "ч", "д")):
        return await message.reply("❌ Укажите срок: 30м, 2ч, 7д или навсегда")
    text = " ".join(rest[1:-1])
    critical = 0
    if duration_raw.endswith("!"):
        critical = 1
        duration_raw = duration_raw[:-1]
    sec, dur_text = parse_duration(duration_raw)
    if sec == "ERROR":
        return await message.reply("❌ Неверный формат срока.")
    await add_rule(code, text, sec, dur_text, critical, None, None, None)
    crit_label = " (критическое)" if critical else ""
    await message.answer(f"✅ Правило {code} добавлено{crit_label}.\n📝 Текст: {text}\n⏳ Срок: {dur_text}")

@router.message(lambda m: m.text and m.text.split()[0].lower().lstrip("./") in ("delrule", "удалитьправило"))
async def cmd_delrule(message: Message, db_user):
    if not is_dm(message):
        return await message.reply(ERR_DM_ONLY)
    if not has_tech_rights(message.from_user.id, db_user):
        return await message.reply(ERR_NO_RIGHTS)
    args = message.text.split()[1:]
    if not args:
        return await message.reply(ERR_ARGS)
    rule = await get_rule(args[0])
    if not rule:
        return await message.reply(ERR_RULE_NOT_FOUND.format(code=args[0]))
    await delete_rule(args[0])
    await message.answer(f"✅ Правило {args[0]} удалено.")

@router.message(lambda m: m.text and m.text.split()[0].lower().lstrip("./") in ("setcritical",))
async def cmd_setcritical(message: Message, db_user):
    if not is_dm(message):
        return await message.reply(ERR_DM_ONLY)
    if not has_tech_rights(message.from_user.id, db_user):
        return await message.reply(ERR_NO_RIGHTS)
    args = message.text.split()[1:]
    if len(args) < 2:
        return await message.reply(ERR_ARGS)
    code, val = args[0], args[1].lower()
    rule = await get_rule(code)
    if not rule:
        return await message.reply(ERR_RULE_NOT_FOUND.format(code=code))
    if val == "on":
        await set_rule_critical(code, 1)
        return await message.answer(f"✅ Правило {code} помечено как критическое.")
    if val == "off":
        await set_rule_critical(code, 0)
        return await message.answer(f"✅ Правило {code} больше не критическое.")
    await message.reply(ERR_ARGS)

@router.message(lambda m: m.text and m.text.split()[0].lower().lstrip("./") in ("rule",))
async def cmd_rule_toggle(message: Message, db_user):
    if not is_dm(message):
        return await message.reply(ERR_DM_ONLY)
    if not has_tech_rights(message.from_user.id, db_user):
        return await message.reply(ERR_NO_RIGHTS)
    args = message.text.split()[1:]
    if len(args) < 2:
        return await message.reply(ERR_ARGS)
    code, val = args[0], args[1].lower()
    rule = await get_rule(code)
    if not rule:
        return await message.reply(ERR_RULE_NOT_FOUND.format(code=code))
    if val == "off":
        await set_rule_active(code, 0)
        return await message.answer(f"🔕 Правило {code} временно отключено.")
    if val == "on":
        await set_rule_active(code, 1)
        return await message.answer(f"🔔 Правило {code} снова активно.")
    await message.reply(ERR_ARGS)

@router.message(lambda m: m.text and m.text.split()[0].lower().lstrip("./") in ("rules", "правила"))
async def cmd_rules(message: Message, db_user):
    if not is_dm(message):
        return await message.reply(ERR_DM_ONLY)
    if not has_tech_rights(message.from_user.id, db_user):
        return await message.reply(ERR_NO_RIGHTS)
    await send_rules_page(message, 0)

async def send_rules_page(message_or_call, page):
    all_rules = await get_all_rules()
    per_page = 10
    total_pages = max(1, (len(all_rules) + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    chunk = all_rules[page*per_page:(page+1)*per_page]
    lines = [f"📋 <b>Правила чата</b> (стр. {page+1}/{total_pages})"]
    for r in chunk:
        mark = " 🔕" if not r["active"] else ""
        crit = " ⚠️" if r["critical"] else ""
        lines.append(f"{r['code']} — {r['text']} — {r['duration_text']}{mark}{crit}")
    text = "\n".join(lines)
    if hasattr(message_or_call, "message"):
        await message_or_call.message.edit_text(text, reply_markup=rules_kb(page, total_pages))
    else:
        await message_or_call.answer(text, reply_markup=rules_kb(page, total_pages))