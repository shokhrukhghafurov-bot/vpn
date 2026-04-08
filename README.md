# INET VPN bundle — Hiddify + personal subscriptions

Included:

- `backend.py` — FastAPI backend
- `db_store.py` — PostgreSQL store, VPN users, plans, payments, personal subscription tokens
- `config.py` — env settings and default Hiddify/plan settings
- `bot.py` — Telegram bot worker for buy / pay / access flow
- `admin/status-dashboard.html` — admin panel page with VPN settings and 1/2/3-device plan pricing
- `deploy/` — helper templates and env examples

## What changed

### Hiddify flow

The bundle no longer depends on your own APK.

The user flow is:

1. User opens the Telegram bot
2. Chooses a tariff in the bot
3. Pays through the bot flow
4. After payment, the bot shows:
   - Hiddify download buttons for Android / iPhone / Windows / macOS
   - a personal subscription URL
   - an `Open in Hiddify` button
5. The backend bridge page `/open-app?token=...` redirects the user into Hiddify import
   - temporary `/open-app?code=...` links are also resolved to the user's personal subscription token
6. Hiddify imports `/sub/<personal_token>` and the user connects

### Personal subscription links

Each VPN user now gets a **personal `subscription_token`** stored in the database.

- `/subscriptions/me` returns the personal token and full personal subscription URL
- `/sub/<token>` now supports per-user access
- legacy shared `SUBSCRIPTION_TOKEN` access is disabled by default and must be explicitly enabled if needed
- payment activation automatically ensures a personal token exists
- the bot uses the personal token in all Hiddify/open/import links

### Plans by device count

The project now uses **four plan slots**:

- `daily` — 1 day / 1 device
- `monthly_1` — 30 days / 1 device
- `monthly_2` — 30 days / 2 devices
- `monthly_3` — 30 days / 3 devices

Each slot has its own:

- code
- RU/EN name
- price
- duration
- device limit
- active flag

The admin page can edit these prices and limits and save them into the database through:

- `GET /api/infra/admin/vpn/settings`
- `POST /api/infra/admin/vpn/settings`

## Important note about device limits

This bundle now supports:

- per-user personal subscription links
- tariff pricing for 1 / 2 / 3 devices
- device limit values in backend/admin/bot logic

But **true hard enforcement of “this token works only on exactly one physical device” is not fully possible with raw Hiddify/VLESS subscription links alone**.

For strict one-device-only enforcement, your VPN server must issue separate client credentials (for example separate UUID/client entries) per device or per user-device slot.

With the current bundle, the business logic, pricing and access flow are ready, but hard physical-device locking requires server-side provisioning.

## New env settings

Main additions:

- `WINDOWS_APP_URL`
- `MACOS_APP_URL`
- `HIDDIFY_IMPORT_NAME`
- `PLAN_DAILY_*`
- `PLAN_MONTHLY_1_*`
- `PLAN_MONTHLY_2_*`
- `PLAN_MONTHLY_3_*`
- `VPN_DEFAULT_DEVICE_LIMIT`
- `VPN_MAX_DEVICES_PER_ACCOUNT`

See `.env.example` for all values.

