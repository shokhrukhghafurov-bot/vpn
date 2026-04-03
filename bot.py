import asyncio
import logging
from typing import Any, Dict, Optional

import httpx
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import BotCommand, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import settings


logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
logger = logging.getLogger(__name__)


TEXT = {
    'ru': {
        'menu': 'Главное меню INET VPN',
        'buy': 'Купить подписку',
        'sub': 'Моя подписка',
        'devices': 'Мои устройства',
        'download': 'Скачать приложение',
        'support': 'Поддержка',
        'language': 'Язык',
        'lang_saved': 'Язык переключен на русский.',
        'choose_plan': 'Выберите тариф:',
        'payments_off': 'Оплата пока отключена. Напишите в поддержку.',
        'subscription_none': 'Активной подписки нет.',
        'devices_none': 'Устройств пока нет.',
        'download_text': 'Ссылки на приложения:',
        'support_text': 'Поддержка:',
        'menu_btn': 'Назад в меню',
        'service_unavailable': 'Сервис временно недоступен. Проверь BACKEND_BASE_URL, DATABASE_URL и логи Railway.',
        'unexpected_error': 'Произошла ошибка. Проверь логи Railway и параметры окружения.',
        'payment_created': 'Платёж создан. Открой ссылку:',
    },
    'en': {
        'menu': 'INET VPN main menu',
        'buy': 'Buy subscription',
        'sub': 'My subscription',
        'devices': 'My devices',
        'download': 'Download app',
        'support': 'Support',
        'language': 'Language',
        'lang_saved': 'Language switched to English.',
        'choose_plan': 'Choose a plan:',
        'payments_off': 'Payments are disabled now. Please contact support.',
        'subscription_none': 'No active subscription.',
        'devices_none': 'No devices yet.',
        'download_text': 'App links:',
        'support_text': 'Support:',
        'menu_btn': 'Back to menu',
        'service_unavailable': 'Service is temporarily unavailable. Check BACKEND_BASE_URL, DATABASE_URL and Railway logs.',
        'unexpected_error': 'Something went wrong. Check Railway logs and environment variables.',
        'payment_created': 'Payment created. Open the link:',
    },
}


bot = Bot(token=settings.BOT_TOKEN)
dp = Dispatcher()


class BackendUnavailable(RuntimeError):
    pass


async def api_request(
    method: str,
    path: str,
    *,
    token: Optional[str] = None,
    json_body: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    url = settings.BACKEND_BASE_URL.rstrip('/') + path
    headers = {}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.request(method, url, json=json_body, headers=headers)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError:
        raise
    except httpx.HTTPError as exc:
        logger.exception('Backend request failed: %s %s', method, url)
        raise BackendUnavailable(str(exc)) from exc


async def auth_user(tg_user: Any, language: Optional[str] = None) -> Dict[str, Any]:
    payload = {
        'telegram_id': tg_user.id,
        'username': tg_user.username,
        'first_name': tg_user.first_name,
        'last_name': tg_user.last_name,
        'language': language or (tg_user.language_code if tg_user.language_code in {'ru', 'en'} else 'ru'),
    }
    return await api_request('POST', '/auth/telegram', json_body=payload)


async def get_lang(tg_user: Any) -> str:
    try:
        data = await auth_user(tg_user)
        user = data.get('user') or {}
        lang = user.get('language') or 'ru'
        return 'en' if lang == 'en' else 'ru'
    except Exception:
        fallback = tg_user.language_code if getattr(tg_user, 'language_code', None) in {'ru', 'en'} else 'ru'
        return 'en' if fallback == 'en' else 'ru'


async def safe_edit(callback: CallbackQuery, text: str, markup: InlineKeyboardMarkup) -> None:
    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except Exception:
        await callback.message.answer(text, reply_markup=markup)


async def show_backend_error(target: Message | CallbackQuery, lang: str) -> None:
    text = TEXT[lang]['service_unavailable']
    if isinstance(target, Message):
        await target.answer(text)
    else:
        await safe_edit(target, text, back_menu(lang))
        await target.answer()


async def show_unexpected_error(target: Message | CallbackQuery, lang: str) -> None:
    text = TEXT[lang]['unexpected_error']
    if isinstance(target, Message):
        await target.answer(text)
    else:
        await safe_edit(target, text, back_menu(lang))
        await target.answer()


async def with_backend_guard(target: Message | CallbackQuery, handler):
    lang = 'ru'
    tg_user = target.from_user if isinstance(target, (Message, CallbackQuery)) else None
    if tg_user:
        lang = await get_lang(tg_user)
    try:
        return await handler(lang)
    except BackendUnavailable:
        await show_backend_error(target, lang)
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:500]
        logger.warning('Backend returned error %s: %s', exc.response.status_code, detail)
        message = f'Error {exc.response.status_code}: {detail}'
        if isinstance(target, Message):
            await target.answer(message)
        else:
            await safe_edit(target, message, back_menu(lang))
            await target.answer()
    except Exception:
        logger.exception('Unhandled bot error')
        await show_unexpected_error(target, lang)


def main_menu(lang: str) -> InlineKeyboardMarkup:
    t = TEXT[lang]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t['buy'], callback_data='menu:buy')],
            [InlineKeyboardButton(text=t['sub'], callback_data='menu:sub')],
            [InlineKeyboardButton(text=t['devices'], callback_data='menu:devices')],
            [InlineKeyboardButton(text=t['download'], callback_data='menu:download')],
            [InlineKeyboardButton(text=t['support'], callback_data='menu:support')],
            [InlineKeyboardButton(text=t['language'], callback_data='menu:language')],
        ]
    )


def back_menu(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=TEXT[lang]['menu_btn'], callback_data='menu:root')]])


async def send_menu(message: Message, lang: str) -> None:
    await message.answer(TEXT[lang]['menu'], reply_markup=main_menu(lang))


@dp.message(Command('start'))
async def start(message: Message) -> None:
    async def _handler(lang: str) -> None:
        await send_menu(message, lang)

    await with_backend_guard(message, _handler)


@dp.message(Command('menu'))
async def menu_command(message: Message) -> None:
    async def _handler(lang: str) -> None:
        await send_menu(message, lang)

    await with_backend_guard(message, _handler)


@dp.callback_query(F.data == 'menu:root')
async def cb_root(callback: CallbackQuery) -> None:
    async def _handler(lang: str) -> None:
        await safe_edit(callback, TEXT[lang]['menu'], main_menu(lang))
        await callback.answer()

    await with_backend_guard(callback, _handler)


@dp.callback_query(F.data == 'menu:buy')
async def cb_buy(callback: CallbackQuery) -> None:
    async def _handler(lang: str) -> None:
        plans = await api_request('GET', '/plans')
        rows = []
        for item in plans.get('items', []):
            label = f"{item['name_ru'] if lang == 'ru' else item['name_en']} — {item['price_rub']} ₽"
            rows.append([InlineKeyboardButton(text=label, callback_data=f"buy:{item['code']}")])
        rows.append([InlineKeyboardButton(text=TEXT[lang]['menu_btn'], callback_data='menu:root')])
        await safe_edit(callback, TEXT[lang]['choose_plan'], InlineKeyboardMarkup(inline_keyboard=rows))
        await callback.answer()

    await with_backend_guard(callback, _handler)


@dp.callback_query(F.data.startswith('buy:'))
async def cb_buy_plan(callback: CallbackQuery) -> None:
    async def _handler(lang: str) -> None:
        auth = await auth_user(callback.from_user)
        token = auth['token']
        plan_code = callback.data.split(':', 1)[1]
        result = await api_request('POST', '/payments/create', token=token, json_body={'plan_code': plan_code, 'method': 'telegram'})
        payment = result.get('payment') or {}
        if not result.get('payments_enabled'):
            text = f"{TEXT[lang]['payments_off']}\n\n{settings.SUPPORT_TELEGRAM_URL}"
        else:
            checkout_url = payment.get('checkout_url') or settings.SUPPORT_TELEGRAM_URL
            text = f"{TEXT[lang]['payment_created']}\n{checkout_url}"
        await safe_edit(callback, text, back_menu(lang))
        await callback.answer()

    await with_backend_guard(callback, _handler)


@dp.callback_query(F.data == 'menu:sub')
async def cb_subscription(callback: CallbackQuery) -> None:
    async def _handler(lang: str) -> None:
        auth = await auth_user(callback.from_user)
        token = auth['token']
        data = await api_request('GET', '/subscriptions/me', token=token)
        sub = data.get('subscription')
        if not sub:
            text = TEXT[lang]['subscription_none']
        else:
            plan_name = sub['name_ru'] if lang == 'ru' else sub['name_en']
            text = (
                f'Plan: {plan_name}\n'
                f"Expires: {sub['expires_at']}\n"
                f"Devices used: {data.get('devices_used', 0)} / {sub['device_limit']}"
            )
        await safe_edit(callback, text, back_menu(lang))
        await callback.answer()

    await with_backend_guard(callback, _handler)


@dp.callback_query(F.data == 'menu:devices')
async def cb_devices(callback: CallbackQuery) -> None:
    async def _handler(lang: str) -> None:
        auth = await auth_user(callback.from_user)
        token = auth['token']
        data = await api_request('GET', '/devices', token=token)
        items = data.get('items', [])
        if not items:
            text = TEXT[lang]['devices_none']
        else:
            lines = [f"{idx}. {row.get('platform')} — {row.get('device_name')}" for idx, row in enumerate(items, 1)]
            text = '\n'.join(lines)
        await safe_edit(callback, text, back_menu(lang))
        await callback.answer()

    await with_backend_guard(callback, _handler)


@dp.callback_query(F.data == 'menu:download')
async def cb_download(callback: CallbackQuery) -> None:
    async def _handler(lang: str) -> None:
        text = (
            f"{TEXT[lang]['download_text']}\n\n"
            f'Android: {settings.ANDROID_APP_URL}\n'
            f'iPhone / iPad: {settings.IOS_APP_URL}'
        )
        await safe_edit(callback, text, back_menu(lang))
        await callback.answer()

    await with_backend_guard(callback, _handler)


@dp.callback_query(F.data == 'menu:support')
async def cb_support(callback: CallbackQuery) -> None:
    async def _handler(lang: str) -> None:
        await safe_edit(callback, f"{TEXT[lang]['support_text']}\n{settings.SUPPORT_TELEGRAM_URL}", back_menu(lang))
        await callback.answer()

    await with_backend_guard(callback, _handler)


@dp.callback_query(F.data == 'menu:language')
async def cb_language(callback: CallbackQuery) -> None:
    async def _handler(lang: str) -> None:
        auth = await auth_user(callback.from_user)
        user = auth.get('user') or {}
        next_lang = 'en' if (user.get('language') or 'ru') == 'ru' else 'ru'
        await auth_user(callback.from_user, language=next_lang)
        await safe_edit(callback, TEXT[next_lang]['lang_saved'], back_menu(next_lang))
        await callback.answer()

    await with_backend_guard(callback, _handler)


async def configure_bot() -> None:
    await bot.delete_webhook(drop_pending_updates=False)
    await bot.set_my_commands([
        BotCommand(command='start', description='Open INET menu'),
        BotCommand(command='menu', description='Open INET menu'),
    ])
    logger.info('Bot configured, webhook removed, commands registered')


async def verify_backend() -> None:
    data = await api_request('GET', '/health')
    logger.info('Backend health check succeeded: %s', data)


async def main() -> None:
    if not settings.BOT_TOKEN:
        raise RuntimeError('BOT_TOKEN is required')
    if not settings.BACKEND_BASE_URL:
        raise RuntimeError('BACKEND_BASE_URL is required')

    logger.info('Starting bot for %s', settings.BOT_USERNAME or settings.BOT_NAME)
    logger.info('Backend base URL: %s', settings.BACKEND_BASE_URL)

    await configure_bot()
    await verify_backend()
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())
