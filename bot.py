import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from config import settings


logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
logger = logging.getLogger(__name__)


TEXT = {
    'ru': {
        'app_title': 'INET VPN',
        'menu': 'Главное меню INET VPN',
        'menu_hint': 'Выберите нужный раздел ниже.',
        'buy': 'Купить подписку',
        'sub': 'Моя подписка',
        'devices': 'Мои устройства',
        'download': 'Скачать приложение',
        'support': 'Поддержка',
        'language': 'Язык',
        'language_ru': 'Русский',
        'language_en': 'English',
        'lang_saved': 'Язык переключен на русский.',
        'choose_plan': 'Выберите тариф:',
        'plan_line': '{name} — {price} ₽ • {days} дн. • {devices} устр.',
        'payments_off': 'Оплата пока отключена. Напишите в поддержку, чтобы активировать доступ вручную.',
        'subscription_none': 'Активной подписки пока нет.',
        'subscription_title': 'Моя подписка',
        'subscription_status': 'Статус: {status}',
        'subscription_plan': 'Тариф: {plan}',
        'subscription_expires': 'Действует до: {expires}',
        'subscription_devices': 'Устройства: {used} / {limit}',
        'subscription_cta': 'Оформите тариф, чтобы начать пользоваться VPN.',
        'status_active': 'активна',
        'status_expired': 'истекла',
        'status_blocked': 'заблокирован',
        'devices_none': 'Устройств пока нет.',
        'devices_title': 'Мои устройства',
        'device_item': '{n}. {platform} • {name}',
        'device_unknown': 'Без названия',
        'device_remove': 'Удалить #{n}',
        'device_remove_confirm': 'Удалить устройство «{name}»?',
        'device_removed': 'Устройство удалено.',
        'device_remove_cancelled': 'Удаление отменено.',
        'download_text': 'Ссылки на приложения:',
        'download_android': 'Android',
        'download_ios': 'iPhone / iPad',
        'support_text': 'Связаться с поддержкой:',
        'support_button': 'Открыть поддержку',
        'language_text': 'Выберите язык интерфейса:',
        'back': 'Назад',
        'back_menu': 'Назад в меню',
        'open_payment': 'Перейти к оплате',
        'payment_created': 'Платёж создан. Откройте ссылку ниже.',
        'menu_summary_guest': 'Добро пожаловать. У вас пока нет активной подписки.',
        'menu_summary_active': 'Текущий тариф: {plan}\nДействует до: {expires}\nУстройства: {used} / {limit}',
        'menu_summary_blocked': 'Ваш доступ сейчас заблокирован. Напишите в поддержку.',
        'service_unavailable': 'Сервис временно недоступен. Проверь BACKEND_BASE_URL, DATABASE_URL и логи Railway.',
        'unexpected_error': 'Произошла ошибка. Проверь логи Railway и параметры окружения.',
        'unknown_message': 'Я показал главное меню ниже.',
        'buy_now': 'Купить подписку',
    },
    'en': {
        'app_title': 'INET VPN',
        'menu': 'INET VPN main menu',
        'menu_hint': 'Choose a section below.',
        'buy': 'Buy subscription',
        'sub': 'My subscription',
        'devices': 'My devices',
        'download': 'Download app',
        'support': 'Support',
        'language': 'Language',
        'language_ru': 'Русский',
        'language_en': 'English',
        'lang_saved': 'Language switched to English.',
        'choose_plan': 'Choose a plan:',
        'plan_line': '{name} — {price} ₽ • {days} days • {devices} devices',
        'payments_off': 'Payments are currently disabled. Please contact support for manual activation.',
        'subscription_none': 'No active subscription yet.',
        'subscription_title': 'My subscription',
        'subscription_status': 'Status: {status}',
        'subscription_plan': 'Plan: {plan}',
        'subscription_expires': 'Valid until: {expires}',
        'subscription_devices': 'Devices: {used} / {limit}',
        'subscription_cta': 'Choose a plan to start using the VPN.',
        'status_active': 'active',
        'status_expired': 'expired',
        'status_blocked': 'blocked',
        'devices_none': 'No devices yet.',
        'devices_title': 'My devices',
        'device_item': '{n}. {platform} • {name}',
        'device_unknown': 'Unnamed device',
        'device_remove': 'Delete #{n}',
        'device_remove_confirm': 'Delete device “{name}”?',
        'device_removed': 'Device deleted.',
        'device_remove_cancelled': 'Deletion cancelled.',
        'download_text': 'App links:',
        'download_android': 'Android',
        'download_ios': 'iPhone / iPad',
        'support_text': 'Contact support:',
        'support_button': 'Open support',
        'language_text': 'Choose interface language:',
        'back': 'Back',
        'back_menu': 'Back to menu',
        'open_payment': 'Open payment',
        'payment_created': 'Payment created. Open the link below.',
        'menu_summary_guest': 'Welcome. You do not have an active subscription yet.',
        'menu_summary_active': 'Current plan: {plan}\nValid until: {expires}\nDevices: {used} / {limit}',
        'menu_summary_blocked': 'Your access is currently blocked. Please contact support.',
        'service_unavailable': 'Service is temporarily unavailable. Check BACKEND_BASE_URL, DATABASE_URL and Railway logs.',
        'unexpected_error': 'Something went wrong. Check Railway logs and environment variables.',
        'unknown_message': 'I opened the main menu below.',
        'buy_now': 'Buy subscription',
    },
}

BUTTON_ACTIONS = {
    'buy': {TEXT['ru']['buy'], TEXT['en']['buy']},
    'sub': {TEXT['ru']['sub'], TEXT['en']['sub']},
    'devices': {TEXT['ru']['devices'], TEXT['en']['devices']},
    'download': {TEXT['ru']['download'], TEXT['en']['download']},
    'support': {TEXT['ru']['support'], TEXT['en']['support']},
    'language': {TEXT['ru']['language'], TEXT['en']['language']},
}

bot = Bot(token=settings.BOT_TOKEN)
dp = Dispatcher()


class BackendUnavailable(RuntimeError):
    pass


def t(lang: str, key: str) -> str:
    lang = 'en' if lang == 'en' else 'ru'
    return TEXT[lang][key]


def normalize_lang(value: Optional[str]) -> str:
    return 'en' if value == 'en' else 'ru'


def format_dt(value: Optional[str]) -> str:
    if not value:
        return '—'
    raw = str(value).replace('Z', '+00:00')
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return str(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt_local = dt.astimezone(timezone.utc)
    return dt_local.strftime('%Y-%m-%d %H:%M UTC')


def menu_keyboard(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t(lang, 'buy'))],
            [KeyboardButton(text=t(lang, 'sub'))],
            [KeyboardButton(text=t(lang, 'devices'))],
            [KeyboardButton(text=t(lang, 'download'))],
            [KeyboardButton(text=t(lang, 'support'))],
            [KeyboardButton(text=t(lang, 'language'))],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder=t(lang, 'menu_hint'),
    )


def back_inline(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t(lang, 'back_menu'), callback_data='menu:root')]]
    )


def language_markup(current_lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t('ru', 'language_ru'), callback_data='lang:set:ru'),
                InlineKeyboardButton(text=t('en', 'language_en'), callback_data='lang:set:en'),
            ],
            [InlineKeyboardButton(text=t(current_lang, 'back_menu'), callback_data='menu:root')],
        ]
    )


def plan_markup(lang: str, items: list[Dict[str, Any]]) -> InlineKeyboardMarkup:
    rows = []
    for item in items:
        name = item['name_ru'] if lang == 'ru' else item['name_en']
        label = t(lang, 'plan_line').format(
            name=name,
            price=item['price_rub'],
            days=item['duration_days'],
            devices=item['device_limit'],
        )
        rows.append([InlineKeyboardButton(text=label, callback_data=f"buy:{item['code']}")])
    rows.append([InlineKeyboardButton(text=t(lang, 'back_menu'), callback_data='menu:root')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def payment_markup(lang: str, checkout_url: Optional[str]) -> InlineKeyboardMarkup:
    rows = []
    if checkout_url:
        rows.append([InlineKeyboardButton(text=t(lang, 'open_payment'), url=checkout_url)])
    rows.append([InlineKeyboardButton(text=t(lang, 'back_menu'), callback_data='menu:root')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def download_markup(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, 'download_android'), url=settings.ANDROID_APP_URL)],
            [InlineKeyboardButton(text=t(lang, 'download_ios'), url=settings.IOS_APP_URL)],
            [InlineKeyboardButton(text=t(lang, 'back_menu'), callback_data='menu:root')],
        ]
    )


def support_markup(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, 'support_button'), url=settings.SUPPORT_TELEGRAM_URL)],
            [InlineKeyboardButton(text=t(lang, 'back_menu'), callback_data='menu:root')],
        ]
    )


def subscription_markup(lang: str, has_subscription: bool) -> InlineKeyboardMarkup:
    rows = []
    if not has_subscription:
        rows.append([InlineKeyboardButton(text=t(lang, 'buy_now'), callback_data='menu:buy')])
    rows.append([InlineKeyboardButton(text=t(lang, 'back_menu'), callback_data='menu:root')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def devices_markup(lang: str, items: list[Dict[str, Any]]) -> InlineKeyboardMarkup:
    rows = []
    for idx, item in enumerate(items, 1):
        rows.append([InlineKeyboardButton(text=t(lang, 'device_remove').format(n=idx), callback_data=f"device:askdel:{item['id']}")])
    rows.append([InlineKeyboardButton(text=t(lang, 'back_menu'), callback_data='menu:root')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_device_delete_markup(lang: str, device_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t(lang, 'device_remove').replace('#', ''), callback_data=f'device:confirmdel:{device_id}'),
                InlineKeyboardButton(text=t(lang, 'back'), callback_data='device:cancel'),
            ],
            [InlineKeyboardButton(text=t(lang, 'back_menu'), callback_data='menu:devices')],
        ]
    )


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
        return normalize_lang(user.get('language'))
    except Exception:
        fallback = tg_user.language_code if getattr(tg_user, 'language_code', None) in {'ru', 'en'} else 'ru'
        return normalize_lang(fallback)


async def safe_edit(callback: CallbackQuery, text: str, markup: Optional[InlineKeyboardMarkup] = None) -> None:
    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except Exception:
        await callback.message.answer(text, reply_markup=markup)


async def show_backend_error(target: Message | CallbackQuery, lang: str) -> None:
    text = t(lang, 'service_unavailable')
    if isinstance(target, Message):
        await target.answer(text, reply_markup=menu_keyboard(lang))
    else:
        await safe_edit(target, text, back_inline(lang))
        await target.answer()


async def show_unexpected_error(target: Message | CallbackQuery, lang: str) -> None:
    text = t(lang, 'unexpected_error')
    if isinstance(target, Message):
        await target.answer(text, reply_markup=menu_keyboard(lang))
    else:
        await safe_edit(target, text, back_inline(lang))
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
            await target.answer(message, reply_markup=menu_keyboard(lang))
        else:
            await safe_edit(target, message, back_inline(lang))
            await target.answer()
    except Exception:
        logger.exception('Unhandled bot error')
        await show_unexpected_error(target, lang)


async def build_home_text(tg_user: Any, lang: str) -> str:
    auth = await auth_user(tg_user, language=lang)
    user = auth.get('user') or {}
    token = auth['token']
    data = await api_request('GET', '/subscriptions/me', token=token)
    sub = data.get('subscription')

    lines = [t(lang, 'menu')]
    lines.append('')

    if user.get('status') == 'blocked':
        lines.append(t(lang, 'menu_summary_blocked'))
    elif not sub:
        lines.append(t(lang, 'menu_summary_guest'))
    else:
        plan_name = sub['name_ru'] if lang == 'ru' else sub['name_en']
        lines.append(
            t(lang, 'menu_summary_active').format(
                plan=plan_name,
                expires=format_dt(sub.get('expires_at')),
                used=data.get('devices_used', 0),
                limit=sub.get('device_limit') or settings.VPN_DEFAULT_DEVICE_LIMIT,
            )
        )
    lines.append('')
    lines.append(t(lang, 'menu_hint'))
    return '\n'.join(lines)


async def send_menu(message: Message, lang: str, note: Optional[str] = None) -> None:
    home_text = await build_home_text(message.from_user, lang)
    if note:
        home_text = f'{note}\n\n{home_text}'
    await message.answer(home_text, reply_markup=menu_keyboard(lang))


async def open_menu_callback(callback: CallbackQuery, lang: str) -> None:
    home_text = await build_home_text(callback.from_user, lang)
    await safe_edit(callback, home_text, None)
    await callback.message.answer(t(lang, 'menu_hint'), reply_markup=menu_keyboard(lang))
    await callback.answer()


async def show_plans(target: Message | CallbackQuery, lang: str) -> None:
    plans = await api_request('GET', '/plans')
    text = t(lang, 'choose_plan')
    markup = plan_markup(lang, plans.get('items', []))
    if isinstance(target, Message):
        await target.answer(text, reply_markup=markup)
    else:
        await safe_edit(target, text, markup)
        await target.answer()


async def show_subscription(target: Message | CallbackQuery, lang: str) -> None:
    auth = await auth_user(target.from_user)
    token = auth['token']
    user = auth.get('user') or {}
    data = await api_request('GET', '/subscriptions/me', token=token)
    sub = data.get('subscription')

    lines = [t(lang, 'subscription_title'), '']
    if user.get('status') == 'blocked':
        lines.append(t(lang, 'menu_summary_blocked'))
        markup = support_markup(lang)
    elif not sub:
        lines.append(t(lang, 'subscription_none'))
        lines.append('')
        lines.append(t(lang, 'subscription_cta'))
        markup = subscription_markup(lang, has_subscription=False)
    else:
        plan_name = sub['name_ru'] if lang == 'ru' else sub['name_en']
        lines.append(t(lang, 'subscription_status').format(status=t(lang, 'status_active')))
        lines.append(t(lang, 'subscription_plan').format(plan=plan_name))
        lines.append(t(lang, 'subscription_expires').format(expires=format_dt(sub.get('expires_at'))))
        lines.append(
            t(lang, 'subscription_devices').format(
                used=data.get('devices_used', 0),
                limit=sub.get('device_limit') or settings.VPN_DEFAULT_DEVICE_LIMIT,
            )
        )
        markup = subscription_markup(lang, has_subscription=True)

    text = '\n'.join(lines)
    if isinstance(target, Message):
        await target.answer(text, reply_markup=markup)
    else:
        await safe_edit(target, text, markup)
        await target.answer()


async def show_devices(target: Message | CallbackQuery, lang: str) -> None:
    auth = await auth_user(target.from_user)
    token = auth['token']
    data = await api_request('GET', '/devices', token=token)
    items = data.get('items', [])

    lines = [t(lang, 'devices_title'), '']
    if not items:
        lines.append(t(lang, 'devices_none'))
        markup = back_inline(lang)
    else:
        for idx, row in enumerate(items, 1):
            device_name = row.get('device_name') or t(lang, 'device_unknown')
            lines.append(
                t(lang, 'device_item').format(
                    n=idx,
                    platform=row.get('platform') or 'unknown',
                    name=device_name,
                )
            )
        markup = devices_markup(lang, items)

    text = '\n'.join(lines)
    if isinstance(target, Message):
        await target.answer(text, reply_markup=markup)
    else:
        await safe_edit(target, text, markup)
        await target.answer()


async def show_download(target: Message | CallbackQuery, lang: str) -> None:
    text = t(lang, 'download_text')
    markup = download_markup(lang)
    if isinstance(target, Message):
        await target.answer(text, reply_markup=markup)
    else:
        await safe_edit(target, text, markup)
        await target.answer()


async def show_support(target: Message | CallbackQuery, lang: str) -> None:
    text = f"{t(lang, 'support_text')}\n{settings.SUPPORT_TELEGRAM_URL}"
    markup = support_markup(lang)
    if isinstance(target, Message):
        await target.answer(text, reply_markup=markup)
    else:
        await safe_edit(target, text, markup)
        await target.answer()


async def show_language(target: Message | CallbackQuery, lang: str) -> None:
    text = t(lang, 'language_text')
    markup = language_markup(lang)
    if isinstance(target, Message):
        await target.answer(text, reply_markup=markup)
    else:
        await safe_edit(target, text, markup)
        await target.answer()


def resolve_action(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    for action, labels in BUTTON_ACTIONS.items():
        if text in labels:
            return action
    return None


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


@dp.message(F.text)
async def menu_text_router(message: Message) -> None:
    action = resolve_action(message.text)

    async def _handler(lang: str) -> None:
        if action == 'buy':
            await show_plans(message, lang)
        elif action == 'sub':
            await show_subscription(message, lang)
        elif action == 'devices':
            await show_devices(message, lang)
        elif action == 'download':
            await show_download(message, lang)
        elif action == 'support':
            await show_support(message, lang)
        elif action == 'language':
            await show_language(message, lang)
        else:
            await send_menu(message, lang, note=t(lang, 'unknown_message'))

    await with_backend_guard(message, _handler)


@dp.callback_query(F.data == 'menu:root')
async def cb_root(callback: CallbackQuery) -> None:
    async def _handler(lang: str) -> None:
        await open_menu_callback(callback, lang)

    await with_backend_guard(callback, _handler)


@dp.callback_query(F.data == 'menu:buy')
async def cb_buy(callback: CallbackQuery) -> None:
    async def _handler(lang: str) -> None:
        await show_plans(callback, lang)

    await with_backend_guard(callback, _handler)


@dp.callback_query(F.data.startswith('buy:'))
async def cb_buy_plan(callback: CallbackQuery) -> None:
    async def _handler(lang: str) -> None:
        auth = await auth_user(callback.from_user)
        token = auth['token']
        plan_code = callback.data.split(':', 1)[1]
        result = await api_request('POST', '/payments/create', token=token, json_body={'plan_code': plan_code, 'method': 'telegram'})
        payment = result.get('payment') or {}
        checkout_url = payment.get('checkout_url') or None
        if not result.get('payments_enabled'):
            text = f"{t(lang, 'payments_off')}\n\n{settings.SUPPORT_TELEGRAM_URL}"
            markup = support_markup(lang)
        else:
            text = t(lang, 'payment_created')
            markup = payment_markup(lang, checkout_url)
        await safe_edit(callback, text, markup)
        await callback.answer()

    await with_backend_guard(callback, _handler)


@dp.callback_query(F.data == 'menu:sub')
async def cb_subscription(callback: CallbackQuery) -> None:
    async def _handler(lang: str) -> None:
        await show_subscription(callback, lang)

    await with_backend_guard(callback, _handler)


@dp.callback_query(F.data == 'menu:devices')
async def cb_devices(callback: CallbackQuery) -> None:
    async def _handler(lang: str) -> None:
        await show_devices(callback, lang)

    await with_backend_guard(callback, _handler)


@dp.callback_query(F.data.startswith('device:askdel:'))
async def cb_device_ask_delete(callback: CallbackQuery) -> None:
    async def _handler(lang: str) -> None:
        auth = await auth_user(callback.from_user)
        token = auth['token']
        data = await api_request('GET', '/devices', token=token)
        items = data.get('items', [])
        device_id = int(callback.data.rsplit(':', 1)[1])
        item = next((row for row in items if int(row['id']) == device_id), None)
        device_name = (item or {}).get('device_name') or t(lang, 'device_unknown')
        text = t(lang, 'device_remove_confirm').format(name=device_name)
        await safe_edit(callback, text, confirm_device_delete_markup(lang, device_id))
        await callback.answer()

    await with_backend_guard(callback, _handler)


@dp.callback_query(F.data.startswith('device:confirmdel:'))
async def cb_device_confirm_delete(callback: CallbackQuery) -> None:
    async def _handler(lang: str) -> None:
        auth = await auth_user(callback.from_user)
        token = auth['token']
        device_id = int(callback.data.rsplit(':', 1)[1])
        await api_request('DELETE', f'/devices/{device_id}', token=token)
        await safe_edit(callback, t(lang, 'device_removed'), back_inline(lang))
        await callback.answer()

    await with_backend_guard(callback, _handler)


@dp.callback_query(F.data == 'device:cancel')
async def cb_device_cancel(callback: CallbackQuery) -> None:
    async def _handler(lang: str) -> None:
        await safe_edit(callback, t(lang, 'device_remove_cancelled'), back_inline(lang))
        await callback.answer()

    await with_backend_guard(callback, _handler)


@dp.callback_query(F.data == 'menu:download')
async def cb_download(callback: CallbackQuery) -> None:
    async def _handler(lang: str) -> None:
        await show_download(callback, lang)

    await with_backend_guard(callback, _handler)


@dp.callback_query(F.data == 'menu:support')
async def cb_support(callback: CallbackQuery) -> None:
    async def _handler(lang: str) -> None:
        await show_support(callback, lang)

    await with_backend_guard(callback, _handler)


@dp.callback_query(F.data == 'menu:language')
async def cb_language(callback: CallbackQuery) -> None:
    async def _handler(lang: str) -> None:
        await show_language(callback, lang)

    await with_backend_guard(callback, _handler)


@dp.callback_query(F.data.startswith('lang:set:'))
async def cb_language_set(callback: CallbackQuery) -> None:
    async def _handler(lang: str) -> None:
        new_lang = normalize_lang(callback.data.rsplit(':', 1)[1])
        await auth_user(callback.from_user, language=new_lang)
        await safe_edit(callback, t(new_lang, 'lang_saved'), back_inline(new_lang))
        await callback.message.answer(t(new_lang, 'menu_hint'), reply_markup=menu_keyboard(new_lang))
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
