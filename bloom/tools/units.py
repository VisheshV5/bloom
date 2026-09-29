"""Unit conversions for mass, length, volume, and temperature."""

from __future__ import annotations

_FACTORS = {
    # mass -> grams
    "g": ("mass", 1.0), "kg": ("mass", 1000.0), "lb": ("mass", 453.59237), "oz": ("mass", 28.349523125),
    # length -> metres
    "mm": ("length", 0.001), "cm": ("length", 0.01), "m": ("length", 1.0), "km": ("length", 1000.0),
    "in": ("length", 0.0254), "ft": ("length", 0.3048), "yd": ("length", 0.9144), "mi": ("length", 1609.344),
    # volume -> millilitres (US customary)
    "ml": ("volume", 1.0), "l": ("volume", 1000.0), "floz": ("volume", 29.5735295625),
    "cup": ("volume", 236.5882365), "gal": ("volume", 3785.411784),
}
_ALIASES = {
    "gram": "g", "grams": "g", "kilogram": "kg", "kilograms": "kg", "kgs": "kg",
    "pound": "lb", "pounds": "lb", "lbs": "lb", "ounce": "oz", "ounces": "oz",
    "meter": "m", "meters": "m", "metre": "m", "metres": "m", "kilometer": "km", "kilometers": "km",
    "centimeter": "cm", "centimeters": "cm", "millimeter": "mm", "inch": "in", "inches": "in",
    "foot": "ft", "feet": "ft", "yard": "yd", "yards": "yd", "mile": "mi", "miles": "mi",
    "liter": "l", "liters": "l", "litre": "l", "litres": "l", "milliliter": "ml", "milliliters": "ml",
    "fl oz": "floz", "fluid ounce": "floz", "fluid ounces": "floz", "cups": "cup",
    "gallon": "gal", "gallons": "gal",
    "c": "c", "celsius": "c", "f": "f", "fahrenheit": "f", "k": "k", "kelvin": "k",
}
_TEMPS = {"c", "f", "k"}


def _norm(unit: str) -> str:
    u = unit.strip().lower().replace("°", "")
    return _ALIASES.get(u, u)


def _to_c(v: float, u: str) -> float:
    return v if u == "c" else (v - 32) * 5 / 9 if u == "f" else v - 273.15


def _from_c(v: float, u: str) -> float:
    return v if u == "c" else v * 9 / 5 + 32 if u == "f" else v + 273.15


def convert(value: float, from_unit: str, to_unit: str) -> float:
    a, b = _norm(from_unit), _norm(to_unit)
    if a in _TEMPS or b in _TEMPS:
        if not (a in _TEMPS and b in _TEMPS):
            raise ValueError(f"Cannot convert {from_unit} to {to_unit}")
        return _from_c(_to_c(float(value), a), b)
    if a not in _FACTORS or b not in _FACTORS:
        raise ValueError(f"Unknown unit: {from_unit if a not in _FACTORS else to_unit}")
    (da, fa), (db, fb) = _FACTORS[a], _FACTORS[b]
    if da != db:
        raise ValueError(f"Cannot convert {da} to {db}")
    return float(value) * fa / fb
