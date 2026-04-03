# Railway setup

## Repo

Один repo: `inet-vpn-core`

## Services

- `inet-postgres`
- `inet-api`
- `inet-bot`

## Build / Start

### inet-api

Build command:

```bash
npm install
```

Start command:

```bash
npm run start:api
```

### inet-bot

Build command:

```bash
npm install
```

Start command:

```bash
npm run start:bot
```

## Variables

Одинаковые env можно прокинуть в оба сервиса, кроме `PORT` — Railway сам подставит если надо.

Минимум обязательно:

- `DATABASE_URL`
- `JWT_SECRET`
- `ADMIN_BASIC_USER`
- `ADMIN_BASIC_PASS`
- `BOT_TOKEN`
- `APP_BASE_URL`
- `SUPPORT_TELEGRAM_URL`

## Domains

Для `inet-api` добавь public domain.

Пример:

- `api.inet.example.com`

## Admin panel

Если хочешь, можешь открыть готовую страницу так:

- загрузить `admin/status-dashboard.inet-vpn.html` в свой admin repo
- либо раздавать `/admin/status-dashboard.inet-vpn.html` с backend

Но если ARBPanel уже отдельная и рабочая, правильнее держать её отдельно и использовать `admin-addon/`.
