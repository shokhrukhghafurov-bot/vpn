import asyncio
from typing import Any, Dict, Optional

import httpx
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import settings


TEXT = {
    "ru": {
        "menu": "Главное меню INET VPN",
        "buy": "Купить подписку",
        "sub": "Моя подписка",
        "devices": "Мои устройства",
        "download": "Скачать приложение",
        "support": "Поддержка",
        "language": "Язык",
        "lang_saved": "Язык переключен на русский.",
        "choose_plan": "Выберите тариф:",
        "payments_off": "Оплата пока отключена. Напишите в поддержку.",
        "subscription_none": "Активной подписки нет.",
        "devices_none": "Устройств пока нет.",
        "download_text": "Ссылки на приложения:",
        "support_text": "Поддержка:",
        "menu_btn": "Назад в меню",
    },
    "en": {
        "menu": "INET VPN main menu",
        "buy": "Buy subscription",
        "sub": "My subscription",
        "devices": "My devices",
        "download": "Download app",
        "support": "Support",
        "language": "Language",
        "lang_saved": "Language switched to English.",
        "choose_plan": "Choose a plan:",
        "payments_off": "Payments are disabled now. Please contact support.",
        "subscription_none": "No active subscription.",
        "devices_none": "No devices yet.",
        "download_text": "App links:",
        "support_text": "Support:",
        "menu_btn": "Back to menu",
    },
}


async def api_request(method: str, path: str, *, token: Optional[str] = None, json_body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    url = settings.BACKEND_BASE_URL.rstrip("/") + path
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.request(method, url, json=json_body, headers=headers)
        response.raise_for_status()
        return response.json()


async def auth_user(tg_user: Any, language: Optional[str] = None) -> Dict[str, Any]:
    payload = {
        "telegram_id": tg_user.id,
        "username": tg_user.username,
        "first_name": tg_user.first_name,
        "last_name": tg_user.last_name,
        "language": language or (tg_user.language_code if tg_user.language_code in {"ru", "en"} else "ru"),
    }
    data = await api_request("POST", "/auth/telegram", json_body=payload)
    return data


async def get_lang(tg_user: Any) -> str:
    data = await auth_user(tg_user)
    user = data.get("user") or {}
    lang = user.get("language") or "ru"
    return "en" if lang == "en" else "ru"


def main_menu(lang: str) -> InlineKeyboardMarkup:
    t = TEXT[lang]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t["buy"], callback_data="menu:buy")],
        [InlineKeyboardButton(text=t["sub"], callback_data="menu:sub")],
        [InlineKeyboardButton(text=t["devices"], callback_data="menu:devices")],
        [InlineKeyboardButton(text=t["download"], callback_data="menu:download")],
        [InlineKeyboardButton(text=t["support"], callback_data="menu:support")],
        [InlineKeyboardButton(text=t["language"], callback_data="menu:language")],
    ])


def back_menu(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=TEXT[lang]["menu_btn"], callback_data="menu:root")]
    ])


async def send_menu(message: Message, lang: str) -> None:
    await message.answer(TEXT[lang]["menu"], reply_markup=main_menu(lang))


bot = Bot(token=settings.BOT_TOKEN)
dp = Dispatcher()


@dp.message(Command("start"))
async def start(message: Message) -> None:
    lang = await get_lang(message.from_user)
    await send_menu(message, lang)


@dp.callback_query(F.data == "menu:root")
async def cb_root(callback: CallbackQuery) -> None:
    lang = await get_lang(callback.from_user)
    await callback.message.edit_text(TEXT[lang]["menu"], reply_markup=main_menu(lang))
    await callback.answer()


@dp.callback_query(F.data == "menu:buy")
async def cb_buy(callback: CallbackQuery) -> None:
    auth = await auth_user(callback.from_user)
    lang = (auth.get("user") or {}).get("language") or "ru"
    plans = await api_request("GET", "/plans")
    rows = []
    for item in plans.get("items", []):
        label = f"{item['name_ru'] if lang == 'ru' else item['name_en']} — {item['price_rub']} ₽"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"buy:{item['code']}")])
    rows.append([InlineKeyboardButton(text=TEXT[lang]["menu_btn"], callback_data="menu:root")])
    await callback.message.edit_text(TEXT[lang]["choose_plan"], reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await callback.answer()


@dp.callback_query(F.data.startswith("buy:"))
async def cb_buy_plan(callback: CallbackQuery) -> None:
    plan_code = callback.data.split(":", 1)[1]
    auth = await auth_user(callback.from_user)
    lang = (auth.get("user") or {}).get("language") or "ru"
    token = auth["token"]
    try:
        result = await api_request("POST", "/payments/create", token=token, json_body={"plan_code": plan_code, "method": "telegram"})
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text
        await callback.message.edit_text(f"Error: {detail}", reply_markup=back_menu(lang))
        await callback.answer()
        return
    payment = result.get("payment") or {}
    if not result.get("payments_enabled"):
        text = f"{TEXT[lang]['payments_off']}\n\n{settings.SUPPORT_TELEGRAM_URL}"
    else:
        checkout_url = payment.get("checkout_url") or settings.SUPPORT_TELEGRAM_URL
        text = f"Payment created. Open link:\n{checkout_url}"
    await callback.message.edit_text(text, reply_markup=back_menu(lang))
    await callback.answer()


@dp.callback_query(F.data == "menu:sub")
async def cb_subscription(callback: CallbackQuery) -> None:
    auth = await auth_user(callback.from_user)
    lang = (auth.get("user") or {}).get("language") or "ru"
    token = auth["token"]
    data = await api_request("GET", "/subscriptions/me", token=token)
    sub = data.get("subscription")
    if not sub:
        text = TEXT[lang]["subscription_none"]
    else:
        plan_name = sub["name_ru"] if lang == "ru" else sub["name_en"]
        text = (
            f"Plan: {plan_name}\n"
            f"Expires: {sub['expires_at']}\n"
            f"Devices used: {data.get('devices_used', 0)} / {sub['device_limit']}"
        )
    await callback.message.edit_text(text, reply_markup=back_menu(lang))
    await callback.answer()


@dp.callback_query(F.data == "menu:devices")
async def cb_devices(callback: CallbackQuery) -> None:
    auth = await auth_user(callback.from_user)
    lang = (auth.get("user") or {}).get("language") or "ru"
    token = auth["token"]
    data = await api_request("GET", "/devices", token=token)
    items = data.get("items", [])
    if not items:
        text = TEXT[lang]["devices_none"]
    else:
        lines = [f"{idx}. {row.get('platform')} — {row.get('device_name')}" for idx, row in enumerate(items, 1)]
        text = "\n".join(lines)
    await callback.message.edit_text(text, reply_markup=back_menu(lang))
    await callback.answer()


@dp.callback_query(F.data == "menu:download")
async def cb_download(callback: CallbackQuery) -> None:
    lang = await get_lang(callback.from_user)
    text = (
        f"{TEXT[lang]['download_text']}\n\n"
        f"Android: {settings.ANDROID_APP_URL}\n"
        f"iPhone / iPad: {settings.IOS_APP_URL}"
    )
    await callback.message.edit_text(text, reply_markup=back_menu(lang))
    await callback.answer()


@dp.callback_query(F.data == "menu:support")
async def cb_support(callback: CallbackQuery) -> None:
    lang = await get_lang(callback.from_user)
    await callback.message.edit_text(f"{TEXT[lang]['support_text']}\n{settings.SUPPORT_TELEGRAM_URL}", reply_markup=back_menu(lang))
    await callback.answer()


@dp.callback_query(F.data == "menu:language")
async def cb_language(callback: CallbackQuery) -> None:
    auth = await auth_user(callback.from_user)
    user = auth.get("user") or {}
    next_lang = "en" if (user.get("language") or "ru") == "ru" else "ru"
    await auth_user(callback.from_user, language=next_lang)
    await callback.message.edit_text(TEXT[next_lang]["lang_saved"], reply_markup=back_menu(next_lang))
    await callback.answer()


async def main() -> None:
    if not settings.BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is required")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
