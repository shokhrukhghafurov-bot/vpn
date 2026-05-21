import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List


BUILTIN_MVP_LOCATIONS_JSON = (
    '[{"code":"auto-fastest","name_ru":"Авто | Самый быстрый","name_en":"Auto | Fastest","country_code":null,"is_active":true,"is_recommended":true,"is_reserve":false,"status":"online","sort_order":10},'
    '{"code":"auto-reserve","name_ru":"Авто | Самый быстрый резерв","name_en":"Auto | Fastest Reserve","country_code":null,"is_active":true,"is_recommended":false,"is_reserve":true,"status":"online","sort_order":20},'
    '{"code":"ru-lte","name_ru":"Россия LTE","name_en":"Russia LTE","country_code":"RU","is_active":true,"is_recommended":true,"is_reserve":false,"status":"offline","sort_order":30,"vpn_payload":{"engine":"xray","protocol":"vless","location_code":"ru-lte","remark":"Russia LTE","transport":"tcp","network":"tcp","security":"reality","flow":"xtls-rprx-vision","server_name":"","sni":"","fingerprint":"chrome","packet_encoding":"xudp","connect_mode":"tun","full_tunnel":false,"route_mode":"split","direct_ru":true,"direct_domains":[".ru",".su",".xn--p1ai"],"dns_servers":["1.1.1.1","8.8.8.8"]}},'
    '{"code":"ru-lte-reserve-1","name_ru":"Россия LTE | Резерв 1","name_en":"Russia LTE | Reserve 1","country_code":"RU","is_active":true,"is_recommended":false,"is_reserve":true,"status":"offline","sort_order":31,"vpn_payload":{"engine":"xray","protocol":"vless","location_code":"ru-lte-reserve-1","remark":"Russia LTE | Reserve 1","transport":"tcp","network":"tcp","security":"reality","flow":"xtls-rprx-vision","server_name":"","sni":"","fingerprint":"chrome","packet_encoding":"xudp","connect_mode":"tun","full_tunnel":false,"route_mode":"split","direct_ru":true,"direct_domains":[".ru",".su",".xn--p1ai"],"dns_servers":["1.1.1.1","8.8.8.8"]}},'
    '{"code":"ru-lte-reserve-2","name_ru":"Россия LTE | Резерв 2","name_en":"Russia LTE | Reserve 2","country_code":"RU","is_active":true,"is_recommended":false,"is_reserve":true,"status":"offline","sort_order":32,"vpn_payload":{"engine":"xray","protocol":"vless","location_code":"ru-lte-reserve-2","remark":"Russia LTE | Reserve 2","transport":"tcp","network":"tcp","security":"reality","flow":"xtls-rprx-vision","server_name":"","sni":"","fingerprint":"chrome","packet_encoding":"xudp","connect_mode":"tun","full_tunnel":false,"route_mode":"split","direct_ru":true,"direct_domains":[".ru",".su",".xn--p1ai"],"dns_servers":["1.1.1.1","8.8.8.8"]}},'
    '{"code":"ru-lte-reserve-3","name_ru":"Россия LTE | Резерв 3","name_en":"Russia LTE | Reserve 3","country_code":"RU","is_active":true,"is_recommended":false,"is_reserve":true,"status":"offline","sort_order":33,"vpn_payload":{"engine":"xray","protocol":"vless","location_code":"ru-lte-reserve-3","remark":"Russia LTE | Reserve 3","transport":"tcp","network":"tcp","security":"reality","flow":"xtls-rprx-vision","server_name":"","sni":"","fingerprint":"chrome","packet_encoding":"xudp","connect_mode":"tun","full_tunnel":false,"route_mode":"split","direct_ru":true,"direct_domains":[".ru",".su",".xn--p1ai"],"dns_servers":["1.1.1.1","8.8.8.8"]}},'
    '{"code":"intl-fast","name_ru":"Fast / International","name_en":"Fast / International","country_code":null,"is_active":true,"is_recommended":false,"is_reserve":false,"status":"offline","sort_order":80,"vpn_payload":{"engine":"xray","protocol":"vless","location_code":"intl-fast","remark":"Fast / International","transport":"tcp","network":"tcp","security":"reality","flow":"xtls-rprx-vision","server_name":"","sni":"","fingerprint":"chrome","packet_encoding":"xudp","dns_servers":["1.1.1.1","8.8.8.8"]}},'
    '{"code":"intl-fast-reserve-1","name_ru":"Fast / International | Reserve 1","name_en":"Fast / International | Reserve 1","country_code":null,"is_active":true,"is_recommended":false,"is_reserve":true,"status":"offline","sort_order":81,"vpn_payload":{"engine":"xray","protocol":"vless","location_code":"intl-fast-reserve-1","remark":"Fast / International | Reserve 1","transport":"tcp","network":"tcp","security":"reality","flow":"xtls-rprx-vision","server_name":"","sni":"","fingerprint":"chrome","packet_encoding":"xudp","dns_servers":["1.1.1.1","8.8.8.8"]}},'
    '{"code":"intl-fast-reserve-2","name_ru":"Fast / International | Reserve 2","name_en":"Fast / International | Reserve 2","country_code":null,"is_active":true,"is_recommended":false,"is_reserve":true,"status":"offline","sort_order":82,"vpn_payload":{"engine":"xray","protocol":"vless","location_code":"intl-fast-reserve-2","remark":"Fast / International | Reserve 2","transport":"tcp","network":"tcp","security":"reality","flow":"xtls-rprx-vision","server_name":"","sni":"","fingerprint":"chrome","packet_encoding":"xudp","dns_servers":["1.1.1.1","8.8.8.8"]}},'
    '{"code":"intl-fast-reserve-3","name_ru":"Fast / International | Reserve 3","name_en":"Fast / International | Reserve 3","country_code":null,"is_active":true,"is_recommended":false,"is_reserve":true,"status":"offline","sort_order":83,"vpn_payload":{"engine":"xray","protocol":"vless","location_code":"intl-fast-reserve-3","remark":"Fast / International | Reserve 3","transport":"tcp","network":"tcp","security":"reality","flow":"xtls-rprx-vision","server_name":"","sni":"","fingerprint":"chrome","packet_encoding":"xudp","dns_servers":["1.1.1.1","8.8.8.8"]}},'
    '{"code":"se","name_ru":"Sweden","name_en":"Sweden","country_code":"SE","is_active":true,"is_recommended":false,"is_reserve":false,"status":"online","sort_order":40},'
    '{"code":"nl-1","name_ru":"Нидерланды","name_en":"Netherlands","country_code":"NL","is_active":true,"is_recommended":false,"is_reserve":false,"status":"online","sort_order":50},'
    '{"code":"de-1","name_ru":"Германия","name_en":"Germany","country_code":"DE","is_active":true,"is_recommended":false,"is_reserve":false,"status":"online","sort_order":60},'
    '{"code":"fi-1","name_ru":"Финляндия","name_en":"Finland","country_code":"FI","is_active":true,"is_recommended":false,"is_reserve":false,"status":"online","sort_order":70}]'
)


PLAN_SLOTS = ("daily", "monthly_1", "monthly_2", "monthly_3")


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _env_list(name: str, default: str = "") -> List[str]:
    value = os.getenv(name, default)
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_json_object(raw: str) -> Dict[str, Any]:
    if not raw or not raw.strip():
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _normalize_store_url(value: str, platform: str) -> str:
    raw = (value or "").strip()
    defaults = {
        "android": "https://app.hiddify.com/play",
        "ios": "https://app.hiddify.com/ios",
        "windows": "https://app.hiddify.com/windows",
        "macos": "https://app.hiddify.com/mac",
    }
    fallback = defaults.get(platform, "")
    if not raw:
        return fallback
    lowered = raw.lower()
    legacy_markers = (
        "/static/inet.apk",
        "com.example.inet",
        "com.inet.app",
        "inet.apk",
    )
    if any(marker in lowered for marker in legacy_markers):
        return fallback
    return raw


def _normalize_android_package(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return "app.hiddify.com"
    lowered = raw.lower()
    if lowered in {"com.example.inet", "com.inet.app"}:
        return "app.hiddify.com"
    return raw


def _vpn_configs_repo_raw_base() -> str:
    return (os.getenv("VPN_CONFIGS_REPO_RAW_BASE", "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/main") or "").strip().rstrip("/")


def _default_ru_lte_source_urls() -> str:
    base = _vpn_configs_repo_raw_base()
    # Keep RU LTE focused on the stricter mobile / checked white-list pools.
    # The broader *-all feed is intentionally excluded by default because it is
    # noisy and produces too many weak candidates that later fail local probes.
    return ",".join([
        f"{base}/Vless-Reality-White-Lists-Rus-Mobile.txt",
        f"{base}/Vless-Reality-White-Lists-Rus-Mobile-2.txt",
        f"{base}/WHITE-CIDR-RU-checked.txt",
    ])


def _default_black_source_urls() -> str:
    base = _vpn_configs_repo_raw_base()
    return ",".join([
        f"{base}/BLACK_VLESS_RUS_mobile.txt",
        f"{base}/BLACK_VLESS_RUS.txt",
    ])


@dataclass
class Settings:
    PORT: int = _env_int("PORT", 3000)
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/inet")
    JWT_SECRET: str = os.getenv("JWT_SECRET", "replace_me")
    CORS_ORIGINS: List[str] = None

    ADMIN_BASIC_USER: str = os.getenv("ADMIN_BASIC_USER", "admin")
    ADMIN_BASIC_PASS: str = os.getenv("ADMIN_BASIC_PASS", "change_me")

    # Railway cost-safe logging. Default: show only real errors, hide HTTP access/probe spam.
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "ERROR").strip().upper()
    UVICORN_ACCESS_LOG: bool = _env_bool("UVICORN_ACCESS_LOG", False)
    STARTUP_PROBE_LOG: bool = _env_bool("STARTUP_PROBE_LOG", False)
    VPN_VERBOSE_PROBE_LOGS: bool = _env_bool("VPN_VERBOSE_PROBE_LOGS", False)
    VPN_PROBE_ERROR_LOGS: bool = _env_bool("VPN_PROBE_ERROR_LOGS", False)
    SUBSCRIPTION_VERBOSE_LOGS: bool = _env_bool("SUBSCRIPTION_VERBOSE_LOGS", False)

    APP_NAME: str = os.getenv("APP_NAME", "INET")
    APP_ENV: str = os.getenv("APP_ENV", "production")
    APP_LANGS: List[str] = None
    APP_BASE_URL: str = os.getenv("APP_BASE_URL", "https://your-domain.com")
    ADMIN_PANEL_BASE_URL: str = os.getenv("ADMIN_PANEL_BASE_URL", "https://your-admin-domain.com")
    OPEN_APP_URL: str = os.getenv("OPEN_APP_URL", "")
    OPEN_APP_BRIDGE_URL: str = os.getenv("OPEN_APP_BRIDGE_URL", "")
    VPN_CLIENT_MODE: str = os.getenv("VPN_CLIENT_MODE", "hiddify")
    ANDROID_APP_URL: str = os.getenv("ANDROID_APP_URL", "https://app.hiddify.com/play")
    ANDROID_APP_PACKAGE: str = os.getenv("ANDROID_APP_PACKAGE", "app.hiddify.com")
    IOS_APP_URL: str = os.getenv("IOS_APP_URL", "https://app.hiddify.com/ios")
    WINDOWS_APP_URL: str = os.getenv("WINDOWS_APP_URL", "https://www.happ.su/main")
    MACOS_APP_URL: str = os.getenv("MACOS_APP_URL", "https://www.happ.su/main")
    HIDDIFY_ANDROID_APP_URL: str = os.getenv("HIDDIFY_ANDROID_APP_URL", os.getenv("ANDROID_APP_URL", "https://app.hiddify.com/play"))
    HIDDIFY_ANDROID_APP_PACKAGE: str = os.getenv("HIDDIFY_ANDROID_APP_PACKAGE", os.getenv("ANDROID_APP_PACKAGE", "app.hiddify.com"))
    HIDDIFY_IOS_APP_URL: str = os.getenv("HIDDIFY_IOS_APP_URL", os.getenv("IOS_APP_URL", "https://app.hiddify.com/ios"))
    HIDDIFY_WINDOWS_APP_URL: str = os.getenv("HIDDIFY_WINDOWS_APP_URL", "https://app.hiddify.com/windows")
    HIDDIFY_MACOS_APP_URL: str = os.getenv("HIDDIFY_MACOS_APP_URL", "https://app.hiddify.com/mac")
    HAPP_WINDOWS_APP_URL: str = os.getenv("HAPP_WINDOWS_APP_URL", os.getenv("WINDOWS_APP_URL", "https://www.happ.su/main"))
    HAPP_MACOS_APP_URL: str = os.getenv("HAPP_MACOS_APP_URL", os.getenv("MACOS_APP_URL", "https://www.happ.su/main"))
    # Happ can always show the final local Xray JSON inside the app.
    # This flag only keeps our subscription feed cleaner for Happ: no inline
    # subscription comments and no non-standard internal route hints in the URL.
    HAPP_SUBSCRIPTION_MINIMAL: bool = _env_bool("HAPP_SUBSCRIPTION_MINIMAL", False)
    # Keep v2RayTun subscriptions compatible: only standard VLESS/Reality
    # parameters are included by default.
    V2RAYTUN_SUBSCRIPTION_MINIMAL: bool = _env_bool("V2RAYTUN_SUBSCRIPTION_MINIMAL", True)
    V2RAYTUN_ANDROID_APP_URL: str = os.getenv("V2RAYTUN_ANDROID_APP_URL", "https://play.google.com/store/apps/details?id=com.v2raytun.android")
    V2RAYTUN_ANDROID_APP_PACKAGE: str = os.getenv("V2RAYTUN_ANDROID_APP_PACKAGE", "com.v2raytun.android")
    V2RAYTUN_IOS_APP_URL: str = os.getenv("V2RAYTUN_IOS_APP_URL", "https://v2raytun.com/")
    V2RAYTUN_WINDOWS_APP_URL: str = os.getenv("V2RAYTUN_WINDOWS_APP_URL", "https://v2raytun.com/")
    V2RAYTUN_MACOS_APP_URL: str = os.getenv("V2RAYTUN_MACOS_APP_URL", "https://v2raytun.com/")
    HIDDIFY_IMPORT_NAME: str = os.getenv("HIDDIFY_IMPORT_NAME", "INET Subscription")
    SUPPORT_TELEGRAM_URL: str = os.getenv("SUPPORT_TELEGRAM_URL", "https://t.me/your_admin")
    SUPPORT_FAQ_RU: str = os.getenv(
        "SUPPORT_FAQ_RU",
        "📩 Поддержка\n\nНапишите:\n• ваш Telegram ID (можно узнать у @userinfobot)\n• подробно опишите проблему\n• приложите скриншот\n\nМы ответим как можно быстрее.",
    )
    SUPPORT_FAQ_EN: str = os.getenv(
        "SUPPORT_FAQ_EN",
        "FAQ:\n1. Buy a plan in the bot.\n2. Install Hiddify.\n3. Open your personal subscription link.\n4. If something fails, contact support.",
    )

    BOT_NAME: str = os.getenv("BOT_NAME", "INET Bot")
    BOT_USERNAME: str = os.getenv("BOT_USERNAME", "inetvpnru_bot")
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    BACKEND_BASE_URL: str = os.getenv("BACKEND_BASE_URL", os.getenv("APP_BASE_URL", "http://127.0.0.1:3000"))
    BACKEND_HEALTH_PATH: str = os.getenv("BACKEND_HEALTH_PATH", "/healthz").strip() or "/healthz"
    BACKEND_REQUEST_TIMEOUT_SEC: int = _env_int("BACKEND_REQUEST_TIMEOUT_SEC", 12)
    BOT_BACKEND_STARTUP_RETRIES: int = _env_int("BOT_BACKEND_STARTUP_RETRIES", 6)
    BOT_BACKEND_STARTUP_RETRY_DELAY_SEC: int = _env_int("BOT_BACKEND_STARTUP_RETRY_DELAY_SEC", 5)
    BOT_SKIP_BACKEND_STARTUP_CHECK: bool = _env_bool("BOT_SKIP_BACKEND_STARTUP_CHECK", False)
    BOT_NOTIFICATION_POLL_SEC: int = _env_int("BOT_NOTIFICATION_POLL_SEC", 45)
    SUBSCRIPTION_WARNING_HOURS: int = _env_int("SUBSCRIPTION_WARNING_HOURS", 12)
    SUBSCRIPTION_TOKEN: str = os.getenv("SUBSCRIPTION_TOKEN", "")
    LEGACY_GLOBAL_SUBSCRIPTION_TOKEN_ENABLED: bool = _env_bool("LEGACY_GLOBAL_SUBSCRIPTION_TOKEN_ENABLED", False)
    # Security: user-wide /sub token is only for bot/open-app bridge.
    # Real VPN clients receive a one-device token that binds on first import.
    DEVICE_TOKEN_REQUIRED_FOR_SUBSCRIPTION: bool = _env_bool("DEVICE_TOKEN_REQUIRED_FOR_SUBSCRIPTION", True)
    # Temporary migration mode for old profiles imported before the dt_
    # per-device token flow. When enabled, /sub/<user_token> keeps returning
    # the template/shared UUID from the location payload, while new /sub/dt_...
    # profiles still receive personal per-device UUIDs. Use only for a short
    # migration window, then switch it off and remove legacy UUIDs from 3X-UI.
    LEGACY_USER_TOKEN_GRACE_ENABLED: bool = _env_bool("LEGACY_USER_TOKEN_GRACE_ENABLED", False)
    # Compatibility for profiles that were imported before the one-device dt_ token flow.
    # When enabled, old /sub/<user_token> profiles are still passed through the
    # device gate and are automatically recorded as one real device instead of
    # returning HTTP 403 in VPN clients.
    DEVICE_TOKEN_AUTO_MIGRATE_USER_TOKEN: bool = _env_bool("DEVICE_TOKEN_AUTO_MIGRATE_USER_TOKEN", True)
    DEVICE_TOKEN_STRICT_BINDING: bool = _env_bool("DEVICE_TOKEN_STRICT_BINDING", True)
    # Some VPN apps keep /sub/dt_... but drop query params like subcid on manual
    # refresh. If the dt_ token is already bound to a reserved device slot, allow
    # the refresh to continue instead of returning HTTP 403. First import still
    # requires the original bot/open-app link with subcid.
    DEVICE_TOKEN_ALLOW_BOUND_REFRESH_WITHOUT_SUBCID: bool = _env_bool("DEVICE_TOKEN_ALLOW_BOUND_REFRESH_WITHOUT_SUBCID", True)
    DEVICE_TOKEN_BIND_IP_ENABLED: bool = _env_bool("DEVICE_TOKEN_BIND_IP_ENABLED", False)
    DEVICE_TOKEN_TTL_HOURS: int = _env_int("DEVICE_TOKEN_TTL_HOURS", 0)
    # Pending slots are created when the bot shows /sub/dt_... buttons, before
    # the VPN app imports the link. Keep the slot reserved so users cannot
    # generate many unused links, but automatically release old pending slots.
    DEVICE_PENDING_SLOT_TTL_HOURS: int = _env_int("DEVICE_PENDING_SLOT_TTL_HOURS", 24)
    SUBSCRIPTION_SHOW_DIRECT_COPY_IN_BOT: bool = _env_bool("SUBSCRIPTION_SHOW_DIRECT_COPY_IN_BOT", False)
    # When a /sub/dt_... link is used, replace template/static UUIDs with a UUID
    # that belongs to this exact device slot. This is required if old imported
    # configs must stop after 🗑 Delete device. Your Xray side must sync these UUIDs.
    DEVICE_UUID_REQUIRED_FOR_SUBSCRIPTION: bool = _env_bool("DEVICE_UUID_REQUIRED_FOR_SUBSCRIPTION", True)
    XRAY_SYNC_WEBHOOK_URL: str = os.getenv("XRAY_SYNC_WEBHOOK_URL", "").strip()
    XRAY_SYNC_WEBHOOK_TOKEN: str = os.getenv("XRAY_SYNC_WEBHOOK_TOKEN", "").strip()
    XRAY_SYNC_TIMEOUT_SEC: int = _env_int("XRAY_SYNC_TIMEOUT_SEC", 8)
    XRAY_SYNC_ON_SUBSCRIPTION: bool = _env_bool("XRAY_SYNC_ON_SUBSCRIPTION", True)
    XRAY_SYNC_MIN_INTERVAL_SEC: int = _env_int("XRAY_SYNC_MIN_INTERVAL_SEC", 60)
    # Direct 3X-UI API sync. Use this when locations are created in 3X-UI and
    # added to the admin panel as templates with xui_inbound_id. Backend adds
    # one managed 3X-UI client per device UUID and removes it when the device
    # is deleted, so raw imported VLESS links stop working too.
    XUI_SYNC_ENABLED: bool = _env_bool("XUI_SYNC_ENABLED", False)
    XUI_BASE_URL: str = os.getenv("XUI_BASE_URL", "").strip()
    XUI_USERNAME: str = os.getenv("XUI_USERNAME", os.getenv("XUI_ADMIN_USER", "")).strip()
    XUI_PASSWORD: str = os.getenv("XUI_PASSWORD", os.getenv("XUI_ADMIN_PASS", "")).strip()
    XUI_TOKEN: str = os.getenv("XUI_TOKEN", "").strip()
    XUI_SERVERS_JSON: str = os.getenv("XUI_SERVERS_JSON", "").strip()
    XUI_DEFAULT_SERVER_KEY: str = os.getenv("XUI_DEFAULT_SERVER_KEY", "default").strip() or "default"
    XUI_CLIENT_EMAIL_PREFIX: str = os.getenv("XUI_CLIENT_EMAIL_PREFIX", "inet:").strip() or "inet:"
    XUI_TIMEOUT_SEC: int = _env_int("XUI_TIMEOUT_SEC", 8)
    XUI_VERIFY_SSL: bool = _env_bool("XUI_VERIFY_SSL", False)
    XUI_SSL_AUTO_FALLBACK: bool = _env_bool("XUI_SSL_AUTO_FALLBACK", True)
    XUI_DRY_RUN: bool = _env_bool("XUI_DRY_RUN", False)

    AUTH_DEV_LOGIN_CODE: str = os.getenv("AUTH_DEV_LOGIN_CODE", "111111")
    AUTH_ALLOW_DEV_CODE: bool = _env_bool("AUTH_ALLOW_DEV_CODE", True)
    AUTH_ACCESS_TOKEN_MINUTES: int = _env_int("AUTH_ACCESS_TOKEN_MINUTES", 60)
    AUTH_REFRESH_TOKEN_DAYS: int = _env_int("AUTH_REFRESH_TOKEN_DAYS", 90)
    AUTH_CODE_TTL_MINUTES: int = _env_int("AUTH_CODE_TTL_MINUTES", 5)
    AUTH_CODE_ISSUER_SECRET: str = os.getenv("AUTH_CODE_ISSUER_SECRET", "")

    VPN_DEFAULT_DEVICE_LIMIT: int = _env_int("VPN_DEFAULT_DEVICE_LIMIT", 1)
    VPN_MAX_DEVICES_PER_ACCOUNT: int = _env_int("VPN_MAX_DEVICES_PER_ACCOUNT", 3)
    VPN_MAINTENANCE_MODE: bool = _env_bool("VPN_MAINTENANCE_MODE", False)
    VPN_NEW_ACTIVATIONS_ENABLED: bool = _env_bool("VPN_NEW_ACTIVATIONS_ENABLED", True)
    VPN_SETTINGS_EDITABLE: bool = _env_bool("VPN_SETTINGS_EDITABLE", False)

    PLAN_DAILY_ENABLED: bool = _env_bool("PLAN_DAILY_ENABLED", True)
    PLAN_DAILY_CODE: str = os.getenv("PLAN_DAILY_CODE", "plan-daily")
    PLAN_DAILY_NAME_RU: str = os.getenv("PLAN_DAILY_NAME_RU", "1 день · 1 устройство")
    PLAN_DAILY_NAME_EN: str = os.getenv("PLAN_DAILY_NAME_EN", "1 day · 1 device")
    PLAN_DAILY_PRICE_RUB: int = _env_int("PLAN_DAILY_PRICE_RUB", 59)
    PLAN_DAILY_DURATION_DAYS: int = 1
    PLAN_DAILY_DEVICE_LIMIT: int = 1

    PLAN_MONTHLY_1_ENABLED: bool = _env_bool("PLAN_MONTHLY_1_ENABLED", True)
    PLAN_MONTHLY_1_CODE: str = os.getenv("PLAN_MONTHLY_1_CODE", "plan-monthly-1-device")
    PLAN_MONTHLY_1_NAME_RU: str = os.getenv("PLAN_MONTHLY_1_NAME_RU", "1 месяц · 1 устройство")
    PLAN_MONTHLY_1_NAME_EN: str = os.getenv("PLAN_MONTHLY_1_NAME_EN", "1 month · 1 device")
    PLAN_MONTHLY_1_PRICE_RUB: int = _env_int("PLAN_MONTHLY_1_PRICE_RUB", 299)
    PLAN_MONTHLY_1_DURATION_DAYS: int = 30
    PLAN_MONTHLY_1_DEVICE_LIMIT: int = 1

    PLAN_MONTHLY_2_ENABLED: bool = _env_bool("PLAN_MONTHLY_2_ENABLED", True)
    PLAN_MONTHLY_2_CODE: str = os.getenv("PLAN_MONTHLY_2_CODE", "plan-monthly-2-devices")
    PLAN_MONTHLY_2_NAME_RU: str = os.getenv("PLAN_MONTHLY_2_NAME_RU", "1 месяц · 2 устройства")
    PLAN_MONTHLY_2_NAME_EN: str = os.getenv("PLAN_MONTHLY_2_NAME_EN", "1 month · 2 devices")
    PLAN_MONTHLY_2_PRICE_RUB: int = _env_int("PLAN_MONTHLY_2_PRICE_RUB", 499)
    PLAN_MONTHLY_2_DURATION_DAYS: int = 30
    PLAN_MONTHLY_2_DEVICE_LIMIT: int = 2

    PLAN_MONTHLY_3_ENABLED: bool = _env_bool("PLAN_MONTHLY_3_ENABLED", True)
    PLAN_MONTHLY_3_CODE: str = os.getenv("PLAN_MONTHLY_3_CODE", "plan-monthly-3-devices")
    PLAN_MONTHLY_3_NAME_RU: str = os.getenv("PLAN_MONTHLY_3_NAME_RU", "1 месяц · 3 устройства")
    PLAN_MONTHLY_3_NAME_EN: str = os.getenv("PLAN_MONTHLY_3_NAME_EN", "1 month · 3 devices")
    PLAN_MONTHLY_3_PRICE_RUB: int = _env_int("PLAN_MONTHLY_3_PRICE_RUB", 699)
    PLAN_MONTHLY_3_DURATION_DAYS: int = 30
    PLAN_MONTHLY_3_DEVICE_LIMIT: int = 3

    PAYMENTS_PROVIDER: str = os.getenv("PAYMENTS_PROVIDER", "robokassa")
    PAYMENTS_ENABLED: bool = _env_bool("PAYMENTS_ENABLED", False)
    PAYMENTS_COMMISSION_PERCENT: float = _env_float("PAYMENTS_COMMISSION_PERCENT", 0.0)
    YOOKASSA_SHOP_ID: str = os.getenv("YOOKASSA_SHOP_ID", "")
    YOOKASSA_SECRET_KEY: str = os.getenv("YOOKASSA_SECRET_KEY", "")
    YOOKASSA_RETURN_URL: str = os.getenv("YOOKASSA_RETURN_URL", "https://your-domain.com/payment/return")
    YOOKASSA_WEBHOOK_URL: str = os.getenv("YOOKASSA_WEBHOOK_URL", "https://your-domain.com/payments/webhook/yookassa")
    ROBOKASSA_MERCHANT_LOGIN: str = os.getenv("ROBOKASSA_MERCHANT_LOGIN", "")
    ROBOKASSA_PASSWORD1: str = os.getenv("ROBOKASSA_PASSWORD1", "")
    ROBOKASSA_PASSWORD2: str = os.getenv("ROBOKASSA_PASSWORD2", "")
    ROBOKASSA_PAYMENT_URL: str = os.getenv("ROBOKASSA_PAYMENT_URL", "https://auth.robokassa.ru/Merchant/Index.aspx")
    ROBOKASSA_RESULT_URL: str = os.getenv("ROBOKASSA_RESULT_URL", "")
    ROBOKASSA_SUCCESS_URL: str = os.getenv("ROBOKASSA_SUCCESS_URL", "")
    ROBOKASSA_FAIL_URL: str = os.getenv("ROBOKASSA_FAIL_URL", "")
    ROBOKASSA_CULTURE: str = os.getenv("ROBOKASSA_CULTURE", "ru")
    ROBOKASSA_HASH_ALGORITHM: str = os.getenv("ROBOKASSA_HASH_ALGORITHM", "md5")
    ROBOKASSA_IS_TEST: bool = _env_bool("ROBOKASSA_IS_TEST", False)
    ROBOKASSA_INCCURRLABEL: str = os.getenv("ROBOKASSA_INCCURRLABEL", "")

    DEFAULT_LOCATIONS_JSON: str = BUILTIN_MVP_LOCATIONS_JSON
    DEFAULT_LOCATIONS_ENV_JSON: str = os.getenv("DEFAULT_LOCATIONS_JSON", "")
    DEFAULT_LOCATIONS_ENV_OVERRIDE_ENABLED: bool = _env_bool("DEFAULT_LOCATIONS_ENV_OVERRIDE_ENABLED", False)

    VPN_ENGINE: str = os.getenv("VPN_ENGINE", "xray")
    VLESS_DEFAULT_CONFIG_JSON: str = os.getenv("VLESS_DEFAULT_CONFIG_JSON", "")
    VLESS_LOCATION_CONFIGS_JSON: str = os.getenv("VLESS_LOCATION_CONFIGS_JSON", "")
    VLESS_SERVER: str = os.getenv("VLESS_SERVER", "")
    VLESS_PORT: int = _env_int("VLESS_PORT", 443)
    VLESS_UUID: str = os.getenv("VLESS_UUID", "")
    VLESS_TRANSPORT: str = os.getenv("VLESS_TRANSPORT", "tcp")
    VLESS_SECURITY: str = os.getenv("VLESS_SECURITY", "reality")
    VLESS_FLOW: str = os.getenv("VLESS_FLOW", "")
    VLESS_SNI: str = os.getenv("VLESS_SNI", "")
    VLESS_HOST: str = os.getenv("VLESS_HOST", "")
    VLESS_PATH: str = os.getenv("VLESS_PATH", "")
    VLESS_SERVICE_NAME: str = os.getenv("VLESS_SERVICE_NAME", "")
    VLESS_PUBLIC_KEY: str = os.getenv("VLESS_PUBLIC_KEY", "")
    VLESS_SHORT_ID: str = os.getenv("VLESS_SHORT_ID", "")
    VLESS_FINGERPRINT: str = os.getenv("VLESS_FINGERPRINT", "chrome")
    VLESS_ALLOW_INSECURE: bool = _env_bool("VLESS_ALLOW_INSECURE", False)
    VLESS_DNS_SERVERS: List[str] = None
    VLESS_ALPN: List[str] = None
    VLESS_DOMAIN_RESOLVER: str = os.getenv("VLESS_DOMAIN_RESOLVER", "dns-remote")
    VLESS_PACKET_ENCODING: str = os.getenv("VLESS_PACKET_ENCODING", "xudp")
    VLESS_MTU: int = _env_int("VLESS_MTU", 1400)
    VLESS_RAW_SING_BOX_CONFIG: str = os.getenv("VLESS_RAW_SING_BOX_CONFIG", "")
    VLESS_RAW_XRAY_CONFIG: str = os.getenv("VLESS_RAW_XRAY_CONFIG", "")
    VLESS_ANTI_BLOCK_SNI_POOL: List[str] = None
    VLESS_ANTI_BLOCK_SNI_POOL_RU_LTE: List[str] = None
    VLESS_ANTI_BLOCK_SNI_POOL_INTL: List[str] = None

    RU_LTE_SOURCE_URLS: List[str] = None
    RU_LTE_REFRESH_ON_STARTUP: bool = _env_bool("RU_LTE_REFRESH_ON_STARTUP", True)
    RU_LTE_AUTO_REFRESH_ENABLED: bool = _env_bool("RU_LTE_AUTO_REFRESH_ENABLED", True)
    RU_LTE_AUTO_REFRESH_MINUTES: int = _env_int("RU_LTE_AUTO_REFRESH_MINUTES", 1)
    RU_LTE_AUTO_REFRESH_TIMEOUT_SEC: int = _env_int("RU_LTE_AUTO_REFRESH_TIMEOUT_SEC", 600)
    RU_LTE_MAX_CANDIDATES: int = _env_int("RU_LTE_MAX_CANDIDATES", 3)
    RU_LTE_TEST_LIMIT: int = _env_int("RU_LTE_TEST_LIMIT", 40)
    RU_LTE_CONNECT_TIMEOUT_SEC: int = _env_int("RU_LTE_CONNECT_TIMEOUT_SEC", 4)
    RU_LTE_DEAD_COOLDOWN_MINUTES: int = _env_int("RU_LTE_DEAD_COOLDOWN_MINUTES", 45)
    RU_LTE_ALLOWED_TRANSPORTS: List[str] = None
    # Keep RU LTE split routing close to the known-good external config: direct by explicit domains only, not broad geoip:ru.
    # geoip:ru direct can send Telegram/YouTube CDN IPs outside the tunnel and causes unstable video/messenger behavior.
    RU_LTE_GEOIP_DIRECT_ENABLED: bool = _env_bool("RU_LTE_GEOIP_DIRECT_ENABLED", False)
    RU_LTE_GEOSITE_DIRECT_ENABLED: bool = _env_bool("RU_LTE_GEOSITE_DIRECT_ENABLED", False)
    RU_LTE_REAL_PROBE_ENABLED: bool = _env_bool("RU_LTE_REAL_PROBE_ENABLED", True)
    RU_LTE_REAL_PROBE_REQUIRED: bool = _env_bool("RU_LTE_REAL_PROBE_REQUIRED", True)
    RU_LTE_REAL_PROBE_MIN_SUCCESS: int = _env_int("RU_LTE_REAL_PROBE_MIN_SUCCESS", 2)
    RU_LTE_REAL_PROBE_RUNNER: str = os.getenv("RU_LTE_REAL_PROBE_RUNNER", "xray")
    RU_LTE_REAL_PROBE_XRAY_BIN: str = os.getenv("RU_LTE_REAL_PROBE_XRAY_BIN", "xray")
    RU_LTE_REAL_PROBE_SINGBOX_BIN: str = os.getenv("RU_LTE_REAL_PROBE_SINGBOX_BIN", "sing-box")
    RU_LTE_REAL_PROBE_URLS: List[str] = None
    RU_LTE_REAL_PROBE_CONNECT_TIMEOUT_SEC: int = _env_int("RU_LTE_REAL_PROBE_CONNECT_TIMEOUT_SEC", 6)
    RU_LTE_REAL_PROBE_MAX_TIME_SEC: int = _env_int("RU_LTE_REAL_PROBE_MAX_TIME_SEC", 12)
    RU_LTE_REAL_PROBE_WARMUP_MS: int = _env_int("RU_LTE_REAL_PROBE_WARMUP_MS", 1200)
    VPN_REAL_PROBE_ENABLED: bool = _env_bool("VPN_REAL_PROBE_ENABLED", True)
    VPN_REAL_PROBE_REQUIRED: bool = _env_bool("VPN_REAL_PROBE_REQUIRED", True)
    VPN_REAL_PROBE_RUNNER: str = os.getenv("VPN_REAL_PROBE_RUNNER", os.getenv("RU_LTE_REAL_PROBE_RUNNER", "auto"))
    VPN_REAL_PROBE_XRAY_BIN: str = os.getenv("VPN_REAL_PROBE_XRAY_BIN", os.getenv("RU_LTE_REAL_PROBE_XRAY_BIN", "xray"))
    VPN_REAL_PROBE_SINGBOX_BIN: str = os.getenv("VPN_REAL_PROBE_SINGBOX_BIN", os.getenv("RU_LTE_REAL_PROBE_SINGBOX_BIN", "sing-box"))
    VPN_REAL_PROBE_URLS: List[str] = None
    VPN_REAL_PROBE_RU_EXTRA_URLS: List[str] = None
    VPN_REAL_PROBE_CONNECT_TIMEOUT_SEC: int = _env_int("VPN_REAL_PROBE_CONNECT_TIMEOUT_SEC", _env_int("RU_LTE_REAL_PROBE_CONNECT_TIMEOUT_SEC", 6))
    VPN_REAL_PROBE_MAX_TIME_SEC: int = _env_int("VPN_REAL_PROBE_MAX_TIME_SEC", _env_int("RU_LTE_REAL_PROBE_MAX_TIME_SEC", 12))
    VPN_REAL_PROBE_WARMUP_MS: int = _env_int("VPN_REAL_PROBE_WARMUP_MS", _env_int("RU_LTE_REAL_PROBE_WARMUP_MS", 1200))
    VPN_REAL_PROBE_MIN_SUCCESS: int = _env_int("VPN_REAL_PROBE_MIN_SUCCESS", 2)
    VPN_LIVE_CHECK_ON_STARTUP: bool = _env_bool("VPN_LIVE_CHECK_ON_STARTUP", True)
    VPN_LIVE_CHECK_AUTO_ENABLED: bool = _env_bool("VPN_LIVE_CHECK_AUTO_ENABLED", True)
    VPN_LIVE_CHECK_AUTO_MINUTES: int = _env_int("VPN_LIVE_CHECK_AUTO_MINUTES", 3)
    VPN_LIVE_CHECK_RETRY_SECONDS: int = _env_int("VPN_LIVE_CHECK_RETRY_SECONDS", 45)
    VPN_LIVE_CHECK_ACTIVE_ONLY: bool = _env_bool("VPN_LIVE_CHECK_ACTIVE_ONLY", True)
    HIDDIFY_SUBSCRIPTION_ALLOWED_TRANSPORTS: List[str] = None
    HIDDIFY_PROFILE_UPDATE_INTERVAL_HOURS: float = _env_float("HIDDIFY_PROFILE_UPDATE_INTERVAL_HOURS", 1.0)  # normalized to whole hours for Hiddify headers
    VIRTUAL_LOCATION_POOL_SIZE: int = _env_int("VIRTUAL_LOCATION_POOL_SIZE", 3)
    VIRTUAL_LOCATION_LOAD_IMBALANCE_THRESHOLD: int = _env_int("VIRTUAL_LOCATION_LOAD_IMBALANCE_THRESHOLD", 0)
    VIRTUAL_LOCATION_MAX_PING_BALANCE_DRIFT_MS: int = _env_int("VIRTUAL_LOCATION_MAX_PING_BALANCE_DRIFT_MS", 180)
    VIRTUAL_LOCATION_MAX_USERS_PER_SERVER: int = _env_int("VIRTUAL_LOCATION_MAX_USERS_PER_SERVER", 0)
    SUBSCRIPTION_ALLOW_READY_FALLBACK: bool = _env_bool("SUBSCRIPTION_ALLOW_READY_FALLBACK", True)
    USER_CONFIG_ALLOW_READY_FALLBACK: bool = _env_bool("USER_CONFIG_ALLOW_READY_FALLBACK", True)
    AUTO_VIRTUAL_ALLOW_READY_FALLBACK: bool = _env_bool("AUTO_VIRTUAL_ALLOW_READY_FALLBACK", True)
    VPN_REAL_PROBE_ALLOW_TCP_FALLBACK_ON_RUNNER_ERROR: bool = _env_bool("VPN_REAL_PROBE_ALLOW_TCP_FALLBACK_ON_RUNNER_ERROR", False)
    SUBSCRIPTION_STRICT_FRESH_PING_MINUTES: int = _env_int("SUBSCRIPTION_STRICT_FRESH_PING_MINUTES", 20)
    SUBSCRIPTION_BROWSER_PREVIEW_NO_DEVICE_TRACK: bool = _env_bool("SUBSCRIPTION_BROWSER_PREVIEW_NO_DEVICE_TRACK", True)

    BLACK_SOURCE_URLS: List[str] = None
    BLACK_REFRESH_ON_STARTUP: bool = _env_bool("BLACK_REFRESH_ON_STARTUP", True)
    BLACK_AUTO_REFRESH_ENABLED: bool = _env_bool("BLACK_AUTO_REFRESH_ENABLED", True)
    BLACK_AUTO_REFRESH_MINUTES: int = _env_int("BLACK_AUTO_REFRESH_MINUTES", 1)
    BLACK_AUTO_REFRESH_TIMEOUT_SEC: int = _env_int("BLACK_AUTO_REFRESH_TIMEOUT_SEC", 600)
    BLACK_MAX_CANDIDATES: int = _env_int("BLACK_MAX_CANDIDATES", 3)
    BLACK_TEST_LIMIT: int = _env_int("BLACK_TEST_LIMIT", 40)
    BLACK_CONNECT_TIMEOUT_SEC: int = _env_int("BLACK_CONNECT_TIMEOUT_SEC", 4)
    BLACK_DEAD_COOLDOWN_MINUTES: int = _env_int("BLACK_DEAD_COOLDOWN_MINUTES", 30)
    BLACK_ALLOWED_TRANSPORTS: List[str] = None
    BLACK_REAL_PROBE_REQUIRED: bool = _env_bool("BLACK_REAL_PROBE_REQUIRED", True)
    BLACK_REAL_PROBE_MIN_SUCCESS: int = _env_int("BLACK_REAL_PROBE_MIN_SUCCESS", _env_int("VPN_REAL_PROBE_MIN_SUCCESS", 2))

    def __post_init__(self) -> None:
        self.ANDROID_APP_URL = _normalize_store_url(self.ANDROID_APP_URL, "android")
        self.IOS_APP_URL = _normalize_store_url(self.IOS_APP_URL, "ios")
        self.WINDOWS_APP_URL = _normalize_store_url(self.WINDOWS_APP_URL, "windows")
        self.MACOS_APP_URL = _normalize_store_url(self.MACOS_APP_URL, "macos")
        self.ANDROID_APP_PACKAGE = _normalize_android_package(self.ANDROID_APP_PACKAGE)
        if self.CORS_ORIGINS is None:
            self.CORS_ORIGINS = _env_list("CORS_ORIGINS", "*")
        if self.APP_LANGS is None:
            self.APP_LANGS = _env_list("APP_LANGS", "ru,en")
        if self.VLESS_DNS_SERVERS is None:
            self.VLESS_DNS_SERVERS = _env_list("VLESS_DNS_SERVERS", "1.1.1.1,8.8.8.8")
        if self.VLESS_ALPN is None:
            self.VLESS_ALPN = _env_list("VLESS_ALPN", "")
        if self.VLESS_ANTI_BLOCK_SNI_POOL is None:
            self.VLESS_ANTI_BLOCK_SNI_POOL = _env_list("VLESS_ANTI_BLOCK_SNI_POOL", "")
        if self.VLESS_ANTI_BLOCK_SNI_POOL_RU_LTE is None:
            self.VLESS_ANTI_BLOCK_SNI_POOL_RU_LTE = _env_list("VLESS_ANTI_BLOCK_SNI_POOL_RU_LTE", ",".join(self.VLESS_ANTI_BLOCK_SNI_POOL or []))
        if self.VLESS_ANTI_BLOCK_SNI_POOL_INTL is None:
            self.VLESS_ANTI_BLOCK_SNI_POOL_INTL = _env_list("VLESS_ANTI_BLOCK_SNI_POOL_INTL", ",".join(self.VLESS_ANTI_BLOCK_SNI_POOL or []))
        if self.RU_LTE_ALLOWED_TRANSPORTS is None:
            self.RU_LTE_ALLOWED_TRANSPORTS = _env_list("RU_LTE_ALLOWED_TRANSPORTS", "grpc,tcp,ws,xhttp")
        if self.HIDDIFY_SUBSCRIPTION_ALLOWED_TRANSPORTS is None:
            self.HIDDIFY_SUBSCRIPTION_ALLOWED_TRANSPORTS = _env_list("HIDDIFY_SUBSCRIPTION_ALLOWED_TRANSPORTS", "grpc,tcp,ws,xhttp")
        if self.RU_LTE_SOURCE_URLS is None:
            self.RU_LTE_SOURCE_URLS = _env_list(
                "RU_LTE_SOURCE_URLS",
                _default_ru_lte_source_urls(),
            )
        if self.RU_LTE_REAL_PROBE_URLS is None:
            self.RU_LTE_REAL_PROBE_URLS = _env_list(
                "RU_LTE_REAL_PROBE_URLS",
                "https://www.youtube.com/generate_204,https://web.telegram.org/",
            )
        if self.VPN_REAL_PROBE_URLS is None:
            self.VPN_REAL_PROBE_URLS = _env_list(
                "VPN_REAL_PROBE_URLS",
                "https://www.youtube.com/generate_204,https://web.telegram.org/,https://www.instagram.com/",
            )
        if self.VPN_REAL_PROBE_RU_EXTRA_URLS is None:
            self.VPN_REAL_PROBE_RU_EXTRA_URLS = _env_list(
                "VPN_REAL_PROBE_RU_EXTRA_URLS",
                "https://www.youtube.com/generate_204,https://web.telegram.org/",
            )
        if self.BLACK_ALLOWED_TRANSPORTS is None:
            self.BLACK_ALLOWED_TRANSPORTS = _env_list("BLACK_ALLOWED_TRANSPORTS", "grpc,tcp,ws,xhttp")
        if self.BLACK_SOURCE_URLS is None:
            self.BLACK_SOURCE_URLS = _env_list(
                "BLACK_SOURCE_URLS",
                _default_black_source_urls(),
            )

    def default_vpn_payload(self) -> Dict[str, Any]:
        from_json = _parse_json_object(self.VLESS_DEFAULT_CONFIG_JSON)
        if from_json:
            return dict(from_json)
        if not (self.VLESS_SERVER.strip() and self.VLESS_UUID.strip()):
            return {}
        payload: Dict[str, Any] = {
            "protocol": "vless",
            "engine": self.VPN_ENGINE or "xray",
            "server": self.VLESS_SERVER.strip(),
            "port": int(self.VLESS_PORT or 443),
            "uuid": self.VLESS_UUID.strip(),
            "transport": (self.VLESS_TRANSPORT or "tcp").strip() or "tcp",
            "security": (self.VLESS_SECURITY or "reality").strip() or "reality",
            "dns_servers": list(self.VLESS_DNS_SERVERS or ["1.1.1.1", "8.8.8.8"]),
            "alpn": list(self.VLESS_ALPN or []),
            "allow_insecure": bool(self.VLESS_ALLOW_INSECURE),
            "mtu": int(self.VLESS_MTU or 1400),
            "domain_resolver": (self.VLESS_DOMAIN_RESOLVER or "dns-remote").strip() or "dns-remote",
            "packet_encoding": (self.VLESS_PACKET_ENCODING or "xudp").strip() or "xudp",
        }
        optional_values = {
            "flow": self.VLESS_FLOW,
            "sni": self.VLESS_SNI,
            "host": self.VLESS_HOST,
            "path": self.VLESS_PATH,
            "service_name": self.VLESS_SERVICE_NAME,
            "public_key": self.VLESS_PUBLIC_KEY,
            "short_id": self.VLESS_SHORT_ID,
            "fingerprint": self.VLESS_FINGERPRINT,
            "raw_sing_box_config": self.VLESS_RAW_SING_BOX_CONFIG,
            "raw_xray_config": self.VLESS_RAW_XRAY_CONFIG,
        }
        for key, value in optional_values.items():
            if isinstance(value, str) and value.strip():
                payload[key] = value.strip()
        return payload

    def location_vpn_payloads(self) -> Dict[str, Dict[str, Any]]:
        raw = _parse_json_object(self.VLESS_LOCATION_CONFIGS_JSON)
        out: Dict[str, Dict[str, Any]] = {}
        for key, value in raw.items():
            if isinstance(value, dict) and str(key).strip():
                out[str(key).strip()] = dict(value)
        return out

    def plan_definitions(self) -> List[Dict[str, Any]]:
        return [
            {
                "code": self.PLAN_DAILY_CODE,
                "name_ru": self.PLAN_DAILY_NAME_RU,
                "name_en": self.PLAN_DAILY_NAME_EN,
                "price_rub": self.PLAN_DAILY_PRICE_RUB,
                "duration_days": self.PLAN_DAILY_DURATION_DAYS,
                "device_limit": 1,
                "is_active": self.PLAN_DAILY_ENABLED,
                "source_env_key": "PLAN_DAILY",
            },
            {
                "code": self.PLAN_MONTHLY_1_CODE,
                "name_ru": self.PLAN_MONTHLY_1_NAME_RU,
                "name_en": self.PLAN_MONTHLY_1_NAME_EN,
                "price_rub": self.PLAN_MONTHLY_1_PRICE_RUB,
                "duration_days": self.PLAN_MONTHLY_1_DURATION_DAYS,
                "device_limit": self.PLAN_MONTHLY_1_DEVICE_LIMIT,
                "is_active": self.PLAN_MONTHLY_1_ENABLED,
                "source_env_key": "PLAN_MONTHLY_1",
            },
            {
                "code": self.PLAN_MONTHLY_2_CODE,
                "name_ru": self.PLAN_MONTHLY_2_NAME_RU,
                "name_en": self.PLAN_MONTHLY_2_NAME_EN,
                "price_rub": self.PLAN_MONTHLY_2_PRICE_RUB,
                "duration_days": self.PLAN_MONTHLY_2_DURATION_DAYS,
                "device_limit": self.PLAN_MONTHLY_2_DEVICE_LIMIT,
                "is_active": self.PLAN_MONTHLY_2_ENABLED,
                "source_env_key": "PLAN_MONTHLY_2",
            },
            {
                "code": self.PLAN_MONTHLY_3_CODE,
                "name_ru": self.PLAN_MONTHLY_3_NAME_RU,
                "name_en": self.PLAN_MONTHLY_3_NAME_EN,
                "price_rub": self.PLAN_MONTHLY_3_PRICE_RUB,
                "duration_days": self.PLAN_MONTHLY_3_DURATION_DAYS,
                "device_limit": self.PLAN_MONTHLY_3_DEVICE_LIMIT,
                "is_active": self.PLAN_MONTHLY_3_ENABLED,
                "source_env_key": "PLAN_MONTHLY_3",
            },
        ]


settings = Settings()


# Runtime access mode defaults
if not hasattr(settings, "VPN_ACCESS_MODE"):
    settings.VPN_ACCESS_MODE = "paid"
if not hasattr(settings, "VPN_FREE_MODE_DEVICE_LIMIT"):
    settings.VPN_FREE_MODE_DEVICE_LIMIT = max(1, int(getattr(settings, "VPN_DEFAULT_DEVICE_LIMIT", 1) or 1))
if not hasattr(settings, "VPN_PAID_GRACE_HOURS"):
    settings.VPN_PAID_GRACE_HOURS = 24
