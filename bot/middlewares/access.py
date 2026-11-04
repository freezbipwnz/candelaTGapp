from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from bot.config import settings


class PrivateAccessMiddleware(BaseMiddleware):
    """
    Middleware, разрешающий взаимодействие с ботом
    только пользователям из списка ALLOWED_USERS.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user_id = None

        if isinstance(event, Message) and event.from_user:
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user:
            user_id = event.from_user.id

        if user_id is not None:
            if user_id not in settings.allowed_user_ids:
                # Если пользователь не авторизован - блокируем доступ
                if isinstance(event, Message):
                    await event.answer(
                        "🔒 <b>Доступ ограничен</b>\n\n"
                        "Этот бот находится на этапе приватного закрытого тестирования.",
                        parse_mode="HTML"
                    )
                elif isinstance(event, CallbackQuery):
                    await event.answer("🔒 Доступ ограничен (приватный бот)", show_alert=True)
                return

        return await handler(event, data)
