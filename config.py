import os
from dataclasses import dataclass
from typing import Any, Dict, List


BUILTIN_MVP_LOCATIONS_JSON = (
    '[{"code":"auto-fastest","name_ru":"Авто | Самый быстрый","name_en":"Auto | Fastest","country_code":null,"is_active":true,"is_recommended":true,"is_reserve":false,"status":"online","sort_order":10},'
    '{"code":"auto-reserve","name_ru":"Авто | Резервный","name_en":"Auto | Reserve","country_code":null,"is_active":true,"is_recommended":false,"is_reserve":true,"status":"online","sort_order":20},'
    '{"code":"ru-1","name_ru":"Россия","name_en":"Russia","country_code":"RU","is_active":true,"is_recommended":false,"is_reserve":false,"status":"online","sort_order":30},'
    '{"code":"fi-1","name_ru":"Финляндия","name_en":"Finland","country_code":"FI","is_active":true,"is_recommended":false,"is_reserve":false,"status":"online","sort_order":40},'
    '{"code":"de-1","name_ru":"Германия","name_en":"Germany","country_code":"DE","is_active":true,"is_recommended":false,"is_reserve":false,"status":"online","sort_order":50},'
    '{"code":"nl-1","name_ru":"Нидерланды","name_en":"Netherlands","country_code":"NL","is_active":true,"is_recommended":false,"is_reserve":false,"status":"online","sort_order":60},'
    '{"code":"fr-1","name_ru":"Франция","name_en":"France","country_code":"FR","is_active":true,"is_recommended":false,"is_reserve":false,"status":"online","sort_order":70},'
    '{"code":"at-1","name_ru":"Австрия","name_en":"Austria","country_code":"AT","is_active":true,"is_recommended":false,"is_reserve":false,"status":"online","sort_order":80}]'
)


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


def _env_list(name: str, default: str = "") -> List[str]:
    value = os.getenv(name, default)
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass
class Settings:
    PORT: int = _env_int("PORT", 3000)
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/inet")
    JWT_SECRET: str = os.getenv("JWT_SECRET", "replace_me")
    CORS_ORIGINS: List[str] = None

    ADMIN_BASIC_USER: str = os.getenv("ADMIN_BASIC_USER", "admin")
    ADMIN_BASIC_PASS: str = os.getenv("ADMIN_BASIC_PASS", "change_me")

    APP_NAME: str = os.getenv("APP_NAME", "INET")
    APP_ENV: str = os.getenv("APP_ENV", "production")
    APP_LANGS: List[str] = None
    APP_BASE_URL: str = os.getenv("APP_BASE_URL", "https://your-domain.com")
    ADMIN_PANEL_BASE_URL: str = os.getenv("ADMIN_PANEL_BASE_URL", "https://your-admin-domain.com")
    OPEN_APP_URL: str = os.getenv("OPEN_APP_URL", "inet://login")
    ANDROID_APP_URL: str = os.getenv("ANDROID_APP_URL", "https://play.google.com/store/apps/details?id=com.example.inet")
    IOS_APP_URL: str = os.getenv("IOS_APP_URL", "https://apps.apple.com/app/id000000000")
    SUPPORT_TELEGRAM_URL: str = os.getenv("SUPPORT_TELEGRAM_URL", "https://t.me/your_admin")
    SUPPORT_FAQ_RU: str = os.getenv(
        "SUPPORT_FAQ_RU",
        "FAQ:\n1. Оплатите тариф в боте.\n2. Скачайте приложение.\n3. Подключите устройство.\n4. Если не получается — напишите в поддержку.",
    )
    SUPPORT_FAQ_EN: str = os.getenv(
        "SUPPORT_FAQ_EN",
        "FAQ:\n1. Buy a plan in the bot.\n2. Download the app.\n3. Connect your device.\n4. If something fails, contact support.",
    )

    BOT_NAME: str = os.getenv("BOT_NAME", "INET Bot")
    BOT_USERNAME: str = os.getenv("BOT_USERNAME", "inet_bot")
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    BACKEND_BASE_URL: str = os.getenv("BACKEND_BASE_URL", os.getenv("APP_BASE_URL", "http://127.0.0.1:3000"))
    BOT_NOTIFICATION_POLL_SEC: int = _env_int("BOT_NOTIFICATION_POLL_SEC", 45)

    AUTH_DEV_LOGIN_CODE: str = os.getenv("AUTH_DEV_LOGIN_CODE", "111111")
    AUTH_ALLOW_DEV_CODE: bool = _env_bool("AUTH_ALLOW_DEV_CODE", True)

    VPN_DEFAULT_DEVICE_LIMIT: int = _env_int("VPN_DEFAULT_DEVICE_LIMIT", 2)
    VPN_MAX_DEVICES_PER_ACCOUNT: int = _env_int("VPN_MAX_DEVICES_PER_ACCOUNT", 2)
    VPN_MAINTENANCE_MODE: bool = _env_bool("VPN_MAINTENANCE_MODE", False)
    VPN_NEW_ACTIVATIONS_ENABLED: bool = _env_bool("VPN_NEW_ACTIVATIONS_ENABLED", True)
    VPN_SHOW_DAILY_PLAN: bool = _env_bool("VPN_SHOW_DAILY_PLAN", True)
    VPN_SHOW_MONTHLY_PLAN: bool = _env_bool("VPN_SHOW_MONTHLY_PLAN", True)
    VPN_SETTINGS_EDITABLE: bool = _env_bool("VPN_SETTINGS_EDITABLE", False)

    PLAN_DAILY_ENABLED: bool = _env_bool("PLAN_DAILY_ENABLED", True)
    PLAN_DAILY_CODE: str = os.getenv("PLAN_DAILY_CODE", "daily")
    PLAN_DAILY_NAME_RU: str = os.getenv("PLAN_DAILY_NAME_RU", "1 день")
    PLAN_DAILY_NAME_EN: str = os.getenv("PLAN_DAILY_NAME_EN", "1 day")
    PLAN_DAILY_PRICE_RUB: int = _env_int("PLAN_DAILY_PRICE_RUB", 10)
    PLAN_DAILY_DURATION_DAYS: int = _env_int("PLAN_DAILY_DURATION_DAYS", 1)
    PLAN_DAILY_DEVICE_LIMIT: int = _env_int("PLAN_DAILY_DEVICE_LIMIT", 2)

    PLAN_MONTHLY_ENABLED: bool = _env_bool("PLAN_MONTHLY_ENABLED", True)
    PLAN_MONTHLY_CODE: str = os.getenv("PLAN_MONTHLY_CODE", "monthly")
    PLAN_MONTHLY_NAME_RU: str = os.getenv("PLAN_MONTHLY_NAME_RU", "30 дней")
    PLAN_MONTHLY_NAME_EN: str = os.getenv("PLAN_MONTHLY_NAME_EN", "30 days")
    PLAN_MONTHLY_PRICE_RUB: int = _env_int("PLAN_MONTHLY_PRICE_RUB", 999)
    PLAN_MONTHLY_DURATION_DAYS: int = _env_int("PLAN_MONTHLY_DURATION_DAYS", 30)
    PLAN_MONTHLY_DEVICE_LIMIT: int = _env_int("PLAN_MONTHLY_DEVICE_LIMIT", 2)

    PAYMENTS_PROVIDER: str = os.getenv("PAYMENTS_PROVIDER", "yookassa")
    PAYMENTS_ENABLED: bool = _env_bool("PAYMENTS_ENABLED", False)
    YOOKASSA_SHOP_ID: str = os.getenv("YOOKASSA_SHOP_ID", "")
    YOOKASSA_SECRET_KEY: str = os.getenv("YOOKASSA_SECRET_KEY", "")
    YOOKASSA_RETURN_URL: str = os.getenv("YOOKASSA_RETURN_URL", "https://your-domain.com/payment/return")
    YOOKASSA_WEBHOOK_URL: str = os.getenv("YOOKASSA_WEBHOOK_URL", "https://your-domain.com/payments/webhook/yookassa")

    DEFAULT_LOCATIONS_JSON: str = BUILTIN_MVP_LOCATIONS_JSON
    DEFAULT_LOCATIONS_ENV_JSON: str = os.getenv("DEFAULT_LOCATIONS_JSON", "")
    DEFAULT_LOCATIONS_ENV_OVERRIDE_ENABLED: bool = _env_bool("DEFAULT_LOCATIONS_ENV_OVERRIDE_ENABLED", False)

    def __post_init__(self) -> None:
        if self.CORS_ORIGINS is None:
            self.CORS_ORIGINS = _env_list("CORS_ORIGINS", "*")
        if self.APP_LANGS is None:
            self.APP_LANGS = _env_list("APP_LANGS", "ru,en")

    def plan_definitions(self) -> List[Dict[str, Any]]:
        return [
            {
                "code": self.PLAN_DAILY_CODE,
                "name_ru": self.PLAN_DAILY_NAME_RU,
                "name_en": self.PLAN_DAILY_NAME_EN,
                "price_rub": self.PLAN_DAILY_PRICE_RUB,
                "duration_days": self.PLAN_DAILY_DURATION_DAYS,
                "device_limit": min(self.PLAN_DAILY_DEVICE_LIMIT, self.VPN_MAX_DEVICES_PER_ACCOUNT),
                "is_active": self.PLAN_DAILY_ENABLED and self.VPN_SHOW_DAILY_PLAN,
                "source_env_key": "PLAN_DAILY",
            },
            {
                "code": self.PLAN_MONTHLY_CODE,
                "name_ru": self.PLAN_MONTHLY_NAME_RU,
                "name_en": self.PLAN_MONTHLY_NAME_EN,
                "price_rub": self.PLAN_MONTHLY_PRICE_RUB,
                "duration_days": self.PLAN_MONTHLY_DURATION_DAYS,
                "device_limit": min(self.PLAN_MONTHLY_DEVICE_LIMIT, self.VPN_MAX_DEVICES_PER_ACCOUNT),
                "is_active": self.PLAN_MONTHLY_ENABLED and self.VPN_SHOW_MONTHLY_PLAN,
                "source_env_key": "PLAN_MONTHLY",
            },
        ]


settings = Settings()
