"""
Pure-Python deterministic Isolation Forest for edge outlier filtering.
"""

import math
import random
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Sequence


@dataclass
class IsolationForestModelState:
    n_trees: int
    sample_size: int
    contamination: float
    random_state: int
    threshold: float
    features: List[str]


class _Node:
    def __init__(
        self,
        *,
        size: int,
        depth: int,
        feature: Optional[int] = None,
        split: Optional[float] = None,
        left: Optional["_Node"] = None,
        right: Optional["_Node"] = None,
    ):
        self.size = size
        self.depth = depth
        self.feature = feature
        self.split = split
        self.left = left
        self.right = right

    @property
    def external(self) -> bool:
        return self.left is None or self.right is None


class IsolationForest:
    """Small production-safe Isolation Forest without sklearn dependency."""

    def __init__(
        self,
        n_trees: int = 100,
        sample_size: int = 256,
        contamination: float = 0.01,
        random_state: int = 1337,
        max_depth: Optional[int] = None,
    ):
        if n_trees <= 0:
            raise ValueError("n_trees must be positive")
        if sample_size <= 1:
            raise ValueError("sample_size must be > 1")
        if not 0 < contamination < 0.5:
            raise ValueError("contamination must be between 0 and 0.5")
        self.n_trees = n_trees
        self.sample_size = sample_size
        self.contamination = contamination
        self.random_state = random_state
        self.max_depth = max_depth
        self.features: List[str] = []
        self._trees: List[_Node] = []
        self.threshold: float = 0.0
        self._fit_sample_size: int = sample_size

    def fit(self, rows: Sequence[Dict[str, Any]] | Sequence[Sequence[float]], features: Optional[List[str]] = None) -> "IsolationForest":
        matrix, names = self._matrix(rows, features)
        if not matrix:
            raise ValueError("rows must not be empty")
        self.features = names
        rng = random.Random(self.random_state)
        sample_size = min(self.sample_size, len(matrix))
        self._fit_sample_size = sample_size
        limit = self.max_depth if self.max_depth is not None else math.ceil(math.log2(sample_size))
        self._trees = []
        for _ in range(self.n_trees):
            sample = rng.sample(matrix, sample_size) if len(matrix) > sample_size else list(matrix)
            self._trees.append(self._build(sample, 0, limit, rng))
        scores = self.score_matrix(matrix)
        sorted_scores = sorted(scores, reverse=True)
        index = min(len(sorted_scores) - 1, max(0, int(math.ceil(len(sorted_scores) * self.contamination)) - 1))
        self.threshold = sorted_scores[index]
        return self

    def score_samples(self, rows: Sequence[Dict[str, Any]] | Sequence[Sequence[float]]) -> List[float]:
        matrix, _ = self._matrix(rows, self.features or None)
        return self.score_matrix(matrix)

    def predict(self, rows: Sequence[Dict[str, Any]] | Sequence[Sequence[float]]) -> List[Dict[str, Any]]:
        scores = self.score_samples(rows)
        return [
            {
                "score": score,
                "is_outlier": score >= self.threshold,
                "threshold": self.threshold,
            }
            for score in scores
        ]

    def state(self) -> Dict[str, Any]:
        return asdict(IsolationForestModelState(
            n_trees=self.n_trees,
            sample_size=self.sample_size,
            contamination=self.contamination,
            random_state=self.random_state,
            threshold=self.threshold,
            features=self.features,
        ))

    def score_matrix(self, matrix: List[List[float]]) -> List[float]:
        if not self._trees:
            raise ValueError("model is not fitted")
        c_n = self._c(max(2, self._fit_sample_size))
        scores = []
        for row in matrix:
            avg_path = sum(self._path_length(row, tree) for tree in self._trees) / len(self._trees)
            scores.append(2 ** (-avg_path / c_n))
        return scores

    def _build(self, rows: List[List[float]], depth: int, max_depth: int, rng: random.Random) -> _Node:
        if depth >= max_depth or len(rows) <= 1 or self._all_equal(rows):
            return _Node(size=len(rows), depth=depth)
        feature = rng.randrange(len(rows[0]))
        values = [row[feature] for row in rows]
        low, high = min(values), max(values)
        if low == high:
            return _Node(size=len(rows), depth=depth)
        split = rng.uniform(low, high)
        left_rows = [row for row in rows if row[feature] < split]
        right_rows = [row for row in rows if row[feature] >= split]
        if not left_rows or not right_rows:
            return _Node(size=len(rows), depth=depth)
        return _Node(
            size=len(rows),
            depth=depth,
            feature=feature,
            split=split,
            left=self._build(left_rows, depth + 1, max_depth, rng),
            right=self._build(right_rows, depth + 1, max_depth, rng),
        )

    def _path_length(self, row: List[float], node: _Node) -> float:
        if node.external:
            return node.depth + self._c(node.size)
        if row[node.feature] < node.split:
            return self._path_length(row, node.left)
        return self._path_length(row, node.right)

    def _matrix(self, rows: Sequence[Dict[str, Any]] | Sequence[Sequence[float]], features: Optional[List[str]]) -> tuple[List[List[float]], List[str]]:
        if not rows:
            return [], features or []
        first = rows[0]
        if isinstance(first, dict):
            names = features or [key for key, value in first.items() if isinstance(value, (int, float))]
            return [[float(row[name]) for name in names] for row in rows], names
        names = features or [f"f{i}" for i in range(len(first))]
        return [[float(value) for value in row] for row in rows], names

    def _all_equal(self, rows: List[List[float]]) -> bool:
        first = rows[0]
        return all(row == first for row in rows[1:])

    def _c(self, n: int) -> float:
        if n <= 1:
            return 0.0
        if n == 2:
            return 1.0
        return 2.0 * (math.log(n - 1) + 0.5772156649) - (2.0 * (n - 1) / n)
