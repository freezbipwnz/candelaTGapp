import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.types import MenuButtonWebApp, WebAppInfo
from bot.config import settings
from bot.middlewares.access import PrivateAccessMiddleware
from bot.handlers.start import router as start_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def set_bot_menu_button(bot: Bot):
    """Установка нативной кнопки открытия Mini App в нижнем меню Telegram."""
    try:
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="Магазин",
                web_app=WebAppInfo(url=settings.WEBAPP_URL)
            )
        )
        logger.info("Меню-кнопка Mini App успешно настроена.")
    except Exception as e:
        logger.error(f"Не удалось настроить меню-кнопку: {e}")


async def main():
    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher()

    # Подключаем middleware для строгой приватности (только ваш Telegram ID)
    dp.message.outer_middleware(PrivateAccessMiddleware())
    dp.callback_query.outer_middleware(PrivateAccessMiddleware())

    # Подключаем роутеры
    dp.include_router(start_router)

    # Настраиваем нативную кнопку меню WebApp
    await set_bot_menu_button(bot)

    logger.info("Тестовый бот Candela запущен в приватном режиме...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен.")
