"""Geospatial helpers for validating if a coordinate is inside India."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Iterable


_INDIA_BOUNDARY_FILE = Path(__file__).resolve().parent / "data" / "india_boundary_110m.geojson"
_INDIA_FALLBACK_BOUNDS = {
    "lat_min": 6.4627,
    "lat_max": 37.0841,
    "lng_min": 68.1097,
    "lng_max": 97.3956,
}


def _point_in_ring(lng: float, lat: float, ring: list[list[float]]) -> bool:
    """Ray-casting point-in-polygon test for one linear ring."""
    if len(ring) < 3:
        return False

    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        # Standard ray-casting with tiny epsilon to avoid divide-by-zero.
        intersects = ((yi > lat) != (yj > lat)) and (
            lng < (xj - xi) * (lat - yi) / ((yj - yi) if (yj - yi) else 1e-12) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def _point_in_polygon(lng: float, lat: float, polygon: list[list[list[float]]]) -> bool:
    if not polygon:
        return False
    if not _point_in_ring(lng, lat, polygon[0]):
        return False
    # If point lies inside any hole ring, treat as outside.
    for hole_ring in polygon[1:]:
        if _point_in_ring(lng, lat, hole_ring):
            return False
    return True


@lru_cache(maxsize=1)
def _load_india_geometry():
    try:
        payload = json.loads(_INDIA_BOUNDARY_FILE.read_text(encoding="utf-8"))
        geom = payload.get("geometry") or {}
        geom_type = geom.get("type")
        coords = geom.get("coordinates") or []
        if geom_type == "Polygon":
            return [coords]
        if geom_type == "MultiPolygon":
            return coords
    except Exception:
        return []
    return []


def _iter_ring_points(polygons: Iterable[list[list[list[float]]]]):
    for polygon in polygons:
        for ring in polygon:
            for point in ring:
                yield point


@lru_cache(maxsize=1)
def _india_bbox():
    polygons = _load_india_geometry()
    if not polygons:
        return (
            _INDIA_FALLBACK_BOUNDS["lng_min"],
            _INDIA_FALLBACK_BOUNDS["lat_min"],
            _INDIA_FALLBACK_BOUNDS["lng_max"],
            _INDIA_FALLBACK_BOUNDS["lat_max"],
        )
    xs = []
    ys = []
    for p in _iter_ring_points(polygons):
        xs.append(float(p[0]))
        ys.append(float(p[1]))
    if not xs:
        return (
            _INDIA_FALLBACK_BOUNDS["lng_min"],
            _INDIA_FALLBACK_BOUNDS["lat_min"],
            _INDIA_FALLBACK_BOUNDS["lng_max"],
            _INDIA_FALLBACK_BOUNDS["lat_max"],
        )
    return min(xs), min(ys), max(xs), max(ys)


def is_point_in_india(lat: float, lng: float) -> bool:
    """Return True when point is inside India polygon (with safe fallback bounds)."""
    if lat is None or lng is None:
        return False

    try:
        lat = float(lat)
        lng = float(lng)
    except (TypeError, ValueError):
        return False

    min_lng, min_lat, max_lng, max_lat = _india_bbox()
    if not (min_lat <= lat <= max_lat and min_lng <= lng <= max_lng):
        return False

    polygons = _load_india_geometry()
    if not polygons:
        return (
            _INDIA_FALLBACK_BOUNDS["lat_min"] <= lat <= _INDIA_FALLBACK_BOUNDS["lat_max"]
            and _INDIA_FALLBACK_BOUNDS["lng_min"] <= lng <= _INDIA_FALLBACK_BOUNDS["lng_max"]
        )

    for polygon in polygons:
        if _point_in_polygon(lng, lat, polygon):
            return True
    return False
