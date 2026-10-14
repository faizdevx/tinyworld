"""Calendar time helpers. Simulation time is a naive ``datetime``."""

import re
from datetime import datetime, timedelta

_STEP = re.compile(r"^\s*(\d+)\s*(m|min|h|d|w|mo|y)\s*$")
_MINUTES = {
    "m": 1,
    "min": 1,
    "h": 60,
    "d": 60 * 24,
    "w": 60 * 24 * 7,
    "mo": 60 * 24 * 30,
    "y": 60 * 24 * 365,
}


def parse_step(text: str) -> int:
    """Parse a step such as ``15m``, ``6h``, ``3d``, ``2mo`` or ``20y`` into minutes."""
    match = _STEP.match(text)
    if match is None:
        raise ValueError(f"invalid step: {text!r}")
    return int(match[1]) * _MINUTES[match[2]]


def add_minutes(moment: datetime, minutes: int) -> datetime:
    if minutes < 0:
        raise ValueError("time cannot move backwards")
    return moment + timedelta(minutes=minutes)


def hours_between(earlier: datetime, later: datetime) -> float:
    return (later - earlier).total_seconds() / 3600.0


def birth_date_for(now: datetime, age: int) -> str:
    """The birthday that makes someone exactly ``age`` today."""
    year = max(1, now.year - age)
    try:
        return now.date().replace(year=year).isoformat()
    except ValueError:  # 29 February in a year without one
        return now.date().replace(year=year, day=28).isoformat()


def describe(moment: datetime) -> str:
    return moment.strftime("%A %d %B %Y, %H:%M")
