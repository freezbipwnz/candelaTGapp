# Интеллектуальный AI-консультант «Арома-сомелье» (Gemini API + aiogram 3)

В этом документе описана настройка AI-консультанта для магазина **Candela Home**. Нейросеть выступает в роли персонального «Арома-сомелье», помогая клиентам подобрать свечи, диффузоры и саше под настроение, интерьер или в подарок, а также дает прямые ссылки на открытие Mini App.

---

## 1. Системный промпт и личность ассистента

Консультант работает на базе модели `gemini-2.5-flash` через официальный **Google GenAI SDK** (`google-genai`).

### Роль и правила поведения:
* **Тон общения**: вежливый, теплый, эстетичный, экспертный (как сомелье в нишевом парфюмерном бутике).
* **Знание ассортимента (RAG)**: рекомендует только реально существующие в каталоге ароматы и категории.
* **Глубина рекомендаций**: раскладывает ароматы по нотам (верхние, сердце, шлейф), объясняет атмосферу (например: *«Для спальни идеально подойдет лаванда и теплый сандал — они замедляют ритм мыслей и готовят ко сну»*).
* **Безопасность использования**: напоминает правила ухода за свечами (подрезать фитиль до 5 мм, не жечь дольше 3 часов за раз).
* **CTA (Call to Action)**: в конце ответа предлагает открыть товар в приложении нажатием на кнопку.

---

## 2. Реализация сервиса «Арома-сомелье» на Python

Файл: `backend/app/services/ai_recommender.py`

```python
import os
from google import genai
from google.genai import types
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.models import Product

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

SYSTEM_INSTRUCTION = """
Ты — изысканный Арома-сомелье и персональный консультант премиального бренда "Candela Home".
Твоя цель — влюбить покупателя в домашние ароматы, помочь выбрать идеальную свечу, диффузор или ароматическое саше.

Правила:
1. Отвечай вежливо, образно и емко, создавая атмосферу уюта и комфорта.
2. При рекомендации ароматов используй только те товары, которые переданы тебе в блоке [АКТУАЛЬНЫЙ КАТАЛОГ].
3. Всегда поясняй звучание нот (верхние, сердце, шлейф) и к какой комнате/настроению подходит аромат.
4. Если клиент ищет подарок, уточни предпочтения получателя (свежие/древесные/сладкие ноты).
5. Напоминай о правилах ухода за свечами из натурального воска: подрезать хлопковый или деревянный фитиль перед зажжением до 5 мм, не жечь дольше 3 часов подряд.
6. Если вопрос касается проблемы с доставкой или возвратом денег — вежливо предложи связаться с поддержкой командой /support.
"""

async def get_active_catalog_context(db: AsyncSession) -> str:
    """Формирует текстовый контекст каталога для промпта (RAG)"""
    result = await db.execute(
        select(Product).where(Product.is_active == True, Product.stock_quantity > 0)
    )
    products = result.scalars().all()
    
    catalog_lines = ["[АКТУАЛЬНЫЙ КАТАЛОГ ТОВАРОВ]:"]
    for p in products:
        notes = p.fragrance_pyramid
        notes_str = f"Верх: {', '.join(notes.get('top', []))}; Сердце: {', '.join(notes.get('heart', []))}; База: {', '.join(notes.get('base', []))}"
        catalog_lines.append(
            f"- ID: {p.id} | Название: {p.title} | Цена: {p.price} руб | Описание: {p.description} | Ноты: [{notes_str}] | Остаток: {p.stock_quantity} шт."
        )
    return "\n".join(catalog_lines)

async def consult_user_with_ai(user_message: str, db: AsyncSession, history: list = None) -> str:
    """Отправляет запрос пользователя в Gemini с подгруженным контекстом каталога"""
    catalog_context = await get_active_catalog_context(db)
    
    prompt = f"{catalog_context}\n\nВопрос клиента: {user_message}"

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=0.7,
            max_output_tokens=1000
        )
    )
    return response.text
```

---

## 3. Обработчик в клиентском Telegram-боте (aiogram 3)

Файл: `bot_client/handlers/ai_chat.py`

```python
from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from app.db.session import async_session_maker
from app.services.ai_recommender import consult_user_with_ai
from app.core.config import settings

router = Router()

@router.message(F.text)
async def handle_ai_consultation(message: types.Message):
    # Показываем статус "печатает...", пока нейросеть формулирует ответ
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")

    async with async_session_maker() as session:
        ai_reply = await consult_user_with_ai(user_message=message.text, db=session)

    # Кнопка для открытия Mini App прямо из чата
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🕯 Открыть витрину Candela Home",
                    web_app=WebAppInfo(url=settings.MINI_APP_URL)
                )
            ]
        ]
    )

    await message.answer(ai_reply, reply_markup=keyboard)
```

---

## 4. Обработка голосовых сообщений (Voice Input)

Клиенты часто предпочитают надиктовать вопрос: *«Хочу что-то пряное для гостиной на осенний вечер»*.

Gemini поддерживает мультимодальный ввод:
1. Бот скачивает аудиофайл голосового сообщения Telegram (формат `.ogg`).
2. Аудиофайл передается напрямую в Gemini API без необходимости стороннего Speech-to-Text:
   ```python
   # Загрузка и распознавание аудиофайла
   uploaded_audio = client.files.upload(file=audio_bytes, mime_type="audio/ogg")
   response = client.models.generate_content(
       model="gemini-2.5-flash",
       contents=[uploaded_audio, "Ответь на аудиовопрос клиента по нашему каталогу"]
   )
   ```
3. Клиент получает текстовый ответ и кнопку перехода к витрине.
