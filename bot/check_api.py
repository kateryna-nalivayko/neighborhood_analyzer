"""Перевірка API-ключа без Telegram: усі три API по черзі.

Запуск:
    python -m bot.check_api "Хрещатик 22, Київ"
"""

from __future__ import annotations

import asyncio
import os
import sys

from dotenv import load_dotenv

from .analyzer import top_places
from .categories import CATEGORY_BY_KEY
from .formatting import UNITS, format_distance, number_uk
from .google_client import GoogleAPIError, GoogleMapsClient


async def run(query: str, radius: int) -> int:
    api_key = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
    if not api_key:
        print("❌ Не задано GOOGLE_MAPS_API_KEY у файлі .env")
        return 1

    client = GoogleMapsClient(api_key)
    ok = True
    try:
        print(f"1) Geocoding API: {query!r}")
        address = await client.geocode(query)
        if address is None:
            print("   😕 Адресу не знайдено")
            return 1
        print(f"   ✓ Місто: {address.city} | Район: {address.district}")
        print(f"   ✓ {address.formatted}  ({address.lat:.5f}, {address.lng:.5f})\n")

        print(f"2) Places API (New): Nearby Search — магазини в радіусі {radius} м")
        try:
            items = await top_places(client, CATEGORY_BY_KEY["shops"], address.lat, address.lng,
                                     radius)
            for i, (place, dist) in enumerate(items[:5], 1):
                rating = number_uk(place.rating, 1) if place.rating is not None else "—"
                print(f"   {i}. {place.name} — {format_distance(dist)}, ⭐ {rating}")
            if not items:
                print("   (нічого не знайдено)")
        except GoogleAPIError as exc:
            ok = False
            print(f"   ❌ {exc}\n   {exc.user_message}")
        print()

        print("3) Air Quality API")
        try:
            aq = await client.air_quality(address.lat, address.lng)
            print(f"   ✓ UAQI: {aq.aqi}/100 — {aq.category}")
            for p in aq.pollutants:
                print(f"     {p.name}: {number_uk(p.value)} {UNITS.get(p.units, p.units)}")
        except GoogleAPIError as exc:
            ok = False
            print(f"   ❌ {exc}\n   {exc.user_message}")
    except GoogleAPIError as exc:
        print(f"   ❌ {exc}\n   {exc.user_message}")
        return 1
    finally:
        await client.aclose()

    print("\n✅ Усі API працюють" if ok else "\n⚠️ Деякі API не відповіли — див. вище")
    return 0 if ok else 1


def main() -> None:
    load_dotenv()
    query = " ".join(sys.argv[1:]).strip() or "Хрещатик 22, Київ"
    radius = int(os.getenv("DEFAULT_RADIUS", "1000") or 1000)
    sys.exit(asyncio.run(run(query, radius)))


if __name__ == "__main__":
    main()
