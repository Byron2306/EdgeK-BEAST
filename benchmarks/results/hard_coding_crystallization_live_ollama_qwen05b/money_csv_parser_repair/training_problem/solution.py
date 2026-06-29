import csv
from decimal import Decimal

def parse_money_rows(text):
    reader = csv.DictReader(line for line in text.splitlines() if line.strip())
    if not reader.fieldnames or 'sku' not in reader.fieldnames or 'price' not in reader.fieldnames:
        raise ValueError('csv must include sku and price columns')
    rows = []
    for row in reader:
        sku = str(row.get('sku') or '').strip()
        raw_price = str(row.get('price') or '').strip().replace('$', '').replace(',', '')
        try:
            price = Decimal(raw_price).quantize(Decimal('0.01'))
        except Exception as exc:
            raise ValueError('invalid money value') from exc
        rows.append((sku, price))
    return rows

