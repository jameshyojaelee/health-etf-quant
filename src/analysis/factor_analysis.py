"""Factor regression analysis and reporting utilities."""

from __future__ import annotations

from typing import Any, Dict, Tuple

import pandas as pd
import statsmodels.api as sm


def align_strategy_and_factors(
    strategy_returns_daily: pd.Series,
    ff_factors_monthly: pd.DataFrame,
) -> Tuple[pd.Series, pd.DataFrame]:
    """Convert daily strategy returns to monthly and align with Fama-French factors."""
    strat_monthly = strategy_returns_daily.resample("ME").apply(lambda r: (1 + r).prod() - 1)
    # RF is usually in percent; convert to decimal if values look like percent
    factors = ff_factors_monthly.copy()
    if factors["RF"].abs().max() > 0.5:  # heuristic: >50bps likely percentage
        factors = factors / 100.0
    aligned = strat_monthly.to_frame("strategy").join(factors, how="inner")
    strategy_excess = aligned["strategy"] - aligned["RF"]
    factor_cols = ["MKT_RF", "SMB", "HML", "RMW", "CMA"]
    ff_aligned = aligned[factor_cols]
    return strategy_excess, ff_aligned


def run_ff_regression(
    strategy_excess: pd.Series,
    ff_factors: pd.DataFrame,
) -> Dict[str, Any]:
    """Run OLS regression of strategy excess returns on FF factors."""
    # Drop any rows with missing values across regressors/target.
    data = pd.concat([strategy_excess, ff_factors], axis=1).dropna()
    y = data.iloc[:, 0]
    X = sm.add_constant(data.iloc[:, 1:], has_constant="add")
    model = sm.OLS(y, X).fit()

    alpha_monthly = model.params["const"]
    alpha_annual = alpha_monthly * 12
    betas = model.params.drop("const").to_dict()
    betas_t = model.tvalues.drop("const").to_dict()

    return {
        "alpha_annual": float(alpha_annual),
        "alpha_tstat": float(model.tvalues["const"]),
        "betas": {k: float(v) for k, v in betas.items()},
        "betas_tstat": {k: float(v) for k, v in betas_t.items()},
        "r2": float(model.rsquared),
        "n_obs": int(model.nobs),
    }
