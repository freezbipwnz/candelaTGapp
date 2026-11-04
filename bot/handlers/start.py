from aiogram import Router, types, F
from aiogram.filters import CommandStart, Command
from bot.keyboards.webapp import get_main_webapp_keyboard

router = Router(name="start_router")


@router.message(CommandStart())
async def handle_start(message: types.Message):
    user_name = message.from_user.first_name if message.from_user else "Ценитель уюта"

    text = (
        f"Добро пожаловать в <b>Candela Home</b>, {user_name}! 🕯️✨\n\n"
        "Мы создаем интерьерные ароматы ручной работы: соевые и кокосовые свечи, "
        "диффузоры с фибровыми палочками и парфюмированные саше.\n\n"
        "✨ Нажмите кнопку ниже или в меню, чтобы открыть витрину каталога:"
    )

    await message.answer(
        text=text,
        reply_markup=get_main_webapp_keyboard(),
        parse_mode="HTML"
    )


@router.message(Command("ping"))
async def handle_ping(message: types.Message):
    await message.answer("🏓 Pong! Тестовый бот Candela активен и защищен.")


@router.message(F.web_app_data)
async def handle_webapp_data(message: types.Message):
    """Прием данных из Telegram Mini App (например, после оформления заказа)."""
    received_data = message.web_app_data.data if message.web_app_data else ""
    await message.answer(
        f"📦 Получены данные из Mini App:\n<code>{received_data}</code>",
        parse_mode="HTML"
    )
