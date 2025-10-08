Generated assets overview

data/cycles
CSV files with candidate triangular cycles for several exchanges. Each row defines a base, an intermediate asset, and a quote with the three legs in order. fee_bps holds the assumed taker fee per leg. min_profit_bps is a target threshold after fees.

configs/strategies
YAML strategy files that point at one cycles file and set thresholds for profit, slippage, latency and capital rules. You can map these to your runner.

scripts/sims
Small sims that load a cycles file and produce quick statistics using synthetic rates. Useful for smoke checks and CI.

tests/tri_arb
Pytest checks that validate cycle structure, pair naming, and thresholds. These are safe to run in CI and make sure the data is clean.

Suggested next steps
1. Run a quick sim
   python scripts/sims/sim_1.py
2. Run tests
   pytest -q tests/tri_arb
3. Point your arbitrage runner at a chosen strategy config
   see configs/strategies
