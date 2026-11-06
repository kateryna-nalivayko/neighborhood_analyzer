import json

import httpx
import pytest

from bot.google_client import (AIR_QUALITY_URL, BASIC_FIELDS, GEOCODE_URL, PLACES_NEARBY_URL,
                               RATED_FIELDS, GoogleAPIError, GoogleMapsClient)

GEOCODE_OK = {
    "status": "OK",
    "results": [{
        "formatted_address": "вулиця Хрещатик, 22, Київ, Україна, 02000",
        "geometry": {"location": {"lat": 50.4475, "lng": 30.5236}},
        "address_components": [
            {"long_name": "22", "types": ["street_number"]},
            {"long_name": "вулиця Хрещатик", "types": ["route"]},
            {"long_name": "Печерський район", "types": ["political", "sublocality", "sublocality_level_1"]},
            {"long_name": "Київ", "types": ["locality", "political"]},
            {"long_name": "Україна", "types": ["country", "political"]},
        ],
    }],
}

AIR_OK = {
    "indexes": [{"code": "uaqi", "displayName": "Universal AQI", "aqi": 79,
                 "category": "Хороша якість повітря", "dominantPollutant": "pm25"}],
    "pollutants": [
        {"code": "no2", "displayName": "NO2", "concentration": {"value": 6.77, "units": "PARTS_PER_BILLION"}},
        {"code": "pm25", "displayName": "PM2.5", "concentration": {"value": 13.41, "units": "MICROGRAMS_PER_CUBIC_METER"}},
    ],
    "healthRecommendations": {"generalPopulation": "Гарний день для прогулянки."},
}


def make_client(handler) -> GoogleMapsClient:
    return GoogleMapsClient("TEST_KEY", http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


@pytest.mark.asyncio
async def test_geocode_parses_city_and_district():
    seen = {}

    def handler(request):
        seen["url"] = request.url
        return httpx.Response(200, json=GEOCODE_OK)

    address = await make_client(handler).geocode("  Хрещатик 22, Київ ")
    assert str(seen["url"]).startswith(GEOCODE_URL)
    assert seen["url"].params["address"] == "Хрещатик 22, Київ"
    assert seen["url"].params["key"] == "TEST_KEY"
    assert seen["url"].params["language"] == "uk"
    assert address.city == "Київ"
    assert address.district == "Печерський район"
    assert address.lat == pytest.approx(50.4475)


@pytest.mark.asyncio
async def test_geocode_zero_results_and_denied():
    client = make_client(lambda r: httpx.Response(200, json={"status": "ZERO_RESULTS", "results": []}))
    assert await client.geocode("ааааа") is None

    denied = make_client(lambda r: httpx.Response(200, json={
        "status": "REQUEST_DENIED", "error_message": "This API project is not authorized"}))
    with pytest.raises(GoogleAPIError) as info:
        await denied.geocode("Київ")
    assert info.value.http_status == 403
    assert "Geocoding API" in info.value.user_message


@pytest.mark.asyncio
async def test_reverse_geocode_uses_latlng():
    seen = {}

    def handler(request):
        seen["params"] = request.url.params
        return httpx.Response(200, json=GEOCODE_OK)

    address = await make_client(handler).reverse_geocode(50.4475, 30.5236)
    assert seen["params"]["latlng"] == "50.4475,30.5236"
    assert address.city == "Київ"


@pytest.mark.asyncio
async def test_nearby_request_field_mask_rank_and_cache():
    calls = []

    def handler(request):
        calls.append((str(request.url), request.headers["X-Goog-FieldMask"], json.loads(request.content)))
        return httpx.Response(200, json={"places": [
            {"displayName": {"text": "АТБ"}, "location": {"latitude": 50.45, "longitude": 30.52},
             "googleMapsUri": "https://maps.google.com/?cid=1", "rating": 4.4, "userRatingCount": 120},
            {"displayName": {"text": "без координат"}},
        ]})

    client = make_client(handler)
    a = await client.search_nearby(50.45, 30.52, 1000, ["supermarket"], with_rating=True)
    b = await client.search_nearby(50.45, 30.52, 1000, ["supermarket"], with_rating=True)
    await client.search_nearby(50.45, 30.52, 1000, ["bus_stop"], rank="DISTANCE", max_results=15)

    assert len(calls) == 2, "повторний запит має братися з кешу"
    assert calls[0][0] == PLACES_NEARBY_URL
    assert calls[0][1] == RATED_FIELDS and calls[1][1] == BASIC_FIELDS
    assert calls[0][2]["rankPreference"] == "DISTANCE"
    assert calls[0][2]["locationRestriction"]["circle"]["radius"] == 1000.0
    assert calls[1][2]["maxResultCount"] == 15
    assert a == b and len(a) == 1 and a[0].rating == 4.4


@pytest.mark.asyncio
async def test_air_quality_request_and_parse():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("X-Goog-Api-Key")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=AIR_OK)

    aq = await make_client(handler).air_quality(50.45, 30.52)
    assert seen["url"] == AIR_QUALITY_URL and seen["key"] == "TEST_KEY"
    assert "POLLUTANT_CONCENTRATION" in seen["body"]["extraComputations"]
    assert seen["body"]["languageCode"] == "uk"
    assert aq.aqi == 79 and aq.dominant == "PM2.5"
    assert [p.name for p in aq.pollutants] == ["NO2", "PM2.5"]
    assert aq.recommendation.startswith("Гарний")


@pytest.mark.asyncio
async def test_http_error_and_network_error():
    forbidden = make_client(lambda r: httpx.Response(403, json={"error": {
        "status": "PERMISSION_DENIED", "message": "Places API (New) has not been used..."}}))
    with pytest.raises(GoogleAPIError) as info:
        await forbidden.search_nearby(1, 2, 500, ["park"])
    assert info.value.status == "PERMISSION_DENIED"
    assert "Places API (New)" in info.value.user_message

    def boom(request):
        raise httpx.ConnectError("boom")

    with pytest.raises(GoogleAPIError) as info:
        await make_client(boom).air_quality(1, 2)
    assert info.value.http_status == 0
