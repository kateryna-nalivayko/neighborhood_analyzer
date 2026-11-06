"""Обробка даних: відстані, сортування за відстанню чи рейтингом, транспорт."""

from __future__ import annotations

import asyncio
import math

from .categories import TOP_LIMIT, TRANSPORT_GROUPS, Category, TransportGroup
from .google_client import GoogleMapsClient, Place

SORT_DISTANCE = "d"
SORT_RATING = "r"


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Відстань між двома точками на поверхні Землі в метрах."""
    r = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def with_distance(lat: float, lng: float, places: list[Place]) -> list[tuple[Place, float]]:
    return [(p, haversine_m(lat, lng, p.lat, p.lng)) for p in places]


def sort_by_distance(items: list[tuple[Place, float]]) -> list[tuple[Place, float]]:
    return sorted(items, key=lambda item: item[1])


def sort_by_rating(items: list[tuple[Place, float]]) -> list[tuple[Place, float]]:
    """Спершу вищий рейтинг; за однакового — більше відгуків; без рейтингу — в кінці."""
    return sorted(items, key=lambda item: (
        item[0].rating is None,
        -(item[0].rating or 0),
        -(item[0].rating_count or 0),
        item[1],
    ))


async def top_places(client: GoogleMapsClient, category: Category, lat: float, lng: float,
                     radius: int, sort: str = SORT_DISTANCE,
                     limit: int = TOP_LIMIT) -> list[tuple[Place, float]]:
    """Топ місць категорії в радіусі: найближчі або з найвищим рейтингом."""
    if sort == SORT_RATING:
        # Для рейтингу беремо 20 найпопулярніших у радіусі, а не 20 найближчих.
        places = await client.search_nearby(lat, lng, radius, category.types,
                                            rank="POPULARITY", with_rating=True)
        return sort_by_rating(with_distance(lat, lng, places))[:limit]
    places = await client.search_nearby(lat, lng, radius, category.types,
                                        rank="DISTANCE", with_rating=True)
    return sort_by_distance(with_distance(lat, lng, places))[:limit]


async def transport(client: GoogleMapsClient, lat: float, lng: float,
                    radius: int) -> list[tuple[TransportGroup, list[tuple[Place, float]]]]:
    """Автостанції, метро, залізничні станції та зупинки — паралельними запитами."""
    responses = await asyncio.gather(*(
        client.search_nearby(lat, lng, radius, [group.type], rank="DISTANCE",
                             max_results=group.limit)
        for group in TRANSPORT_GROUPS
    ))
    return [(group, sort_by_distance(with_distance(lat, lng, places)))
            for group, places in zip(TRANSPORT_GROUPS, responses)]
