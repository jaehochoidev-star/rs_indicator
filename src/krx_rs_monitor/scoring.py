from dataclasses import dataclass
import math

import numpy as np
import pandas as pd

from .models import DataError, MarketData

PERIODS = (1, 5, 20, 60)


@dataclass(frozen=True)
class ScreenConfig:
    weights: tuple[float, ...] = (10, 30, 40, 20)
    avg_turnover_min: float = 5_000_000_000
    turnover_min: float = 10_000_000_000
    rs20_min: float = 90
    rs5_min: float = 90
    top: int = 20

    def __post_init__(self):
        if len(self.weights) != 4 or any(not math.isfinite(x) or x < 0 for x in self.weights):
            raise ValueError("Weights must be four finite nonnegative numbers.")
        if sum(self.weights) <= 0 or not math.isfinite(sum(self.weights)):
            raise ValueError("Weight sum must be positive and finite.")
        if any(not math.isfinite(x) or x < 0 for x in (self.avg_turnover_min, self.turnover_min)):
            raise ValueError("Turnover thresholds must be finite and nonnegative.")
        if not 0 <= self.rs20_min <= 100 or not 0 <= self.rs5_min <= 100:
            raise ValueError("RS thresholds must be within 0..100.")
        if self.top < 1:
            raise ValueError("top must be positive.")


def score(data: MarketData, config: ScreenConfig) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    sessions = data.sessions
    if len(sessions) < 61 or sessions.has_duplicates or not sessions.is_monotonic_increasing:
        raise DataError("At least 61 unique, ascending trading sessions are required.")
    if sessions[-1].date() != data.as_of:
        raise DataError("Latest session does not match as_of.")
    universe = data.universe
    if universe.empty or universe.index.has_duplicates:
        raise DataError("Universe is empty or contains duplicate tickers.")
    if not {"KOSPI", "KOSDAQ"}.issubset(set(universe.market)):
        raise DataError("Both KOSPI and KOSDAQ must be present.")
    if not set(universe.market).issubset({"KOSPI", "KOSDAQ"}):
        raise DataError("Unexpected market in universe.")
    for matrix in (data.closes, data.turnover):
        if matrix.index.has_duplicates or matrix.columns.has_duplicates:
            raise DataError("Duplicate dates or tickers in market data.")
        if not set(universe.index).issubset(matrix.columns):
            raise DataError("Provider omitted universe tickers.")
    closes = data.closes.reindex(index=sessions[-61:], columns=universe.index)
    value = data.turnover.reindex(index=sessions[-20:], columns=universe.index)
    # Missing prices are never forward-filled; use a common eligible universe.
    eligible = (closes.notna() & np.isfinite(closes) & (closes > 0)).all()
    result = universe.loc[eligible].copy()
    if result.empty:
        raise DataError("No tickers have 61 valid adjusted closes.")
    valid_value = value.loc[:, eligible]
    if valid_value.isna().any().any() or not np.isfinite(valid_value.to_numpy()).all() or (valid_value < 0).any().any():
        raise DataError("Missing, negative or invalid turnover data in 20-session window.")
    prices = closes.loc[:, eligible]
    result["close_adjusted"] = prices.iloc[-1]
    for period in PERIODS:
        returns = prices.iloc[-1] / prices.iloc[-period - 1] - 1
        result[f"return{period}"] = returns * 100
        result[f"RS{period}"] = returns.rank(method="average", pct=True) * 100
    result["RS_Score"] = sum(result[f"RS{p}"] * w for p, w in zip(PERIODS, config.weights)) / sum(config.weights)
    result["turnover_20d_avg"] = value.mean()
    result["turnover_today"] = value.iloc[-1]
    result["passes"] = (
        (result.turnover_20d_avg >= config.avg_turnover_min)
        & (result.turnover_today >= config.turnover_min)
        & (result.RS20 >= config.rs20_min)
        & (result.RS5 >= config.rs5_min)
    )
    result.index.name = "ticker"
    result = result.reset_index().sort_values(
        ["RS_Score", "RS20", "RS5", "turnover_today", "ticker"],
        ascending=[False, False, False, False, True],
    ).reset_index(drop=True)
    top = result.loc[result.passes].head(config.top).copy()
    stats = {"universe": len(universe), "eligible": len(result),
             "excluded_short_or_invalid_history": int((~eligible).sum()),
             "matched": int(result.passes.sum()), "displayed": len(top)}
    return result, top, stats
