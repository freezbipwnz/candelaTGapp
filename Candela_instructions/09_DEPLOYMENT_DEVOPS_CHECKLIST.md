# Развертывание и DevOps чек-лист (Docker, Nginx, SSL, Production)

В этом документе приведена пошаговая инструкция по развертыванию экосистемы **Candela Home** на виртуальном сервере (VPS) под управлением Ubuntu Linux с использованием Docker Compose, Nginx и бесплатных SSL-сертификатов Let's Encrypt.

---

## 1. Подготовка сервера

1. **Аренда сервера**:
   * Сервер должен физически располагаться в РФ (согласно 152-ФЗ): Selectel, Timeweb Cloud, Beget, VK Cloud.
   * Минимальные характеристики: 2 CPU, 2–4 GB RAM, 30 GB SSD.
2. **Настройка DNS**:
   * Направьте А-запись вашего домена (например: `candela-shop.ru` и `api.candela-shop.ru`) на IP-адрес арендованного VPS.
3. **Установка системных пакетов**:
   ```bash
   sudo apt update && sudo apt upgrade -y
   sudo apt install -y curl git ufw
   
   # Установка Docker и Docker Compose
   curl -fsSL https://get.docker.com -o get-docker.sh
   sudo sh get-docker.sh
   sudo usermod -aG docker $USER
   
   # Настройка фаервола UFW
   sudo ufw allow 22/tcp
   sudo ufw allow 80/tcp
   sudo ufw allow 443/tcp
   sudo ufw enable
   ```

---

## 2. Конфигурация Docker Compose

Файл: `Candela_Home/docker-compose.yml`

```yaml
version: '3.8'

services:
  db:
    image: postgres:16-alpine
    container_name: candela_postgres
    restart: always
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - pgdata:/var/lib/postgresql/data
    networks:
      - candela_net

  redis:
    image: redis:7-alpine
    container_name: candela_redis
    restart: always
    command: redis-server --appendonly yes --requirepass ${REDIS_PASSWORD}
    volumes:
      - redisdata:/data
    networks:
      - candela_net

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: candela_backend
    restart: always
    env_file:
      - .env
    depends_on:
      - db
      - redis
    networks:
      - candela_net

  bot_client:
    build:
      context: ./bot_client
      dockerfile: Dockerfile
    container_name: candela_bot_client
    restart: always
    env_file:
      - .env
    depends_on:
      - backend
    networks:
      - candela_net

  bot_admin:
    build:
      context: ./bot_admin
      dockerfile: Dockerfile
    container_name: candela_bot_admin
    restart: always
    env_file:
      - .env
    depends_on:
      - backend
    networks:
      - candela_net

  nginx:
    image: nginx:alpine
    container_name: candela_nginx
    restart: always
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./frontend_miniapp/dist:/usr/share/nginx/html:ro
      - /etc/letsencrypt:/etc/letsencrypt:ro
    depends_on:
      - backend
    networks:
      - candela_net

volumes:
  pgdata:
  redisdata:

networks:
  candela_net:
    driver: bridge
```

---

## 3. Конфигурация Nginx и SSL (HTTPS)

Telegram Mini App открывается **исключительно по HTTPS**.

Файл: `Candela_Home/nginx.conf`

```nginx
events {
    worker_connections 1024;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;
    sendfile on;
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml;

    # Редирект HTTP -> HTTPS
    server {
        listen 80;
        server_name candela-shop.ru api.candela-shop.ru;
        return 301 https://$host$request_uri;
    }

    # Сервер Telegram Mini App и API
    server {
        listen 443 ssl http2;
        server_name candela-shop.ru;

        ssl_certificate /etc/letsencrypt/live/candela-shop.ru/fullchain.pem;
        ssl_certificate_key /etc/letsencrypt/live/candela-shop.ru/privkey.pem;

        # Безопасные заголовки
        add_header X-Content-Type-Options nosniff;
        add_header X-XSS-Protection "1; mode=block";

        # Статика фронтенда (React Mini App)
        location / {
            root /usr/share/nginx/html;
            index index.html;
            try_files $uri $uri/ /index.html;
        }

        # Бэкенд API
        location /api/ {
            proxy_pass http://backend:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto https;
        }
    }
}
```

---

## 4. Выпуск бесплатного SSL-сертификата (Certbot)

Перед запуском Nginx в Docker выпустите сертификат через автономный Certbot:
```bash
sudo apt install -y certbot
sudo certbot certonly --standalone -d candela-shop.ru -d api.candela-shop.ru
```

---

## 5. Шаблон файла окружения `.env`

Создайте в папке `Candela_Home/.env`:

```env
# Окружение
ENVIRONMENT=production
DEBUG=False

# База данных
POSTGRES_USER=candela_user
POSTGRES_PASSWORD=super_secret_db_password_123
POSTGRES_DB=candela_db
DATABASE_URL=postgresql+asyncpg://candela_user:super_secret_db_password_123@db:5432/candela_db

# Redis
REDIS_PASSWORD=super_secret_redis_password_456
REDIS_URL=redis://:super_secret_redis_password_456@redis:6379/0

# Telegram Bots
CLIENT_BOT_TOKEN=123456789:AA...ВАШ_ТОКЕН_КЛИЕНТСКОГО_БОТА
ADMIN_BOT_TOKEN=987654321:BB...ВАШ_ТОКЕН_АДМИНСКОГО_БОТА
ADMIN_TELEGRAM_IDS=12345678,87654321

# Mini App URL
MINI_APP_URL=https://candela-shop.ru

# ИИ (Gemini API)
GEMINI_API_KEY=AIzaSy...ВАШ_КЛЮЧ_GEMINI

# Эквайринг ЮKassa (54-ФЗ)
YOOKASSA_SHOP_ID=123456
YOOKASSA_SECRET_KEY=live_...ВАШ_КЛЮЧ_ЮКАССЫ
```

---

## 6. Резервное копирование (Backup Cron)

Автоматический ежедневный бэкап базы данных PostgreSQL в 03:00 ночи:
```bash
crontab -e
```
Добавьте строку:
```bash
0 3 * * * docker exec candela_postgres pg_dump -U candela_user candela_db | gzip > /home/ubuntu/backups/candela_backup_$(date +\%F).sql.gz
```
