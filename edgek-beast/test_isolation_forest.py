import random

from app.kernel.isolation_forest import IsolationForest


def test_isolation_forest_flags_planted_outliers():
    random.seed(11)
    rows = [
        {
            "temperature": 70 + random.random(),
            "vibration": 1.0 + random.random() * 0.1,
            "pressure": 12 + random.random() * 0.2,
        }
        for _ in range(120)
    ]
    outliers = [
        {"temperature": 130.0, "vibration": 9.5, "pressure": 4.0},
        {"temperature": 20.0, "vibration": 8.8, "pressure": 30.0},
    ]
    all_rows = rows + outliers

    model = IsolationForest(n_trees=80, sample_size=64, contamination=0.03, random_state=5)
    model.fit(all_rows, features=["temperature", "vibration", "pressure"])
    predictions = model.predict(outliers)
    normal_predictions = model.predict(rows[:10])

    assert all(item["is_outlier"] for item in predictions)
    assert sum(item["is_outlier"] for item in normal_predictions) <= 2
    assert model.state()["features"] == ["temperature", "vibration", "pressure"]
