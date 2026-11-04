from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from bot.config import settings


def get_main_webapp_keyboard() -> InlineKeyboardMarkup:
    """Инлайн-клавиатура для запуска Mini App."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🕯️ Открыть магазин Candela",
                    web_app=WebAppInfo(url=settings.WEBAPP_URL)
                )
            ]
        ]
    )
