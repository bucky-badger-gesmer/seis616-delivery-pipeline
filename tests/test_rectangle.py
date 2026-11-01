import pytest

from rectangle import area, diagonal, perimeter


def test_area():
    assert area(3, 4) == 12


def test_perimeter():
    assert perimeter(3, 4) == 14


def test_diagonal():
    assert diagonal(3, 4) == 5


def test_zero_sides():
    assert area(0, 5) == 0
    assert perimeter(0, 0) == 0


def test_negative_side_rejected():
    with pytest.raises(ValueError):
        area(-1, 2)
    with pytest.raises(ValueError):
        perimeter(1, -2)
