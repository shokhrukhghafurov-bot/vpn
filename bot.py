import contextlib
import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

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
    mark_notification_sent,
    record_bot_error,
)


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


TEXT: Dict[str, Dict[str, str]] = {
    "ru": {
        "welcome": "Добро пожаловать в INET\nВыберите действие ниже",
        "welcome_back": "Главное меню INET",
        "menu": "Главное меню INET",
        "buy": "Купить подписку",
        "sub": "Моя подписка",
        "devices": "Мои устройства",
        "download": "Скачать приложение",
        "support": "Поддержка",
        "language": "Язык",
        "renew": "Продлить",
        "open_app": "Открыть приложение",
        "download_app": "Скачать приложение",
        "back": "Назад",
        "main_menu": "Главное меню",
        "choose_language": "Выберите язык",
        "language_saved": "Язык сохранён.",
        "choose_plan": "Выберите тариф:",
        "plan": "Тариф",
        "price": "Цена",
        "devices_up_to": "Устройств",
        "payment_method": "Способ оплаты",
        "pay_card": "Оплатить картой / СБП",
        "proceed_payment": "Перейти к оплате",
        "check_payment": "Проверить оплату",
        "cancel": "Отменить",
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
        "device_removed": "Устройство удалено. Слот освобождён.",
        "choose_platform": "Выберите платформу:",
        "android": "Android",
        "ios": "iPhone / iPad",
        "download_android": "Android: скачайте приложение по кнопке ниже, затем войдите под своим аккаунтом.",
        "download_ios": "iPhone / iPad: откройте ссылку ниже и установите приложение.",
        "support_text": "Связаться с поддержкой",
        "faq": "FAQ",
        "write_support": "Написать в поддержку",
        "service_unavailable": "Сервис временно недоступен. Проверь BACKEND_BASE_URL, DATABASE_URL и логи Railway.",
        "unexpected_error": "Произошла ошибка. Проверь логи Railway и параметры окружения.",
        "one_day_left": "Ваша подписка скоро закончится\nОстался 1 день.",
        "expired_notice": "Подписка истекла",
        "payment_failed": "Оплата не прошла. Попробуйте ещё раз или обратитесь в поддержку.",
        "status_label": "Статус",
        "remove": "Удалить",
        "device_slot": "Слот",
        "device_active": "активен",
        "device_inactive": "неактивен",
        "available_devices": "Доступно устройств",
        "token_label": "Токен входа",
        "copy_token": "Скопировать токен",
    },
    "en": {
        "welcome": "Welcome to INET\nChoose an action below",
        "welcome_back": "INET main menu",
        "menu": "INET main menu",
        "buy": "Buy subscription",
        "sub": "My subscription",
        "devices": "My devices",
        "download": "Download app",
        "support": "Support",
        "language": "Language",
        "renew": "Renew",
        "open_app": "Open app",
        "download_app": "Download app",
        "back": "Back",
        "main_menu": "Main menu",
        "choose_language": "Choose language",
        "language_saved": "Language saved.",
        "choose_plan": "Choose a plan:",
        "plan": "Plan",
        "price": "Price",
        "devices_up_to": "Devices",
        "payment_method": "Payment method",
        "pay_card": "Pay by card / SBP",
        "proceed_payment": "Proceed to payment",
        "check_payment": "Check payment",
        "cancel": "Cancel",
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
        "device_removed": "Device removed. Slot released.",
        "choose_platform": "Choose platform:",
        "android": "Android",
        "ios": "iPhone / iPad",
        "download_android": "Android: download the app with the button below and sign in with your account.",
        "download_ios": "iPhone / iPad: open the link below and install the app.",
        "support_text": "Contact support",
        "faq": "FAQ",
        "write_support": "Write to support",
        "service_unavailable": "Service is temporarily unavailable. Check BACKEND_BASE_URL, DATABASE_URL and Railway logs.",
        "unexpected_error": "Something went wrong. Check Railway logs and environment variables.",
        "one_day_left": "Your subscription will expire soon\n1 day left.",
        "expired_notice": "Subscription expired",
        "payment_failed": "Payment failed. Please try again or contact support.",
        "status_label": "Status",
        "remove": "Remove",
        "device_slot": "Slot",
        "device_active": "active",
        "device_inactive": "inactive",
        "available_devices": "Devices available",
        "token_label": "Login token",
        "copy_token": "Copy token",
    },
}


bot: Optional[Bot] = None
dp = Dispatcher()


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
) -> Dict[str, Any]:
    url = settings.BACKEND_BASE_URL.rstrip("/") + path
    headers = {}
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
    auth = await auth_user(tg_user, language_override)
    user = auth.get("user") or {}
    lang = "en" if (user.get("language") == "en") else "ru"
    return {"auth": auth, "user": user, "token": auth.get("token"), "lang": lang}



async def issue_login_token_for_telegram_id(telegram_id: int, language: str = "ru") -> Optional[str]:
    try:
        data = await api_request(
            "POST",
            "/auth/telegram",
            json_body={
                "telegram_id": int(telegram_id),
                "language": "en" if language == "en" else "ru",
            },
        )
        token = (data.get("token") or "").strip()
        return token or None
    except Exception:
        logger.exception("Failed to issue login token for telegram user %s", telegram_id)
        return None


def append_token_details(text: str, lang: str, token: Optional[str], device_limit: Optional[int] = None) -> str:
    # Token text is intentionally hidden in the message body.
    # Access is provided via the copy button only.
    return text


def token_copy_rows(lang: str, token: Optional[str]) -> List[List[InlineKeyboardButton]]:
    if not token:
        return []
    return [[InlineKeyboardButton(text=TEXT[lang]["copy_token"], copy_text=CopyTextButton(text=token))]]


def is_supported_telegram_url(url: Optional[str]) -> bool:
    if not url:
        return False
    scheme = (urlsplit(url).scheme or "").lower()
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
        await target.answer(text, reply_markup=main_menu_inline(lang))
    else:
        await safe_edit(target, text, back_inline(lang))
        await target.answer()


async def show_unexpected_error(target: Message | CallbackQuery, lang: str) -> None:
    text = TEXT[lang]["unexpected_error"]
    if isinstance(target, Message):
        await target.answer(text, reply_markup=main_menu_inline(lang))
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
            await target.answer(message, reply_markup=main_menu_inline(lang))
        else:
            await safe_edit(target, message, back_inline(lang))
            await target.answer()
    except Exception:
        logger.exception("Unhandled bot error")
        await show_unexpected_error(target, lang)



def main_menu_inline(lang: str) -> InlineKeyboardMarkup:
    t = TEXT[lang]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t["buy"], callback_data="menu:buy"),
                InlineKeyboardButton(text=t["sub"], callback_data="menu:sub"),
            ],
            [
                InlineKeyboardButton(text=t["devices"], callback_data="menu:devices"),
                InlineKeyboardButton(text=t["download"], callback_data="menu:download"),
            ],
            [
                InlineKeyboardButton(text=t["support"], callback_data="menu:support"),
                InlineKeyboardButton(text=t["language"], callback_data="menu:language"),
            ],
        ]
    )



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



def build_open_app_url(token: Optional[str] = None, lang: Optional[str] = None) -> str:
    base = settings.OPEN_APP_URL or settings.APP_BASE_URL
    if not token and not lang:
        return base
    parts = urlsplit(base)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    if token:
        query["token"] = token
    if lang:
        query["lang"] = lang
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))



def activated_inline(lang: str, open_app_url: Optional[str] = None, token: Optional[str] = None) -> InlineKeyboardMarkup:
    t = TEXT[lang]
    rows: List[List[InlineKeyboardButton]] = []
    rows.extend(token_copy_rows(lang, token))
    final_open_url = open_app_url or build_open_app_url(lang=lang)
    if is_supported_telegram_url(final_open_url):
        rows.append([InlineKeyboardButton(text=t["open_app"], url=final_open_url)])
    rows.append([InlineKeyboardButton(text=t["download_app"], callback_data="menu:download")])
    rows.append([InlineKeyboardButton(text=t["sub"], callback_data="menu:sub")])
    rows.append([InlineKeyboardButton(text=t["main_menu"], callback_data="menu:root")])
    return InlineKeyboardMarkup(inline_keyboard=rows)



def support_inline(lang: str) -> InlineKeyboardMarkup:
    t = TEXT[lang]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t["write_support"], url=settings.SUPPORT_TELEGRAM_URL)],
            [InlineKeyboardButton(text=t["back"], callback_data="menu:root")],
        ]
    )



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
            [InlineKeyboardButton(text=t["back"], callback_data="menu:root")],
        ]
    )



def platform_open_inline(lang: str, platform: str, open_app_url: Optional[str] = None) -> InlineKeyboardMarkup:
    t = TEXT[lang]
    url = settings.ANDROID_APP_URL if platform == "android" else settings.IOS_APP_URL
    rows: List[List[InlineKeyboardButton]] = [[InlineKeyboardButton(text=t["download_app"], url=url)]]
    final_open_url = open_app_url or build_open_app_url(lang=lang)
    if is_supported_telegram_url(final_open_url):
        rows.append([InlineKeyboardButton(text=t["open_app"], url=final_open_url)])
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


async def send_menu(message: Message, lang: str, welcome: bool = False, cleanup_keyboard: bool = False) -> None:
    if cleanup_keyboard:
        await remove_legacy_reply_keyboard(message)
    text = TEXT[lang]["welcome"] if welcome else TEXT[lang]["welcome_back"]
    await message.answer(text, reply_markup=main_menu_inline(lang))


async def send_menu_for_callback(callback: CallbackQuery, lang: str) -> None:
    if callback.message:
        await safe_edit(callback, TEXT[lang]["menu"], main_menu_inline(lang))
        return
    await callback.answer(TEXT[lang]["menu"])


async def render_subscription_message(lang: str, token: str) -> Tuple[str, InlineKeyboardMarkup]:
    t = TEXT[lang]
    open_app_url = build_open_app_url(token, lang)
    data = await api_request("GET", "/subscriptions/me", token=token)
    sub = data.get("subscription")
    used = int(data.get("devices_used") or 0)
    limit = int(data.get("device_limit") or settings.VPN_DEFAULT_DEVICE_LIMIT)
    if not sub:
        text = append_token_details(t["subscription_none"], lang, token, limit)
    else:
        plan_name = sub["name_ru"] if lang == "ru" else sub["name_en"]
        status_text = t["subscription_active"] if data.get("is_active") else t["subscription_expired"]
        text = "\n".join(
            [
                f"{t['subscription_status']}: {status_text}",
                f"{t['plan']}: {plan_name}",
                f"{t['valid_until']}: {_fmt_dt(sub.get('expires_at'))}",
                f"{t['devices_used']}: {used} / {limit}",
            ]
        )
        text = append_token_details(text, lang, token, limit)
    rows: List[List[InlineKeyboardButton]] = []
    rows.extend(token_copy_rows(lang, token))
    rows.append([InlineKeyboardButton(text=t["renew"], callback_data="menu:buy")])
    if is_supported_telegram_url(open_app_url):
        rows.append([InlineKeyboardButton(text=t["open_app"], url=open_app_url)])
    rows.append([InlineKeyboardButton(text=t["back"], callback_data="menu:root")])
    markup = InlineKeyboardMarkup(inline_keyboard=rows)
    return text, markup


async def render_devices_message(lang: str, token: str) -> Tuple[str, InlineKeyboardMarkup]:
    t = TEXT[lang]
    data = await api_request("GET", "/devices", token=token)
    items = data.get("items", [])
    used = int(data.get("devices_used") or 0)
    limit = int(data.get("device_limit") or settings.VPN_DEFAULT_DEVICE_LIMIT)
    if not items:
        text = f"{t['devices_none']}\n\n{t['connected_now']}: {used} / {limit}"
        return text, back_inline(lang)
    lines = []
    rows: List[List[InlineKeyboardButton]] = []
    for row in items:
        device_name = row.get("device_name") or "—"
        platform = _platform_label(str(row.get("platform") or ""))
        status_text = t["device_active"] if row.get("is_active", True) else t["device_inactive"]
        lines.append(f"• {platform} — {device_name} — {status_text} — {_fmt_dt(row.get('last_seen_at'))}")
        rows.append([InlineKeyboardButton(text=f"{t['remove']} {platform}", callback_data=f"device:remove:{row['id']}")])
    lines.append("")
    lines.append(f"{t['connected_now']}: {used} / {limit}")
    if used >= limit:
        lines.append(t["limit_reached"])
    rows.append([InlineKeyboardButton(text=t["back"], callback_data="menu:root")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


async def render_support_message(lang: str) -> Tuple[str, InlineKeyboardMarkup]:
    t = TEXT[lang]
    faq = await api_request("GET", f"/support/faq?lang={lang}")
    text = f"{t['support_text']}\n{faq.get('support_url', settings.SUPPORT_TELEGRAM_URL)}\n\n{faq.get('faq', '')}"
    return text, support_inline(lang)


async def render_payment_success_message(lang: str, token: str) -> Tuple[str, InlineKeyboardMarkup]:
    t = TEXT[lang]
    open_app_url = build_open_app_url(token, lang)
    data = await api_request("GET", "/subscriptions/me", token=token)
    sub = data.get("subscription")
    if not sub:
        text = append_token_details(t["payment_received"], lang, token, int(data.get('device_limit') or settings.VPN_DEFAULT_DEVICE_LIMIT))
        return text, activated_inline(lang, open_app_url, token)
    plan_name = sub["name_ru"] if lang == "ru" else sub["name_en"]
    device_limit = int(data.get('device_limit') or sub.get('device_limit') or settings.VPN_DEFAULT_DEVICE_LIMIT)
    text = "\n".join(
        [
            t["payment_received"],
            t["subscription_activated"],
            f"{t['plan']}: {plan_name}",
            f"{t['active_until']}: {_fmt_dt(sub.get('expires_at'))}",
            f"{t['available_devices']}: {device_limit} / {device_limit}",
        ]
    )
    text = append_token_details(text, lang, token, device_limit)
    return text, activated_inline(lang, open_app_url, token)


@dp.message(Command("start"))
async def start(message: Message) -> None:
    async def _handler(_lang: str, ctx: Dict[str, Any]) -> None:
        current_lang = "en" if (ctx.get("lang") == "en") else "ru"
        is_new = bool((ctx.get("auth") or {}).get("is_new"))
        user_language = (ctx.get("user") or {}).get("language")
        if is_new or user_language not in {"ru", "en"}:
            await remove_legacy_reply_keyboard(message)
            await message.answer(TEXT[current_lang]["choose_language"], reply_markup=language_inline())
            return
        await send_menu(message, current_lang, welcome=True, cleanup_keyboard=True)

    await with_user_guard(message, _handler)


@dp.message(Command("menu"))
async def menu_command(message: Message) -> None:
    async def _handler(lang: str, _ctx: Dict[str, Any]) -> None:
        await send_menu(message, lang, cleanup_keyboard=True)

    await with_user_guard(message, _handler)


@dp.message(F.text.in_({TEXT["ru"]["buy"], TEXT["en"]["buy"]}))
async def buy_from_text(message: Message) -> None:
    async def _handler(lang: str, _ctx: Dict[str, Any]) -> None:
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
        text, markup = await render_subscription_message(lang, ctx["token"])
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
        await message.answer(TEXT[lang]["choose_platform"], reply_markup=download_platforms_inline(lang))

    await with_user_guard(message, _handler)


@dp.message(F.text.in_({TEXT["ru"]["support"], TEXT["en"]["support"]}))
async def support_from_text(message: Message) -> None:
    async def _handler(lang: str, _ctx: Dict[str, Any]) -> None:
        text, markup = await render_support_message(lang)
        await message.answer(text, reply_markup=markup)

    await with_user_guard(message, _handler)


@dp.message(F.text.in_({TEXT["ru"]["language"], TEXT["en"]["language"], "Русский", "English"}))
async def language_from_text(message: Message) -> None:
    if message.text in {"Русский", "English"}:
        lang = "ru" if message.text == "Русский" else "en"
        async def _handler(_lang: str, ctx: Dict[str, Any]) -> None:
            await api_request("PATCH", "/users/me/language", token=ctx["token"], json_body={"language": lang})
            await message.answer(
                f"{TEXT[lang]['language_saved']}\n\n{TEXT[lang]['welcome']}",
                reply_markup=main_menu_inline(lang),
            )
        await with_user_guard(message, _handler, preferred_lang=lang)
        return

    async def _handler(lang: str, _ctx: Dict[str, Any]) -> None:
        await remove_legacy_reply_keyboard(message)
        await message.answer(TEXT[lang]["choose_language"], reply_markup=language_inline())

    await with_user_guard(message, _handler)


@dp.message(F.text.in_({TEXT["ru"]["renew"], TEXT["en"]["renew"]}))
async def renew_from_text(message: Message) -> None:
    await buy_from_text(message)


@dp.message(F.text.in_({TEXT["ru"]["back"], TEXT["en"]["back"], TEXT["ru"]["main_menu"], TEXT["en"]["main_menu"]}))
async def menu_from_text_alias(message: Message) -> None:
    async def _handler(lang: str, _ctx: Dict[str, Any]) -> None:
        await send_menu(message, lang, cleanup_keyboard=True)

    await with_user_guard(message, _handler)


@dp.message(F.text.in_({TEXT["ru"]["android"], TEXT["en"]["android"]}))
async def download_android_from_text(message: Message) -> None:
    async def _handler(lang: str, _ctx: Dict[str, Any]) -> None:
        await message.answer(TEXT[lang]["download_android"], reply_markup=platform_open_inline(lang, "android", build_open_app_url(_ctx.get("token"), lang)))

    await with_user_guard(message, _handler)


@dp.message(F.text.in_({TEXT["ru"]["ios"], TEXT["en"]["ios"]}))
async def download_ios_from_text(message: Message) -> None:
    async def _handler(lang: str, _ctx: Dict[str, Any]) -> None:
        await message.answer(TEXT[lang]["download_ios"], reply_markup=platform_open_inline(lang, "ios", build_open_app_url(_ctx.get("token"), lang)))

    await with_user_guard(message, _handler)


@dp.message()
async def fallback_message(message: Message) -> None:
    async def _handler(lang: str, _ctx: Dict[str, Any]) -> None:
        await send_menu(message, lang, cleanup_keyboard=True)

    await with_user_guard(message, _handler)


@dp.callback_query(F.data == "menu:root")
async def cb_root(callback: CallbackQuery) -> None:
    async def _handler(lang: str, _ctx: Dict[str, Any]) -> None:
        await send_menu_for_callback(callback, lang)
        await callback.answer()

    await with_user_guard(callback, _handler)


@dp.callback_query(F.data == "menu:buy")
async def cb_buy(callback: CallbackQuery) -> None:
    async def _handler(lang: str, _ctx: Dict[str, Any]) -> None:
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
            ]
        )
        await safe_edit(callback, text, plan_actions_inline(lang, plan_code))
        await callback.answer()

    await with_user_guard(callback, _handler)


@dp.callback_query(F.data.startswith("plan:pay:"))
async def cb_plan_pay(callback: CallbackQuery) -> None:
    async def _handler(lang: str, ctx: Dict[str, Any]) -> None:
        plan_code = callback.data.split(":", 2)[2]
        result = await api_request("POST", "/payments/create", token=ctx["token"], json_body={"plan_code": plan_code, "method": "telegram"})
        payment = result.get("payment") or {}
        if not result.get("payments_enabled"):
            await safe_edit(callback, TEXT[lang]["payments_off"], back_inline(lang))
            await callback.answer()
            return
        checkout_url = payment.get("checkout_url") or settings.SUPPORT_TELEGRAM_URL
        await safe_edit(callback, TEXT[lang]["payment_created"], payment_inline(lang, checkout_url, payment["id"]))
        await callback.answer()

    await with_user_guard(callback, _handler)


@dp.callback_query(F.data.startswith("payment:check:"))
async def cb_payment_check(callback: CallbackQuery) -> None:
    async def _handler(lang: str, ctx: Dict[str, Any]) -> None:
        payment_id = callback.data.split(":", 2)[2]
        data = await api_request("GET", f"/payments/{payment_id}", token=ctx["token"])
        payment = data.get("payment") or {}
        if payment.get("status") == "paid":
            text, markup = await render_payment_success_message(lang, ctx["token"])
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
        text, markup = await render_subscription_message(lang, ctx["token"])
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


@dp.callback_query(F.data == "menu:download")
async def cb_download(callback: CallbackQuery) -> None:
    async def _handler(lang: str, _ctx: Dict[str, Any]) -> None:
        await safe_edit(callback, TEXT[lang]["choose_platform"], download_platforms_inline(lang))
        await callback.answer()

    await with_user_guard(callback, _handler)


@dp.callback_query(F.data.startswith("download:"))
async def cb_download_platform(callback: CallbackQuery) -> None:
    async def _handler(lang: str, _ctx: Dict[str, Any]) -> None:
        platform = callback.data.split(":", 1)[1]
        if platform == "android":
            text = TEXT[lang]["download_android"]
        else:
            text = TEXT[lang]["download_ios"]
        await safe_edit(callback, text, platform_open_inline(lang, platform, build_open_app_url(_ctx.get("token"), lang)))
        await callback.answer()

    await with_user_guard(callback, _handler)


@dp.callback_query(F.data == "menu:support")
async def cb_support(callback: CallbackQuery) -> None:
    async def _handler(lang: str, _ctx: Dict[str, Any]) -> None:
        text, markup = await render_support_message(lang)
        await safe_edit(callback, text, markup)
        await callback.answer()

    await with_user_guard(callback, _handler)


@dp.callback_query(F.data == "menu:language")
async def cb_language(callback: CallbackQuery) -> None:
    async def _handler(lang: str, _ctx: Dict[str, Any]) -> None:
        await safe_edit(callback, TEXT[lang]["choose_language"], language_inline())
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
            main_menu_inline(norm),
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
        token = await issue_login_token_for_telegram_id(int(item["telegram_id"]), lang)
        text = "\n".join(
            [
                t["payment_received"],
                t["subscription_activated"],
                f"{t['plan']}: {plan_name}",
                f"{t['active_until']}: {_fmt_dt(payload.get('expires_at'))}",
                f"{t['available_devices']}: {device_limit} / {device_limit}",
            ]
        )
        text = append_token_details(text, lang, token, device_limit)
        open_app_url = build_open_app_url(token, lang) if token else build_open_app_url(lang=lang)
        return text, activated_inline(lang, open_app_url, token)
    if event_type == "subscription_expiring":
        text = f"{t['one_day_left']}\n\n{t['active_until']}: {_fmt_dt(payload.get('expires_at'))}"
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=t["renew"], callback_data="menu:buy")],
                [InlineKeyboardButton(text=t["main_menu"], callback_data="menu:root")],
            ]
        )
        return text, markup
    if event_type == "subscription_expired":
        text = t["expired_notice"]
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=t["renew"], callback_data="menu:buy")],
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
                    record_bot_error("bot-notification", str(item.get("unique_key") or item.get("id")), str(exc))
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
    logger.info("Bot configured, webhook removed, command menu cleared")


async def verify_backend() -> None:
    data = await api_request("GET", "/health")
    logger.info("Backend health check succeeded: %s", data)


async def main() -> None:
    global bot
    if not settings.BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is required")
    if not settings.BACKEND_BASE_URL:
        raise RuntimeError("BACKEND_BASE_URL is required")

    bot = Bot(token=settings.BOT_TOKEN)

    logger.info("Starting bot for %s", settings.BOT_USERNAME or settings.BOT_NAME)
    logger.info("Backend base URL: %s", settings.BACKEND_BASE_URL)

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
