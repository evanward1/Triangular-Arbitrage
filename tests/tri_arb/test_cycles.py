#!/usr/bin/env python3
"""
Parameterized tests for triangular arbitrage cycle files.

Consolidates test_cycles_1.py through test_cycles_N.py into a single
parameterized test file for easier maintenance.
"""
import csv
import glob
import os

import pytest


def get_cycle_files():
    """Get all cycle CSV files."""
    pattern = "data/cycles/binance_cycles_*.csv"
    files = sorted(glob.glob(pattern))
    if not files:
        pytest.skip(f"No cycle files found matching {pattern}")
    return files


@pytest.mark.parametrize("cycles_file", get_cycle_files())
def test_cycles_file_exists(cycles_file):
    """Test that cycle file exists and is readable."""
    assert os.path.exists(cycles_file), f"cycles file missing: {cycles_file}"
    assert os.path.isfile(cycles_file), f"cycles path is not a file: {cycles_file}"


@pytest.mark.parametrize("cycles_file", get_cycle_files())
def test_cycles_have_unique_assets_per_row(cycles_file):
    """Test that each cycle has 3 unique assets (no duplicates)."""
    with open(cycles_file, newline="") as f:
        r = csv.DictReader(f)
        for k, row in enumerate(r, start=1):
            a = row["base"].strip()
            b = row["inter"].strip()
            c = row["quote"].strip()
            assert a and b and c, f"{cycles_file} row {k}: empty asset"
            assert (
                len({a, b, c}) == 3
            ), f"{cycles_file} row {k} has duplicate asset in cycle"


@pytest.mark.parametrize("cycles_file", get_cycle_files())
def test_pairs_match_assets(cycles_file):
    """Test that pair columns correctly match asset columns."""
    with open(cycles_file, newline="") as f:
        r = csv.DictReader(f)
        for k, row in enumerate(r, start=1):
            a, b, c = row["base"], row["inter"], row["quote"]
            p1, p2, p3 = row["pair1"], row["pair2"], row["pair3"]
            assert p1 == f"{a}/{b}", f"{cycles_file} row {k} pair1 mismatch"
            assert p2 == f"{b}/{c}", f"{cycles_file} row {k} pair2 mismatch"
            assert p3 == f"{c}/{a}", f"{cycles_file} row {k} pair3 mismatch"


@pytest.mark.parametrize("cycles_file", get_cycle_files())
def test_thresholds_reasonable(cycles_file):
    """Test that fee and profit thresholds are in reasonable ranges."""
    with open(cycles_file, newline="") as f:
        r = csv.DictReader(f)
        for k, row in enumerate(r, start=1):
            fee = int(row["fee_bps"])
            tgt = int(row["min_profit_bps"])
            assert (
                0 < fee < 50
            ), f"{cycles_file} row {k} fee_bps {fee} out of expected range (0, 50)"
            assert (
                0 < tgt < 100
            ), f"{cycles_file} row {k} min_profit_bps {tgt} out of expected range (0, 100)"
