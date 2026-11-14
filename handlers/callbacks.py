from datetime import datetime, timedelta
from aiogram import Router, Bot, F
from aiogram.types import CallbackQuery, ChatPermissions
from bot.models import (get_application, set_application_status,
                        add_log, get_user, get_rule)
from bot.config import LOG_CHAT_ID, role_level
from bot.handlers.rules import send_rules_page
from bot.utils import seconds_to_text, apply_vip

router = Router()

@router.callback_query(F.data == "show_rules")
async def cb_show_rules(call: CallbackQuery):
    await send_rules_page(call, 0)
    await call.answer()

@router.callback_query(F.data.startswith("rules_page:"))
async def cb_rules_page(call: CallbackQuery):
    page = int(call.data.split(":")[1])
    await send_rules_page(call, page)
    await call.answer()

@router.callback_query(F.data == "noop")
async def cb_noop(call: CallbackQuery):
    await call.answer()

@router.callback_query(F.data.startswith("app_approve:"))
async def cb_approve(call: CallbackQuery, bot: Bot, db_user):
    app_id = int(call.data.split(":")[1])
    app = await get_application(app_id)
    if not app or app["status"] != "pending":
        return await call.answer("Заявка уже обработана.", show_alert=True)
    if role_level(db_user["role"]) < role_level("senior_mod"):
        return await call.answer("Недостаточно прав.", show_alert=True)
    target = await get_user(app["target_id"])
    target_role = target["role"]
    target_username = target["username"]
    rule_code = app["rule_code"]
    duration = None
    duration_text = "навсегда"
    if rule_code:
        rule = await get_rule(rule_code)
        if rule and rule["duration_sec"]:
            duration = rule["duration_sec"]
    if target_role == "vip" and duration:
        duration = apply_vip(duration)
        duration_text = seconds_to_text(duration)
    elif duration:
        duration_text = seconds_to_text(duration)
    until = None if duration is None else datetime.now() + timedelta(seconds=duration)
    perms = ChatPermissions(can_send_messages=False)
    # мут применяется в чате нарушения
    try:
        await bot.restrict_chat_member(app["chat_id"], app["target_id"], perms, until_date=until)
    except Exception:
        pass
    await set_application_status(app_id, "approved", db_user["telegram_id"])
    await add_log(db_user["telegram_id"], app["target_id"], "approve", rule_code, None, duration, app["chat_id"])
    await call.message.edit_text(call.message.text + f"\n\n✅ Одобрено @{db_user['username']} — мут на {duration_text}")
    try:
        await bot.send_message(app["applicant_id"], f"✅ Ваша заявка одобрена. @{target_username} получил мут на {duration_text}.")
    except Exception:
        pass
    await call.answer("Одобрено.")

@router.callback_query(F.data.startswith("app_reject:"))
async def cb_reject(call: CallbackQuery, bot: Bot, db_user):
    app_id = int(call.data.split(":")[1])
    app = await get_application(app_id)
    if not app or app["status"] != "pending":
        return await call.answer("Заявка уже обработана.", show_alert=True)
    if role_level(db_user["role"]) < role_level("senior_mod"):
        return await call.answer("Недостаточно прав.", show_alert=True)
    await set_application_status(app_id, "rejected", db_user["telegram_id"])
    await add_log(db_user["telegram_id"], app["target_id"], "reject", app["rule_code"], None, None, app["chat_id"])
    await call.message.edit_text(call.message.text + f"\n\n❌ Отклонено @{db_user['username']}")
    try:
        await bot.send_message(app["applicant_id"], "❌ Ваша заявка отклонена.")
    except Exception:
        pass
    await call.answer("Отклонено.")