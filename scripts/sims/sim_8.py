#!/usr/bin/env python3
import csv, math, random, time, statistics

cycles_file = "data/cycles/kraken_cycles_8.csv"
taker_bps = 10
slippage_bps = 3

def rand_price():
    return 10 ** random.uniform(-1, 5)

def price_with_slippage(p, bps):
    return p * (1 + bps / 10000.0)

def log_profit_for_cycle():
    r1 = price_with_slippage(rand_price(), slippage_bps)
    r2 = price_with_slippage(rand_price(), slippage_bps)
    r3 = price_with_slippage(rand_price(), slippage_bps)
    fees = 3 * (taker_bps / 10000.0)
    gross = r1 * r2 * r3
    net = gross * (1 - fees)
    return math.log(net)

def run():
    rows = []
    with open(cycles_file, newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    if not rows:
        print("no cycles in", cycles_file)
        return

    winners = 0
    profits = []
    trials = min(500, len(rows) * 5)
    for _ in range(trials):
        lp = log_profit_for_cycle()
        profits.append(lp)
        if lp > 0:
            winners += 1

    print("cycles loaded:", len(rows))
    print("wins:", winners, "trials:", len(profits))
    print("win rate:", round(100.0 * winners / len(profits), 2), "%")
    print("mean log profit:", round(statistics.mean(profits), 6))

if __name__ == "__main__":
    start = time.time()
    run()
    print("elapsed_sec:", round(time.time() - start, 3))
