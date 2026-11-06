"""Обробники повідомлень і кнопок Telegram (aiogram 3)."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from .analyzer import top_places, transport
from .cache import TTLCache
from .categories import CATEGORY_BY_KEY
from .config import Settings
from .formatting import (HELP_TEXT, NEW_ADDRESS_TEXT, WELCOME_TEXT, format_address_card,
                         format_air_quality, format_top_places, format_transport)
from .google_client import Address, GoogleAPIError, GoogleMapsClient
from .keyboards import ActionCb, CategoryCb, back_keyboard, main_menu, sort_keyboard

log = logging.getLogger(__name__)
router = Router(name="neighborhood")


def _key(lat: float, lng: float) -> tuple[float, float]:
    return round(lat, 5), round(lng, 5)


async def _show(callback: CallbackQuery, text: str, markup: InlineKeyboardMarkup | None) -> None:
    """Замінює текст повідомлення з кнопками (як «сторінки» меню)."""
    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(WELCOME_TEXT)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT)


@router.message(F.text & ~F.text.startswith("/"))
async def on_address(message: Message, google: GoogleMapsClient, settings: Settings,
                     addresses: TTLCache[Address]) -> None:
    query = message.text.strip()
    if len(query) < 3:
        await message.answer("Адреса закоротка. Приклад: <i>Хрещатик 22, Київ</i>")
        return
    try:
        address = await google.geocode(query)
    except GoogleAPIError as exc:
        await message.answer("⚠️ " + exc.user_message)
        return
    if address is None:
        await message.answer("😕 Не вдалося знайти таку адресу. Спробуйте додати місто, "
                             "наприклад: <i>вул. Січових Стрільців 10, Львів</i>")
        return

    addresses.set(_key(address.lat, address.lng), address)
    await message.answer(format_address_card(address, settings.default_radius),
                         reply_markup=main_menu(address.lat, address.lng))
    await message.answer_location(latitude=address.lat, longitude=address.lng)


@router.callback_query(CategoryCb.filter())
async def on_category(callback: CallbackQuery, callback_data: CategoryCb,
                      google: GoogleMapsClient, settings: Settings) -> None:
    category = CATEGORY_BY_KEY.get(callback_data.key)
    if category is None:
        await callback.answer("Невідома категорія", show_alert=True)
        return
    try:
        items = await top_places(google, category, callback_data.lat, callback_data.lng,
                                 settings.default_radius, callback_data.sort)
    except GoogleAPIError as exc:
        await callback.answer(exc.user_message, show_alert=True)
        return
    await callback.answer()
    await _show(callback,
                format_top_places(category, callback_data.sort, settings.default_radius, items),
                sort_keyboard(category.key, callback_data.sort, callback_data.lat, callback_data.lng))


@router.callback_query(ActionCb.filter(F.act == "tr"))
async def on_transport(callback: CallbackQuery, callback_data: ActionCb,
                       google: GoogleMapsClient, settings: Settings) -> None:
    try:
        groups = await transport(google, callback_data.lat, callback_data.lng,
                                 settings.default_radius)
    except GoogleAPIError as exc:
        await callback.answer(exc.user_message, show_alert=True)
        return
    await callback.answer()
    await _show(callback, format_transport(settings.default_radius, groups),
                back_keyboard(callback_data.lat, callback_data.lng))


@router.callback_query(ActionCb.filter(F.act == "eco"))
async def on_ecology(callback: CallbackQuery, callback_data: ActionCb,
                     google: GoogleMapsClient) -> None:
    try:
        aq = await google.air_quality(callback_data.lat, callback_data.lng)
    except GoogleAPIError as exc:
        await callback.answer(exc.user_message, show_alert=True)
        return
    await callback.answer()
    await _show(callback, format_air_quality(aq),
                back_keyboard(callback_data.lat, callback_data.lng))


@router.callback_query(ActionCb.filter(F.act == "menu"))
async def on_menu(callback: CallbackQuery, callback_data: ActionCb, google: GoogleMapsClient,
                  settings: Settings, addresses: TTLCache[Address]) -> None:
    lat, lng = callback_data.lat, callback_data.lng
    address = addresses.get(_key(lat, lng))
    if address is None:
        # Бот перезапускався — відновлюємо адресу за координатами.
        try:
            address = await google.reverse_geocode(lat, lng)
        except GoogleAPIError:
            address = None
        address = address or Address(lat, lng, f"{lat:.5f}, {lng:.5f}")
        addresses.set(_key(lat, lng), address)
    await callback.answer()
    await _show(callback, format_address_card(address, settings.default_radius),
                main_menu(lat, lng))


@router.callback_query(ActionCb.filter(F.act == "new"))
async def on_new_address(callback: CallbackQuery) -> None:
    await callback.answer()
    await _show(callback, NEW_ADDRESS_TEXT, None)
