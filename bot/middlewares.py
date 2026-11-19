from aiogram import BaseMiddleware
from aiogram.types import Message
from bot.models import get_user, update_username, add_message_count
from bot.config import BARAHOLKA_CHATS

class UserMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data, *args, **kwargs):
        if isinstance(event, Message) and event.from_user:
            user = await get_user(event.from_user.id)
            data["db_user"] = user
            if event.from_user.username:
                await update_username(event.from_user.id, event.from_user.username)
            
            if not event.from_user.is_bot and event.chat.id in BARAHOLKA_CHATS:
                await add_message_count(event.chat.id, event.from_user.id)
                
        return await handler(event, data)
