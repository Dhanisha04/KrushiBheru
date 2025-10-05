import json
import numpy as np
from typing import Dict, List, Tuple
from geopy.geocoders import Nominatim
import os

geolocator = Nominatim(user_agent="agro_monitor")

def validate_geojson(boundary: str) -> bool:
    """Validate GeoJSON boundary string."""
    try:
        data = json.loads(boundary)
        if not all(k in data for k in ('type', 'coordinates')) or data['type'] != 'Polygon':
            return False
        coords = data['coordinates'][0]
        return all(len(c) == 2 for c in coords) and len(coords) >= 4 and coords[0] == coords[-1]
    except (json.JSONDecodeError, KeyError):
        return False

def convert_coords(boundary: str) -> List[Tuple[float, float]]:
    """Convert GeoJSON coordinates to [lat, lon] list."""
    data = json.loads(boundary)
    return [[c[1], c[0]] for c in data['coordinates'][0]]  # Flip to [lat, lon]

def ensure_dir(directory: str) -> None:
    """Create directory if it doesn’t exist."""
    os.makedirs(directory, exist_ok=True)

def calculate_centroid(coords: List[Tuple[float, float]]) -> Tuple[float, float]:
    """Calculate centroid of a polygon."""
    n = len(coords) - 1  # Exclude repeated point
    cx = cy = area = 0
    for i in range(n):
        j = (i + 1) % n
        factor = coords[i][0] * coords[j][1] - coords[j][0] * coords[i][1]
        cx += (coords[i][0] + coords[j][0]) * factor
        cy += (coords[i][1] + coords[j][1]) * factor
        area += factor
    area *= 0.5
    factor = 1 / (6 * area) if area else 1
    return (cx * factor, cy * factor)

def calculate_area(coords: List[Tuple[float, float]]) -> float:
    """Calculate area of a polygon in hectares."""
    area = 0
    n = len(coords) - 1
    for i in range(n):
        j = (i + 1) % n
        area += coords[i][0] * coords[j][1]
        area -= coords[j][0] * coords[i][1]
    area = abs(area) / 2
    return area * 111139 ** 2 / 10000  # Convert to hectares

def calculate_perimeter(coords: List[Tuple[float, float]]) -> float:
    """Calculate perimeter of a polygon in kilometers."""
    perimeter = 0
    n = len(coords) - 1
    for i in range(n):
        j = (i + 1) % n
        dx = coords[j][0] - coords[i][0]
        dy = coords[j][1] - coords[i][1]
        perimeter += np.sqrt(dx**2 + dy**2) * 111
    return perimeter

def normalize_ndvi(ndvi: float) -> str:
    """Normalize NDVI to color code (red, yellow, green)."""
    if ndvi < 0.4:
        return 'red'
    elif ndvi < 0.6:
        return 'yellow'
    return 'green'

def get_state_from_coords(lat: float, lon: float) -> str:
    """Get state from coordinates using geopy."""
    try:
        location = geolocator.reverse((lat, lon), exactly_one=True, timeout=10)
        return location.raw['address'].get('state', 'Unknown')
    except:
        return 'Unknown'

def get_district_from_coords(lat: float, lon: float) -> str:
    """Get district from coordinates using geopy."""
    try:
        location = geolocator.reverse((lat, lon), exactly_one=True, timeout=10)
        return location.raw['address'].get('county', 'Unknown')
    except:
        return 'Unknown'