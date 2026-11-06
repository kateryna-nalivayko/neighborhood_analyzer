import pytest

from bot.analyzer import (SORT_DISTANCE, SORT_RATING, haversine_m, sort_by_rating, top_places,
                          transport)
from bot.categories import CATEGORY_BY_KEY, TRANSPORT_GROUPS
from bot.google_client import Place

LAT, LNG = 50.4501, 30.5234


def north(meters: float) -> tuple[float, float]:
    return LAT + meters / 111_195.0, LNG


def test_haversine_known_distance():
    # Київ → Львів ≈ 468 км по прямій
    assert haversine_m(50.4501, 30.5234, 49.8397, 24.0297) == pytest.approx(468_000, rel=0.01)


def test_sort_by_rating_puts_unrated_last_and_uses_review_count():
    a = (Place("A", 0, 0, rating=4.5, rating_count=10), 300.0)
    b = (Place("B", 0, 0, rating=4.5, rating_count=500), 600.0)
    c = (Place("C", 0, 0, rating=None), 100.0)
    d = (Place("D", 0, 0, rating=4.9, rating_count=3), 900.0)
    assert [p.name for p, _ in sort_by_rating([a, b, c, d])] == ["D", "B", "A", "C"]


class FakeGoogle:
    def __init__(self):
        self.calls = []

    async def search_nearby(self, lat, lng, radius, types, *, rank="DISTANCE",
                            with_rating=False, max_results=20):
        self.calls.append({"types": tuple(types), "rank": rank, "rating": with_rating,
                           "max": max_results})
        if "bus_stop" in types:
            return [Place(f"Зупинка {i}", *north(50 * i)) for i in range(1, 20)]
        if "train_station" in types:
            return []
        if "supermarket" in types:
            return [Place(f"М{i}", *north(100 * i), rating=3.0 + i / 10) for i in range(15, 0, -1)]
        return [Place("Станція", *north(400))]


@pytest.mark.asyncio
async def test_top_places_by_distance_and_by_rating():
    g = FakeGoogle()
    shops = CATEGORY_BY_KEY["shops"]
    near = await top_places(g, shops, LAT, LNG, 1000, SORT_DISTANCE)
    best = await top_places(g, shops, LAT, LNG, 1000, SORT_RATING)
    assert g.calls[0]["rank"] == "DISTANCE" and g.calls[0]["rating"] is True
    assert g.calls[1]["rank"] == "POPULARITY"
    assert len(near) == 10 and near[0][0].name == "М1"
    assert [d for _, d in near] == sorted(d for _, d in near)
    assert best[0][0].name == "М15"


@pytest.mark.asyncio
async def test_transport_queries_each_group_once():
    g = FakeGoogle()
    groups = await transport(g, LAT, LNG, 1000)
    assert [grp.type for grp, _ in groups] == [t.type for t in TRANSPORT_GROUPS]
    assert all(c["rating"] is False for c in g.calls)
    stops = dict((grp.type, items) for grp, items in groups)
    assert stops["train_station"] == []
    assert stops["bus_stop"][0][0].name == "Зупинка 1"
