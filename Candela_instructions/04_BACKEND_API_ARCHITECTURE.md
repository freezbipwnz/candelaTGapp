# Архитектура бэкенда (FastAPI + Asynchronous Services)

В этом документе описана архитектура серверной части магазина **Candela Home** на фреймворке **FastAPI**: маршруты, внедрение зависимостей, обработка заказов и оповещения через Telegram-бота.

---

## 1. Структура модулей бэкенда

```text
backend/app/
├── api/
│   ├── deps.py             # Инъекция зависимостей: get_db, get_current_user, get_current_admin
│   └── v1/
│       ├── catalog.py      # Категории, товары, фильтрация по нотам ароматов
│       ├── orders.py       # Создание заказа, валидация остатков, просмотр статуса
│       ├── payments.py     # Обработка вебхука платежной системы (ЮKassa)
│       └── admin.py        # Защищенные API для админки и аналитики
├── core/
│   ├── config.py           # Настройки Pydantic Settings (.env)
│   └── security.py         # Криптографическая валидация initData
├── db/
│   ├── session.py          # AsyncSession, подключение asyncpg
│   └── models.py           # Модели SQLAlchemy 2.0
├── services/
│   ├── yookassa_service.py # Создание платежа и передача чека 54-ФЗ
│   ├── telegram_notify.py  # Отправка сообщений клиенту и админу через aiogram
│   └── ai_recommender.py   # RAG и интеграция с Gemini API
└── main.py                 # Инициализация FastAPI приложения и lifespan
```

---

## 2. Спецификация ключевых API маршрутов

### Публичные маршруты витрины (Mini App):

| Метод | URL | Авторизация | Описание |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/categories` | Не требуется | Список активных категорий |
| `GET` | `/api/v1/products` | Не требуется | Каталог с фильтрами (`category_id`, `search`, `note`) |
| `GET` | `/api/v1/products/{id}` | Не требуется | Детальная карточка с пирамидой аромата |
| `POST` | `/api/v1/orders` | **initData** | Создание заказа, бронь остатков, выдача ссылки на оплату |
| `GET` | `/api/v1/orders/my` | **initData** | Список заказов текущего пользователя |
| `GET` | `/api/v1/orders/{id}` | **initData** | Детали конкретного заказа |

### Сервисные и платёжные маршруты:

| Метод | URL | Защита | Описание |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/payments/webhook` | IP Whitelist + Проверка через API | Приём уведомлений об оплате от ЮKassa |

### Административные маршруты (Admin Hub):

| Метод | URL | Защита | Описание |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/admin/dashboard` | `get_current_admin` | Аналитика: выручка за день/месяц, число заказов |
| `GET` | `/api/v1/admin/orders` | `get_current_admin` | Список всех заказов с фильтром по статусам |
| `PATCH` | `/api/v1/admin/orders/{id}/status` | `get_current_admin` | Смена статуса заказа и привязка трек-номера |
| `POST` | `/api/v1/admin/products` | `get_current_admin` | Создание/обновление товара |

---

## 3. Пример реализации эндпоинта создания заказа

Файл: `backend/app/api/v1/orders.py`

```python
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.api.deps import get_db, get_current_user
from app.core.security import ValidatedInitData
from app.db.models import Order, OrderItem, Product, OrderStatus, DeliveryType, User
from app.services.order_number import generate_order_number
from app.services.yookassa_service import create_yookassa_payment
from app.services.telegram_notify import notify_admin_new_order

router = APIRouter(prefix="/orders", tags=["Orders"])

class OrderItemSchema(BaseModel):
    product_id: str
    quantity: int

class CreateOrderSchema(BaseModel):
    items: list[OrderItemSchema]
    delivery_type: DeliveryType
    delivery_address: str
    recipient_name: str
    recipient_phone: str
    recipient_email: EmailStr
    pd_consent: bool # Согласие 152-ФЗ обязано быть True

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_order(
    payload: CreateOrderSchema,
    init_data: ValidatedInitData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if not payload.pd_consent:
        raise HTTPException(status_code=400, detail="Согласие на обработку персональных данных обязательно (152-ФЗ)")

    if not payload.items:
        raise HTTPException(status_code=400, detail="Корзина пуста")

    # 1. Синхронизируем профиль пользователя в БД
    user_id = init_data.user.id
    user = await db.get(User, user_id)
    if not user:
        user = User(
            id=user_id,
            first_name=init_data.user.first_name,
            last_name=init_data.user.last_name,
            username=init_data.user.username,
            phone=payload.recipient_phone,
            email=payload.recipient_email
        )
        db.add(user)
    else:
        user.phone = payload.recipient_phone
        user.email = payload.recipient_email

    # 2. Проверяем товары, остатки и считаем общую сумму
    order_items_to_create = []
    total_amount = Decimal("0.00")

    for item in payload.items:
        product = await db.get(Product, item.product_id)
        if not product or not product.is_active:
            raise HTTPException(status_code=404, detail=f"Товар {item.product_id} не найден или недоступен")
        
        if product.stock_quantity < item.quantity:
            raise HTTPException(status_code=400, detail=f"Недостаточно остатков для товара '{product.title}'. В наличии: {product.stock_quantity}")

        # Уменьшаем остаток на складе
        product.stock_quantity -= item.quantity
        item_total = product.price * item.quantity
        total_amount += item_total

        order_items_to_create.append(
            OrderItem(
                product_id=product.id,
                title_snapshot=product.title,
                unit_price=product.price,
                quantity=item.quantity
            )
        )

    # Добавляем стоимость доставки (например, фиксированная или расчет СДЭК)
    delivery_cost = Decimal("350.00") if payload.delivery_type != DeliveryType.SELF_PICKUP else Decimal("0.00")
    total_amount += delivery_cost

    # 3. Создаем сущность заказа
    order_number = await generate_order_number(db)
    new_order = Order(
        order_number=order_number,
        user_id=user_id,
        status=OrderStatus.PENDING_PAYMENT,
        delivery_type=payload.delivery_type,
        delivery_cost=delivery_cost,
        total_amount=total_amount,
        delivery_details={
            "recipient_name": payload.recipient_name,
            "recipient_phone": payload.recipient_phone,
            "recipient_email": payload.recipient_email,
            "address": payload.delivery_address
        },
        items=order_items_to_create
    )
    db.add(new_order)
    await db.commit()
    await db.refresh(new_order)

    # 4. Инициируем платеж в ЮKassa с позициями чека (54-ФЗ)
    payment_url, payment_id = await create_yookassa_payment(new_order)

    return {
        "order_id": str(new_order.id),
        "order_number": new_order.order_number,
        "total_amount": float(new_order.total_amount),
        "payment_url": payment_url
    }
```

---

## 4. Обработчик платёжного вебхука (Идемпотентность и уведомления)

Файл: `backend/app/api/v1/payments.py`

```python
from fastapi import APIRouter, Request, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.api.deps import get_db
from app.db.models import Order, OrderStatus, Payment
from app.services.yookassa_service import verify_yookassa_status
from app.services.telegram_notify import notify_user_order_paid, notify_admins_order_paid

router = APIRouter(prefix="/payments", tags=["Payments"])

@router.post("/webhook")
async def yookassa_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    event_data = await request.json()
    
    # 1. Проверяем тип события
    if event_data.get("event") != "payment.succeeded":
        return {"status": "ignored"}

    payment_obj = event_data["object"]
    payment_id = payment_obj["id"]
    order_id = payment_obj["metadata"].get("order_id")

    if not order_id:
        raise HTTPException(status_code=400, detail="Missing order_id in metadata")

    # 2. Встречная проверка через API ЮKassa (защита от поддельных вебхуков)
    is_confirmed = await verify_yookassa_status(payment_id)
    if not is_confirmed:
        raise HTTPException(status_code=400, detail="Payment verification failed")

    # 3. Идемпотентное обновление заказа в БД
    order = await db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.status == OrderStatus.PAID:
        return {"status": "already_processed"} # Идемпотентность

    order.status = OrderStatus.PAID
    
    # Сохраняем информацию о платеже
    payment = Payment(
        order_id=order.id,
        provider="yookassa",
        provider_payment_id=payment_id,
        status="succeeded",
        amount=order.total_amount
    )
    db.add(payment)
    await db.commit()

    # 4. Моментальные Telegram уведомления
    await notify_user_order_paid(user_id=order.user_id, order_number=order.order_number)
    await notify_admins_order_paid(order=order)

    # 5. Снятие временных блокировок остатков в Redis
    for item in order.items:
        await redis.delete(f"stock_lock:{item.product_id}:{order.id}")

    return {"status": "success"}
```

---

## 5. Эндпоинты профиля, программы лояльности и отзывов

* `GET /api/v1/profile/me` — получение баланса бонусов, уровня (Bronze/Silver/Gold) и истории заказов.
* `POST /api/v1/orders/calculate` — расчет заказа с учетом списания бонусов (до 100% стоимости товара).
* `POST /api/v1/reviews` — отправка отзыва на купленный товар (рейтинг 1-5, соответствие описанию, стойкость, плюсы/минусы, фото).
* `GET /api/v1/products/{product_id}/reviews` — получение списка проверенных отзывов с официальными ответами бренда.
