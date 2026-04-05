# Backend + admin bundle

Included:

- `backend.py` — FastAPI backend
- `db_store.py` — PostgreSQL store and location sync
- `config.py` — env settings and builtin locations catalog
- `bot.py` — Telegram bot worker
- `admin/status-dashboard.html` — admin panel with VPN location payload editor
- `deploy/` — LTE bridge templates and env examples

## LTE-ready changes

- admin locations API now returns `vpn_payload` for admin editing
- builtin catalog includes `ru-lte` and `uz-lte`
- admin panel includes `Edit payload` modal and RU/UZ LTE presets
- mobile app accepts both snake_case and camelCase VPN payload keys
