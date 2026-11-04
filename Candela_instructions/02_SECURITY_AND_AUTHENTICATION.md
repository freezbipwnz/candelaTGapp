# Безопасность и криптографическая аутентификация в Telegram Mini App

Безопасность в Telegram Mini App критически важна: так как фронтенд работает в браузере клиента, **любые данные от клиента могут быть подделаны**, если не проверять криптографическую подпись Telegram.

---

## 1. Валидация Telegram `initData` (HMAC-SHA256)

Когда Mini App открывается в Telegram, в объекте `window.Telegram.WebApp.initData` передается строка с данными пользователя и криптографическим хэшем, подписанным секретным ключом бота.

### Алгоритм проверки подписи:
1. Разобрать строку `initData` как URL query string (ключ=значение).
2. Извлечь параметр `hash`.
3. Отсортировать все остальные параметры по алфавиту ключей в формате `key=value`, объединив их через перевод строки `\n` (получается `data_check_string`).
4. Рассчитать `secret_key = HMAC_SHA256(key="WebAppData", message=BOT_TOKEN)`.
5. Рассчитать `calculated_hash = HMAC_SHA256(key=secret_key, message=data_check_string)`.
6. Сравнить `calculated_hash` с полученным `hash` через безопасное сравнение строк (`hmac.compare_digest`).
7. **Защита от Replay-атак:** Проверить параметр `auth_date`. Если время создания подписи старше допустимого окна (например, 1800 секунд / 30 минут), запрос должен быть отклонен.

### Готовый модуль верификации на Python (FastAPI):

```python
# app/core/security.py
import hmac
import hashlib
import json
import time
from urllib.parse import parse_qsl, unquote
from fastapi import HTTPException, Header, status
from pydantic import BaseModel

class TelegramUser(BaseModel):
    id: int
    first_name: str
    last_name: str | None = None
    username: str | None = None
    language_code: str | None = None
    is_premium: bool | None = False

class ValidatedInitData(BaseModel):
    user: TelegramUser
    auth_date: int
    query_id: str | None = None

def verify_telegram_init_data(init_data_raw: str, bot_token: str, max_age_seconds: int = 1800) -> ValidatedInitData:
    """
    Криптографическая проверка подписи Telegram Web App initData.
    Возвращает валидированные данные пользователя или выбрасывает HTTPException 401.
    """
    if not init_data_raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="InitData missing")

    try:
        parsed_data = dict(parse_qsl(init_data_raw, keep_blank_values=True))
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed initData")

    received_hash = parsed_data.pop("hash", None)
    if not received_hash:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Hash missing in initData")

    # 1. Проверка времени жизни подписи (защита от Replay-атак)
    auth_date = int(parsed_data.get("auth_date", 0))
    current_timestamp = int(time.time())
    if current_timestamp - auth_date > max_age_seconds:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="InitData expired (replay attack prevention)")

    # 2. Формирование data_check_string
    sorted_items = sorted(parsed_data.items(), key=lambda item: item[0])
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted_items)

    # 3. Вычисление HMAC-SHA256
    # Секретный ключ вычисляется как HMAC-SHA256 от токена бота с ключом "WebAppData"
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    # 4. Безопасное сравнение хэшей
    if not hmac.compare_digest(calculated_hash, received_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Telegram signature")

    # 5. Извлечение пользователя
    user_json_str = parsed_data.get("user")
    if not user_json_str:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User field missing")

    user_dict = json.loads(user_json_str)
    return ValidatedInitData(
        user=TelegramUser(**user_dict),
        auth_date=auth_date,
        query_id=parsed_data.get("query_id")
    )
```

---

## 2. Безопасность приёма платёжных вебхуков

Платежные системы (ЮKassa / Prodamus) отправляют HTTP POST запросы на ваш сервер при успешной оплате заказа.

### Уязвимости и правила защиты:
1. **Злоумышленник может отправить ложный вебхук:**
   Никогда не доверяйте содержимому тела запроса без проверки подлинности источника.
2. **Проверка IP-адресов источника (IP Whitelisting):**
   ЮKassa использует фиксированные диапазоны IP-адресов для отправки уведомлений:
   * `185.71.76.0/27`
   * `185.71.77.0/27`
   * `77.75.153.0/25`
   * `77.75.156.11`, `77.75.156.35`
   Запросы на `/api/v1/payments/webhook` с других IP должны блокироваться Nginx или FastAPI middleware с кодом `403 Forbidden`.
3. **Проверка статуса через API (Pull Verification):**
   * Даже при получении вебхука «payment.succeeded», бэкенд должен сделать встречный запрос в API платёжной системы: `GET /v3/payments/{payment_id}` с авторизацией по вашим приватным ключам.
   * Менять статус заказа на «Оплачен» можно **только если встречный запрос подтвердил статус `succeeded`**.
4. **Идемпотентность обработки (Idempotency):**
   * Платёжные шлюзы могут повторно слать вебхук, если не получили ответ `200 OK` за 3 секунды.
   * База данных должна иметь транзакционную блокировку: если заказ уже имеет статус `PAID`, повторная обработка игнорируется и возвращается статус `200 OK`.

---

## 3. Разграничение прав доступа (RBAC) и защита админ-панели

1. **Белый список администраторов:**
   В файле окружения `.env` задаются числовые ID доверенных пользователей:
   ```env
   ADMIN_TELEGRAM_IDS=123456789,987654321
   ```
2. **FastAPI Dependency для защищенных админ-эндпоинтов:**
   ```python
   # app/api/deps.py
   from fastapi import Depends, HTTPException, status
   from app.core.config import settings
   from app.core.security import verify_telegram_init_data, ValidatedInitData

   def get_current_admin(init_data: ValidatedInitData = Depends(get_current_user)) -> ValidatedInitData:
       if init_data.user.id not in settings.ADMIN_TELEGRAM_IDS:
           raise HTTPException(
               status_code=status.HTTP_403_FORBIDDEN, 
               detail="Access denied: Admin role required"
           )
       return init_data
   ```
3. **Фильтр администратора в aiogram 3:**
   ```python
   # bot_admin/filters.py
   from aiogram.filters import BaseFilter
   from aiogram.types import Message

   class IsAdminFilter(BaseFilter):
       def __init__(self, admin_ids: list[int]):
           self.admin_ids = admin_ids

       async def __call__(self, message: Message) -> bool:
           return message.from_user is not None and message.from_user.id in self.admin_ids
   ```

---

## 4. Защита от DDoS и спама (Rate Limiting)

Чтобы предотвратить парсинг каталога и перегрузку сервера:
* Используйте Redis-based rate limiting на уровне FastAPI (библиотека `slowapi`):
  * Публичные эндпоинты каталога: 60 запросов в минуту на одного пользователя;
  * Создание заказа: не более 5 заказов в минуту от одного `telegram_id`;
  * Запросы к AI-консультанту: не более 10 сообщений в минуту на пользователя (защита от исчерпания токенов Gemini API).

---

## 5. Защита веб-сервера (Nginx, CORS, CSP)

1. **CORS:** Разрешать запросы только с домена, на котором развернут Mini App. Не использовать `Allow-Origin: *`.
2. **CSP (Content Security Policy):**
   ```nginx
   add_header Content-Security-Policy "default-src 'self'; script-src 'self' https://telegram.org; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; connect-src 'self' https://your-backend-domain.ru;";
   ```
3. **Запрет отображения в сторонних фреймах:**
   ```nginx
   add_header X-Frame-Options "SAMEORIGIN";
   # Разрешаем фрейминг только внутри Telegram webview
   ```
