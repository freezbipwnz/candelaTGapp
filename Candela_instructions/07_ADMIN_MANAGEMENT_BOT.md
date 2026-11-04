# Административный бот управления (Candela Admin Hub)

Административный Telegram-бот — это карманный центр управления магазином **Candela Home**. Он позволяет владельцу и менеджерам без компьютера отслеживать выручку, менять статусы заказов, передавать трек-номера клиентам и создавать новые карточки товаров для Mini App.

---

## 1. Авторизация и безопасность администратора

Доступ разрешен только тем Telegram ID, которые прописаны в переменной окружения `ADMIN_TELEGRAM_IDS`.

Файл: `bot_admin/filters.py`

```python
from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery
from app.core.config import settings

class AdminOnlyFilter(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user_id = event.from_user.id if event.from_user else 0
        return user_id in settings.ADMIN_TELEGRAM_IDS
```

---

## 2. Главное меню администратора

При вводе команды `/start` администратор видит удобное меню быстрых действий:

```text
🕯 Candela Admin Hub:
━━━━━━━━━━━━━━━━━━
📊 Финансы и выручка
📦 Заказы в обработке (3 новых)
➕ Добавить новый товар
🏷 Управление складом и ценами
```

---

## 3. Модуль аналитики и мониторинга выручки

Файл: `bot_admin/handlers/analytics.py`

```python
from datetime import datetime, time
from aiogram import Router, F, types
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.db.session import async_session_maker
from app.db.models import Order, OrderStatus
from bot_admin.filters import AdminOnlyFilter

router = Router()
router.message.filter(AdminOnlyFilter())

@router.message(F.text == "📊 Финансы и выручка")
async def show_revenue_stats(message: types.Message):
    today_start = datetime.combine(datetime.now().date(), time.min)

    async with async_session_maker() as session:
        # Выручка и количество за сегодня
        res_today = await session.execute(
            select(func.count(Order.id), func.sum(Order.total_amount))
            .where(Order.status.in_([OrderStatus.PAID, OrderStatus.IN_PROCESSING, OrderStatus.SHIPPED, OrderStatus.DELIVERED]))
            .where(Order.created_at >= today_start)
        )
        orders_today, revenue_today = res_today.one()
        revenue_today = revenue_today or 0

        # Выручка за всё время
        res_total = await session.execute(
            select(func.count(Order.id), func.sum(Order.total_amount))
            .where(Order.status.in_([OrderStatus.PAID, OrderStatus.IN_PROCESSING, OrderStatus.SHIPPED, OrderStatus.DELIVERED]))
        )
        orders_total, revenue_total = res_total.one()
        revenue_total = revenue_total or 0

    avg_check = (revenue_total / orders_total) if orders_total else 0

    text = (
        f"📊 <b>Финансовая сводка Candela Home</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"<b>За сегодня:</b>\n"
        f"• Оплачено заказов: <b>{orders_today} шт.</b>\n"
        f"• Выручка: <b>{revenue_today:,.2f} ₽</b>\n\n"
        f"<b>Всего за всё время:</b>\n"
        f"• Заказов: <b>{orders_total} шт.</b>\n"
        f"• Общая выручка: <b>{revenue_total:,.2f} ₽</b>\n"
        f"• Средний чек: <b>{avg_check:,.2f} ₽</b>\n"
    )

    await message.answer(text, parse_mode="HTML")
```

---

## 4. Пошаговый FSM-мастер создания карточки товара

Чтобы добавить новый товар в Mini App, администратору не нужно открывать веб-панель — достаточно пройти диалог в Telegram.

### Машина состояний (FSM):
Файл: `bot_admin/handlers/add_product.py`

```python
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from app.db.session import async_session_maker
from app.db.models import Product, Category
from bot_admin.filters import AdminOnlyFilter

router = Router()
router.message.filter(AdminOnlyFilter())

class AddProductState(StatesGroup):
    waiting_for_category = State()
    waiting_for_title = State()
    waiting_for_price = State()
    waiting_for_description = State()
    waiting_for_notes = State() # Верхние, средние, базовые ноты
    waiting_for_photo = State()
    waiting_for_stock = State()

@router.message(F.text == "➕ Добавить новый товар")
async def start_add_product(message: types.Message, state: FSMContext):
    # Клавиатура выбора категории
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🕯 Свечи", callback_data="cat_1")],
            [InlineKeyboardButton(text="🌿 Диффузоры", callback_data="cat_2")],
            [InlineKeyboardButton(text="🌸 Саше", callback_data="cat_3")],
            [InlineKeyboardButton(text="🎁 Подарочные боксы", callback_data="cat_4")],
        ]
    )
    await message.answer("Выберите категорию создаваемого товара:", reply_markup=keyboard)
    await state.set_state(AddProductState.waiting_for_category)

@router.callback_query(AddProductState.waiting_for_category)
async def process_category(callback: types.CallbackQuery, state: FSMContext):
    category_id = int(callback.data.replace("cat_", ""))
    await state.update_data(category_id=category_id)
    await callback.message.edit_text("Введите <b>название товара</b> (например: <i>Свеча «Табак и Ваниль»</i>):", parse_mode="HTML")
    await state.set_state(AddProductState.waiting_for_title)

@router.message(AddProductState.waiting_for_title)
async def process_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await message.answer("Укажите <b>цену</b> в рублях (только число, например: <i>1890</i>):", parse_mode="HTML")
    await state.set_state(AddProductState.waiting_for_price)

@router.message(AddProductState.waiting_for_price)
async def process_price(message: types.Message, state: FSMContext):
    try:
        price = float(message.text.replace(",", "."))
        await state.update_data(price=price)
        await message.answer("Введите <b>описание товара</b>, объем (мл) и время горения:", parse_mode="HTML")
        await state.set_state(AddProductState.waiting_for_description)
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число для цены!")

@router.message(AddProductState.waiting_for_description)
async def process_description(message: types.Message, state: FSMContext):
    await state.update_data(description=message.text)
    await message.answer(
        "Укажите пирамиду аромата через точку с запятой:\n"
        "Формат: <code>Верхние ноты; Ноты сердца; Базовые ноты</code>\n"
        "Пример: <code>Бергамот, Перец; Табачный лист, Гвоздика; Ваниль, Бобы тонка</code>",
        parse_mode="HTML"
    )
    await state.set_state(AddProductState.waiting_for_notes)

@router.message(AddProductState.waiting_for_notes)
async def process_notes(message: types.Message, state: FSMContext):
    parts = [p.strip() for p in message.text.split(";")]
    top = [x.strip() for x in parts[0].split(",")] if len(parts) > 0 else []
    heart = [x.strip() for x in parts[1].split(",")] if len(parts) > 1 else []
    base = [x.strip() for x in parts[2].split(",")] if len(parts) > 2 else []

    await state.update_data(fragrance_pyramid={"top": top, "heart": heart, "base": base})
    await message.answer("Отправьте <b>фотографию товара</b>:", parse_mode="HTML")
    await state.set_state(AddProductState.waiting_for_photo)

@router.message(AddProductState.waiting_for_photo, F.photo)
async def process_photo(message: types.Message, state: FSMContext):
    # Сохраняем file_id фото для загрузки в S3 или медиа-сервер
    photo_file_id = message.photo[-1].file_id
    await state.update_data(photo_file_id=photo_file_id)
    await message.answer("Укажите начальный <b>остаток на складе</b> (количество штук):", parse_mode="HTML")
    await state.set_state(AddProductState.waiting_for_stock)

@router.message(AddProductState.waiting_for_stock)
async def process_stock_and_save(message: types.Message, state: FSMContext):
    try:
        stock = int(message.text)
        data = await state.get_data()

        async with async_session_maker() as session:
            new_prod = Product(
                category_id=data["category_id"],
                title=data["title"],
                slug=data["title"].lower().replace(" ", "-"),
                description=data["description"],
                price=data["price"],
                stock_quantity=stock,
                fragrance_pyramid=data["fragrance_pyramid"],
                images=["https://storage.yandexcloud.net/candela-home/sample.jpg"], # URL после загрузки
                is_active=True
            )
            session.add(new_prod)
            await session.commit()

        await state.clear()
        await message.answer(f"✅ Товар <b>«{data['title']}»</b> успешно создан и опубликован в Mini App!", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Ошибка сохранения: {e}")
```

---

## 5. Обработка заказов и отправка трек-номеров

Когда заказ оплачен, администратор получает уведомление с инлайн-кнопками:
* `[В сборку ⚙️]`
* `[Указать трек-номер 🚚]`
* `[Отменить ❌]`

При клике на «Указать трек-номер»:
1. Админ вводит номер накладной СДЭК (например, `1456789012`).
2. Бот обновляет заказ в базе: `tracking_number = "1456789012"`, `status = SHIPPED`.
3. Клиентский бот мгновенно отправляет покупателю уведомление:
   > *«Ваш заказ #CH-1024 передан в службу доставки СДЭК! Трек-номер для отслеживания: 1456789012»*.

---

## 6. Уведомления о новых отзывах и ответ от лица компании

Каждый раз, когда покупатель оставляет отзыв в Mini App, администраторам в бота приходит карточка:

```text
⭐ Новый отзыв на товар: «Диффузор Табак и Ваниль»
Оценка: 5/5
Соответствует описанию: Да
Стойкость аромата: Стойкий и глубокий

Плюсы: Наполнил всю гостиную за 2 часа!
Минусы: Нет
Комментарий: Очень красивый флакон, упаковано бережно.

Автор: @username (Заказ #CH-1045)
```

Инлайн-кнопки под сообщением:
* `[ 💬 Ответить от лица компании ]`
* `[ 👁️ Скрыть / Удалить отзыв ]`

При нажатии на «Ответить от лица компании» бот переходит в FSM-состояние ожидания ответа. Введенный текст сохраняется в поле `company_reply` таблицы `reviews` и мгновенно отображается в Mini App под отзывом с официальной плашкой бренда.
