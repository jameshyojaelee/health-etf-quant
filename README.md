# Healthcare ETF Quant Strategies

Quantitative strategies on healthcare ETFs (regime long-short biotech vs pharma, and momentum-based rotation).

## Overview
- **Regime long-short:** Use macro regime labels (risk-on vs risk-off) to tilt long/short exposure between biotech (e.g., XBI) and pharma (e.g., XPH), staying mindful of broad healthcare benchmarks.
- **Momentum rotation:** Rank a set of healthcare ETFs by medium-term momentum, rotate into leaders, and optionally include a market hedge (SPY) or cash when signals weaken.

## Quickstart
1. Create and activate a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
   ```
2. Install dependencies:
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```
3. (Optional) Adjust parameters in `config/settings.yaml` or `src/config.py` for tickers, dates, and paths.
4. Launch Jupyter and open the notebooks:
   ```bash
   jupyter notebook notebooks/
   ```
5. Run notebooks in order (01 through 04) to check data, inspect regimes, demo rotation, and review risk/factor results.

Data folders:
- `data_raw/` holds raw downloaded CSVs; never edit by hand.
- `data_processed/` stores cleaned, aligned time series.
