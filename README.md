# INET VPN core repo

Этот архив для **основного repo**:

- backend API
- Telegram bot
- PostgreSQL bootstrap
- env-first тарифы и лимиты
- payment-ready логика под Yookassa

## Что внутри

- `src/` — API, bot, services, db
- `scripts/` — migrate, sync plans, check
- `docs/SEPARATE_ADMIN_REPO.md` — как подключить отдельный repo админки
- `.env.example` — шаблон env для Railway

## Что не входит

В этот архив **не входит admin panel**, потому что она у тебя лежит в другом repo.
Для панели используй отдельный архив admin repo.

## Как класть в GitHub

Создай repo, например `inet-vpn-core`, и положи в корень:

- `.env.example`
- `.gitignore`
- `package.json`
- `package-lock.json`
- `README.md`
- `RAILWAY_SETUP.md`
- `src/`
- `scripts/`
- `docs/`

## Railway

Создай 3 сервиса:

1. `inet-postgres` — PostgreSQL
2. `inet-api` — Start Command: `npm run start:api`
3. `inet-bot` — Start Command: `npm run start:bot`

Все основные env уже перечислены в `.env.example` и `RAILWAY_SETUP.md`.

## Проверка

```bash
npm install
npm run check
npm run migrate
npm run start:api
npm run start:bot
```
