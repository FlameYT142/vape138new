import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from bot.config import BOT_TOKEN, LOG_CHAT_ID
from bot.models import init_db, get_due_deletes, delete_pending
from bot.seed_rules import seed_rules
from bot.middlewares import UserMiddleware
from bot.handlers import register_all
from bot.handlers.moderation import check_fsm_timeouts

# Настраиваем логи, чтобы всё падало в консоль Bothost
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

async def cleanup_job(bot):
    due = await get_due_deletes()
    for row in due:
        try:
            await bot.delete_message(row["chat_id"], row["message_id"])
        except Exception:
            pass
        await delete_pending(row["id"])

async def startup_check(bot):
    """Проверка работоспособности при старте"""
    logger.info("⏳ Запуск проверки систем...")
    try:
        # Проверка БД
        await init_db()
        logger.info("✅ База данных подключена.")
        
        # Проверка лог-канала
        await bot.send_message(LOG_CHAT_ID, "🤖 Бот запущен. Все системы в норме.")
        logger.info("✅ Лог-канал доступен и отвечает.")
    except Exception as e:
        logger.error(f"❌ ОШИБКА ПРИ ЗАПУСКЕ: {e}")

async def main():
    await init_db()
    await seed_rules()

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.message.middleware(UserMiddleware())
    register_all(dp)

    scheduler = AsyncIOScheduler(timezone="Asia/Irkutsk")
    scheduler.add_job(cleanup_job, "interval", seconds=60, args=[bot])
    scheduler.add_job(check_fsm_timeouts, "interval", seconds=10, args=[bot])
    scheduler.start()

    # Проверка перед запуском
    await startup_check(bot)

    logger.info("🚀 Бот вышел на связь (Polling started).")
    await dp.start_polling(bot)
