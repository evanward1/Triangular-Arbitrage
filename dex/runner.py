"""
Main DEX arbitrage paper trading runner.

Scans for cross-DEX arbitrage opportunities and prints results
in a console-friendly format matching the CEX runner style.
"""

import sys
import time
from collections import deque
from decimal import Decimal
from itertools import combinations
from typing import Dict, List, Optional, Tuple

from web3 import Web3

from .adapters.v2 import fetch_pool, swap_out
from .config import DexConfig
from .types import ArbRow, DexPool

# Depth guard: skip trades consuming more than this fraction of reserves
MAX_DEPTH_FRACTION = Decimal("0.10")  # 10%

# EMA alpha for 15-period exponential moving average
EMA_ALPHA = Decimal("2") / Decimal("16")  # 2/(N+1) where N=15


class DexRunner:
    """
    DEX arbitrage paper trading scanner.

    Fetches pool reserves, simulates cross-DEX cycles, and prints
    top opportunities with detailed P&L breakdown.
    """

    def __init__(self, config: DexConfig, quiet: bool = False):
        """
        Initialize runner with config.

        Args:
            config: Validated DexConfig instance
            quiet: If True, only show opportunities + batch summaries (less noise)
        """
        self.config = config
        self.quiet = quiet
        self.web3: Optional[Web3] = None
        self.pools: List[DexPool] = []

        # Token address mappings
        self.addr_of: Dict[str, str] = {}
        self.decimals_of: Dict[str, int] = {}
        self.symbol_of: Dict[str, str] = {}

        # Scan stats for EMA tracking
        self.scan_count = 0
        self.ema_gross: Optional[float] = None
        self.ema_net: Optional[float] = None
        self.pnl_history: deque = deque(maxlen=15)  # Last 15 scans for EV calculation

        # Quiet mode batch tracking
        self.batch_start_scan = 1
        self.batch_size = 10
        self.batch_best_net = None

    def connect(self) -> None:
        """
        Connect to RPC and validate connection.

        Raises:
            Exception: If RPC connection fails
        """
        print(f"🔗 Connecting to RPC: {self.config.rpc_url}")
        self.web3 = Web3(
            Web3.HTTPProvider(self.config.rpc_url, request_kwargs={"timeout": 10})
        )

        if not self.web3.is_connected():
            raise Exception(f"Failed to connect to RPC: {self.config.rpc_url}")

        chain_id = self.web3.eth.chain_id
        block = self.web3.eth.block_number
        print(f"✓ Connected to chain {chain_id}, block {block}")

    def build_token_maps(self) -> None:
        """Build token address and decimals lookup maps."""
        for symbol, info in self.config.tokens.items():
            addr = Web3.to_checksum_address(info["address"])
            decimals = info["decimals"]

            self.addr_of[symbol] = addr
            self.decimals_of[symbol] = decimals
            self.symbol_of[addr] = symbol

        print(f"📋 Loaded {len(self.config.tokens)} tokens")

    def fetch_pools(self) -> None:
        """
        Fetch all configured V2 pools from chain.

        Skips pools that fail to fetch (logs warning but continues).
        """
        if not self.web3:
            raise RuntimeError("Must call connect() before fetch_pools()")

        self.pools = []
        for dex_cfg in self.config.dexes:
            if dex_cfg["kind"] != "v2":
                print(f"⚠ Skipping {dex_cfg['name']} (only V2 supported for now)")
                continue

            for pair_cfg in dex_cfg["pairs"]:
                try:
                    pool = self._fetch_v2_pool(dex_cfg, pair_cfg)
                    self.pools.append(pool)
                except Exception as e:
                    print(
                        f"⚠ Failed to fetch {dex_cfg['name']}/{pair_cfg['name']}: {e}"
                    )
                    continue

        if not self.pools:
            raise RuntimeError("No pools successfully fetched")

        print(f"✓ Fetched {len(self.pools)} V2 pools")

    def _fetch_v2_pool(self, dex_cfg: Dict, pair_cfg: Dict) -> DexPool:
        """
        Fetch a single V2 pool and normalize reserves.

        Args:
            dex_cfg: DEX config dict
            pair_cfg: Pair config dict

        Returns:
            DexPool with normalized reserves

        Raises:
            Exception: If fetch or normalization fails
        """
        pair_addr = Web3.to_checksum_address(pair_cfg["address"])
        token0_addr, token1_addr, r0, r1 = fetch_pool(self.web3, pair_addr)

        base_sym = pair_cfg["base"]
        quote_sym = pair_cfg["quote"]

        # Validate tokens are configured
        if base_sym not in self.addr_of or quote_sym not in self.addr_of:
            raise ValueError(f"Pair uses unconfigured tokens: {base_sym}/{quote_sym}")

        base_addr = self.addr_of[base_sym]
        quote_addr = self.addr_of[quote_sym]

        # Normalize reserves to match (base, quote) orientation
        if token0_addr == base_addr and token1_addr == quote_addr:
            # Already correct orientation
            pass
        elif token0_addr == quote_addr and token1_addr == base_addr:
            # Flip reserves
            r0, r1 = r1, r0
            token0_addr, token1_addr = token1_addr, token0_addr
        else:
            raise ValueError(
                f"Pair {pair_addr} tokens ({token0_addr}, {token1_addr}) "
                f"don't match config ({base_addr}, {quote_addr})"
            )

        fee_decimal = Decimal(dex_cfg["fee_bps"]) / Decimal(10_000)

        return DexPool(
            dex=dex_cfg["name"],
            kind=dex_cfg["kind"],
            pair_name=pair_cfg["name"],
            pair_addr=pair_addr,
            token0=token0_addr,
            token1=token1_addr,
            r0=r0,
            r1=r1,
            fee=fee_decimal,
            base_symbol=base_sym,
            quote_symbol=quote_sym,
        )

    def refresh_reserves(self) -> None:
        """
        Refresh reserves for all pools.

        Skips pools that fail (logs warning but continues).
        """
        for pool in self.pools:
            try:
                _, _, r0, r1 = fetch_pool(self.web3, pool.pair_addr)
                pool.r0 = r0
                pool.r1 = r1
            except Exception as e:
                print(f"⚠ Failed to refresh {pool.dex}/{pool.pair_name}: {e}")
                continue

    def scan(self) -> List[ArbRow]:
        """
        Scan for arbitrage opportunities across all pool pairs.

        Returns:
            List of ArbRow results sorted by net_pct descending
        """
        self.refresh_reserves()

        # Group pools by (base, quote) pair
        pair_groups: Dict[Tuple[str, str], List[DexPool]] = {}
        for pool in self.pools:
            key = (pool.base_symbol, pool.quote_symbol)
            pair_groups.setdefault(key, []).append(pool)

        rows = []
        cycles_simulated = 0

        # For each pair, try all combinations of distinct venues
        for (base_sym, quote_sym), pools_for_pair in pair_groups.items():
            if len(pools_for_pair) < 2:
                continue  # Need at least 2 venues for arb

            # Try all ordered pairs of distinct venues
            for poolA, poolB in combinations(pools_for_pair, 2):
                # Direction 1: buy base on A, sell base on B
                row1 = self._simulate_cycle(poolA, poolB, base_sym, quote_sym)
                if row1:
                    rows.append(row1)
                cycles_simulated += 1

                # Direction 2: buy base on B, sell base on A
                row2 = self._simulate_cycle(poolB, poolA, base_sym, quote_sym)
                if row2:
                    rows.append(row2)
                cycles_simulated += 1

        # Sort by net profit descending
        rows.sort(key=lambda r: r.net_pct, reverse=True)

        # Update scan stats
        self.scan_count += 1
        if rows:
            best_gross = rows[0].gross_pct
            best_net = rows[0].net_pct
            self._update_ema(best_gross, best_net)
            self.pnl_history.append(rows[0].pnl_usd)

        return rows

    def _simulate_cycle(
        self,
        poolA: DexPool,
        poolB: DexPool,
        base_sym: str,
        quote_sym: str,
    ) -> Optional[ArbRow]:
        """
        Simulate a single arbitrage cycle: quote -> base (A) -> quote (B).

        Args:
            poolA: Pool to buy base on
            poolB: Pool to sell base on
            base_sym: Base token symbol
            quote_sym: Quote token symbol

        Returns:
            ArbRow if cycle is valid, None if rejected by depth guard
        """
        # Start with USD notional in quote token
        quote_decimals = self.decimals_of[quote_sym]

        initial_quote = self.config.max_position_usd * Decimal(10**quote_decimals)

        # Leg 1: Buy base on poolA (quote -> base)
        # poolA reserves: r0=base, r1=quote
        amount_in_leg1 = initial_quote
        reserve_in_leg1 = poolA.r1  # quote reserve
        reserve_out_leg1 = poolA.r0  # base reserve

        # Depth guard on leg 1
        if amount_in_leg1 > MAX_DEPTH_FRACTION * reserve_in_leg1:
            return None

        base_amount = swap_out(
            amount_in_leg1, reserve_in_leg1, reserve_out_leg1, poolA.fee
        )

        # Leg 2: Sell base on poolB (base -> quote)
        # poolB reserves: r0=base, r1=quote
        amount_in_leg2 = base_amount
        reserve_in_leg2 = poolB.r0  # base reserve
        reserve_out_leg2 = poolB.r1  # quote reserve

        # Depth guard on leg 2
        if amount_in_leg2 > MAX_DEPTH_FRACTION * reserve_in_leg2:
            return None

        final_quote_before_slip = swap_out(
            amount_in_leg2, reserve_in_leg2, reserve_out_leg2, poolB.fee
        )

        # Apply slippage haircut to final proceeds
        slippage_factor = Decimal(1) - self.config.slippage_decimal
        final_quote = final_quote_before_slip * slippage_factor

        # Calculate percentages
        gross_pct = float((final_quote_before_slip / initial_quote - 1) * 100)
        net_quote = final_quote

        # Subtract gas cost if override set
        if self.config.gas_cost_usd_override:
            gas_cost_native = Decimal(self.config.gas_cost_usd_override) * Decimal(
                10**quote_decimals
            )
            net_quote -= gas_cost_native

        net_pct = float((net_quote / initial_quote - 1) * 100)
        pnl_usd = float((net_quote - initial_quote) / Decimal(10**quote_decimals))

        cycle_str = (
            f"{quote_sym} -> {base_sym} ({poolA.dex}) -> {quote_sym} ({poolB.dex})"
        )

        return ArbRow(
            cycle=cycle_str,
            dexA=poolA.dex,
            dexB=poolB.dex,
            pair=f"{base_sym}/{quote_sym}",
            gross_pct=gross_pct,
            net_pct=net_pct,
            pnl_usd=pnl_usd,
        )

    def _update_ema(self, gross: float, net: float) -> None:
        """Update EMA15 for gross and net percentages."""
        alpha = float(EMA_ALPHA)
        if self.ema_gross is None:
            self.ema_gross = gross
            self.ema_net = net
        else:
            self.ema_gross = alpha * gross + (1 - alpha) * self.ema_gross
            self.ema_net = alpha * net + (1 - alpha) * self.ema_net

    def print_banner(self) -> None:
        """Print startup banner with config summary."""
        cfg = self.config
        print("\n" + "=" * 80)
        print("📝 DEX PAPER MODE — scanning for cross-DEX arbitrage")
        print("=" * 80)
        print(f"🔍 Pools: {len(self.pools)} | Poll: {cfg.poll_sec}s | Once: {cfg.once}")
        print(
            f"💰 Size: ${cfg.max_position_usd} | Threshold: {cfg.threshold_net_pct:.2f}% NET"
        )

        gas_str = ""
        if cfg.gas_cost_usd_override:
            gas_str = f" + gas({cfg.gas_pct:.2f}%)"

        print(
            f"   (need gross ≥ {cfg.breakeven_pct:.2f}% = "
            f"thr({cfg.threshold_net_pct:.2f}%) + slip({cfg.slippage_pct:.2f}%){gas_str})"
        )
        print("=" * 80 + "\n")

    def print_results(self, rows: List[ArbRow], scan_num: int) -> None:
        """
        Print scan results in CEX runner style.

        Args:
            rows: Sorted list of ArbRow results
            scan_num: Current scan number
        """
        # Check for opportunities (net >= threshold)
        opportunities = [r for r in rows if r.net_pct >= self.config.threshold_net_pct]

        # In quiet mode, batch scans and only show opportunities
        if self.quiet:
            # Track best net for batch
            if rows:
                best_net = rows[0].net_pct
                if self.batch_best_net is None or best_net > self.batch_best_net:
                    self.batch_best_net = best_net

            # If opportunity found, print it immediately
            if opportunities:
                self._print_opportunity(opportunities[0], scan_num)
                self.batch_best_net = None  # Reset batch tracking
                self.batch_start_scan = scan_num + 1
                return

            # Print batch summary every N scans
            if scan_num % self.batch_size == 0:
                self._print_batch_summary(self.batch_start_scan, scan_num)
                self.batch_start_scan = scan_num + 1
                self.batch_best_net = None
            return

        # Normal mode: print full details for every scan
        print(f"\n🔍 Scan {scan_num}")
        print("-" * 80)

        # Top 10 opportunities
        top10 = rows[:10]
        if not top10:
            print("  (no valid cycles found)")
        else:
            for i, row in enumerate(top10, 1):
                slip_str = f"slip={self.config.slippage_pct:.2f}%"
                gas_str = ""
                if self.config.gas_cost_usd_override:
                    gas_str = f" gas={self.config.gas_pct:.2f}%"

                print(
                    f"  {i:2d}. {row.cycle} [{row.pair}]: "
                    f"gross={row.gross_pct:+.2f}% {slip_str}{gas_str} net={row.net_pct:+.2f}%"
                )

        # Why line if best doesn't meet threshold
        if rows and rows[0].net_pct < self.config.threshold_net_pct:
            best = rows[0]
            delta = best.net_pct - self.config.threshold_net_pct
            slip_str = f"slip={self.config.slippage_pct:.2f}%"
            gas_str = ""
            if self.config.gas_cost_usd_override:
                gas_str = f" gas={self.config.gas_pct:.2f}%"

            print(
                f"\n  ✗ why: best_net={best.net_pct:.2f}% (< thr by {delta:.2f}%), "
                f"gross={best.gross_pct:+.2f}% – {slip_str}{gas_str}"
            )

        # Footer with stats
        above_thr = len(opportunities)

        ema_str = ""
        if self.ema_gross is not None:
            ema_str = f"EMA15 g={self.ema_gross:+.2f}% n={self.ema_net:+.2f}% | "

        cycles = len(rows)
        size_str = f"${self.config.max_position_usd:.0f}"

        hyp_pnl = 0.0
        if rows:
            hyp_pnl = rows[0].pnl_usd * above_thr

        ev_scan = 0.0
        if self.pnl_history:
            ev_scan = sum(self.pnl_history) / len(self.pnl_history)

        print(
            f"\n  → {above_thr} above {self.config.threshold_net_pct:.2f}% threshold | "
            f"{ema_str}cycles={cycles} | size≈{size_str} hyp_P&L=${hyp_pnl:.2f} | "
            f"EV/scan=${ev_scan:.2f}"
        )
        print("-" * 80)

    def _print_opportunity(self, row: ArbRow, scan_num: int) -> None:
        """Print a single opportunity (for quiet mode)."""
        print(f"\n✨ OPPORTUNITY FOUND! (Scan {scan_num})")
        print("=" * 80)
        print(f"  {row.cycle}")
        print(
            f"  Gross: {row.gross_pct:+.2f}% | Slip: {self.config.slippage_pct:.2f}%",
            end="",
        )
        if self.config.gas_cost_usd_override:
            print(f" | Gas: {self.config.gas_pct:.2f}%", end="")
        print(f" | Net: {row.net_pct:+.2f}% ✅")
        print(
            f"  Expected profit: ${abs(row.pnl_usd):.2f} on ${self.config.max_position_usd}"
        )
        print(
            f"  Would execute: YES (net={row.net_pct:.2f}% > threshold={self.config.threshold_net_pct:.2f}%)"
        )
        print("=" * 80)

    def _print_batch_summary(self, start_scan: int, end_scan: int) -> None:
        """Print summary for a batch of scans (for quiet mode)."""
        ema_str = ""
        if self.ema_gross is not None:
            ema_str = (
                f" | avg_gross={self.ema_gross:+.2f}% avg_net={self.ema_net:+.2f}%"
            )

        best_str = ""
        if self.batch_best_net is not None:
            indicator = "🔴"
            if self.batch_best_net >= self.config.threshold_net_pct:
                indicator = "🟢"
            best_str = f" | best_net={self.batch_best_net:+.2f}% {indicator}"

        ev_str = ""
        if self.pnl_history:
            ev_scan = sum(self.pnl_history) / len(self.pnl_history)
            ev_str = f" | EV/scan=${ev_scan:.2f}"

        print(
            f"⏱  Scans {start_scan}-{end_scan}: 0 opportunities{best_str}{ema_str}{ev_str}"
        )

    def run(self) -> None:
        """
        Main loop: scan, print, sleep.

        Runs indefinitely unless config.once=True.
        """
        self.print_banner()

        scan_num = 0
        while True:
            scan_num += 1
            try:
                rows = self.scan()
                self.print_results(rows, scan_num)
            except KeyboardInterrupt:
                print("\n\n⏸ Interrupted by user")
                sys.exit(0)
            except Exception as e:
                print(f"\n⚠ Scan {scan_num} failed: {e}")
                if self.config.once:
                    raise

            if self.config.once:
                break

            time.sleep(self.config.poll_sec)
