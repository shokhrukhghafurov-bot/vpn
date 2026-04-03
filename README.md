# INET Python core

Минимальный Python repo под твой план.

## Файлы

- `backend.py` - весь FastAPI backend
- `bot.py` - Telegram bot
- `db_store.py` - PostgreSQL schema + все SQL helper функции
- `config.py` - env конфиг
- `requirements.txt`
- `.env.example`
- `railway.json`

## Что уже готово

- PostgreSQL таблицы создаются автоматически при старте backend
- планы синхронизируются из Railway env
- бот берет тарифы из API
- VPN admin API готов
- YooKassa модуль подготовлен
- если `PAYMENTS_ENABLED=false`, оплаты не ломают backend и возвращают статус disabled

## API

### Public / App / Bot

- `POST /auth/telegram`
- `POST /auth/code`
- `GET /auth/me`
- `GET /plans`
- `GET /subscriptions/me`
- `GET /devices`
- `POST /devices/register`
- `DELETE /devices/{id}`
- `GET /locations`
- `GET /locations/status`
- `POST /payments/create`
- `GET /payments/{id}`
- `POST /payments/webhook/yookassa`

### Admin VPN

Basic Auth через `ADMIN_BASIC_USER` и `ADMIN_BASIC_PASS`.

- `GET /api/infra/admin/vpn/users`
- `POST /api/infra/admin/vpn/users`
- `PATCH /api/infra/admin/vpn/users/{telegram_id}/block`
- `PATCH /api/infra/admin/vpn/users/{telegram_id}/unblock`
- `POST /api/infra/admin/vpn/users/{telegram_id}/extend`
- `POST /api/infra/admin/vpn/users/{telegram_id}/reset-devices`
- `GET /api/infra/admin/vpn/payments`
- `GET /api/infra/admin/vpn/payments/export.csv`
- `GET /api/infra/admin/vpn/locations`
- `POST /api/infra/admin/vpn/locations`
- `PATCH /api/infra/admin/vpn/locations/{id}`
- `GET /api/infra/admin/vpn/settings`
- `POST /api/infra/admin/vpn/settings`

## Railway

Сделай 3 сервиса:

1. `inet-postgres` - PostgreSQL
2. `inet-api` - этот repo, start command:

```bash
uvicorn backend:app --host 0.0.0.0 --port $PORT
```

3. `inet-bot` - этот же repo, start command:

```bash
python bot.py
```

В оба сервиса подай одинаковый `DATABASE_URL`.

## GitHub

В root repo положи эти файлы как есть.

## Важно

- мобильные приложения сейчас не включены
- admin panel вынесена в отдельный repo
- настройки тарифов и лимитов не хардкодятся в UI, а берутся из env -> backend -> API
