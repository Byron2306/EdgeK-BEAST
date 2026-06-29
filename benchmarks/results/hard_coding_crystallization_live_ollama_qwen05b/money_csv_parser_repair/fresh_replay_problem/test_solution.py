from decimal import Decimal
import pytest
from solution import parse_money_rows

def test_parses_decimal_money_and_trims_sku():
    text = 'sku,price\n A-1 , $12.30 \nB-2,7\n'
    assert parse_money_rows(text) == [('A-1', Decimal('12.30')), ('B-2', Decimal('7.00'))]

def test_skips_blank_lines():
    text = 'sku,price\n\nA,$1.00\n'
    assert parse_money_rows(text) == [('A', Decimal('1.00'))]

def test_rejects_bad_money():
    with pytest.raises(ValueError):
        parse_money_rows('sku,price\nA,wat\n')

def test_rejects_missing_columns():
    with pytest.raises(ValueError):
        parse_money_rows('sku,cost\nA,1\n')

