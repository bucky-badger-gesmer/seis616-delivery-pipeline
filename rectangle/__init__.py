"""Rectangle geometry: the app built and tested by the delivery pipeline."""

import math


def area(length: float, width: float) -> float:
    _check(length, width)
    return length * width


def perimeter(length: float, width: float) -> float:
    _check(length, width)
    return 2 * (length + width)


def diagonal(length: float, width: float) -> float:
    _check(length, width)
    return math.hypot(length, width)


def _check(length: float, width: float) -> None:
    if length < 0 or width < 0:
        raise ValueError('length and width must be non-negative')
