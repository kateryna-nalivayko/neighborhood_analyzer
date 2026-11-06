"""Асинхронний клієнт трьох API Google Maps Platform.

  * Geocoding API      — адреса → координати, місто, район;
  * Places API (New)   — Nearby Search: об'єкти потрібних типів у радіусі;
  * Air Quality API    — якість повітря в точці.

Ключ API передається:
  * Geocoding  — параметром ?key=... (так вимагає цей API);
  * Places / Air Quality — заголовком X-Goog-Api-Key.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Iterable

import httpx

from .cache import TTLCache

log = logging.getLogger(__name__)

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
PLACES_NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"
AIR_QUALITY_URL = "https://airquality.googleapis.com/v1/currentConditions:lookup"

# Від набору полів (FieldMask) залежить тариф Places API:
# базові поля — SKU Pro, рейтинг — SKU Enterprise.
BASIC_FIELDS = "places.displayName,places.location,places.googleMapsUri"
RATED_FIELDS = BASIC_FIELDS + ",places.rating,places.userRatingCount"


# ---------- моделі даних ----------

@dataclass(frozen=True)
class Address:
    lat: float
    lng: float
    formatted: str
    city: str | None = None
    district: str | None = None


@dataclass(frozen=True)
class Place:
    name: str
    lat: float
    lng: float
    maps_url: str | None = None
    rating: float | None = None
    rating_count: int | None = None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "Place | None":
        loc = data.get("location") or {}
        if "latitude" not in loc or "longitude" not in loc:
            return None
        return cls(
            name=(data.get("displayName") or {}).get("text", "Без назви"),
            lat=float(loc["latitude"]),
            lng=float(loc["longitude"]),
            maps_url=data.get("googleMapsUri"),
            rating=data.get("rating"),
            rating_count=data.get("userRatingCount"),
        )


@dataclass(frozen=True)
class Pollutant:
    code: str
    name: str
    value: float
    units: str


@dataclass(frozen=True)
class AirQuality:
    aqi: int | None
    category: str | None
    dominant: str | None
    pollutants: tuple[Pollutant, ...]
    recommendation: str | None


class GoogleAPIError(Exception):
    """Помилка відповіді Google API або мережі."""

    def __init__(self, api: str, http_status: int, status: str, message: str) -> None:
        super().__init__(f"{api}: {http_status} {status}: {message}")
        self.api = api
        self.http_status = http_status
        self.status = status
        self.message = message

    @property
    def user_message(self) -> str:
        if self.http_status in (401, 403) or self.status in ("PERMISSION_DENIED", "REQUEST_DENIED"):
            return (f"Google відхилив запит до {self.api}. Перевірте, що цей API увімкнено, "
                    "підключено білінг і API-ключ не обмежено іншими API.")
        if self.http_status == 429 or self.status in ("RESOURCE_EXHAUSTED", "OVER_QUERY_LIMIT"):
            return "Вичерпано ліміт запитів до Google. Спробуйте пізніше."
        if self.http_status == 0:
            return "Немає з'єднання з Google. Спробуйте ще раз."
        return f"Сервіс {self.api} тимчасово недоступний. Спробуйте пізніше."


# ---------- розбір відповіді Geocoding ----------

_GEOCODE_STATUS_HTTP = {"REQUEST_DENIED": 403, "OVER_QUERY_LIMIT": 429,
                        "OVER_DAILY_LIMIT": 429, "INVALID_REQUEST": 400}


def _component(components: list[dict[str, Any]], *types: str) -> str | None:
    for wanted in types:
        for comp in components:
            if wanted in comp.get("types", []):
                return comp.get("long_name")
    return None


def parse_geocode_result(result: dict[str, Any]) -> Address:
    comps = result.get("address_components", [])
    loc = result["geometry"]["location"]
    return Address(
        lat=float(loc["lat"]),
        lng=float(loc["lng"]),
        formatted=result.get("formatted_address", ""),
        city=_component(comps, "locality", "postal_town", "administrative_area_level_1"),
        district=_component(comps, "sublocality_level_1", "sublocality",
                            "administrative_area_level_2"),
    )


def parse_air_quality(data: dict[str, Any]) -> AirQuality:
    indexes = data.get("indexes") or []
    index = next((i for i in indexes if i.get("code") == "uaqi"), indexes[0] if indexes else {})
    pollutants = tuple(
        Pollutant(
            code=p.get("code", ""),
            name=p.get("displayName", p.get("code", "").upper()),
            value=float(p["concentration"]["value"]),
            units=p["concentration"].get("units", ""),
        )
        for p in data.get("pollutants") or []
        if "concentration" in p and "value" in p["concentration"]
    )
    dominant_code = index.get("dominantPollutant")
    dominant = next((p.name for p in pollutants if p.code == dominant_code), dominant_code)
    return AirQuality(
        aqi=index.get("aqi"),
        category=index.get("category"),
        dominant=dominant,
        pollutants=pollutants,
        recommendation=(data.get("healthRecommendations") or {}).get("generalPopulation"),
    )


# ---------- клієнт ----------

class GoogleMapsClient:
    def __init__(self, api_key: str, *, language: str = "uk", region: str = "UA",
                 cache_ttl: int = 3600, timeout: float = 10.0,
                 http_client: httpx.AsyncClient | None = None) -> None:
        self._key = api_key
        self._language = language
        self._region = region
        self._http = http_client or httpx.AsyncClient(timeout=timeout)
        self._cache: TTLCache[Any] = TTLCache(ttl_seconds=cache_ttl)

    async def aclose(self) -> None:
        await self._http.aclose()

    # --- Geocoding API ---

    async def geocode(self, address: str) -> Address | None:
        """Адреса → координати, місто, район."""
        return await self._geocode({"address": address.strip()})

    async def reverse_geocode(self, lat: float, lng: float) -> Address | None:
        """Координати → адреса (для повернення в меню після перезапуску бота)."""
        return await self._geocode({"latlng": f"{lat},{lng}"})

    async def _geocode(self, params: dict[str, str]) -> Address | None:
        cache_key = ("geo", tuple(sorted(params.items())))
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        query = {**params, "key": self._key, "language": self._language,
                 "region": self._region.lower()}
        data = await self._request("Geocoding API", "GET", GEOCODE_URL, params=query)
        status = data.get("status", "UNKNOWN_ERROR")
        if status == "ZERO_RESULTS":
            return None
        if status != "OK":
            raise GoogleAPIError("Geocoding API", _GEOCODE_STATUS_HTTP.get(status, 500), status,
                                 data.get("error_message", ""))
        address = parse_geocode_result(data["results"][0])
        self._cache.set(cache_key, address)
        return address

    # --- Places API (New) ---

    async def search_nearby(self, lat: float, lng: float, radius: int, types: Iterable[str], *,
                            rank: str = "DISTANCE", with_rating: bool = False,
                            max_results: int = 20) -> list[Place]:
        """Nearby Search (New): до 20 місць заданих типів у колі радіусом `radius` м."""
        types = sorted(set(types))
        cache_key = ("nearby", round(lat, 5), round(lng, 5), radius, tuple(types), rank,
                     with_rating, max_results)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        body = {
            "includedTypes": types,
            "maxResultCount": max(1, min(max_results, 20)),
            "rankPreference": rank,
            "languageCode": self._language,
            "regionCode": self._region,
            "locationRestriction": {"circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": float(radius),
            }},
        }
        headers = {"X-Goog-Api-Key": self._key,
                   "X-Goog-FieldMask": RATED_FIELDS if with_rating else BASIC_FIELDS}
        data = await self._request("Places API (New)", "POST", PLACES_NEARBY_URL,
                                   json=body, headers=headers)
        places = [p for p in (Place.from_api(x) for x in data.get("places") or []) if p]
        self._cache.set(cache_key, places)
        return places

    # --- Air Quality API ---

    async def air_quality(self, lat: float, lng: float) -> AirQuality:
        cache_key = ("air", round(lat, 3), round(lng, 3))
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        body = {
            "location": {"latitude": lat, "longitude": lng},
            "universalAqi": True,
            "extraComputations": ["HEALTH_RECOMMENDATIONS", "DOMINANT_POLLUTANT_CONCENTRATION",
                                  "POLLUTANT_CONCENTRATION"],
            "languageCode": self._language,
        }
        data = await self._request("Air Quality API", "POST", AIR_QUALITY_URL, json=body,
                                   headers={"X-Goog-Api-Key": self._key})
        result = parse_air_quality(data)
        self._cache.set(cache_key, result)
        return result

    # --- службове ---

    async def _request(self, api: str, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = await self._http.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            log.warning("%s network error: %s", api, exc)
            raise GoogleAPIError(api, 0, "NETWORK_ERROR", str(exc)) from exc
        if response.status_code >= 400:
            status, message = "UNKNOWN", response.text[:300]
            try:
                err = response.json().get("error", {})
                status, message = err.get("status", status), err.get("message", message)
            except ValueError:
                pass
            log.error("%s -> %s %s: %s", api, response.status_code, status, message)
            raise GoogleAPIError(api, response.status_code, status, message)
        return response.json()
