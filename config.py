import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List


BUILTIN_MVP_LOCATIONS_JSON = (
    '[{"code":"auto-fastest","name_ru":"Авто | Самый быстрый","name_en":"Auto | Fastest","country_code":null,"is_active":true,"is_recommended":true,"is_reserve":false,"status":"online","sort_order":10},'
    '{"code":"auto-reserve","name_ru":"Авто | Резервный","name_en":"Auto | Reserve","country_code":null,"is_active":true,"is_recommended":false,"is_reserve":true,"status":"online","sort_order":20},'
    '{"code":"ru-lte","name_ru":"Россия LTE","name_en":"Russia LTE","country_code":"RU","is_active":true,"is_recommended":true,"is_reserve":false,"status":"offline","sort_order":30,"vpn_payload":{"engine":"xray","protocol":"vless","location_code":"ru-lte","remark":"Russia LTE","transport":"tcp","network":"tcp","security":"reality","flow":"xtls-rprx-vision","server_name":"www.cloudflare.com","sni":"www.cloudflare.com","fingerprint":"chrome","packet_encoding":"xudp","dns_servers":["1.1.1.1","8.8.8.8"]}},'
    '{"code":"ru-lte-reserve-1","name_ru":"Россия LTE | Резерв 1","name_en":"Russia LTE | Reserve 1","country_code":"RU","is_active":true,"is_recommended":false,"is_reserve":true,"status":"offline","sort_order":31,"vpn_payload":{"engine":"xray","protocol":"vless","location_code":"ru-lte-reserve-1","remark":"Russia LTE | Reserve 1","transport":"tcp","network":"tcp","security":"reality","flow":"xtls-rprx-vision","server_name":"www.cloudflare.com","sni":"www.cloudflare.com","fingerprint":"chrome","packet_encoding":"xudp","dns_servers":["1.1.1.1","8.8.8.8"]}},'
    '{"code":"ru-lte-reserve-2","name_ru":"Россия LTE | Резерв 2","name_en":"Russia LTE | Reserve 2","country_code":"RU","is_active":true,"is_recommended":false,"is_reserve":true,"status":"offline","sort_order":32,"vpn_payload":{"engine":"xray","protocol":"vless","location_code":"ru-lte-reserve-2","remark":"Russia LTE | Reserve 2","transport":"tcp","network":"tcp","security":"reality","flow":"xtls-rprx-vision","server_name":"www.cloudflare.com","sni":"www.cloudflare.com","fingerprint":"chrome","packet_encoding":"xudp","dns_servers":["1.1.1.1","8.8.8.8"]}},'
    '{"code":"ru-lte-reserve-3","name_ru":"Россия LTE | Резерв 3","name_en":"Russia LTE | Reserve 3","country_code":"RU","is_active":true,"is_recommended":false,"is_reserve":true,"status":"offline","sort_order":33,"vpn_payload":{"engine":"xray","protocol":"vless","location_code":"ru-lte-reserve-3","remark":"Russia LTE | Reserve 3","transport":"tcp","network":"tcp","security":"reality","flow":"xtls-rprx-vision","server_name":"www.cloudflare.com","sni":"www.cloudflare.com","fingerprint":"chrome","packet_encoding":"xudp","dns_servers":["1.1.1.1","8.8.8.8"]}},'
    '{"code":"intl-fast","name_ru":"Fast / International","name_en":"Fast / International","country_code":null,"is_active":true,"is_recommended":false,"is_reserve":false,"status":"offline","sort_order":80,"vpn_payload":{"engine":"xray","protocol":"vless","location_code":"intl-fast","remark":"Fast / International","transport":"tcp","network":"tcp","security":"tls","fingerprint":"chrome","packet_encoding":"xudp","dns_servers":["1.1.1.1","8.8.8.8"]}},'
    '{"code":"intl-fast-reserve-1","name_ru":"Fast / International | Reserve 1","name_en":"Fast / International | Reserve 1","country_code":null,"is_active":true,"is_recommended":false,"is_reserve":true,"status":"offline","sort_order":81,"vpn_payload":{"engine":"xray","protocol":"vless","location_code":"intl-fast-reserve-1","remark":"Fast / International | Reserve 1","transport":"tcp","network":"tcp","security":"tls","fingerprint":"chrome","packet_encoding":"xudp","dns_servers":["1.1.1.1","8.8.8.8"]}},'
    '{"code":"intl-fast-reserve-2","name_ru":"Fast / International | Reserve 2","name_en":"Fast / International | Reserve 2","country_code":null,"is_active":true,"is_recommended":false,"is_reserve":true,"status":"offline","sort_order":82,"vpn_payload":{"engine":"xray","protocol":"vless","location_code":"intl-fast-reserve-2","remark":"Fast / International | Reserve 2","transport":"tcp","network":"tcp","security":"tls","fingerprint":"chrome","packet_encoding":"xudp","dns_servers":["1.1.1.1","8.8.8.8"]}},'
    '{"code":"intl-fast-reserve-3","name_ru":"Fast / International | Reserve 3","name_en":"Fast / International | Reserve 3","country_code":null,"is_active":true,"is_recommended":false,"is_reserve":true,"status":"offline","sort_order":83,"vpn_payload":{"engine":"xray","protocol":"vless","location_code":"intl-fast-reserve-3","remark":"Fast / International | Reserve 3","transport":"tcp","network":"tcp","security":"tls","fingerprint":"chrome","packet_encoding":"xudp","dns_servers":["1.1.1.1","8.8.8.8"]}},'
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
    return ",".join([
        f"{base}/Vless-Reality-White-Lists-Rus-Mobile.txt",
        f"{base}/Vless-Reality-White-Lists-Rus-Mobile-2.txt",
        f"{base}/WHITE-CIDR-RU-checked.txt",
        f"{base}/WHITE-CIDR-RU-all.txt",
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

    APP_NAME: str = os.getenv("APP_NAME", "INET")
    APP_ENV: str = os.getenv("APP_ENV", "production")
    APP_LANGS: List[str] = None
    APP_BASE_URL: str = os.getenv("APP_BASE_URL", "https://your-domain.com")
    ADMIN_PANEL_BASE_URL: str = os.getenv("ADMIN_PANEL_BASE_URL", "https://your-admin-domain.com")
    OPEN_APP_URL: str = os.getenv("OPEN_APP_URL", "")
    OPEN_APP_BRIDGE_URL: str = os.getenv("OPEN_APP_BRIDGE_URL", "")
    ANDROID_APP_URL: str = os.getenv("ANDROID_APP_URL", "https://app.hiddify.com/play")
    ANDROID_APP_PACKAGE: str = os.getenv("ANDROID_APP_PACKAGE", "app.hiddify.com")
    IOS_APP_URL: str = os.getenv("IOS_APP_URL", "https://app.hiddify.com/ios")
    WINDOWS_APP_URL: str = os.getenv("WINDOWS_APP_URL", "https://app.hiddify.com/windows")
    MACOS_APP_URL: str = os.getenv("MACOS_APP_URL", "https://app.hiddify.com/mac")
    HIDDIFY_IMPORT_NAME: str = os.getenv("HIDDIFY_IMPORT_NAME", "INET Subscription")
    SUPPORT_TELEGRAM_URL: str = os.getenv("SUPPORT_TELEGRAM_URL", "https://t.me/your_admin")
    SUPPORT_FAQ_RU: str = os.getenv(
        "SUPPORT_FAQ_RU",
        "FAQ:\n1. Оплатите тариф в боте.\n2. Установите Hiddify.\n3. Откройте персональную ссылку подписки.\n4. Если не получается — напишите в поддержку.",
    )
    SUPPORT_FAQ_EN: str = os.getenv(
        "SUPPORT_FAQ_EN",
        "FAQ:\n1. Buy a plan in the bot.\n2. Install Hiddify.\n3. Open your personal subscription link.\n4. If something fails, contact support.",
    )

    BOT_NAME: str = os.getenv("BOT_NAME", "INET Bot")
    BOT_USERNAME: str = os.getenv("BOT_USERNAME", "inetvpnru_bot")
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    BACKEND_BASE_URL: str = os.getenv("BACKEND_BASE_URL", os.getenv("APP_BASE_URL", "http://127.0.0.1:3000"))
    BOT_NOTIFICATION_POLL_SEC: int = _env_int("BOT_NOTIFICATION_POLL_SEC", 45)
    SUBSCRIPTION_WARNING_HOURS: int = _env_int("SUBSCRIPTION_WARNING_HOURS", 12)
    SUBSCRIPTION_TOKEN: str = os.getenv("SUBSCRIPTION_TOKEN", "")
    LEGACY_GLOBAL_SUBSCRIPTION_TOKEN_ENABLED: bool = _env_bool("LEGACY_GLOBAL_SUBSCRIPTION_TOKEN_ENABLED", False)

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

    PAYMENTS_PROVIDER: str = os.getenv("PAYMENTS_PROVIDER", "yookassa")
    PAYMENTS_ENABLED: bool = _env_bool("PAYMENTS_ENABLED", False)
    YOOKASSA_SHOP_ID: str = os.getenv("YOOKASSA_SHOP_ID", "")
    YOOKASSA_SECRET_KEY: str = os.getenv("YOOKASSA_SECRET_KEY", "")
    YOOKASSA_RETURN_URL: str = os.getenv("YOOKASSA_RETURN_URL", "https://your-domain.com/payment/return")
    YOOKASSA_WEBHOOK_URL: str = os.getenv("YOOKASSA_WEBHOOK_URL", "https://your-domain.com/payments/webhook/yookassa")

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

    RU_LTE_SOURCE_URLS: List[str] = None
    RU_LTE_REFRESH_ON_STARTUP: bool = _env_bool("RU_LTE_REFRESH_ON_STARTUP", True)
    RU_LTE_AUTO_REFRESH_ENABLED: bool = _env_bool("RU_LTE_AUTO_REFRESH_ENABLED", True)
    RU_LTE_AUTO_REFRESH_MINUTES: int = _env_int("RU_LTE_AUTO_REFRESH_MINUTES", 3)
    RU_LTE_AUTO_REFRESH_TIMEOUT_SEC: int = _env_int("RU_LTE_AUTO_REFRESH_TIMEOUT_SEC", 600)
    RU_LTE_MAX_CANDIDATES: int = _env_int("RU_LTE_MAX_CANDIDATES", 3)
    RU_LTE_TEST_LIMIT: int = _env_int("RU_LTE_TEST_LIMIT", 40)
    RU_LTE_CONNECT_TIMEOUT_SEC: int = _env_int("RU_LTE_CONNECT_TIMEOUT_SEC", 4)
    RU_LTE_DEAD_COOLDOWN_MINUTES: int = _env_int("RU_LTE_DEAD_COOLDOWN_MINUTES", 45)
    RU_LTE_ALLOWED_TRANSPORTS: List[str] = None
    RU_LTE_REAL_PROBE_ENABLED: bool = _env_bool("RU_LTE_REAL_PROBE_ENABLED", True)
    RU_LTE_REAL_PROBE_REQUIRED: bool = _env_bool("RU_LTE_REAL_PROBE_REQUIRED", False)
    RU_LTE_REAL_PROBE_RUNNER: str = os.getenv("RU_LTE_REAL_PROBE_RUNNER", "xray")
    RU_LTE_REAL_PROBE_XRAY_BIN: str = os.getenv("RU_LTE_REAL_PROBE_XRAY_BIN", "xray")
    RU_LTE_REAL_PROBE_SINGBOX_BIN: str = os.getenv("RU_LTE_REAL_PROBE_SINGBOX_BIN", "sing-box")
    RU_LTE_REAL_PROBE_URLS: List[str] = None
    RU_LTE_REAL_PROBE_CONNECT_TIMEOUT_SEC: int = _env_int("RU_LTE_REAL_PROBE_CONNECT_TIMEOUT_SEC", 6)
    RU_LTE_REAL_PROBE_MAX_TIME_SEC: int = _env_int("RU_LTE_REAL_PROBE_MAX_TIME_SEC", 12)
    RU_LTE_REAL_PROBE_WARMUP_MS: int = _env_int("RU_LTE_REAL_PROBE_WARMUP_MS", 1200)
    HIDDIFY_SUBSCRIPTION_ALLOWED_TRANSPORTS: List[str] = None
    HIDDIFY_PROFILE_UPDATE_INTERVAL_HOURS: float = _env_float("HIDDIFY_PROFILE_UPDATE_INTERVAL_HOURS", 1.0)  # normalized to whole hours for Hiddify headers

    BLACK_SOURCE_URLS: List[str] = None
    BLACK_REFRESH_ON_STARTUP: bool = _env_bool("BLACK_REFRESH_ON_STARTUP", True)
    BLACK_AUTO_REFRESH_ENABLED: bool = _env_bool("BLACK_AUTO_REFRESH_ENABLED", True)
    BLACK_AUTO_REFRESH_MINUTES: int = _env_int("BLACK_AUTO_REFRESH_MINUTES", 3)
    BLACK_AUTO_REFRESH_TIMEOUT_SEC: int = _env_int("BLACK_AUTO_REFRESH_TIMEOUT_SEC", 600)
    BLACK_MAX_CANDIDATES: int = _env_int("BLACK_MAX_CANDIDATES", 3)
    BLACK_TEST_LIMIT: int = _env_int("BLACK_TEST_LIMIT", 40)
    BLACK_CONNECT_TIMEOUT_SEC: int = _env_int("BLACK_CONNECT_TIMEOUT_SEC", 4)
    BLACK_DEAD_COOLDOWN_MINUTES: int = _env_int("BLACK_DEAD_COOLDOWN_MINUTES", 30)
    BLACK_ALLOWED_TRANSPORTS: List[str] = None

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
        if self.RU_LTE_ALLOWED_TRANSPORTS is None:
            self.RU_LTE_ALLOWED_TRANSPORTS = _env_list("RU_LTE_ALLOWED_TRANSPORTS", "grpc,tcp,ws")
        if self.HIDDIFY_SUBSCRIPTION_ALLOWED_TRANSPORTS is None:
            self.HIDDIFY_SUBSCRIPTION_ALLOWED_TRANSPORTS = _env_list("HIDDIFY_SUBSCRIPTION_ALLOWED_TRANSPORTS", "grpc,tcp,ws")
        if self.RU_LTE_SOURCE_URLS is None:
            self.RU_LTE_SOURCE_URLS = _env_list(
                "RU_LTE_SOURCE_URLS",
                _default_ru_lte_source_urls(),
            )
        if self.RU_LTE_REAL_PROBE_URLS is None:
            self.RU_LTE_REAL_PROBE_URLS = _env_list(
                "RU_LTE_REAL_PROBE_URLS",
                "https://www.vk.com/,https://ya.ru/",
            )
        if self.BLACK_ALLOWED_TRANSPORTS is None:
            self.BLACK_ALLOWED_TRANSPORTS = _env_list("BLACK_ALLOWED_TRANSPORTS", "grpc,tcp,ws")
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
                "device_limit": 1,
                "is_active": self.PLAN_MONTHLY_1_ENABLED,
                "source_env_key": "PLAN_MONTHLY_1",
            },
            {
                "code": self.PLAN_MONTHLY_2_CODE,
                "name_ru": self.PLAN_MONTHLY_2_NAME_RU,
                "name_en": self.PLAN_MONTHLY_2_NAME_EN,
                "price_rub": self.PLAN_MONTHLY_2_PRICE_RUB,
                "duration_days": self.PLAN_MONTHLY_2_DURATION_DAYS,
                "device_limit": min(2, self.VPN_MAX_DEVICES_PER_ACCOUNT),
                "is_active": self.PLAN_MONTHLY_2_ENABLED,
                "source_env_key": "PLAN_MONTHLY_2",
            },
            {
                "code": self.PLAN_MONTHLY_3_CODE,
                "name_ru": self.PLAN_MONTHLY_3_NAME_RU,
                "name_en": self.PLAN_MONTHLY_3_NAME_EN,
                "price_rub": self.PLAN_MONTHLY_3_PRICE_RUB,
                "duration_days": self.PLAN_MONTHLY_3_DURATION_DAYS,
                "device_limit": min(3, self.VPN_MAX_DEVICES_PER_ACCOUNT),
                "is_active": self.PLAN_MONTHLY_3_ENABLED,
                "source_env_key": "PLAN_MONTHLY_3",
            },
        ]


settings = Settings()
