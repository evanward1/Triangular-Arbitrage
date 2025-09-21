import csv
import os

CYCLES_FILE = "data/cycles/binance_cycles_6.csv"

def test_cycles_file_exists():
    assert os.path.exists(CYCLES_FILE), "cycles file missing"

def test_cycles_have_unique_assets_per_row():
    with open(CYCLES_FILE, newline="") as f:
        r = csv.DictReader(f)
        for k,row in enumerate(r, start=1):
            a = row["base"].strip()
            b = row["inter"].strip()
            c = row["quote"].strip()
            assert a and b and c
            assert len({a,b,c}) == 3, f"row {k} has duplicate asset in cycle"

def test_pairs_match_assets():
    with open(CYCLES_FILE, newline="") as f:
        r = csv.DictReader(f)
        for k,row in enumerate(r, start=1):
            a,b,c = row["base"], row["inter"], row["quote"]
            p1,p2,p3 = row["pair1"], row["pair2"], row["pair3"]
            assert p1 == f"{a}/{b}", f"row {k} pair1 mismatch"
            assert p2 == f"{b}/{c}", f"row {k} pair2 mismatch"
            assert p3 == f"{c}/{a}", f"row {k} pair3 mismatch"

def test_thresholds_reasonable():
    with open(CYCLES_FILE, newline="") as f:
        r = csv.DictReader(f)
        for k,row in enumerate(r, start=1):
            fee = int(row["fee_bps"])
            tgt = int(row["min_profit_bps"])
            assert 0 < fee < 50, f"row {k} fee_bps out of expected range"
            assert 0 < tgt < 100, f"row {k} min_profit_bps out of expected range"
