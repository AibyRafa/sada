"""Small logistic regression (numpy only) with standardization, saved as JSON.

Kept dependency-free so the trained models load anywhere (no pickle, no sklearn needed).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np


class LogReg:
    def __init__(self, l2: float = 1.0):
        self.l2 = l2
        self.mean = self.std = self.w = None
        self.b = 0.0
        self.names: list[str] = []

    def fit(self, X: np.ndarray, y: np.ndarray, names: list[str] | None = None, iters: int = 50) -> "LogReg":
        X = np.asarray(X, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64)
        self.mean, self.std = X.mean(axis=0), X.std(axis=0) + 1e-9
        Z = (X - self.mean) / self.std
        n, d = Z.shape
        # balanced class weights: few positives must still count
        pos = max(1.0, y.sum())
        neg = max(1.0, n - y.sum())
        sw = np.where(y > 0.5, n / (2 * pos), n / (2 * neg))
        w, b = np.zeros(d), 0.0
        for _ in range(iters):  # Newton / IRLS
            p = 1 / (1 + np.exp(-(Z @ w + b)))
            g_w = Z.T @ (sw * (p - y)) + self.l2 * w
            g_b = float(np.sum(sw * (p - y)))
            r = sw * p * (1 - p)
            H = (Z.T * r) @ Z + self.l2 * np.eye(d)
            H_b = float(r.sum()) + 1e-9
            H_wb = Z.T @ r
            # full Newton step on [w, b]
            Hfull = np.block([[H, H_wb[:, None]], [H_wb[None, :], np.array([[H_b]])]])
            step = np.linalg.solve(Hfull + 1e-9 * np.eye(d + 1), np.concatenate([g_w, [g_b]]))
            w, b = w - step[:d], b - step[d]
            if np.max(np.abs(step)) < 1e-6:
                break
        self.w, self.b = w, float(b)
        self.names = list(names or [f"f{i}" for i in range(d)])
        return self

    def proba(self, X: np.ndarray) -> np.ndarray:
        Z = (np.atleast_2d(np.asarray(X, dtype=np.float64)) - self.mean) / self.std
        return 1 / (1 + np.exp(-(Z @ self.w + self.b)))

    def save(self, path: str | Path, extra: dict | None = None) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps({
            "l2": self.l2, "mean": self.mean.tolist(), "std": self.std.tolist(), "w": self.w.tolist(),
            "b": self.b, "names": self.names, **(extra or {})}, indent=1), encoding="utf-8")

    @staticmethod
    def load(path: str | Path) -> tuple["LogReg", dict]:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        m = LogReg(d.get("l2", 1.0))
        m.mean, m.std, m.w = (np.array(d[k]) for k in ("mean", "std", "w"))
        m.b, m.names = float(d["b"]), d.get("names", [])
        return m, d
