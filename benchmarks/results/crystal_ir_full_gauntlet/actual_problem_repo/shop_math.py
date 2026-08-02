def calculate_discounted_total(price, percent):
    try:
        numeric_price = float(price)
        numeric_percent = float(percent)
    except (TypeError, ValueError):
        raise ValueError("price and percent must be numeric")
    clamped_percent = max(0.0, min(100.0, numeric_percent))
    discounted = numeric_price * (1.0 - clamped_percent / 100.0)
    return round(discounted, 2)
