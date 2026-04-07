import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List


BUILTIN_MVP_LOCATIONS_JSON = (
    '[{"code":"auto-fastest","name_ru":"Авто | Самый быстрый","name_en":"Auto | Fastest","country_code":null,"is_active":true,"is_recommended":true,"is_reserve":false,"status":"online","sort_order":10},'
    '{"code":"auto-reserve","name_ru":"Авто | Резервный","name_en":"Auto | Reserve","country_code":null,"is_active":true,"is_recommended":false,"is_reserve":true,"status":"online","sort_order":20},'
    '{"code":"ru-lte","name_ru":"Россия LTE","name_en":"Russia LTE","country_code":"RU","is_active":true,"is_recommended":true,"is_reserve":false,"status":"offline","sort_order":30,"vpn_payload":{"engine":"sing-box","protocol":"vless","location_code":"ru-lte","remark":"Russia LTE","transport":"tcp","network":"tcp","security":"reality","flow":"xtls-rprx-vision","server_name":"www.cloudflare.com","sni":"www.cloudflare.com","fingerprint":"chrome","packet_encoding":"xudp","dns_servers":["1.1.1.1","8.8.8.8"]}},'
    '{"code":"ru-lte-reserve-1","name_ru":"Россия LTE | Резерв 1","name_en":"Russia LTE | Reserve 1","country_code":"RU","is_active":true,"is_recommended":false,"is_reserve":true,"status":"offline","sort_order":31,"vpn_payload":{"engine":"sing-box","protocol":"vless","location_code":"ru-lte-reserve-1","remark":"Russia LTE | Reserve 1","transport":"tcp","network":"tcp","security":"reality","flow":"xtls-rprx-vision","server_name":"www.cloudflare.com","sni":"www.cloudflare.com","fingerprint":"chrome","packet_encoding":"xudp","dns_servers":["1.1.1.1","8.8.8.8"]}},'
    '{"code":"ru-lte-reserve-2","name_ru":"Россия LTE | Резерв 2","name_en":"Russia LTE | Reserve 2","country_code":"RU","is_active":true,"is_recommended":false,"is_reserve":true,"status":"offline","sort_order":32,"vpn_payload":{"engine":"sing-box","protocol":"vless","location_code":"ru-lte-reserve-2","remark":"Russia LTE | Reserve 2","transport":"tcp","network":"tcp","security":"reality","flow":"xtls-rprx-vision","server_name":"www.cloudflare.com","sni":"www.cloudflare.com","fingerprint":"chrome","packet_encoding":"xudp","dns_servers":["1.1.1.1","8.8.8.8"]}},'
    '{"code":"se","name_ru":"Sweden","name_en":"Sweden","country_code":"SE","is_active":true,"is_recommended":false,"is_reserve":false,"status":"online","sort_order":40},'
    '{"code":"nl-1","name_ru":"Нидерланды","name_en":"Netherlands","country_code":"NL","is_active":true,"is_recommended":false,"is_reserve":false,"status":"online","sort_order":50},'
    '{"code":"de-1","name_ru":"Германия","name_en":"Germany","country_code":"DE","is_active":true,"is_recommended":false,"is_reserve":false,"status":"online","sort_order":60},'
    '{"code":"fi-1","name_ru":"Финляндия","name_en":"Finland","country_code":"FI","is_active":true,"is_recommended":false,"is_reserve":false,"status":"online","sort_order":70}]'
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


def _parse_json_object(raw: str) -> Dict[str, Any]:
    if not raw or not raw.strip():
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


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
    OPEN_APP_BRIDGE_URL: str = os.getenv("OPEN_APP_BRIDGE_URL", "")
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
    BOT_USERNAME: str = os.getenv("BOT_USERNAME", "inetvpnru_bot")
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    BACKEND_BASE_URL: str = os.getenv("BACKEND_BASE_URL", os.getenv("APP_BASE_URL", "http://127.0.0.1:3000"))
    BOT_NOTIFICATION_POLL_SEC: int = _env_int("BOT_NOTIFICATION_POLL_SEC", 45)

    AUTH_DEV_LOGIN_CODE: str = os.getenv("AUTH_DEV_LOGIN_CODE", "111111")
    AUTH_ALLOW_DEV_CODE: bool = _env_bool("AUTH_ALLOW_DEV_CODE", True)
    AUTH_ACCESS_TOKEN_MINUTES: int = _env_int("AUTH_ACCESS_TOKEN_MINUTES", 60)
    AUTH_REFRESH_TOKEN_DAYS: int = _env_int("AUTH_REFRESH_TOKEN_DAYS", 90)
    AUTH_CODE_TTL_MINUTES: int = _env_int("AUTH_CODE_TTL_MINUTES", 5)
    AUTH_CODE_ISSUER_SECRET: str = os.getenv("AUTH_CODE_ISSUER_SECRET", "")

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

    VPN_ENGINE: str = os.getenv("VPN_ENGINE", "sing-box")
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

    RU_LTE_SOURCE_URLS: List[str] = None
    RU_LTE_REFRESH_ON_STARTUP: bool = _env_bool("RU_LTE_REFRESH_ON_STARTUP", False)
    RU_LTE_MAX_CANDIDATES: int = _env_int("RU_LTE_MAX_CANDIDATES", 3)

    def __post_init__(self) -> None:
        if self.CORS_ORIGINS is None:
            self.CORS_ORIGINS = _env_list("CORS_ORIGINS", "*")
        if self.APP_LANGS is None:
            self.APP_LANGS = _env_list("APP_LANGS", "ru,en")
        if self.VLESS_DNS_SERVERS is None:
            self.VLESS_DNS_SERVERS = _env_list("VLESS_DNS_SERVERS", "1.1.1.1,8.8.8.8")
        if self.VLESS_ALPN is None:
            self.VLESS_ALPN = _env_list("VLESS_ALPN", "")
        if self.RU_LTE_SOURCE_URLS is None:
            self.RU_LTE_SOURCE_URLS = _env_list(
                "RU_LTE_SOURCE_URLS",
                "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/main/Vless-Reality-White-Lists-Rus-Mobile.txt,https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/main/Vless-Reality-White-Lists-Rus-Mobile-2.txt",
            )

    def default_vpn_payload(self) -> Dict[str, Any]:
        from_json = _parse_json_object(self.VLESS_DEFAULT_CONFIG_JSON)
        if from_json:
            return dict(from_json)
        if not (self.VLESS_SERVER.strip() and self.VLESS_UUID.strip()):
            return {}
        payload: Dict[str, Any] = {
            "protocol": "vless",
            "engine": self.VPN_ENGINE or "sing-box",
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
