# Codex Prompts (Copy/Paste)

Use this file as a queue of **one-prompt-at-a-time** tasks for Codex. Each prompt is designed to be self-contained and to move the project closer to the end-state described in `Plan.md`.

Guidelines to include in every prompt you paste:
- Prefer the smallest coherent change; don’t refactor unrelated areas.
- Don’t add new runtime dependencies without asking first.
- After changes: run `pytest -q` (and any relevant scripts) and report results.

---

## Prompt 01 — Make YAML Settings Fully Drive Scripts

```text
You are working in the repo `healthcare-etf-quant`.

Goal: make `config/settings.yaml` the single source of truth for default parameters used by scripts and results generation.

Tasks:
1) Audit how defaults are currently derived in:
   - `src/config.py`
   - `run_strategies.py`
   - `results/make_results.py`
2) Update `results/make_results.py` so it does NOT hardcode values like `transaction_cost_bps=10.0` and strategy params; instead pull defaults from `src/config.py` (which reads YAML).
3) Add a `--settings` CLI arg to `run_strategies.py` and `results/make_results.py`:
   - If provided, load that YAML file (same schema) and override defaults for that run only.
   - If not provided, fall back to `config/settings.yaml` when present.
4) Keep behavior backward-compatible (scripts should still run with no YAML file on disk).

Acceptance criteria:
- Running `python run_strategies.py` uses YAML defaults when `config/settings.yaml` exists.
- Running `python results/make_results.py` uses YAML defaults and produces the same artifacts.
- `pytest -q` passes.
```

---

## Prompt 02 — Add Macro Data Caching (Offline Reproducibility)

```text
Goal: add a cache layer for macro series so repeated runs don’t re-download data.

Context:
- ETF prices already cache in `src/data/etf_loader.py`.
- Macro loaders in `src/data/macro_loader.py` currently download every time.

Tasks:
1) Implement a small caching mechanism in `src/data/macro_loader.py`:
   - Cache files under `data_raw/` (e.g., `tnx_raw.csv`, `vix_raw.csv`) with a `Date` index and one column of values.
   - Add a `force_refresh: bool = False` parameter to `load_tnx_10y` and `load_vix`.
   - If cache exists and `force_refresh` is False, read from cache and slice to requested `start/end`.
2) Ensure alignment is robust:
   - Always return a `pd.Series` with a `DatetimeIndex`, sorted ascending.
3) Update `run_strategies.py` and `results/make_results.py` to use the cache by default (no forced refresh).

Acceptance criteria:
- First run downloads and writes cache; second run reads cache (no network calls).
- `pytest -q` passes.
```

---

## Prompt 03 — Add FRED-Based Macro Loader (Optional)

```text
Goal: support macro data from FRED (optional) without introducing new dependencies.

Constraints:
- Use the standard library + existing deps only (requests is OK only if already installed; otherwise use urllib).
- Do not break the existing Yahoo Finance proxy behavior.

Tasks:
1) Add `src/data/fred_loader.py` that can fetch a FRED series as a pandas Series:
   - Inputs: `series_id`, `api_key` (optional), `start`, `end`
   - Output: daily (or native) series with datetime index
2) Add one credit-spread proxy series (e.g., BAA-AAA or BAA-10Y) as a helper function.
3) Add a config toggle (YAML) to choose macro source:
   - `macro.source: yahoo|fred` (default yahoo)
   - `macro.fred_api_key: null|<string>`
4) Update `run_strategies.py` regime macro fetch to respect this toggle.

Acceptance criteria:
- With default config, behavior is unchanged (Yahoo proxies).
- With `macro.source=fred` and API key present, FRED series loads and caches (reuse Prompt 02 caching scheme).
- `pytest -q` passes.
```

---

## Prompt 04 — Add Borrow + Financing Costs to Backtest Engine

```text
Goal: make backtests more realistic for long/short portfolios.

Context:
- `src/backtest/engine.py` supports transaction costs via turnover bps.
- It currently has no short borrow cost and cash earns 0%.

Tasks:
1) Extend `run_backtest` with optional parameters:
   - `borrow_cost_annual: float = 0.0` applied to short notional (sum of abs(negative weights))
   - `cash_rate_annual: float = 0.0` applied to residual cash when net exposure < 1 (cash = 1 - sum(weights))
2) Apply these costs/returns consistently with the engine’s timing convention (weights shifted by one day).
3) Add unit tests in `tests/test_engine.py` to verify:
   - Borrow cost reduces returns when weights include shorts
   - Cash rate increases returns when portfolio is partially in cash

Acceptance criteria:
- Existing tests still pass (update expected values as needed).
- New tests cover the new functionality.
- `pytest -q` passes.
```

---

## Prompt 05 — Make Regime LS Strategy Selectable: Simple vs Risk-Balanced

```text
Goal: allow `run_strategies.py` to run either:
- Simple regime LS (constant +/- 1 spread), or
- Risk-balanced + spread-momentum-gated LS (the “advanced” path already supported by `src/signals/ls_biotech_pharma.py`).

Tasks:
1) Add a CLI arg `--ls_mode simple|risk_balanced` (default: simple).
2) For `risk_balanced`:
   - Build / compute `spread_momentum` and `vol_df` internally in `run_strategies.py` (no notebook-only logic).
   - Expose CLI params for `spread_mom_threshold`, `target_gross_exposure`, and `vol_lookback_days`.
3) Update printed summary to include: average gross exposure, average net exposure, and turnover.

Acceptance criteria:
- `python run_strategies.py --strategy regime --ls_mode simple` runs.
- `python run_strategies.py --strategy regime --ls_mode risk_balanced` runs.
- `pytest -q` passes.
```

---

## Prompt 06 — Rotation Strategy: Add “Cash Or Defensive” Option

```text
Goal: improve the momentum rotation strategy to behave better in sector-wide drawdowns.

Tasks:
1) Update `src/signals/rotation_signals.py` to support a configurable “defensive asset”:
   - New args: `defensive_ticker: str | None = None`, `defensive_on_negative_momentum: bool = True`
   - If all momentum scores are <= 0, allocate either:
     - 100% cash if `defensive_ticker is None`, OR
     - 100% to `defensive_ticker` if it exists in prices
2) Add tests in `tests/test_signals.py` verifying:
   - When all scores are <= 0, the strategy is either all-cash or all-defensive.
3) Update README quickstart usage examples showing the new option.

Acceptance criteria:
- `pytest -q` passes.
- No look-ahead bias is introduced (signals must use only information available at rebalance time).
```

---

## Prompt 07 — Reporting: Add Drawdown + Allocation Heatmaps to `results/`

```text
Goal: make `results/make_results.py` generate a PM-readable results bundle.

Tasks:
1) Extend `src/plots/plotting.py` with:
   - A drawdown plot (already exists) + optional episode shading hooks
   - A weights heatmap utility (monthly resampled to reduce noise)
2) Update `results/make_results.py` to save:
   - `drawdowns.png` (one subplot per strategy + benchmark)
   - `weights_heatmap_rotation.png`
   - `weights_heatmap_regime.png`
3) Keep plot generation deterministic and headless-friendly.

Acceptance criteria:
- Running `python results/make_results.py` produces the new artifacts.
- `pytest -q` passes.
```

---

## Prompt 08 — Factor Pipeline: Download + Parse Fama-French (FF5 + Momentum)

```text
Goal: stop requiring users to manually drop `ff_factors_monthly.csv` into `data_processed/`.

Tasks:
1) Implement `src/data/ff_factors_download.py`:
   - Download FF5 monthly and momentum (UMD) monthly from the Ken French library.
   - Parse into a clean DataFrame with month-end index and decimal returns.
   - Cache raw downloads to `data_raw/` and save processed CSV to `data_processed/`.
2) Update `src/data/ff_factors.py` to:
   - If the processed CSV is missing, auto-download + build it.
   - Support both FF5-only and FF5+UMD regressions.
3) Update `src/analysis/factor_analysis.py` to optionally include UMD in regressions.
4) Add at least one unit test verifying alignment and RF scaling heuristics.

Acceptance criteria:
- `python run_strategies.py` prints factor regressions without requiring manual factor files.
- `pytest -q` passes.
```

---

## Prompt 09 — Robustness: Structured Experiment Runner (Train/Test + Sweeps)

```text
Goal: turn parameter sweeps into a reproducible experiment artifact.

Tasks:
1) Add `src/analysis/experiments.py`:
   - A small “experiment runner” that takes:
     - strategy name
     - parameter grid
     - split date (train/test)
   - Outputs a CSV with full/in/out metrics, plus top-N configs by out-of-sample Sharpe.
2) Reuse existing sweep logic in:
   - `src/analysis/robustness.py`
   - `src/analysis/robustness_extension.py`
   but reduce duplication (keep smallest refactor possible).
3) Update `results/` generation to optionally run a sweep and save:
   - `rotation_sweep.csv`
   - `regime_sweep.csv`

Acceptance criteria:
- Experiment runner works from CLI (add a small `python -m ...` entry or script).
- `pytest -q` passes.
```

---

## Prompt 10 — Notebook Refresh + Final “Report Notebook”

```text
Goal: convert the analysis into a single notebook that reads like a research report.

Tasks:
1) Update existing notebooks (minimal edits) so they still run after any API changes.
2) Add a new notebook `notebooks/00_final_report.ipynb` that:
   - States hypotheses clearly
   - Describes data sources and assumptions
   - Shows both strategies vs benchmarks
   - Includes risk metrics, factor regression table, drawdowns, and robustness summary
3) Ensure the notebook runs top-to-bottom without manual steps other than installing requirements.

Acceptance criteria:
- Notebook is deterministic and uses cached datasets where possible.
- The narrative matches the structure in `Plan.md` (WS1–WS5).
```

---

## Prompt 11 — CI: Add Minimal GitHub Actions For `pytest`

```text
Goal: make it easy to keep the repo healthy as it grows.

Tasks:
1) Add a GitHub Actions workflow that runs on push/PR:
   - Set up Python 3.10+
   - Install requirements
   - Run `pytest -q`
2) Keep it minimal (no linting/tooling additions unless requested).

Acceptance criteria:
- Workflow file exists and runs successfully in CI.
- `pytest -q` passes locally.
```

