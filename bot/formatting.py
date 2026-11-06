"""Тексти повідомлень бота (Telegram HTML)."""

from __future__ import annotations

from html import escape

from .analyzer import SORT_RATING
from .categories import Category, TransportGroup
from .google_client import Address, AirQuality, Place

UNITS = {"PARTS_PER_BILLION": "ч/млрд", "MICROGRAMS_PER_CUBIC_METER": "мкг/м³"}
POLLUTANT_EMOJI = {"co": "🔥", "no2": "🚗", "o3": "☀️", "pm10": "🌫", "pm25": "🌫", "so2": "🏭"}


def h(text: str) -> str:
    """Екранує текст для Telegram HTML (апострофи лишаємо як є)."""
    return escape(text, quote=False)


def number_uk(value: float, digits: int = 2) -> str:
    text = f"{value:.{digits}f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")


def format_distance(meters: float) -> str:
    if meters < 1000:
        return f"{int(round(meters))} м"
    return f"{number_uk(meters / 1000, 1)} км"


def format_radius(meters: int) -> str:
    return f"{meters} м" if meters < 1000 else f"{number_uk(meters / 1000, 1)} км"


def place_link(place: Place) -> str:
    name = h(place.name)
    if place.maps_url:
        return f'<a href="{escape(place.maps_url, quote=True)}">{name}</a>'
    return name


WELCOME_TEXT = (
    "👋 Привіт! Я <b>Neighborhood Analyzer</b>.\n\n"
    "Надішли мені адресу, наприклад <i>Хрещатик 22, Київ</i>, — я покажу її на карті "
    "й розповім, що є поруч: магазини, ресторани, розваги, спорт, парки, транспорт "
    "і якість повітря."
)

HELP_TEXT = (
    "ℹ️ <b>Як користуватися</b>\n\n"
    "1. Надішли адресу (краще з назвою міста).\n"
    "2. Обери кнопку категорії під повідомленням.\n"
    "3. У категорії перемикай сортування: 📏 за відстанню або ⭐ за рейтингом.\n"
    "4. «⬅️ Назад» повертає до меню адреси."
)

NEW_ADDRESS_TEXT = "✍️ Надішли нову адресу — і я проаналізую інший район."


def format_address_card(address: Address, radius: int) -> str:
    return "\n".join([
        "📍 <b>Адресу знайдено!</b>",
        "",
        f"<b>Місто:</b> {h(address.city or 'не визначено')}",
        f"<b>Район:</b> {h(address.district or 'не визначено')}",
        f"<b>Адреса:</b> {h(address.formatted)}",
        "",
        f"Що показати поблизу (радіус {format_radius(radius)})?",
    ])


def format_top_places(category: Category, sort: str, radius: int,
                      items: list[tuple[Place, float]]) -> str:
    mode = "за рейтингом" if sort == SORT_RATING else "за відстанню"
    header = f"{category.emoji} <b>{h(category.title)}: топ {mode}</b>"
    if not items:
        return f"{header}\n\nУ радіусі {format_radius(radius)} нічого не знайдено 😕"
    lines = [header, ""]
    for i, (place, dist) in enumerate(items, start=1):
        if place.rating is not None:
            rating = f"⭐ {number_uk(place.rating, 1)}"
            if place.rating_count:
                rating += f" ({place.rating_count})"
        else:
            rating = "⭐ немає оцінок"
        lines.append(f"{i}. {place_link(place)}")
        lines.append(f"📏 {format_distance(dist)} | {rating}")
        lines.append("")
    return "\n".join(lines).rstrip()


def format_transport(radius: int,
                     groups: list[tuple[TransportGroup, list[tuple[Place, float]]]]) -> str:
    lines = [f"🚌 <b>Транспорт поблизу (до {format_radius(radius)})</b>"]
    for group, items in groups:
        lines.append("")
        if not items:
            lines.append(f"<b>{h(group.title)}:</b> <i>немає поблизу</i>")
            continue
        lines.append(f"<b>{h(group.title)}:</b>")
        for place, dist in items[:group.limit]:
            lines.append(f"{place_link(place)} | 📏 {format_distance(dist)}")
    return "\n".join(lines)


def aqi_emoji(aqi: int | None) -> str:
    # Universal AQI: 100 — найкраще повітря, 0 — найгірше.
    if aqi is None:
        return "⚪️"
    if aqi >= 80:
        return "🟢"
    if aqi >= 60:
        return "🟡"
    if aqi >= 40:
        return "🟠"
    if aqi >= 20:
        return "🔴"
    return "🟣"


def format_air_quality(aq: AirQuality) -> str:
    aqi_text = f"{aq.aqi} / 100" if aq.aqi is not None else "немає даних"
    lines = [
        "🌍 <b>Екологія району</b>",
        "",
        f"🌿 <b>Якість повітря (UAQI):</b> {aqi_emoji(aq.aqi)} {aqi_text}",
    ]
    if aq.category:
        lines.append(f"📊 <b>Категорія:</b> {h(aq.category)}")
    if aq.dominant:
        lines.append(f"⚠️ <b>Основний забруднювач:</b> {h(aq.dominant)}")
    if aq.pollutants:
        lines += ["", "🔬 <b>Концентрація речовин:</b>"]
        for p in aq.pollutants:
            emoji = POLLUTANT_EMOJI.get(p.code, "•")
            units = UNITS.get(p.units, p.units.lower())
            lines.append(f"{emoji} <b>{h(p.name)}:</b> {number_uk(p.value)} {units}")
    if aq.recommendation:
        lines += ["", f"💡 <i>{h(aq.recommendation)}</i>"]
    return "\n".join(lines)
