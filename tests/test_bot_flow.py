"""Перевірка логіки обробників без реального Telegram і Google API."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.analyzer import SORT_DISTANCE, SORT_RATING
from bot.cache import TTLCache
from bot.categories import CATEGORY_BY_KEY, TRANSPORT_GROUPS
from bot.config import Settings
from bot.formatting import format_air_quality, format_top_places, format_transport
from bot.google_client import Address, AirQuality, GoogleAPIError, Place, Pollutant
from bot.handlers import on_address, on_category, on_ecology, on_menu, on_new_address
from bot.keyboards import ActionCb, CategoryCb, main_menu, sort_keyboard

SETTINGS = Settings(telegram_token="t", google_api_key="k", default_radius=1000)
ADDR = Address(50.4475, 30.5236, "вулиця Хрещатик, 22, Київ", city="Київ", district="Печерський район")


class FakeGoogle:
    def __init__(self, address=ADDR, error=None):
        self.address, self.error = address, error
        self.reverse_calls = 0

    async def geocode(self, query):
        if self.error:
            raise self.error
        return self.address

    async def reverse_geocode(self, lat, lng):
        self.reverse_calls += 1
        return self.address

    async def search_nearby(self, lat, lng, radius, types, **kw):
        return [Place("Кафе <Львівські круасани>", lat + 0.002, lng, rating=4.6, rating_count=812,
                      maps_url="https://maps.google.com/?cid=7")]

    async def air_quality(self, lat, lng):
        return AirQuality(79, "Хороша якість повітря", "PM2.5",
                          (Pollutant("pm25", "PM2.5", 13.41, "MICROGRAMS_PER_CUBIC_METER"),), "Гуляйте!")


def callback_mock():
    cb = MagicMock()
    cb.answer = AsyncMock()
    cb.message.edit_text = AsyncMock()
    return cb


@pytest.mark.asyncio
async def test_address_flow_sends_card_with_menu_then_map():
    msg = MagicMock()
    msg.text = "Хрещатик 22, Київ"
    msg.answer = AsyncMock()
    msg.answer_location = AsyncMock()
    addresses = TTLCache()
    await on_address(msg, FakeGoogle(), SETTINGS, addresses)

    text = msg.answer.await_args.args[0]
    assert "Адресу знайдено" in text and "Печерський район" in text and "Київ" in text
    keyboard = msg.answer.await_args.kwargs["reply_markup"].inline_keyboard
    labels = [b.text for row in keyboard for b in row]
    assert labels == ["🛒 Магазини", "🍽 Ресторани", "🎡 Розваги", "🏃 Спорт", "🌳 Парки",
                      "🚌 Транспорт", "🌿 Екологія", "⬅️ Назад"]
    msg.answer_location.assert_awaited_once()
    assert addresses.get((50.4475, 30.5236)) == ADDR


@pytest.mark.asyncio
async def test_address_flow_reports_api_error():
    msg = MagicMock()
    msg.text = "Хрещатик 22"
    msg.answer = AsyncMock()
    msg.answer_location = AsyncMock()
    err = GoogleAPIError("Geocoding API", 403, "REQUEST_DENIED", "")
    await on_address(msg, FakeGoogle(error=err), SETTINGS, TTLCache())
    assert "Geocoding API" in msg.answer.await_args.args[0]
    msg.answer_location.assert_not_awaited()


@pytest.mark.asyncio
async def test_category_shows_list_with_sort_buttons():
    cb = callback_mock()
    data = CategoryCb(key="food", sort=SORT_RATING, lat=50.4475, lng=30.5236)
    await on_category(cb, data, FakeGoogle(), SETTINGS)
    text = cb.message.edit_text.await_args.args[0]
    assert "топ за рейтингом" in text
    assert "&lt;Львівські круасани&gt;" in text and "⭐ 4,6 (812)" in text
    buttons = [b.text for row in cb.message.edit_text.await_args.kwargs["reply_markup"].inline_keyboard for b in row]
    assert buttons == ["📏 За відстанню", "✓ ⭐ За рейтингом", "⬅️ Назад"]


@pytest.mark.asyncio
async def test_ecology_and_back_to_menu_restores_card():
    cb = callback_mock()
    await on_ecology(cb, ActionCb(act="eco", lat=50.4475, lng=30.5236), FakeGoogle())
    assert "79 / 100" in cb.message.edit_text.await_args.args[0]

    cb2 = callback_mock()
    google = FakeGoogle()
    await on_menu(cb2, ActionCb(act="menu", lat=50.4475, lng=30.5236), google, SETTINGS, TTLCache())
    assert google.reverse_calls == 1, "без кешу адреса відновлюється reverse geocoding"
    assert "Печерський район" in cb2.message.edit_text.await_args.args[0]


@pytest.mark.asyncio
async def test_back_on_card_asks_for_new_address():
    cb = callback_mock()
    await on_new_address(cb)
    assert "нову адресу" in cb.message.edit_text.await_args.args[0]


def test_callback_data_fits_telegram_limit():
    for kb in (main_menu(-33.868820123, 151.209295456),
               sort_keyboard("sport", SORT_DISTANCE, -33.868820123, 151.209295456)):
        for row in kb.inline_keyboard:
            for button in row:
                assert len(button.callback_data.encode()) <= 64, button.callback_data


def test_texts_for_empty_results():
    assert "нічого не знайдено" in format_top_places(CATEGORY_BY_KEY["parks"], SORT_DISTANCE, 1000, [])
    text = format_transport(1000, [(g, []) for g in TRANSPORT_GROUPS])
    assert text.count("немає поблизу") == len(TRANSPORT_GROUPS)
    assert "немає даних" in format_air_quality(AirQuality(None, None, None, (), None))
