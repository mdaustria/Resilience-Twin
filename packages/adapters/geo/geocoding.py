"""Bounded Geoapify suggestions; a suggestion never approves a location."""

import json
from dataclasses import dataclass
from math import isfinite
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True, slots=True)
class LocationSuggestion:
    label: str
    longitude: float
    latitude: float
    confidence: float
    source: str = "geoapify-suggestion"


def parse_saved_suggestions(payload: dict[str, Any]) -> tuple[LocationSuggestion, ...]:
    features = payload.get("features")
    if not isinstance(features, list) or len(features) > 10:
        raise ValueError("bounded Geoapify features array required")
    result: list[LocationSuggestion] = []
    for feature in features:
        if not isinstance(feature, dict):
            raise TypeError("invalid suggestion")
        properties = feature.get("properties")
        geometry = feature.get("geometry")
        if (not isinstance(properties, dict) or not isinstance(geometry, dict)
                or geometry.get("type") != "Point"):
            raise TypeError("suggestion metadata missing")
        coordinates = geometry.get("coordinates")
        rank = properties.get("rank")
        confidence = rank.get("confidence") if isinstance(rank, dict) else None
        label = properties.get("formatted")
        if (not isinstance(coordinates, list) or len(coordinates) != 2
                or any(type(value) not in (float, int) for value in coordinates)
                or type(confidence) not in (float, int)
                or not isinstance(label, str) or not label.strip()):
            raise ValueError("invalid suggestion coordinates, rank or label")
        assert isinstance(confidence, (float, int))
        if not isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError("confidence outside supported range")
        lon, lat = coordinates
        if not isfinite(lon) or not isfinite(lat) or not -180 <= lon <= 180 or not -90 <= lat <= 90:
            raise ValueError("suggestion outside coordinate bounds")
        result.append(LocationSuggestion(label.strip(), lon, lat, confidence))
    return tuple(sorted(result, key=lambda item: (-item.confidence, item.label)))


def suggest_locations(text: str, api_key: str) -> tuple[LocationSuggestion, ...]:
    if not api_key or not 3 <= len(text) <= 120:
        raise ValueError("bounded text and configured Geoapify key required")
    query = urlencode({"text": text, "limit": 5, "format": "geojson",
                       "filter": "countrycode:ph"})
    request = Request(f"https://api.geoapify.com/v1/geocode/search?{query}",
                      headers={"x-api-key": api_key, "Accept": "application/geo+json"})
    with urlopen(request, timeout=5) as response:
        raw = response.read(128_001)
    if len(raw) > 128_000:
        raise ValueError("Geoapify response exceeds local limit")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise TypeError("Geoapify response must be an object")
    return parse_saved_suggestions(payload)


__all__ = ("LocationSuggestion", "parse_saved_suggestions", "suggest_locations")
