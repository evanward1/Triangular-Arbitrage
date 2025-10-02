import csv
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class EquitySnapshot:
    ts: float
    scan_index: int
    cash: float
    asset_value: float
    equity: float
    realized_pnl: float
    unrealized_pnl: float


class EquityTracker:
    def __init__(self, out_dir: str = "logs"):
        self.scan_index = 0
        self.realized_pnl = 0.0
        self.unrealized_pnl = 0.0
        self.path = Path(out_dir) / "equity_timeseries.csv"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            with self.path.open("w", newline="") as f:
                w = csv.writer(f)
                w.writerow(
                    [
                        "ts",
                        "scan",
                        "cash",
                        "asset_value",
                        "equity",
                        "realized_pnl",
                        "unrealized_pnl",
                    ]
                )

    def on_fill(self, pnl_realized: float):
        self.realized_pnl += float(pnl_realized)

    async def on_scan(self, get_cash, get_asset_value):
        self.scan_index += 1
        cash = float(await get_cash())
        assets = float(await get_asset_value())
        equity = cash + assets
        snap = EquitySnapshot(
            ts=time.time(),
            scan_index=self.scan_index,
            cash=cash,
            asset_value=assets,
            equity=equity,
            realized_pnl=self.realized_pnl,
            unrealized_pnl=self.unrealized_pnl,
        )
        with self.path.open("a", newline="") as f:
            w = csv.writer(f)
            w.writerow(
                [
                    snap.ts,
                    snap.scan_index,
                    snap.cash,
                    snap.asset_value,
                    snap.equity,
                    snap.realized_pnl,
                    snap.unrealized_pnl,
                ]
            )
        return snap
