"""Кнопки-категорії бота і відповідні типи місць Places API (New).

Типи — з таблиці A: https://developers.google.com/maps/documentation/places/web-service/place-types
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Category:
    key: str
    emoji: str
    title: str
    types: tuple[str, ...]

    @property
    def label(self) -> str:
        return f"{self.emoji} {self.title}"


PLACE_CATEGORIES: tuple[Category, ...] = (
    Category("shops", "🛒", "Магазини",
             ("supermarket", "grocery_store", "convenience_store", "shopping_mall")),
    Category("food", "🍽", "Ресторани",
             ("restaurant", "cafe", "coffee_shop", "fast_food_restaurant")),
    Category("fun", "🎡", "Розваги",
             ("movie_theater", "amusement_park", "amusement_center", "bowling_alley",
              "night_club", "karaoke", "museum", "zoo", "aquarium")),
    Category("sport", "🏃", "Спорт",
             ("gym", "fitness_center", "sports_complex", "sports_club", "stadium")),
    Category("parks", "🌳", "Парки",
             ("park", "city_park", "botanical_garden", "garden")),
)

CATEGORY_BY_KEY: dict[str, Category] = {c.key: c for c in PLACE_CATEGORIES}


@dataclass(frozen=True)
class TransportGroup:
    type: str
    title: str
    limit: int


TRANSPORT_GROUPS: tuple[TransportGroup, ...] = (
    TransportGroup("bus_station", "Автостанції", 5),
    TransportGroup("subway_station", "Станції метро", 5),
    TransportGroup("train_station", "Залізничні станції", 5),
    TransportGroup("bus_stop", "Зупинки громадського транспорту", 15),
)

TOP_LIMIT = 10  # скільки місць показувати в категорії
