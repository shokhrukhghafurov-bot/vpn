import contextlib
import asyncio
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit, unquote

import httpx
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    CopyTextButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardRemove,
)

from config import settings
from db_store import (
    enqueue_subscription_notifications,
    list_pending_notifications,
    mark_notification_failed,
    mark_notification_retry,
    mark_notification_sent,
    record_bot_error,
)


logging.basicConfig(level=getattr(logging, os.getenv("LOG_LEVEL", "ERROR").strip().upper(), logging.ERROR), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


TEXT: Dict[str, Dict[str, str]] = {
    "ru": {
        "welcome": "👋 Добро пожаловать в INET\nВыберите действие ниже",
        "welcome_back": "🏠 Главное меню INET VPN",
        "menu": "🏠 Главное меню INET VPN",
        "buy": "💳 Купить подписку",
        "sub": "📄 Моя подписка",
        "devices": "📱 Мои устройства",
        "download": "⬇️ Приложение / Подключение",
        "connect_this_device": "📱 Подключить это устройство",
        "add_second_device": "➕ Добавить второе устройство",
        "add_device": "➕ Добавить устройство",
        "delete_device": "🗑 Удалить устройство",
        "reset_device": "🔄 Сбросить устройство",
        "device_reset_done": "Устройство удалено. Старый token и UUID отключены. Слот освобождён. Теперь можно подключить другой телефон.",
        "devices_hint": "Нажмите «Подключить это устройство» / «Добавить второе устройство». Если ссылка создана, но приложение ещё не импортировало профиль, слот будет занят как «⏳ ожидает подключения». Если передумали — удалите это устройство, слот освободится.",
        "support": "🛟 Поддержка",
        "instructions": "📘 Инструкция",
        "renew": "🔄 Продлить",
        "open_app": "🚀 Открыть подключение",
        "download_app": "⬇️ Скачать приложение",
        "back": "⬅️ Назад",
        "main_menu": "🏠 Главное меню",
        "choose_language": "🌐 Выберите язык",
        "language_saved": "Язык сохранён.",
        "instructions_text": "📘 Инструкция\n\n1. Нажмите «📱 Подключить это устройство».\n2. Выберите вашу платформу.\n3. Нажмите «🚀 Открыть подключение» — приложение должно импортировать профиль автоматически.\n4. Если авто-импорт не сработал, нажмите «📋 Скопировать ссылку подписки» и вставьте её в приложении как Subscription / URL.\n5. Нажмите «Обновить», чтобы загрузить свежие локации и конфиги.\n6. Подключитесь к VPN.\n\nЕсли какая-то локация или LTE не работает:\n• нажмите кнопку «Обновить»\n• подождите, пока профиль обновится\n• попробуйте другую локацию или резервный сервер\n\nЕсли после воздушной тревоги или блокировки часть интернета не работает:\n• подключите LTE-локацию\n• затем снова нажмите «Обновить»\n• если проблема осталась — попробуйте резервный LTE\n\nВажно: не передавайте вашу ссылку подписки другим людям. Бот показывает только subscription-ссылку /sub/dt_..., не сырой VLESS.",
        "choose_plan": "💼 Выберите тариф:",
        "plan": "Тариф",
        "price": "Цена",
        "devices_up_to": "Устройств",
        "payment_method": "Способ оплаты",
        "pay_card": "💳 Оплатить картой / СБП",
        "proceed_payment": "💸 Перейти к оплате",
        "check_payment": "✅ Проверить оплату",
        "cancel": "✖️ Отменить",
        "payments_off": "Оплата скоро будет доступна",
        "payment_created": "После нажатия перейдите к оплате. Подписка активируется автоматически после подтверждения платежа.",
        "payment_waiting": "Платёж ещё не подтверждён. Статус",
        "payment_received": "Оплата получена",
        "subscription_activated": "Подписка активирована",
        "subscription_none": "Активной подписки нет.",
        "subscription_status": "Статус",
        "subscription_active": "Активна",
        "subscription_expired": "Истекла",
        "active_until": "Активна до",
        "valid_until": "Действует до",
        "devices_used": "Устройства",
        "connected_now": "Подключено",
        "limit_reached": "Лимит устройств достигнут",
        "devices_none": "Устройств пока нет.",
        "device_removed": "Устройство удалено. Старый token и UUID отключены. Слот освобождён. Теперь можно подключить другой телефон.",
        "choose_platform": "Выберите платформу для подключения:",
        "android": "🤖 Android",
        "ios": "🍎 iPhone / iPad",
        "windows": "🪟 Windows",
        "macos": "💻 macOS",
        "download_android": "Android: установите Hiddify, затем нажмите «🚀 Открыть подключение». Если авто-импорт не сработал — нажмите «📋 Скопировать ссылку подписки» и импортируйте её в приложении вручную.",
        "download_ios": "iPhone / iPad: установите Hiddify, затем нажмите «🚀 Открыть подключение». Если авто-импорт не сработал — нажмите «📋 Скопировать ссылку подписки» и импортируйте её в приложении вручную.",
        "support_text": "🛟 Связаться с поддержкой",
        "faq": "FAQ",
        "write_support": "✉️ Написать в поддержку",
        "service_unavailable": "Сервис временно недоступен. Проверь BACKEND_BASE_URL, DATABASE_URL и логи Railway.",
        "unexpected_error": "Произошла ошибка. Проверь логи Railway и параметры окружения.",
        "one_day_left": "Ваша подписка скоро закончится\nОстался 1 день.",
        "twelve_hours_left": "Ваша подписка скоро закончится\nОсталось меньше 12 часов.",
        "expired_notice": "Подписка истекла",
        "expired_access_disabled": "Доступ к VPN отключён.",
        "expired_buy_cta": "Чтобы снова подключиться, купите подписку.",
        "payment_failed": "Оплата не прошла. Попробуйте ещё раз или обратитесь в поддержку.",
        "status_label": "Статус",
        "remove": "🗑️ Удалить",
        "device_slot": "Слот",
        "device_active": "✅ подключено",
        "device_pending": "⏳ ожидает подключения",
        "device_inactive": "неактивен",
        "available_devices": "Доступно устройств",
        "token_label": "Код входа",
        "copy_token": "📋 Скопировать код",
        "download_windows": "Windows: установите Happ, затем нажмите «📋 Скопировать ссылку подписки» и добавьте её в Happ вручную как Subscription / URL. Токен уже внутри ссылки.",
        "download_macos": "macOS: установите Happ, затем нажмите «📋 Скопировать ссылку подписки» и добавьте её в Happ вручную как Subscription / URL. Токен уже внутри ссылки.",
        "copy_subscription": "📋 Скопировать ссылку подписки",
        "manual_import_hint": "Нажмите «📱 Подключить это устройство», выберите платформу и используйте «🚀 Открыть подключение». Если авто-импорт не сработал — используйте «📋 Скопировать ссылку подписки». Не пересылайте ссылку на другой телефон. На Windows для TUN запустите Happ от имени администратора.",
        "subscription_buy_prompt": "Чтобы подключиться, купите или продлите подписку.",
        "free_mode_label": "Бесплатный режим",
        "free_mode_access": "Сейчас для всех включён бесплатный режим доступа.",
        "grace_mode_access": "Сейчас у вас временный бесплатный доступ после возврата в платный режим.",
        "buy_hidden_free_mode": "Сейчас включён бесплатный режим. Кнопка покупки скрыта, потому что доступ уже бесплатный.",
        "grace_hours_left": "Осталось часов",
    },
    "en": {
        "welcome": "👋 Welcome to INET\nChoose an action below",
        "welcome_back": "🏠 INET VPN main menu",
        "menu": "🏠 INET VPN main menu",
        "buy": "💳 Buy subscription",
        "sub": "📄 My subscription",
        "devices": "📱 My devices",
        "download": "⬇️ Apps / Connect",
        "connect_this_device": "📱 Connect this device",
        "add_second_device": "➕ Add second device",
        "add_device": "➕ Add device",
        "delete_device": "🗑 Delete device",
        "reset_device": "🔄 Reset device",
        "device_reset_done": "Device removed. The old token and UUID are disabled. The slot is free. You can now connect another phone.",
        "devices_hint": "Tap “Connect this device” / “Add second device”. If the link is created but the VPN app has not imported it yet, the slot stays reserved as “⏳ waiting for connection”. Delete it if you changed your mind.",
        "support": "🛟 Support",
        "instructions": "📘 Instructions",
        "renew": "🔄 Renew",
        "open_app": "🚀 Open connection",
        "download_app": "⬇️ Download app",
        "back": "⬅️ Back",
        "main_menu": "🏠 Main menu",
        "choose_language": "🌐 Choose language",
        "language_saved": "Language saved.",
        "instructions_text": "📘 Instructions\n\n1. Tap \"Apps / Connect\".\n2. Choose your platform.\n3. Tap “🚀 Open connection” — the app should import the profile automatically.\n4. If auto-import does not work, tap “📋 Copy subscription link” and add it in the app as Subscription / URL.\n5. Tap \"Refresh\" to load fresh locations and configs.\n6. Connect to VPN.\n\nIf any location or LTE does not work:\n• tap the \"Refresh\" button\n• wait until the profile updates\n• try another location or a reserve server\n\nIf part of the internet does not work after an air raid alert or blocking:\n• connect to an LTE location\n• then tap \"Refresh\" again\n• if the problem remains, try a reserve LTE\n\nImportant: do not share your personal subscription link with other people. The bot shows only a subscription URL /sub/dt_..., never a raw VLESS link.",
        "choose_plan": "💼 Choose a plan:",
        "plan": "Plan",
        "price": "Price",
        "devices_up_to": "Devices",
        "payment_method": "Payment method",
        "pay_card": "💳 Pay by card / SBP",
        "proceed_payment": "💸 Proceed to payment",
        "check_payment": "✅ Check payment",
        "cancel": "✖️ Cancel",
        "payments_off": "Payment will be available soon",
        "payment_created": "Continue to payment. Subscription will be activated automatically after payment confirmation.",
        "payment_waiting": "Payment is not confirmed yet. Status",
        "payment_received": "Payment received",
        "subscription_activated": "Subscription activated",
        "subscription_none": "No subscription yet.",
        "subscription_status": "Status",
        "subscription_active": "Active",
        "subscription_expired": "Expired",
        "active_until": "Active until",
        "valid_until": "Valid until",
        "devices_used": "Devices",
        "connected_now": "Connected",
        "limit_reached": "Device limit reached",
        "devices_none": "No devices yet.",
        "device_removed": "Device removed. The old token and UUID are disabled. The slot is free. You can now connect another phone.",
        "choose_platform": "Choose a platform to connect:",
        "android": "🤖 Android",
        "ios": "🍎 iPhone / iPad",
        "windows": "🪟 Windows",
        "macos": "💻 macOS",
        "download_android": "Android: install Hiddify, then tap “🚀 Open connection”. If auto-import does not work, tap “📋 Copy subscription link” and import it manually in the app.",
        "download_ios": "iPhone / iPad: install Hiddify, then tap “🚀 Open connection”. If auto-import does not work, tap “📋 Copy subscription link” and import it manually in the app.",
        "support_text": "🛟 Contact support",
        "faq": "FAQ",
        "write_support": "✉️ Write to support",
        "service_unavailable": "Service is temporarily unavailable. Check BACKEND_BASE_URL, DATABASE_URL and Railway logs.",
        "unexpected_error": "Something went wrong. Check Railway logs and environment variables.",
        "one_day_left": "Your subscription will expire soon\n1 day left.",
        "twelve_hours_left": "Your subscription will expire soon\nLess than 12 hours left.",
        "expired_notice": "Subscription expired",
        "expired_access_disabled": "VPN access is disabled.",
        "expired_buy_cta": "Buy a subscription to connect again.",
        "payment_failed": "Payment failed. Please try again or contact support.",
        "status_label": "Status",
        "remove": "🗑️ Remove",
        "device_slot": "Slot",
        "device_active": "✅ connected",
        "device_pending": "⏳ waiting for connection",
        "device_inactive": "inactive",
        "available_devices": "Devices available",
        "token_label": "Login code",
        "copy_token": "📋 Copy code",
        "download_windows": "Windows: install Happ, then tap “📋 Copy subscription link” and add it in Happ manually as Subscription / URL. The token is already inside the link.",
        "download_macos": "macOS: install Happ, then tap “📋 Copy subscription link” and add it in Happ manually as Subscription / URL. The token is already inside the link.",
        "copy_subscription": "📋 Copy subscription link",
        "manual_import_hint": "Tap “Connect this device”, choose your platform and use “🚀 Open connection”. If auto-import does not work, use “📋 Copy subscription link”. Do not forward the link to another phone. On Windows run Happ as administrator for TUN mode.",
        "subscription_buy_prompt": "To connect, buy or renew a subscription.",
        "free_mode_label": "Free mode",
        "free_mode_access": "Free access for all users is enabled right now.",
        "grace_mode_access": "You currently have temporary free access after switching back to paid mode.",
        "buy_hidden_free_mode": "Free mode is enabled right now. The buy button is hidden because access is already free.",
        "grace_hours_left": "Hours left",
    },
}


bot: Optional[Bot] = None
dp = Dispatcher()

_APP_CONFIG_CACHE: Dict[str, Any] = {"ts": 0.0, "payment_commission_percent": None}


def selected_client_mode() -> str:
    mode = str(getattr(settings, "VPN_CLIENT_MODE", "hiddify") or "").strip().lower()
    return "v2raytun" if mode == "v2raytun" else "hiddify"


def selected_client_name() -> str:
    return "v2RayTun" if selected_client_mode() == "v2raytun" else "Hiddify"


def tx(lang: str, key: str) -> str:
    raw = TEXT[lang][key]
    if key in {"download_android", "download_ios", "manual_import_hint"}:
        return raw.replace("Hiddify", selected_client_name())
    return raw


def payment_created_text(lang: str) -> str:
    cached_commission = _APP_CONFIG_CACHE.get("payment_commission_percent")
    raw_commission = cached_commission if cached_commission is not None else getattr(settings, "PAYMENTS_COMMISSION_PERCENT", 0.0)
    commission = max(float(raw_commission or 0.0), 0.0)
    percent = int(commission) if float(commission).is_integer() else commission
    if lang == "ru":
        lines = [
            "✅ Подписка активируется автоматически после успешной оплаты.",
            f"💰 Обратите внимание: к сумме добавляется комиссия платёжной системы — {percent}%.",
            "После оплаты может потребоваться подождать до 10 минут из-за обработки платежа банком 🕒.",
        ]
        return "\n".join(lines)
    lines = [
        "✅ Your subscription activates automatically after successful payment.",
        f"💰 Please note: a payment system fee of {percent}% is added to the amount.",
        "After payment, it may take up to 10 minutes because of bank processing 🕒.",
    ]
    return "\n".join(lines)


def platform_download_button_text(lang: str, platform: str) -> str:
    key = (platform or "").strip().lower()
    if lang == "ru":
        if key == "windows":
            return "⬇️ Скачать Happ для Windows"
        if key in {"macos", "mac", "osx"}:
            return "⬇️ Скачать Happ для macOS"
        return f"⬇️ Скачать {selected_client_name()}"
    if key == "windows":
        return "⬇️ Download Happ for Windows"
    if key in {"macos", "mac", "osx"}:
        return "⬇️ Download Happ for macOS"
    return f"⬇️ Download {selected_client_name()}"


async def refresh_app_config(force: bool = False) -> None:
    now = time.time()
    if not force and now - float(_APP_CONFIG_CACHE.get("ts") or 0.0) < 60:
        return
    try:
        data = await api_request("GET", "/app/config")
    except Exception:
        return
    settings.VPN_CLIENT_MODE = str(data.get("mobile_client_mode") or data.get("client_mode") or getattr(settings, "VPN_CLIENT_MODE", "hiddify"))
    settings.ANDROID_APP_URL = str(data.get("android_app_url") or settings.ANDROID_APP_URL)
    settings.IOS_APP_URL = str(data.get("ios_app_url") or settings.IOS_APP_URL)
    settings.WINDOWS_APP_URL = str(data.get("windows_app_url") or getattr(settings, "WINDOWS_APP_URL", ""))
    settings.MACOS_APP_URL = str(data.get("macos_app_url") or getattr(settings, "MACOS_APP_URL", ""))
    commission = data.get("payment_commission_percent")
    _APP_CONFIG_CACHE["payment_commission_percent"] = float(commission or 0.0) if commission is not None else None
    _APP_CONFIG_CACHE["ts"] = now


def require_bot() -> Bot:
    if bot is None:
        raise RuntimeError("Bot is not initialized")
    return bot


class BackendUnavailable(RuntimeError):
    pass


class ApiError(RuntimeError):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


async def api_request(
    method: str,
    path: str,
    *,
    token: Optional[str] = None,
    json_body: Optional[Dict[str, Any]] = None,
    extra_headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    url = settings.BACKEND_BASE_URL.rstrip("/") + path
    headers = dict(extra_headers or {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.request(method, url, json=json_body, headers=headers)
    except httpx.HTTPError as exc:
        logger.exception("Backend request failed: %s %s", method, url)
        raise BackendUnavailable(str(exc)) from exc
    if response.status_code >= 400:
        detail = response.text
        try:
            body = response.json()
            detail = body.get("detail") or body.get("message") or str(body)
        except Exception:
            pass
        raise ApiError(response.status_code, detail)
    try:
        return response.json()
    except Exception as exc:
        raise BackendUnavailable(f"Invalid JSON response from backend: {exc}") from exc


async def auth_user(tg_user: Any, language: Optional[str] = None) -> Dict[str, Any]:
    payload = {
        "telegram_id": tg_user.id,
        "username": tg_user.username,
        "first_name": tg_user.first_name,
        "last_name": tg_user.last_name,
        "language": language or (tg_user.language_code if tg_user.language_code in {"ru", "en"} else "ru"),
    }
    return await api_request("POST", "/auth/telegram", json_body=payload)


async def get_user_ctx(tg_user: Any, language_override: Optional[str] = None) -> Dict[str, Any]:
    await refresh_app_config()
    auth = await auth_user(tg_user, language_override)
    user = auth.get("user") or {}
    lang = "en" if (user.get("language") == "en") else "ru"
    return {"auth": auth, "user": user, "token": auth.get("token"), "lang": lang}



async def issue_login_code_for_telegram_id(telegram_id: int, language: str = "ru") -> Tuple[Optional[str], Optional[str]]:
    try:
        headers: Dict[str, str] = {}
        if settings.AUTH_CODE_ISSUER_SECRET:
            headers["X-Auth-Code-Secret"] = settings.AUTH_CODE_ISSUER_SECRET
        data = await api_request(
            "POST",
            "/auth/code/issue",
            json_body={
                "telegram_id": int(telegram_id),
                "language": "en" if language == "en" else "ru",
            },
            extra_headers=headers or None,
        )
        code = (data.get("code") or "").strip() or None
        deep_link = (data.get("deep_link") or "").strip() or None
        return code, deep_link
    except Exception:
        logger.exception("Failed to issue login code for telegram user %s", telegram_id)
        return None, None


def append_token_details(text: str, lang: str, token: Optional[str], device_limit: Optional[int] = None) -> str:
    if not token:
        return text
    token_label = TEXT[lang]["token_label"]
    lines = [text, "", f"{token_label}: {token}"]
    if device_limit:
        lines.append(f"Устройства: 1 / {device_limit}" if lang == "ru" else f"Devices: 1 / {device_limit}")
    return "\n".join(lines)


def _client_hint_for_platform(platform: Optional[str]) -> str:
    key = (platform or "").strip().lower()
    if key in {"windows", "win", "macos", "mac", "osx", "darwin"}:
        return "happ"
    if key in {"android", "ios", "iphone", "ipad"}:
        return "v2raytun" if selected_client_mode() == "v2raytun" else "hiddify"
    return ""


def _append_subscription_client_hint(url: str, platform: Optional[str] = None) -> str:
    clean_url = str(url or "").strip()
    client_hint = _client_hint_for_platform(platform)
    if not clean_url or not client_hint:
        return clean_url
    try:
        parts = urlsplit(clean_url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query.setdefault("client", client_hint)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
    except Exception:
        joiner = "&" if "?" in clean_url else "?"
        return f"{clean_url}{joiner}client={client_hint}"


def build_subscription_url(subscription_token: Optional[str] = None, subscription_url: Optional[str] = None, platform: Optional[str] = None) -> Optional[str]:
    explicit_url = str(subscription_url or "").strip()
    if explicit_url:
        return _append_subscription_client_hint(explicit_url, platform=platform)
    token = str(subscription_token or "").strip()
    base = str(settings.BACKEND_BASE_URL or "").strip().rstrip("/")
    if not token or not base:
        return None
    return _append_subscription_client_hint(f"{base}/sub/{token}", platform=platform)


def _is_device_subscription_url(url: Optional[str]) -> bool:
    clean_url = str(url or "").strip()
    if not clean_url:
        return False
    try:
        parts = urlsplit(clean_url)
        token_part = unquote((parts.path or "").rstrip("/").rsplit("/", 1)[-1])
        return token_part.startswith("dt_")
    except Exception:
        return "/sub/dt_" in clean_url


def subscription_copy_rows(
    lang: str,
    subscription_url: Optional[str] = None,
    platform: Optional[str] = None,
    *,
    force: bool = False,
) -> List[List[InlineKeyboardButton]]:
    final_url = build_subscription_url(subscription_url=subscription_url, platform=platform)
    if not final_url:
        return []
    # Never put raw VLESS or old user-wide /sub/<user_token> into Telegram copy buttons.
    # Forced copy is allowed only for one-device dt_ subscription URLs.
    if force:
        if not _is_device_subscription_url(final_url):
            return []
    elif not bool(getattr(settings, "SUBSCRIPTION_SHOW_DIRECT_COPY_IN_BOT", False)):
        return []
    return [[InlineKeyboardButton(text=TEXT[lang]["copy_subscription"], copy_text=CopyTextButton(text=final_url))]]


def token_copy_rows(lang: str, token: Optional[str]) -> List[List[InlineKeyboardButton]]:
    if not token:
        return []
    return [[InlineKeyboardButton(text=TEXT[lang]["copy_token"], copy_text=CopyTextButton(text=token))]]


def platform_store_url(platform: str) -> str:
    key = (platform or "").strip().lower()
    if key == "windows":
        return str(getattr(settings, "HAPP_WINDOWS_APP_URL", getattr(settings, "WINDOWS_APP_URL", "")) or "").strip()
    if key in {"macos", "mac", "osx"}:
        return str(getattr(settings, "HAPP_MACOS_APP_URL", getattr(settings, "MACOS_APP_URL", "")) or "").strip()
    if selected_client_mode() == "v2raytun":
        if key == "android":
            return str(getattr(settings, "V2RAYTUN_ANDROID_APP_URL", getattr(settings, "ANDROID_APP_URL", "")) or "").strip()
        if key in {"ios", "iphone", "ipad"}:
            return str(getattr(settings, "V2RAYTUN_IOS_APP_URL", getattr(settings, "IOS_APP_URL", "")) or "").strip()
    if key == "android":
        return str(getattr(settings, "HIDDIFY_ANDROID_APP_URL", getattr(settings, "ANDROID_APP_URL", "")) or "").strip()
    if key in {"ios", "iphone", "ipad"}:
        return str(getattr(settings, "HIDDIFY_IOS_APP_URL", getattr(settings, "IOS_APP_URL", "")) or "").strip()
    return str(getattr(settings, "HAPP_WINDOWS_APP_URL", getattr(settings, "WINDOWS_APP_URL", "")) or "").strip()


def normalize_telegram_contact_url(url: Optional[str]) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""
    if raw.startswith("@"):
        username = raw[1:].strip()
        return f"https://t.me/{username}" if username else ""
    lowered = raw.lower()
    if lowered.startswith("t.me/"):
        return f"https://{raw}"
    if lowered.startswith(("http://", "https://", "tg://")):
        return raw
    if raw and " " not in raw and "/" not in raw:
        return f"https://t.me/{raw}"
    return raw


def is_supported_telegram_url(url: Optional[str]) -> bool:
    normalized = normalize_telegram_contact_url(url)
    if not normalized:
        return False
    scheme = (urlsplit(normalized).scheme or "").lower()
    return scheme in {"http", "https", "tg"}


async def safe_edit(callback: CallbackQuery, text: str, markup: Optional[InlineKeyboardMarkup] = None) -> None:
    try:
        if callback.message:
            await callback.message.edit_text(text, reply_markup=markup)
        else:
            await callback.answer(text)
    except Exception:
        if callback.message:
            await callback.message.answer(text, reply_markup=markup)


async def show_backend_error(target: Message | CallbackQuery, lang: str) -> None:
    text = TEXT[lang]["service_unavailable"]
    if isinstance(target, Message):
        await target.answer(text)
    else:
        await safe_edit(target, text, back_inline(lang))
        await target.answer()


async def show_unexpected_error(target: Message | CallbackQuery, lang: str) -> None:
    text = TEXT[lang]["unexpected_error"]
    if isinstance(target, Message):
        await target.answer(text)
    else:
        await safe_edit(target, text, back_inline(lang))
        await target.answer()


async def with_user_guard(target: Message | CallbackQuery, handler, preferred_lang: Optional[str] = None):
    lang = preferred_lang or "ru"
    tg_user = target.from_user if isinstance(target, (Message, CallbackQuery)) else None
    try:
        if tg_user:
            ctx = await get_user_ctx(tg_user)
            lang = ctx["lang"]
            return await handler(lang, ctx)
        return await handler(lang, None)
    except BackendUnavailable:
        await show_backend_error(target, lang)
    except ApiError as exc:
        logger.warning("Backend returned error %s: %s", exc.status_code, exc.detail)
        message = f"Error {exc.status_code}: {exc.detail}"
        if isinstance(target, Message):
            await target.answer(message)
        else:
            await safe_edit(target, message, back_inline(lang))
            await target.answer()
    except Exception:
        logger.exception("Unhandled bot error")
        await show_unexpected_error(target, lang)



def _show_buy_button_from_access(data: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(data, dict):
        return True
    return bool(data.get("show_buy_button", True))


async def _fetch_access_state(token: Optional[str]) -> Dict[str, Any]:
    if not token:
        return {}
    data = await api_request("GET", "/subscriptions/me", token=token)
    return data if isinstance(data, dict) else {}


async def build_main_menu_inline(lang: str, token: Optional[str] = None) -> InlineKeyboardMarkup:
    t = TEXT[lang]
    show_buy = True
    used = 0
    limit = int(getattr(settings, "VPN_DEFAULT_DEVICE_LIMIT", 1) or 1)
    is_active = False
    if token:
        with contextlib.suppress(Exception):
            access = await api_request("GET", "/subscriptions/me", token=token)
            show_buy = _show_buy_button_from_access(access)
            used = int(access.get("devices_used") or 0)
            limit = int(access.get("device_limit") or limit)
            is_active = bool(access.get("is_active"))
    connect_text = t["connect_this_device"]
    if is_active and used > 0 and used < limit:
        connect_text = t["add_second_device"] if used == 1 and limit >= 2 else t["add_device"]

    rows: List[List[InlineKeyboardButton]] = []
    if not is_active and show_buy:
        rows.append([InlineKeyboardButton(text=t["buy"], callback_data="menu:buy")])
    if is_active:
        rows.append([InlineKeyboardButton(text=connect_text, callback_data="menu:download")])
        rows.append([InlineKeyboardButton(text=t["devices"], callback_data="menu:devices")])
    else:
        rows.append([InlineKeyboardButton(text=t["sub"], callback_data="menu:sub")])
    rows.append([InlineKeyboardButton(text=t["support"], callback_data="menu:support")])
    rows.append([InlineKeyboardButton(text=t["instructions"], callback_data="menu:instructions")])
    return InlineKeyboardMarkup(inline_keyboard=rows)



def language_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Русский", callback_data="lang:ru")],
            [InlineKeyboardButton(text="English", callback_data="lang:en")],
        ]
    )



def remove_keyboard_markup() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()



def back_inline(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=TEXT[lang]["back"], callback_data="menu:root")]])



def payment_inline(lang: str, checkout_url: str, payment_id: str) -> InlineKeyboardMarkup:
    t = TEXT[lang]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t["proceed_payment"], url=checkout_url)],
            [InlineKeyboardButton(text=t["check_payment"], callback_data=f"payment:check:{payment_id}")],
            [InlineKeyboardButton(text=t["back"], callback_data="menu:root")],
        ]
    )



def build_open_app_url(
    credential: Optional[str] = None,
    lang: Optional[str] = None,
    *,
    code: Optional[str] = None,
    token: Optional[str] = None,
    platform: Optional[str] = None,
) -> str:
    base = (settings.OPEN_APP_BRIDGE_URL or "").strip() or f"{settings.BACKEND_BASE_URL.rstrip('/')}/open-app"
    final_code = code or credential
    final_token = token if not final_code else None
    if not final_code and not final_token and not lang:
        return base
    parts = urlsplit(base)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    if final_code:
        query["code"] = final_code
    elif final_token:
        query["token"] = final_token
    if lang:
        query["lang"] = lang
    if platform:
        query["platform"] = platform
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))



def activated_inline(
    lang: str,
    open_app_url: Optional[str] = None,
    *,
    subscription_url: Optional[str] = None,
    subscription_token: Optional[str] = None,
) -> InlineKeyboardMarkup:
    t = TEXT[lang]
    rows: List[List[InlineKeyboardButton]] = []
    rows.extend(subscription_copy_rows(lang, subscription_url))
    final_open_url = open_app_url or build_open_app_url(lang=lang, token=subscription_token)
    if is_supported_telegram_url(final_open_url):
        rows.append([InlineKeyboardButton(text=tx(lang, "open_app"), url=final_open_url)])
    rows.append([InlineKeyboardButton(text=tx(lang, "download_app"), callback_data="menu:download")])
    rows.append([InlineKeyboardButton(text=t["sub"], callback_data="menu:sub")])
    rows.append([InlineKeyboardButton(text=t["main_menu"], callback_data="menu:root")])
    return InlineKeyboardMarkup(inline_keyboard=rows)



def support_inline(lang: str, support_url: Optional[str] = None) -> InlineKeyboardMarkup:
    t = TEXT[lang]
    final_support_url = normalize_telegram_contact_url(support_url or settings.SUPPORT_TELEGRAM_URL)
    rows: List[List[InlineKeyboardButton]] = []
    if is_supported_telegram_url(final_support_url):
        rows.append([InlineKeyboardButton(text=t["write_support"], url=final_support_url)])
    rows.append([InlineKeyboardButton(text=t["back"], callback_data="menu:root")])
    return InlineKeyboardMarkup(inline_keyboard=rows)



def plan_actions_inline(lang: str, plan_code: str) -> InlineKeyboardMarkup:
    t = TEXT[lang]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t["pay_card"], callback_data=f"plan:pay:{plan_code}")],
            [InlineKeyboardButton(text=t["back"], callback_data="menu:buy")],
        ]
    )



def download_platforms_inline(lang: str) -> InlineKeyboardMarkup:
    t = TEXT[lang]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t["android"], callback_data="download:android")],
            [InlineKeyboardButton(text=t["ios"], callback_data="download:ios")],
            [InlineKeyboardButton(text=t["windows"], callback_data="download:windows")],
            [InlineKeyboardButton(text=t["macos"], callback_data="download:macos")],
            [InlineKeyboardButton(text=t["back"], callback_data="menu:root")],
        ]
    )



def platform_open_inline(
    lang: str,
    platform: str,
    open_app_url: Optional[str] = None,
    *,
    subscription_url: Optional[str] = None,
    subscription_token: Optional[str] = None,
) -> InlineKeyboardMarkup:
    t = TEXT[lang]
    url = platform_store_url(platform)
    rows: List[List[InlineKeyboardButton]] = [[InlineKeyboardButton(text=platform_download_button_text(lang, platform), url=url)]]
    final_open_url = open_app_url or (build_open_app_url(lang=lang, token=subscription_token, platform=platform) if subscription_token else build_open_app_url(lang=lang, platform=platform))
    if is_supported_telegram_url(final_open_url):
        rows.append([InlineKeyboardButton(text=tx(lang, "open_app"), url=final_open_url)])
    platform_subscription_url = build_subscription_url(subscription_url=subscription_url, subscription_token=subscription_token, platform=platform)
    rows.extend(subscription_copy_rows(lang, platform_subscription_url, platform=platform, force=True))
    rows.append([InlineKeyboardButton(text=t["back"], callback_data="menu:download")])
    return InlineKeyboardMarkup(inline_keyboard=rows)



def _fmt_dt(value: Optional[str]) -> str:
    if not value:
        return "—"
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone().strftime("%d.%m.%Y %H:%M")
    except Exception:
        return value



def _platform_label(platform: str) -> str:
    raw = (platform or "").strip().lower()
    if raw in {"ios", "iphone", "iphone / ipad", "ipad"}:
        return "iPhone / iPad"
    if raw == "android":
        return "Android"
    return platform or "Device"


async def remove_legacy_reply_keyboard(message: Message) -> None:
    with contextlib.suppress(Exception):
        cleanup = await message.answer("⁠", reply_markup=remove_keyboard_markup())
        with contextlib.suppress(Exception):
            await cleanup.delete()


async def send_menu(
    message: Message,
    lang: str,
    token: Optional[str] = None,
    welcome: bool = False,
    cleanup_keyboard: bool = False,
) -> None:
    if cleanup_keyboard:
        await remove_legacy_reply_keyboard(message)
    text = TEXT[lang]["welcome"] if welcome else TEXT[lang]["welcome_back"]
    await message.answer(text, reply_markup=await build_main_menu_inline(lang, token))


async def send_menu_for_callback(callback: CallbackQuery, lang: str, token: Optional[str] = None) -> None:
    if callback.message:
        await safe_edit(callback, TEXT[lang]["menu"], await build_main_menu_inline(lang, token))
        return
    await callback.answer(TEXT[lang]["menu"])


async def fetch_subscription_access(token: str) -> Dict[str, Optional[str]]:
    data = await api_request("GET", "/subscriptions/me", token=token)
    if not data.get("is_active"):
        return {
            "subscription_url": None,
            "subscription_token": None,
            "open_app_url": None,
        }
    clean_token = (data.get("subscription_token") or "").strip() or None
    return {
        "subscription_url": (data.get("subscription_url") or "").strip() or None,
        "subscription_token": clean_token,
        "open_app_url": build_open_app_url(lang=None, token=clean_token) if clean_token else None,
    }


async def fetch_platform_subscription_access(token: str, platform: str, lang: str) -> Dict[str, Optional[str]]:
    """Create/reuse a one-device dt_ token for this platform before showing buttons.

    The copy button must contain only /sub/dt_... (device-scoped subscription),
    never raw VLESS and never the old user-wide subscription token.
    """
    client_hint = _client_hint_for_platform(platform)
    data = await api_request(
        "POST",
        "/devices/subscription-token",
        token=token,
        json_body={
            "platform": platform,
            "client": client_hint,
            "device_name": "Happ" if client_hint == "happ" else selected_client_name(),
            "language": "en" if lang == "en" else "ru",
        },
    )
    clean_token = (data.get("subscription_token") or "").strip() or None
    return {
        "subscription_url": (data.get("subscription_url") or "").strip() or None,
        "subscription_token": clean_token,
        "open_app_url": (data.get("open_app_url") or "").strip() or (build_open_app_url(lang=lang, token=clean_token, platform=platform) if clean_token else None),
    }


def subscription_required_inline(lang: str, show_buy: bool = True) -> InlineKeyboardMarkup:
    t = TEXT[lang]
    rows = []
    if show_buy:
        rows.append([InlineKeyboardButton(text=t["buy"], callback_data="menu:buy")])
    rows.append([InlineKeyboardButton(text=t["back"], callback_data="menu:root")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def device_connect_rows(lang: str, used: int, limit: int, *, include_devices: bool = True) -> List[List[InlineKeyboardButton]]:
    t = TEXT[lang]
    rows: List[List[InlineKeyboardButton]] = []
    safe_used = max(0, int(used or 0))
    safe_limit = max(1, int(limit or 1))
    if safe_used < safe_limit:
        if safe_used == 0:
            label = t["connect_this_device"]
        elif safe_used == 1 and safe_limit >= 2:
            label = t["add_second_device"]
        else:
            label = t["add_device"]
        rows.append([InlineKeyboardButton(text=label, callback_data="menu:download")])
    if include_devices:
        rows.append([InlineKeyboardButton(text=t["devices"], callback_data="menu:devices")])
    return rows


async def render_subscription_message(lang: str, token: str, telegram_id: int) -> Tuple[str, InlineKeyboardMarkup]:
    del telegram_id
    t = TEXT[lang]
    data = await api_request("GET", "/subscriptions/me", token=token)
    sub = data.get("subscription")
    used = int(data.get("devices_used") or 0)
    limit = int(data.get("device_limit") or settings.VPN_DEFAULT_DEVICE_LIMIT)
    subscription_url = (data.get("subscription_url") or "").strip() or None
    subscription_token = (data.get("subscription_token") or "").strip() or None
    open_app_url = build_open_app_url(lang=lang, token=subscription_token) if subscription_token else ""
    access_source = str(data.get("access_source") or "").strip().lower()
    show_buy = _show_buy_button_from_access(data)

    if access_source == "free_mode":
        text = "\n".join(
            [
                f"{t['subscription_status']}: {t['subscription_active']}",
                f"{t['plan']}: {t['free_mode_label']}",
                f"{t['devices_used']}: {used} / {limit}",
                "",
                t["free_mode_access"],
                "",
                tx(lang, "manual_import_hint"),
            ]
        ).strip()
        rows: List[List[InlineKeyboardButton]] = []
        rows.extend(device_connect_rows(lang, used, limit))
        rows.extend(subscription_copy_rows(lang, subscription_url))
        if is_supported_telegram_url(open_app_url):
            rows.append([InlineKeyboardButton(text=tx(lang, "open_app"), url=open_app_url)])
        rows.append([InlineKeyboardButton(text=tx(lang, "download_app"), callback_data="menu:download")])
        rows.append([InlineKeyboardButton(text=t["back"], callback_data="menu:root")])
        return text, InlineKeyboardMarkup(inline_keyboard=rows)

    if access_source == "paid_grace":
        grace_started_at = data.get("paid_grace_started_at")
        grace_hours = int(data.get("paid_grace_hours") or 24)
        hours_left_text = str(grace_hours)
        if grace_started_at:
            with contextlib.suppress(Exception):
                from datetime import datetime, timezone, timedelta
                started = datetime.fromisoformat(str(grace_started_at).replace("Z", "+00:00"))
                left = started + timedelta(hours=grace_hours) - datetime.now(timezone.utc)
                hours_left_text = str(max(0, int(left.total_seconds() // 3600)))
        text = "\n".join(
            [
                f"{t['subscription_status']}: {t['subscription_active']}",
                f"{t['plan']}: {t['free_mode_label']} / grace",
                f"{t['devices_used']}: {used} / {limit}",
                "",
                t["grace_mode_access"],
                f"{t['grace_hours_left']}: {hours_left_text}",
                "",
                tx(lang, "manual_import_hint"),
            ]
        ).strip()
        rows: List[List[InlineKeyboardButton]] = []
        rows.extend(device_connect_rows(lang, used, limit))
        rows.extend(subscription_copy_rows(lang, subscription_url))
        if show_buy:
            rows.append([InlineKeyboardButton(text=t["renew"], callback_data="menu:buy")])
        if is_supported_telegram_url(open_app_url):
            rows.append([InlineKeyboardButton(text=tx(lang, "open_app"), url=open_app_url)])
        rows.append([InlineKeyboardButton(text=tx(lang, "download_app"), callback_data="menu:download")])
        rows.append([InlineKeyboardButton(text=t["back"], callback_data="menu:root")])
        return text, InlineKeyboardMarkup(inline_keyboard=rows)

    if not sub:
        text = "\n".join([t["subscription_none"], "", t["subscription_buy_prompt"]]).strip()
        return text, subscription_required_inline(lang, show_buy=show_buy)

    plan_name = sub["name_ru"] if lang == "ru" else sub["name_en"]
    status_text = t["subscription_active"] if data.get("is_active") else t["subscription_expired"]

    if not data.get("is_active"):
        text = "\n".join(
            [
                f"{t['subscription_status']}: {status_text}",
                f"{t['plan']}: {plan_name}",
                f"{t['valid_until']}: {_fmt_dt(sub.get('expires_at'))}",
                f"{t['devices_used']}: {used} / {limit}",
                "",
                t["expired_access_disabled"],
                t["expired_buy_cta"],
            ]
        ).strip()
        return text, subscription_required_inline(lang, show_buy=show_buy)

    text = "\n".join(
        [
            f"{t['subscription_status']}: {status_text}",
            f"{t['plan']}: {plan_name}",
            f"{t['valid_until']}: {_fmt_dt(sub.get('expires_at'))}",
            f"{t['devices_used']}: {used} / {limit}",
            "",
            tx(lang, "manual_import_hint"),
        ]
    ).strip()
    rows: List[List[InlineKeyboardButton]] = []
    rows.extend(device_connect_rows(lang, used, limit))
    rows.extend(subscription_copy_rows(lang, subscription_url))
    if show_buy:
        rows.append([InlineKeyboardButton(text=t["renew"], callback_data="menu:buy")])
    if is_supported_telegram_url(open_app_url):
        rows.append([InlineKeyboardButton(text=tx(lang, "open_app"), url=open_app_url)])
    rows.append([InlineKeyboardButton(text=tx(lang, "download_app"), callback_data="menu:download")])
    rows.append([InlineKeyboardButton(text=t["back"], callback_data="menu:root")])
    markup = InlineKeyboardMarkup(inline_keyboard=rows)
    return text, markup


async def render_devices_message(lang: str, token: str) -> Tuple[str, InlineKeyboardMarkup]:
    t = TEXT[lang]
    data = await api_request("GET", "/devices", token=token)
    items = data.get("items", [])
    used = int(data.get("devices_used") or 0)
    limit = int(data.get("device_limit") or settings.VPN_DEFAULT_DEVICE_LIMIT)
    lines: List[str] = [t["devices"], f"{t['devices_used']}: {used} / {limit}", "", t["devices_hint"], ""]
    rows: List[List[InlineKeyboardButton]] = []

    if not items:
        lines.append(t["devices_none"])
    else:
        for idx, row in enumerate(items, start=1):
            device_name = row.get("device_name") or "—"
            platform = _platform_label(str(row.get("platform") or ""))
            is_pending = bool(row.get("is_pending")) or str(row.get("device_status") or "").lower() == "pending"
            if is_pending:
                status_text = t.get("device_pending", "⏳ waiting for connection")
                shown_time = _fmt_dt(row.get("pending_created_at") or row.get("created_at"))
            else:
                status_text = t["device_active"] if row.get("is_active", True) else t["device_inactive"]
                shown_time = _fmt_dt(row.get("last_seen_at"))
            lines.append(f"{idx}. {platform} — {device_name} — {status_text} — {shown_time}")
            rows.append([InlineKeyboardButton(text=f"{t['delete_device']} #{idx}", callback_data=f"device:remove:{row['id']}")])

    if used >= limit:
        lines.extend(["", t["limit_reached"]])
    rows.extend(device_connect_rows(lang, used, limit, include_devices=False))
    rows.append([InlineKeyboardButton(text=t["back"], callback_data="menu:root")])
    return "\n".join(lines).strip(), InlineKeyboardMarkup(inline_keyboard=rows)


async def ensure_active_subscription_ui(lang: str, token: str) -> Optional[Tuple[str, InlineKeyboardMarkup]]:
    data = await api_request("GET", "/subscriptions/me", token=token)
    if data.get("is_active"):
        return None
    sub = data.get("subscription")
    show_buy = _show_buy_button_from_access(data)
    if sub:
        plan_name = sub["name_ru"] if lang == "ru" else sub["name_en"]
        text = "\n".join(
            [
                f"{TEXT[lang]['subscription_status']}: {TEXT[lang]['subscription_expired']}",
                f"{TEXT[lang]['plan']}: {plan_name}",
                f"{TEXT[lang]['valid_until']}: {_fmt_dt(sub.get('expires_at'))}",
                "",
                TEXT[lang]["expired_access_disabled"],
                TEXT[lang]["expired_buy_cta"],
            ]
        ).strip()
    else:
        text = "\n".join([TEXT[lang]["subscription_none"], "", TEXT[lang]["subscription_buy_prompt"]]).strip()
    return text, subscription_required_inline(lang, show_buy=show_buy)


async def render_support_message(lang: str) -> Tuple[str, InlineKeyboardMarkup]:
    faq = await api_request("GET", f"/support/faq?lang={lang}")
    support_url = normalize_telegram_contact_url(faq.get("support_url") or settings.SUPPORT_TELEGRAM_URL)
    text = faq.get("faq") or (settings.SUPPORT_FAQ_EN if lang == "en" else settings.SUPPORT_FAQ_RU)
    return str(text).strip(), support_inline(lang, support_url)


async def render_instructions_message(lang: str) -> Tuple[str, InlineKeyboardMarkup]:
    return tx(lang, "instructions_text"), InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=tx(lang, "download"), callback_data="menu:download")],
            [InlineKeyboardButton(text=TEXT[lang]["back"], callback_data="menu:root")],
        ]
    )


async def render_payment_success_message(lang: str, token: str, telegram_id: int) -> Tuple[str, InlineKeyboardMarkup]:
    del telegram_id
    t = TEXT[lang]
    data = await api_request("GET", "/subscriptions/me", token=token)
    sub = data.get("subscription")
    subscription_url = (data.get("subscription_url") or "").strip() or None
    subscription_token = (data.get("subscription_token") or "").strip() or None
    open_app_url = build_open_app_url(lang=lang, token=subscription_token) if subscription_token else ""
    if not sub:
        text = "\n".join([t["payment_received"], tx(lang, "manual_import_hint")]).strip()
        return text, activated_inline(lang, open_app_url, subscription_url=subscription_url, subscription_token=subscription_token)
    plan_name = sub["name_ru"] if lang == "ru" else sub["name_en"]
    device_limit = int(data.get('device_limit') or sub.get('device_limit') or settings.VPN_DEFAULT_DEVICE_LIMIT)
    text = "\n".join(
        [
            t["payment_received"],
            t["subscription_activated"],
            f"{t['plan']}: {plan_name}",
            f"{t['active_until']}: {_fmt_dt(sub.get('expires_at'))}",
            f"{t['available_devices']}: {device_limit} / {device_limit}",
            "",
            tx(lang, "manual_import_hint"),
        ]
    ).strip()
    return text, activated_inline(lang, open_app_url, subscription_url=subscription_url, subscription_token=subscription_token)


@dp.message(Command("start"))
async def start(message: Message) -> None:
    async def _handler(_lang: str, ctx: Dict[str, Any]) -> None:
        current_lang = "en" if (ctx.get("lang") == "en") else "ru"
        await remove_legacy_reply_keyboard(message)
        await message.answer(TEXT[current_lang]["choose_language"], reply_markup=language_inline())

    await with_user_guard(message, _handler)


@dp.message(Command("menu"))
async def menu_command(message: Message) -> None:
    async def _handler(lang: str, _ctx: Dict[str, Any]) -> None:
        await send_menu(message, lang, _ctx.get('token') if isinstance(_ctx, dict) else None, cleanup_keyboard=True)

    await with_user_guard(message, _handler)


@dp.message(F.text.in_({TEXT["ru"]["buy"], TEXT["en"]["buy"]}))
async def buy_from_text(message: Message) -> None:
    async def _handler(lang: str, _ctx: Dict[str, Any]) -> None:
        access = await _fetch_access_state(_ctx.get("token") if isinstance(_ctx, dict) else None)
        if not _show_buy_button_from_access(access):
            await message.answer(TEXT[lang]["buy_hidden_free_mode"], reply_markup=await build_main_menu_inline(lang, _ctx.get("token") if isinstance(_ctx, dict) else None))
            return
        plans = await api_request("GET", "/plans")
        rows = []
        for item in plans.get("items", []):
            label = f"{item['name_ru'] if lang == 'ru' else item['name_en']} — {item['price_rub']} ₽"
            rows.append([InlineKeyboardButton(text=label, callback_data=f"plan:view:{item['code']}")])
        rows.append([InlineKeyboardButton(text=TEXT[lang]["back"], callback_data="menu:root")])
        await message.answer(TEXT[lang]["choose_plan"], reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

    await with_user_guard(message, _handler)


@dp.message(F.text.in_({TEXT["ru"]["sub"], TEXT["en"]["sub"]}))
async def subscription_from_text(message: Message) -> None:
    async def _handler(lang: str, ctx: Dict[str, Any]) -> None:
        text, markup = await render_subscription_message(lang, ctx["token"], int(ctx["user"]["telegram_id"]))
        await message.answer(text, reply_markup=markup)

    await with_user_guard(message, _handler)


@dp.message(F.text.in_({TEXT["ru"]["devices"], TEXT["en"]["devices"]}))
async def devices_from_text(message: Message) -> None:
    async def _handler(lang: str, ctx: Dict[str, Any]) -> None:
        text, markup = await render_devices_message(lang, ctx["token"])
        await message.answer(text, reply_markup=markup)

    await with_user_guard(message, _handler)


@dp.message(F.text.in_({TEXT["ru"]["download"], TEXT["en"]["download"]}))
async def download_from_text(message: Message) -> None:
    async def _handler(lang: str, _ctx: Dict[str, Any]) -> None:
        await message.answer(tx(lang, "choose_platform"), reply_markup=download_platforms_inline(lang))

    await with_user_guard(message, _handler)


@dp.message(F.text.in_({TEXT["ru"]["support"], TEXT["en"]["support"]}))
async def support_from_text(message: Message) -> None:
    async def _handler(lang: str, _ctx: Dict[str, Any]) -> None:
        text, markup = await render_support_message(lang)
        await message.answer(text, reply_markup=markup)

    await with_user_guard(message, _handler)


@dp.message(F.text.in_({TEXT["ru"]["instructions"], TEXT["en"]["instructions"]}))
async def instructions_from_text(message: Message) -> None:
    async def _handler(lang: str, _ctx: Dict[str, Any]) -> None:
        text, markup = await render_instructions_message(lang)
        await message.answer(text, reply_markup=markup)

    await with_user_guard(message, _handler)


@dp.message(F.text.in_({"Русский", "English"}))
async def language_from_text(message: Message) -> None:
    if message.text in {"Русский", "English"}:
        lang = "ru" if message.text == "Русский" else "en"
        async def _handler(_lang: str, ctx: Dict[str, Any]) -> None:
            await api_request("PATCH", "/users/me/language", token=ctx["token"], json_body={"language": lang})
            await message.answer(
                f"{TEXT[lang]['language_saved']}\n\n{TEXT[lang]['welcome']}",
                reply_markup=await build_main_menu_inline(lang, ctx.get('token') if isinstance(ctx, dict) else None),
            )
        await with_user_guard(message, _handler, preferred_lang=lang)
        return



@dp.message(F.text.in_({TEXT["ru"]["renew"], TEXT["en"]["renew"]}))
async def renew_from_text(message: Message) -> None:
    await buy_from_text(message)


@dp.message(F.text.in_({TEXT["ru"]["back"], TEXT["en"]["back"], TEXT["ru"]["main_menu"], TEXT["en"]["main_menu"]}))
async def menu_from_text_alias(message: Message) -> None:
    async def _handler(lang: str, _ctx: Dict[str, Any]) -> None:
        await send_menu(message, lang, _ctx.get('token') if isinstance(_ctx, dict) else None, cleanup_keyboard=True)

    await with_user_guard(message, _handler)


@dp.message(F.text.in_({TEXT["ru"]["android"], TEXT["en"]["android"]}))
async def download_android_from_text(message: Message) -> None:
    async def _handler(lang: str, _ctx: Dict[str, Any]) -> None:
        inactive = await ensure_active_subscription_ui(lang, _ctx["token"])
        if inactive:
            text, markup = inactive
            await message.answer(text, reply_markup=markup)
            return
        access = await fetch_platform_subscription_access(_ctx["token"], "android", lang)
        await message.answer(tx(lang, "download_android"), reply_markup=platform_open_inline(lang, "android", access.get("open_app_url"), subscription_url=access.get("subscription_url"), subscription_token=access.get("subscription_token")))

    await with_user_guard(message, _handler)


@dp.message(F.text.in_({TEXT["ru"]["ios"], TEXT["en"]["ios"]}))
async def download_ios_from_text(message: Message) -> None:
    async def _handler(lang: str, _ctx: Dict[str, Any]) -> None:
        inactive = await ensure_active_subscription_ui(lang, _ctx["token"])
        if inactive:
            text, markup = inactive
            await message.answer(text, reply_markup=markup)
            return
        access = await fetch_platform_subscription_access(_ctx["token"], "ios", lang)
        await message.answer(tx(lang, "download_ios"), reply_markup=platform_open_inline(lang, "ios", access.get("open_app_url"), subscription_url=access.get("subscription_url"), subscription_token=access.get("subscription_token")))

    await with_user_guard(message, _handler)


@dp.message(F.text.in_({TEXT["ru"]["windows"], TEXT["en"]["windows"]}))
async def download_windows_from_text(message: Message) -> None:
    async def _handler(lang: str, _ctx: Dict[str, Any]) -> None:
        inactive = await ensure_active_subscription_ui(lang, _ctx["token"])
        if inactive:
            text, markup = inactive
            await message.answer(text, reply_markup=markup)
            return
        access = await fetch_platform_subscription_access(_ctx["token"], "windows", lang)
        await message.answer(tx(lang, "download_windows"), reply_markup=platform_open_inline(lang, "windows", access.get("open_app_url"), subscription_url=access.get("subscription_url"), subscription_token=access.get("subscription_token")))

    await with_user_guard(message, _handler)


@dp.message(F.text.in_({TEXT["ru"]["macos"], TEXT["en"]["macos"]}))
async def download_macos_from_text(message: Message) -> None:
    async def _handler(lang: str, _ctx: Dict[str, Any]) -> None:
        inactive = await ensure_active_subscription_ui(lang, _ctx["token"])
        if inactive:
            text, markup = inactive
            await message.answer(text, reply_markup=markup)
            return
        access = await fetch_platform_subscription_access(_ctx["token"], "macos", lang)
        await message.answer(tx(lang, "download_macos"), reply_markup=platform_open_inline(lang, "macos", access.get("open_app_url"), subscription_url=access.get("subscription_url"), subscription_token=access.get("subscription_token")))

    await with_user_guard(message, _handler)


@dp.message()
async def fallback_message(message: Message) -> None:
    async def _handler(lang: str, _ctx: Dict[str, Any]) -> None:
        await send_menu(message, lang, _ctx.get('token') if isinstance(_ctx, dict) else None, cleanup_keyboard=True)

    await with_user_guard(message, _handler)


@dp.callback_query(F.data == "menu:root")
async def cb_root(callback: CallbackQuery) -> None:
    async def _handler(lang: str, _ctx: Dict[str, Any]) -> None:
        await send_menu_for_callback(callback, lang, _ctx.get('token') if isinstance(_ctx, dict) else None)
        await callback.answer()

    await with_user_guard(callback, _handler)


@dp.callback_query(F.data == "menu:buy")
async def cb_buy(callback: CallbackQuery) -> None:
    async def _handler(lang: str, _ctx: Dict[str, Any]) -> None:
        access = await _fetch_access_state(_ctx.get("token") if isinstance(_ctx, dict) else None)
        if not _show_buy_button_from_access(access):
            await safe_edit(callback, TEXT[lang]["buy_hidden_free_mode"], await build_main_menu_inline(lang, _ctx["token"]))
            await callback.answer()
            return
        plans = await api_request("GET", "/plans")
        rows = []
        for item in plans.get("items", []):
            label = f"{item['name_ru'] if lang == 'ru' else item['name_en']} — {item['price_rub']} ₽"
            rows.append([InlineKeyboardButton(text=label, callback_data=f"plan:view:{item['code']}")])
        rows.append([InlineKeyboardButton(text=TEXT[lang]["back"], callback_data="menu:root")])
        await safe_edit(callback, TEXT[lang]["choose_plan"], InlineKeyboardMarkup(inline_keyboard=rows))
        await callback.answer()

    await with_user_guard(callback, _handler)


@dp.callback_query(F.data.startswith("plan:view:"))
async def cb_plan_view(callback: CallbackQuery) -> None:
    async def _handler(lang: str, _ctx: Dict[str, Any]) -> None:
        access = await _fetch_access_state(_ctx.get("token") if isinstance(_ctx, dict) else None)
        if not _show_buy_button_from_access(access):
            await safe_edit(callback, TEXT[lang]["buy_hidden_free_mode"], await build_main_menu_inline(lang, _ctx.get("token") if isinstance(_ctx, dict) else None))
            await callback.answer()
            return
        plan_code = callback.data.split(":", 2)[2]
        plans = await api_request("GET", "/plans")
        plan = next((item for item in plans.get("items", []) if item["code"] == plan_code), None)
        if not plan:
            raise ApiError(404, "Plan not found")
        plan_name = plan["name_ru"] if lang == "ru" else plan["name_en"]
        text = "\n".join(
            [
                f"{TEXT[lang]['plan']}: {plan_name}",
                f"{TEXT[lang]['price']}: {plan['price_rub']} ₽",
                f"{TEXT[lang]['devices_up_to']}: {plan['device_limit']}",
                f"{TEXT[lang]['payment_method']}: {TEXT[lang]['pay_card']}",
                "",
                payment_created_text(lang),
            ]
        )
        await safe_edit(callback, text, plan_actions_inline(lang, plan_code))
        await callback.answer()

    await with_user_guard(callback, _handler)


@dp.callback_query(F.data.startswith("plan:pay:"))
async def cb_plan_pay(callback: CallbackQuery) -> None:
    async def _handler(lang: str, ctx: Dict[str, Any]) -> None:
        access = await _fetch_access_state(ctx.get("token") if isinstance(ctx, dict) else None)
        if not _show_buy_button_from_access(access):
            await safe_edit(callback, TEXT[lang]["buy_hidden_free_mode"], await build_main_menu_inline(lang, ctx.get("token") if isinstance(ctx, dict) else None))
            await callback.answer()
            return
        plan_code = callback.data.split(":", 2)[2]
        result = await api_request("POST", "/payments/create", token=ctx["token"], json_body={"plan_code": plan_code, "method": "telegram"})
        payment = result.get("payment") or {}
        if not result.get("payments_enabled"):
            await safe_edit(callback, TEXT[lang]["payments_off"], back_inline(lang))
            await callback.answer()
            return
        checkout_url = payment.get("checkout_url") or settings.SUPPORT_TELEGRAM_URL
        await safe_edit(callback, payment_created_text(lang), payment_inline(lang, checkout_url, payment["id"]))
        await callback.answer()

    await with_user_guard(callback, _handler)


@dp.callback_query(F.data.startswith("payment:check:"))
async def cb_payment_check(callback: CallbackQuery) -> None:
    async def _handler(lang: str, ctx: Dict[str, Any]) -> None:
        payment_id = callback.data.split(":", 2)[2]
        data = await api_request("GET", f"/payments/{payment_id}", token=ctx["token"])
        payment = data.get("payment") or {}
        if payment.get("status") == "paid":
            text, markup = await render_payment_success_message(lang, ctx["token"], int(ctx["user"]["telegram_id"]))
            await safe_edit(callback, text, markup)
        else:
            text = f"{TEXT[lang]['payment_waiting']}: {payment.get('status', 'created')}"
            markup = payment_inline(lang, payment.get("checkout_url") or settings.SUPPORT_TELEGRAM_URL, payment_id)
            await safe_edit(callback, text, markup)
        await callback.answer()

    await with_user_guard(callback, _handler)


@dp.callback_query(F.data == "menu:sub")
async def cb_subscription(callback: CallbackQuery) -> None:
    async def _handler(lang: str, ctx: Dict[str, Any]) -> None:
        text, markup = await render_subscription_message(lang, ctx["token"], int(ctx["user"]["telegram_id"]))
        await safe_edit(callback, text, markup)
        await callback.answer()

    await with_user_guard(callback, _handler)


@dp.callback_query(F.data == "menu:devices")
async def cb_devices(callback: CallbackQuery) -> None:
    async def _handler(lang: str, ctx: Dict[str, Any]) -> None:
        text, markup = await render_devices_message(lang, ctx["token"])
        await safe_edit(callback, text, markup)
        await callback.answer()

    await with_user_guard(callback, _handler)


@dp.callback_query(F.data.startswith("device:remove:"))
async def cb_device_remove(callback: CallbackQuery) -> None:
    async def _handler(lang: str, ctx: Dict[str, Any]) -> None:
        device_id = int(callback.data.split(":", 2)[2])
        await api_request("DELETE", f"/devices/{device_id}", token=ctx["token"])
        text, markup = await render_devices_message(lang, ctx["token"])
        await safe_edit(callback, f"{TEXT[lang]['device_removed']}\n\n{text}", markup)
        await callback.answer()

    await with_user_guard(callback, _handler)


@dp.callback_query(F.data.startswith("device:reset:"))
async def cb_device_reset(callback: CallbackQuery) -> None:
    async def _handler(lang: str, ctx: Dict[str, Any]) -> None:
        device_id = int(callback.data.split(":", 2)[2])
        await api_request("DELETE", f"/devices/{device_id}", token=ctx["token"])
        text, markup = await render_devices_message(lang, ctx["token"])
        await safe_edit(callback, f"{TEXT[lang]['device_removed']}\n\n{text}", markup)
        await callback.answer()

    await with_user_guard(callback, _handler)


@dp.callback_query(F.data == "menu:download")
async def cb_download(callback: CallbackQuery) -> None:
    async def _handler(lang: str, _ctx: Dict[str, Any]) -> None:
        inactive = await ensure_active_subscription_ui(lang, _ctx["token"])
        if inactive:
            text, markup = inactive
            await safe_edit(callback, text, markup)
            await callback.answer()
            return
        await safe_edit(callback, tx(lang, "choose_platform"), download_platforms_inline(lang))
        await callback.answer()

    await with_user_guard(callback, _handler)


@dp.callback_query(F.data.startswith("download:"))
async def cb_download_platform(callback: CallbackQuery) -> None:
    async def _handler(lang: str, _ctx: Dict[str, Any]) -> None:
        inactive = await ensure_active_subscription_ui(lang, _ctx["token"])
        if inactive:
            text, markup = inactive
            await safe_edit(callback, text, markup)
            await callback.answer()
            return
        platform = callback.data.split(":", 1)[1]
        if platform == "android":
            text = tx(lang, "download_android")
        elif platform == "ios":
            text = tx(lang, "download_ios")
        elif platform == "windows":
            text = tx(lang, "download_windows")
        else:
            text = tx(lang, "download_macos")
        access = await fetch_platform_subscription_access(_ctx["token"], platform, lang)
        await safe_edit(callback, text, platform_open_inline(lang, platform, access.get("open_app_url"), subscription_url=access.get("subscription_url"), subscription_token=access.get("subscription_token")))
        await callback.answer()

    await with_user_guard(callback, _handler)


@dp.callback_query(F.data == "menu:support")
async def cb_support(callback: CallbackQuery) -> None:
    async def _handler(lang: str, _ctx: Dict[str, Any]) -> None:
        text, markup = await render_support_message(lang)
        await safe_edit(callback, text, markup)
        await callback.answer()

    await with_user_guard(callback, _handler)


@dp.callback_query(F.data == "menu:instructions")
async def cb_instructions(callback: CallbackQuery) -> None:
    async def _handler(lang: str, _ctx: Dict[str, Any]) -> None:
        text, markup = await render_instructions_message(lang)
        await safe_edit(callback, text, markup)
        await callback.answer()

    await with_user_guard(callback, _handler)


@dp.callback_query(F.data.startswith("lang:"))
async def cb_set_language(callback: CallbackQuery) -> None:
    lang = callback.data.split(":", 1)[1]
    norm = "en" if lang == "en" else "ru"

    async def _handler(_lang: str, ctx: Dict[str, Any]) -> None:
        await api_request("PATCH", "/users/me/language", token=ctx["token"], json_body={"language": norm})
        await safe_edit(
            callback,
            f"{TEXT[norm]['language_saved']}\n\n{TEXT[norm]['welcome']}",
            await build_main_menu_inline(norm, ctx.get('token')),
        )
        await callback.answer()

    await with_user_guard(callback, _handler, preferred_lang=norm)


async def build_notification_message(item: Dict[str, Any]) -> Tuple[str, Optional[InlineKeyboardMarkup]]:
    lang = "en" if item.get("language") == "en" else "ru"
    t = TEXT[lang]
    payload = item.get("payload") or {}
    event_type = item.get("event_type")
    if event_type == "payment_paid":
        plan_name = payload.get("plan_name_en") if lang == "en" else payload.get("plan_name_ru")
        device_limit = int(payload.get('device_limit', settings.VPN_DEFAULT_DEVICE_LIMIT) or settings.VPN_DEFAULT_DEVICE_LIMIT)
        subscription_token = (payload.get("subscription_token") or "").strip() or None
        subscription_url = build_subscription_url(subscription_token=subscription_token)
        open_app_url = build_open_app_url(lang=lang, token=subscription_token) if subscription_token else ""
        text = "\n".join(
            [
                t["payment_received"],
                t["subscription_activated"],
                f"{t['plan']}: {plan_name}",
                f"{t['active_until']}: {_fmt_dt(payload.get('expires_at'))}",
                f"{t['available_devices']}: {device_limit} / {device_limit}",
                "",
                tx(lang, "manual_import_hint"),
            ]
        ).strip()
        return text, activated_inline(lang, open_app_url, subscription_url=subscription_url, subscription_token=subscription_token)
    if event_type == "subscription_expiring":
        text = f"{t['one_day_left']}\n\n{t['active_until']}: {_fmt_dt(payload.get('expires_at'))}"
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=t["renew"], callback_data="menu:buy")],
                [InlineKeyboardButton(text=t["main_menu"], callback_data="menu:root")],
            ]
        )
        return text, markup
    if event_type == "subscription_expiring_12h":
        text = f"{t['twelve_hours_left']}\n\n{t['active_until']}: {_fmt_dt(payload.get('expires_at'))}"
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=t["renew"], callback_data="menu:buy")],
                [InlineKeyboardButton(text=t["main_menu"], callback_data="menu:root")],
            ]
        )
        return text, markup
    if event_type == "subscription_expired":
        text = "\n".join([t["expired_notice"], "", t["expired_access_disabled"], t["expired_buy_cta"]]).strip()
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=t["buy"], callback_data="menu:buy")],
                [InlineKeyboardButton(text=t["main_menu"], callback_data="menu:root")],
            ]
        )
        return text, markup
    if event_type == "payment_failed":
        return t['payment_failed'], back_inline(lang)
    if event_type == "device_removed":
        name = payload.get("device_name") or payload.get("platform") or "device"
        return f"{t['device_removed']}\n{name}", back_inline(lang)
    return t["main_menu"], back_inline(lang)


def _notification_error_is_permanent(error_message: str) -> bool:
    raw = str(error_message or "").strip().lower()
    if not raw:
        return False
    permanent_markers = (
        "chat not found",
        "bot was blocked by the user",
        "user is deactivated",
        "forbidden: bot was blocked",
        "forbidden: user is deactivated",
    )
    return any(marker in raw for marker in permanent_markers)


async def notification_loop() -> None:
    await asyncio.sleep(3)
    while True:
        try:
            enqueue_subscription_notifications()
            items = list_pending_notifications(limit=50)
            for item in items:
                try:
                    text, markup = await build_notification_message(item)
                    await require_bot().send_message(int(item["telegram_id"]), text, reply_markup=markup)
                    mark_notification_sent(int(item["id"]))
                except Exception as exc:
                    error_message = str(exc)
                    record_bot_error("bot-notification", str(item.get("unique_key") or item.get("id")), error_message)
                    if _notification_error_is_permanent(error_message):
                        mark_notification_failed(int(item["id"]), error_message)
                    else:
                        mark_notification_retry(int(item["id"]), error_message, int(getattr(settings, "BOT_NOTIFICATION_RETRY_BACKOFF_SEC", 300) or 300))
            await asyncio.sleep(max(15, settings.BOT_NOTIFICATION_POLL_SEC))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Notification loop error")
            record_bot_error("bot-notification-loop", "loop", str(exc))
            await asyncio.sleep(30)


async def configure_bot() -> None:
    app_bot = require_bot()
    await app_bot.delete_webhook(drop_pending_updates=False)
    with contextlib.suppress(Exception):
        await app_bot.delete_my_commands()
    logger.debug("Bot configured, webhook removed, command menu cleared")


async def verify_backend() -> None:
    data = await api_request("GET", "/health")
    logger.debug("Backend health check succeeded: %s", data)


async def main() -> None:
    global bot
    if not settings.BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is required")
    if not settings.BACKEND_BASE_URL:
        raise RuntimeError("BACKEND_BASE_URL is required")

    bot = Bot(token=settings.BOT_TOKEN)

    logger.debug("Starting bot for %s", settings.BOT_USERNAME or settings.BOT_NAME)
    logger.debug("Backend base URL: %s", settings.BACKEND_BASE_URL)

    await configure_bot()
    await verify_backend()

    notifier = asyncio.create_task(notification_loop())
    try:
        await dp.start_polling(bot)
    finally:
        notifier.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await notifier


if __name__ == "__main__":
    asyncio.run(main())
