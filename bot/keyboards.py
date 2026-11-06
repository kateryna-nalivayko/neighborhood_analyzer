"""Інлайн-кнопки бота. Координати зберігаються прямо в кнопці (callback_data ≤ 64 байти)."""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .analyzer import SORT_DISTANCE, SORT_RATING
from .categories import PLACE_CATEGORIES


class CategoryCb(CallbackData, prefix="c"):
    key: str     # shops / food / fun / sport / parks
    sort: str    # d — за відстанню, r — за рейтингом
    lat: float
    lng: float


class ActionCb(CallbackData, prefix="a"):
    act: str     # tr — транспорт, eco — екологія, menu — меню адреси, new — нова адреса
    lat: float
    lng: float


def _c(value: float) -> float:
    return round(value, 5)


def main_menu(lat: float, lng: float) -> InlineKeyboardMarkup:
    lat, lng = _c(lat), _c(lng)
    buttons = [
        InlineKeyboardButton(text=c.label, callback_data=CategoryCb(
            key=c.key, sort=SORT_DISTANCE, lat=lat, lng=lng).pack())
        for c in PLACE_CATEGORIES
    ]
    buttons += [
        InlineKeyboardButton(text="🚌 Транспорт", callback_data=ActionCb(act="tr", lat=lat, lng=lng).pack()),
        InlineKeyboardButton(text="🌿 Екологія", callback_data=ActionCb(act="eco", lat=lat, lng=lng).pack()),
        InlineKeyboardButton(text="⬅️ Назад", callback_data=ActionCb(act="new", lat=lat, lng=lng).pack()),
    ]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def sort_keyboard(key: str, current: str, lat: float, lng: float) -> InlineKeyboardMarkup:
    lat, lng = _c(lat), _c(lng)

    def btn(sort: str, text: str) -> InlineKeyboardButton:
        mark = "✓ " if sort == current else ""
        return InlineKeyboardButton(text=mark + text, callback_data=CategoryCb(
            key=key, sort=sort, lat=lat, lng=lng).pack())

    return InlineKeyboardMarkup(inline_keyboard=[
        [btn(SORT_DISTANCE, "📏 За відстанню"), btn(SORT_RATING, "⭐ За рейтингом")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=ActionCb(act="menu", lat=lat, lng=lng).pack())],
    ])


def back_keyboard(lat: float, lng: float) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text="⬅️ Назад", callback_data=ActionCb(act="menu", lat=_c(lat), lng=_c(lng)).pack())]])
