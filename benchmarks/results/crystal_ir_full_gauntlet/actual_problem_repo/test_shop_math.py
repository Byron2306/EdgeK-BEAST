import pytest
from shop_math import calculate_discounted_total

def test_discount_regular_case():
    assert calculate_discounted_total(100, 25) == 75.00

def test_discount_numeric_strings_and_rounding():
    assert calculate_discounted_total('19.99', '10') == 17.99

def test_discount_clamps_high_and_low():
    assert calculate_discounted_total(50, 150) == 0.00
    assert calculate_discounted_total(50, -20) == 50.00

def test_discount_rejects_bad_input():
    with pytest.raises(ValueError):
        calculate_discounted_total('bad', 10)
