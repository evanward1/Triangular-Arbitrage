"""
Main DEX arbitrage paper trading runner.

Scans for cross-DEX arbitrage opportunities and logs results
in a console-friendly format matching the CEX runner style.
"""

import asyncio
import logging
import sys
import time
from collections import deque
from decimal import Decimal
from itertools import combinations
from typing import Dict, List, Optional, Tuple

from web3 import Web3

from triangular_arbitrage.utils import get_logger
from triangular_arbitrage.validation.breakeven import BreakevenGuard, LegInfo

from .adapters.v2 import fetch_pool, fetch_pool_async, swap_out
from .config import DexConfig
from .types import ArbRow, DexPool


# ANSI color codes for pretty output
class Colors:
    """ANSI color codes for terminal output."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # Colors
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"

    # Background colors
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_BLUE = "\033[44m"

    @staticmethod
    def strip(text: str) -> str:
        """Remove all ANSI codes from text."""
        import re

        return re.sub(r"\033\[[0-9;]+m", "", text)


# Initialize logger
logger = get_logger(__name__)

# Import pool factory scanner for dynamic pool discovery
try:
    from triangular_arbitrage.dex_mev.pool_factory_scanner import PoolFactoryScanner

    FACTORY_SCANNER_AVAILABLE = True
except ImportError:
    FACTORY_SCANNER_AVAILABLE = False
    logger.warning("Pool factory scanner not available - using static pool config only")

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

    def __init__(
        self, config: DexConfig, quiet: bool = False, use_dynamic_pools: bool = None
    ):
        """
        Initialize runner with config.

        Args:
            config: Validated DexConfig instance
            quiet: If True, only show opportunities + batch summaries (less noise)
            use_dynamic_pools: If True/False, override config. If None, use config value.
        """
        self.config = config
        self.quiet = quiet

        # Determine dynamic pools setting: CLI arg > config > default (True)
        if use_dynamic_pools is not None:
            self.use_dynamic_pools = use_dynamic_pools and FACTORY_SCANNER_AVAILABLE
        elif hasattr(config, "dynamic_pools") and config.dynamic_pools:
            self.use_dynamic_pools = (
                config.dynamic_pools.get("enabled", True) and FACTORY_SCANNER_AVAILABLE
            )
        else:
            # Default: use dynamic pools if available and no static pools configured
            self.use_dynamic_pools = (
                FACTORY_SCANNER_AVAILABLE and len(config.dexes) == 0
            )
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

        # Initialize BreakevenGuard for profitability validation
        self.breakeven_guard = BreakevenGuard(max_leg_latency_ms=750)

        # Pool factory scanner for dynamic discovery
        self.factory_scanner: Optional[PoolFactoryScanner] = None

    def connect(self) -> None:
        """
        Connect to RPC and validate connection with fallback support.

        Tries the configured RPC URL first, then falls back to public endpoints
        if the primary fails.

        Raises:
            Exception: If all RPC connections fail
        """
        # List of fallback RPCs for Ethereum mainnet (prioritized by reliability)
        fallback_rpcs = [
            self.config.rpc_url,
            "https://eth.drpc.org",  # Fast and reliable
            "https://ethereum.publicnode.com",  # Reliable
            "https://1rpc.io/eth",  # Reliable but slower
            "https://rpc.ankr.com/eth",  # Sometimes unreliable
            "https://eth.llamarpc.com",  # Sometimes unreliable
        ]

        # Debug: Log the configured RPC URL
        logger.debug(
            f"Config RPC URL: {self.config.rpc_url} (type: {type(self.config.rpc_url)})"
        )

        last_error = None
        for rpc_url in fallback_rpcs:
            # Skip None or empty URLs
            if not rpc_url or not isinstance(rpc_url, str) or not rpc_url.strip():
                logger.debug(f"Skipping invalid RPC URL: {rpc_url}")
                continue

            try:
                logger.info(f"Connecting to RPC: {rpc_url}")
                # Validate URL format before passing to Web3
                if not rpc_url.startswith(("http://", "https://")):
                    raise ValueError(f"Invalid RPC URL format: {rpc_url}")

                self.web3 = Web3(
                    Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 10})
                )

                # Verify we can query the chain (skip is_connected() as it's unreliable)
                chain_id = self.web3.eth.chain_id
                block = self.web3.eth.block_number

                # Map chain IDs to readable names
                chain_names = {
                    1: "Ethereum Mainnet",
                    8453: "Base",
                    42161: "Arbitrum",
                    10: "Optimism",
                    137: "Polygon",
                    56: "BSC",
                }
                chain_name = chain_names.get(chain_id, f"Chain {chain_id}")

                logger.info(f"✓ Connected to {chain_name} (block #{block:,})")

                # Update config to remember working RPC
                self.config.rpc_url = rpc_url
                return

            except Exception as e:
                last_error = e
                logger.warning(f"RPC connection failed: {e}")
                if rpc_url != fallback_rpcs[-1]:
                    logger.info("Trying next endpoint...")
                continue

        # If we get here, all RPCs failed
        raise Exception(
            f"Failed to connect to any RPC endpoint. Last error: {last_error}\n"
            f"Tried {len(fallback_rpcs)} endpoints. Check your internet connection."
        )

    def build_token_maps(self) -> None:
        """Build token address and decimals lookup maps."""
        for symbol, info in self.config.tokens.items():
            addr = Web3.to_checksum_address(info["address"])
            decimals = info["decimals"]

            self.addr_of[symbol] = addr
            self.decimals_of[symbol] = decimals
            self.symbol_of[addr] = symbol

        logger.info(f"Loaded {len(self.config.tokens)} tokens")

    def fetch_pools(self, max_pools_per_dex: Optional[int] = None) -> None:
        """
        Fetch pools from chain - either from config or dynamically from factories.

        Args:
            max_pools_per_dex: For dynamic discovery, limit pools per DEX (default: no limit)

        Skips pools that fail to fetch (logs warning but continues).
        """
        if not self.web3:
            raise RuntimeError("Must call connect() before fetch_pools()")

        # Check if we should use dynamic pool discovery
        if self.use_dynamic_pools:
            logger.info("Using dynamic pool discovery from factory contracts...")
            self._fetch_pools_dynamically(max_pools_per_dex)
        else:
            logger.info("Using static pool configuration from config file...")
            self._fetch_pools_from_config()

        if not self.pools:
            raise RuntimeError("No pools successfully fetched")

        logger.info(f"Fetched {len(self.pools)} V2 pools")

    def _fetch_pools_from_config(self) -> None:
        """
        Fetch all configured V2 pools from chain (original static method).

        Skips pools that fail to fetch (logs warning but continues).
        Adds 0.5s delay between fetches to avoid rate limiting.
        """
        self.pools = []
        pool_count = 0
        for dex_cfg in self.config.dexes:
            if dex_cfg["kind"] != "v2":
                logger.warning(
                    f"Skipping {dex_cfg['name']} (only V2 supported for now)"
                )
                continue

            for pair_cfg in dex_cfg["pairs"]:
                # Add delay between fetches to avoid rate limiting (skip first)
                if pool_count > 0:
                    time.sleep(0.5)
                pool_count += 1

                try:
                    pool = self._fetch_v2_pool(dex_cfg, pair_cfg)
                    self.pools.append(pool)
                except Exception as e:
                    logger.warning(
                        f"Failed to fetch {dex_cfg['name']}/{pair_cfg['name']}: {e}"
                    )
                    continue

    def _fetch_pools_dynamically(self, max_pools_per_dex: Optional[int] = None) -> None:
        """
        Dynamically discover pools from factory contracts.

        Args:
            max_pools_per_dex: Limit pools per DEX (sorted by liquidity)
        """
        # Get config values if available
        if self.config.dynamic_pools:
            min_liq = Decimal(
                str(self.config.dynamic_pools.get("min_liquidity_usd", 10000))
            )
            max_pools = self.config.dynamic_pools.get(
                "max_pools_per_dex", max_pools_per_dex
            )
            max_scan = self.config.dynamic_pools.get("max_scan_pools")
            factories_config = self.config.dynamic_pools.get("factories", [])
        else:
            # Defaults if dynamic_pools not in config
            min_liq = Decimal("10000")
            max_pools = max_pools_per_dex
            max_scan = None
            factories_config = []

        # Initialize factory scanner
        logger.info(f"Initializing pool factory scanner (min liquidity: ${min_liq})")
        self.factory_scanner = PoolFactoryScanner(
            w3=self.web3,
            min_liquidity_usd=min_liq,
            eth_price_usd=Decimal("2500"),  # Reasonable ETH price estimate
        )
        logger.info("Factory scanner initialized")

        # Use factories from config or fall back to hardcoded defaults
        if factories_config:
            factories = [
                (f["address"], f["name"], f["fee_bps"]) for f in factories_config
            ]
        else:
            # Default factories for Ethereum
            factories = [
                ("0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f", "uniswap_v2", 30),
                ("0xC0AEe478e3658e2610c5F7A4A2E1777cE9e4f2Ac", "sushiswap", 30),
            ]

        # Scan all factories (no token whitelist - discover ALL tokens)
        logger.info(f"Starting scan of {len(factories)} factory contracts...")
        logger.info(f"Scan limits: max_scan={max_scan}, max_pools_per_dex={max_pools}")

        discovered_pools = self.factory_scanner.scan_multiple_factories(
            factories=factories,
            max_pools_per_factory=max_pools,
            token_whitelist=None,  # Scan all tokens
            max_scan_pools=max_scan,  # Limit total pools scanned for speed
        )

        logger.info("Factory scan completed")

        # Convert discovered pools to DexPool objects
        self.pools = []
        for dex_name, pools_info in discovered_pools.items():
            for pool_info in pools_info:
                try:
                    pool = self._convert_discovered_pool(pool_info, dex_name)
                    if pool:
                        self.pools.append(pool)
                except Exception as e:
                    logger.warning(
                        f"Failed to convert pool {pool_info.get('address')}: {e}"
                    )
                    continue

        logger.info(f"Discovered {len(self.pools)} pools dynamically")

        # Filter to keep only pairs that exist on multiple DEXes
        self._filter_cross_dex_pairs()

        # Debug: log pool pairs for troubleshooting
        if logger.level <= logging.DEBUG:
            logger.debug("Discovered pool details:")
            for pool in self.pools:
                logger.debug(f"  {pool.dex}: {pool.base_symbol}/{pool.quote_symbol}")

    def _filter_cross_dex_pairs(self) -> None:
        """
        Filter pools to keep only pairs that exist on at least 2 DEXes.

        This ensures we only scan pools that have arbitrage potential
        (same pair available on multiple venues).
        """
        from collections import defaultdict

        # Group pools by normalized pair (sort tokens alphabetically)
        pair_to_dexes: Dict[Tuple[str, str], List[str]] = defaultdict(list)
        pair_to_pools: Dict[Tuple[str, str], List[DexPool]] = defaultdict(list)

        for pool in self.pools:
            # Normalize pair by sorting tokens alphabetically
            # This handles both WBNB/USDT and USDT/WBNB as the same pair
            tokens = tuple(sorted([pool.base_symbol, pool.quote_symbol]))

            pair_to_dexes[tokens].append(pool.dex)
            pair_to_pools[tokens].append(pool)

        # Keep only pairs that appear on at least 2 DEXes
        filtered_pools = []
        cross_dex_pairs = 0

        for pair, dexes in pair_to_dexes.items():
            unique_dexes = set(dexes)
            if len(unique_dexes) >= 2:
                # This pair exists on multiple DEXes - keep all pools for it
                filtered_pools.extend(pair_to_pools[pair])
                cross_dex_pairs += 1

        # Log filtering results
        original_count = len(self.pools)
        self.pools = filtered_pools
        filtered_count = len(self.pools)

        logger.info(
            f"Filtered to {cross_dex_pairs} cross-DEX pairs "
            f"({filtered_count} pools, removed {original_count - filtered_count})"
        )

        if filtered_count == 0:
            logger.warning(
                "⚠ No cross-DEX pairs found! All pools are unique to single DEXes. "
                "This means no arbitrage opportunities are possible with current pool set. "
                "Consider: 1) Lowering min_liquidity_usd, 2) Increasing max_pools_per_dex"
            )

    def _convert_discovered_pool(
        self, pool_info: Dict, dex_name: str
    ) -> Optional[DexPool]:
        """
        Convert discovered pool info to DexPool object.

        Args:
            pool_info: Pool info dict from factory scanner
            dex_name: DEX name

        Returns:
            DexPool object or None if conversion fails
        """
        try:
            # Get or register tokens
            token0_addr = Web3.to_checksum_address(pool_info["token0"])
            token1_addr = Web3.to_checksum_address(pool_info["token1"])

            # Register tokens if not already known
            symbol0 = pool_info["symbol0"]
            symbol1 = pool_info["symbol1"]

            if token0_addr not in self.symbol_of:
                self.addr_of[symbol0] = token0_addr
                self.decimals_of[symbol0] = pool_info["decimals0"]
                self.symbol_of[token0_addr] = symbol0

            if token1_addr not in self.symbol_of:
                self.addr_of[symbol1] = token1_addr
                self.decimals_of[symbol1] = pool_info["decimals1"]
                self.symbol_of[token1_addr] = symbol1

            # Create DexPool
            fee_decimal = Decimal(pool_info["fee_bps"]) / Decimal(10_000)
            pair_name = f"{symbol0}/{symbol1}"

            return DexPool(
                dex=dex_name,
                kind="v2",
                pair_name=pair_name,
                pair_addr=Web3.to_checksum_address(pool_info["address"]),
                token0=token0_addr,
                token1=token1_addr,
                r0=Decimal(pool_info["reserve0"]),
                r1=Decimal(pool_info["reserve1"]),
                fee=fee_decimal,
                base_symbol=symbol0,
                quote_symbol=symbol1,
            )

        except Exception as e:
            logger.debug(f"Error converting pool: {e}")
            return None

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
        Refresh reserves for all pools (synchronous version).

        Skips pools that fail (logs warning but continues).
        """
        for pool in self.pools:
            try:
                _, _, r0, r1 = fetch_pool(self.web3, pool.pair_addr)
                pool.r0 = r0
                pool.r1 = r1
            except Exception as e:
                logger.warning(f"Failed to refresh {pool.dex}/{pool.pair_name}: {e}")
                continue

    async def refresh_reserves_async(
        self, use_cache: bool = True, cache_ttl_sec: int = 6
    ) -> None:
        """
        Refresh reserves for all pools concurrently (async version).

        Uses asyncio.gather() to fetch all pool reserves in parallel,
        providing 20-40x speedup compared to sequential fetching.

        Implements connection throttling and caching to avoid rate limits.

        With 3s scan interval and 6s cache: Fresh, Fresh, Cached pattern.

        Args:
            use_cache: Whether to use cached reserve data (default: True)
            cache_ttl_sec: Cache time-to-live in seconds (default: 6 for 3s scans)

        Skips pools that fail (logs warning but continues).
        """
        import time as time_module

        # Initialize cache if not exists
        if not hasattr(self, "_reserve_cache"):
            self._reserve_cache = {}

        # Check cache timestamp
        cache_valid = False
        if use_cache and hasattr(self, "_cache_timestamp"):
            age = time_module.time() - self._cache_timestamp
            cache_valid = age < cache_ttl_sec

        # Use cache if valid
        if cache_valid and self._reserve_cache:
            logger.debug(f"Using cached reserves ({len(self._reserve_cache)} pools)")
            for pool in self.pools:
                if pool.pair_addr in self._reserve_cache:
                    r0, r1 = self._reserve_cache[pool.pair_addr]
                    pool.r0 = r0
                    pool.r1 = r1
            return

        # Create semaphore to limit concurrent requests (max 10 at once for 1000 pools)
        semaphore = asyncio.Semaphore(10)

        async def fetch_one_pool(
            pool: DexPool,
        ) -> Optional[Tuple[DexPool, Decimal, Decimal]]:
            """Fetch reserves for a single pool with rate limiting."""
            async with semaphore:
                try:
                    # Add small delay between requests to avoid bursts
                    await asyncio.sleep(0.1)
                    _, _, r0, r1 = await fetch_pool_async(
                        self.web3, pool.pair_addr, max_retries=5
                    )
                    return (pool, r0, r1)
                except Exception as e:
                    # Silently skip failed pools (too noisy)
                    error_msg = str(e)
                    if "limit exceeded" not in error_msg.lower():
                        logger.warning(
                            f"Failed to refresh {pool.dex}/{pool.pair_name}: {e}"
                        )
                    return None

        # Fetch all pools concurrently (with semaphore limiting parallelism)
        results = await asyncio.gather(
            *[fetch_one_pool(pool) for pool in self.pools], return_exceptions=True
        )

        # Update successful results and cache
        self._reserve_cache = {}
        successful_count = 0
        for result in results:
            if result and not isinstance(result, Exception):
                pool, r0, r1 = result
                pool.r0 = r0
                pool.r1 = r1
                self._reserve_cache[pool.pair_addr] = (r0, r1)
                successful_count += 1

        # Update cache timestamp
        self._cache_timestamp = time_module.time()

        if successful_count < len(self.pools):
            logger.debug(f"Refreshed {successful_count}/{len(self.pools)} pools")

    def scan(self) -> List[ArbRow]:
        """
        Scan for arbitrage opportunities across all pool pairs (synchronous).

        Returns:
            List of ArbRow results sorted by net_pct descending
        """
        self.refresh_reserves()
        return self._calculate_opportunities()

    async def scan_async(self) -> List[ArbRow]:
        """
        Scan for arbitrage opportunities across all pool pairs (async).

        Uses concurrent reserve fetching for 20-40x speedup.

        Returns:
            List of ArbRow results sorted by net_pct descending
        """
        await self.refresh_reserves_async()
        return self._calculate_opportunities()

    def _calculate_opportunities(self) -> List[ArbRow]:
        """
        Calculate arbitrage opportunities from current pool reserves.

        This is separated from refresh_reserves so we can use either
        sync or async reserve fetching.

        Returns:
            List of ArbRow results sorted by net_pct descending
        """

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
        # Validate pools have reasonable reserves (filter out dead/scam tokens)
        # Minimum reserve threshold: equivalent to $100 worth
        MIN_RESERVE = Decimal("100") * Decimal(10**18)  # 100 tokens with 18 decimals

        if poolA.r0 < MIN_RESERVE or poolA.r1 < MIN_RESERVE:
            logger.debug(
                f"Rejected {poolA.dex} {base_sym}/{quote_sym}: reserves too low "
                f"(r0={float(poolA.r0):,.0f}, r1={float(poolA.r1):,.0f})"
            )
            return None

        if poolB.r0 < MIN_RESERVE or poolB.r1 < MIN_RESERVE:
            logger.debug(
                f"Rejected {poolB.dex} {base_sym}/{quote_sym}: reserves too low "
                f"(r0={float(poolB.r0):,.0f}, r1={float(poolB.r1):,.0f})"
            )
            return None

        # Check for extreme price ratios (possible scam/dead tokens)
        # Ratio should be within 1000x either direction for legitimate pairs
        MAX_RATIO = Decimal("1000000")  # 1M:1 max ratio

        ratioA = poolA.r1 / poolA.r0 if poolA.r0 > 0 else Decimal("0")
        ratioB = poolB.r1 / poolB.r0 if poolB.r0 > 0 else Decimal("0")

        if ratioA > MAX_RATIO or ratioA < (Decimal("1") / MAX_RATIO):
            logger.debug(
                f"Rejected {poolA.dex} {base_sym}/{quote_sym}: extreme price ratio "
                f"({float(ratioA):.2e})"
            )
            return None

        if ratioB > MAX_RATIO or ratioB < (Decimal("1") / MAX_RATIO):
            logger.debug(
                f"Rejected {poolB.dex} {base_sym}/{quote_sym}: extreme price ratio "
                f"({float(ratioB):.2e})"
            )
            return None

        # Start with USD notional in quote token
        # NOTE: The arbitrage cycle is: quote -> base (poolA) -> quote (poolB)
        # We need to convert max_position_usd to quote token units

        usd_token = self.config.usd_token
        usd_decimals = self.decimals_of[usd_token]
        quote_decimals = self.decimals_of[quote_sym]

        # Amount in USD token raw units (e.g., 1000 USDC = 1000 * 10^6)
        usd_amount_raw = (
            Decimal(str(self.config.max_position_usd)) * Decimal(10) ** usd_decimals
        )

        # Convert USD to quote token using pool prices
        if quote_sym == usd_token:
            # Quote is USD - use directly
            initial_quote = usd_amount_raw
        elif base_sym == usd_token:
            # Base is USD - convert USD to quote using pool price (r1/r0 = quote per base)
            # $1000 USD = X quote, where X = $1000 * (quote_reserve / usd_reserve)
            initial_quote = (usd_amount_raw * poolA.r1) / poolA.r0
        else:
            # Neither token is USD - need to estimate
            # Use a rough approximation: assume quote is WETH at $2500
            # $1000 = X WETH, where X = $1000 / $2500 = 0.4 WETH = 0.4 * 10^18
            eth_price_usd = Decimal("2500")
            initial_quote = (usd_amount_raw * Decimal(10) ** quote_decimals) / (
                eth_price_usd * Decimal(10) ** usd_decimals
            )

        # Leg 1: Buy base on poolA (quote -> base)
        # poolA reserves: r0=base, r1=quote
        amount_in_leg1 = initial_quote
        reserve_in_leg1 = poolA.r1  # quote reserve
        reserve_out_leg1 = poolA.r0  # base reserve

        # Depth guard on leg 1
        if amount_in_leg1 > MAX_DEPTH_FRACTION * reserve_in_leg1:
            logger.debug(
                f"Rejected by depth guard leg1: {poolA.dex} {base_sym}/{quote_sym} "
                f"(trade={float(amount_in_leg1):,.0f} > 10% of reserve={float(reserve_in_leg1):,.0f})"
            )
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
            logger.debug(
                f"Rejected by depth guard leg2: {poolB.dex} {base_sym}/{quote_sym} "
                f"(trade={float(amount_in_leg2):,.0f} > 10% of reserve={float(reserve_in_leg2):,.0f})"
            )
            return None

        final_quote_before_slip = swap_out(
            amount_in_leg2, reserve_in_leg2, reserve_out_leg2, poolB.fee
        )

        # Apply slippage haircut to final proceeds
        slippage_factor = Decimal(1) - self.config.slippage_decimal
        final_quote = final_quote_before_slip * slippage_factor

        # Calculate percentages
        gross_pct_raw = (final_quote_before_slip / initial_quote - 1) * 100

        # Sanity check: Cap profit at reasonable bounds
        # Real arbitrage opportunities are typically < 5%, anything > 100% is likely bad data
        MAX_PROFIT_PCT = Decimal("100")
        if gross_pct_raw > MAX_PROFIT_PCT or gross_pct_raw < -MAX_PROFIT_PCT:
            logger.debug(
                f"Rejected {poolA.dex} -> {poolB.dex} {base_sym}/{quote_sym}: "
                f"unrealistic profit {float(gross_pct_raw):.2f}% (likely bad reserve data)"
            )
            return None

        gross_pct = float(gross_pct_raw)
        net_quote = final_quote

        # Subtract gas cost if override set (convert USD to quote token units)
        if self.config.gas_cost_usd_override:
            # Gas cost is in USD, convert to quote token
            gas_cost_usd_raw = (
                Decimal(str(self.config.gas_cost_usd_override))
                * Decimal(10) ** usd_decimals
            )
            if quote_sym == usd_token:
                gas_cost_quote = gas_cost_usd_raw
            elif base_sym == usd_token:
                # Convert USD to quote using pool price
                gas_cost_quote = (gas_cost_usd_raw * poolA.r1) / poolA.r0
            else:
                # Estimate using WETH price
                eth_price_usd = Decimal("2500")
                gas_cost_quote = (gas_cost_usd_raw * Decimal(10) ** quote_decimals) / (
                    eth_price_usd * Decimal(10) ** usd_decimals
                )
            net_quote -= gas_cost_quote

        net_pct = float((net_quote / initial_quote - 1) * 100)

        # Calculate PnL in USD
        # We started with max_position_usd worth of quote token, ended with net_quote
        # Need to convert the profit back to USD
        if quote_sym == usd_token:
            # Quote is USD - direct conversion
            pnl_usd = float((net_quote - initial_quote) / Decimal(10) ** usd_decimals)
        elif base_sym == usd_token:
            # Base is USD, quote is something else (e.g., WETH)
            # We started with $1000 worth of WETH and ended with slightly different amount of WETH
            # Convert WETH to USD: WETH * (USDC per WETH) = USDC
            # USDC per WETH = r0 / r1
            usdc_per_weth = poolA.r0 / poolA.r1
            initial_usd = (initial_quote * usdc_per_weth) / Decimal(10) ** usd_decimals
            final_usd = (net_quote * usdc_per_weth) / Decimal(10) ** usd_decimals
            pnl_usd = float(final_usd - initial_usd)
        else:
            # Neither is USD - estimate using WETH price ($2500)
            eth_price_usd = Decimal("2500")
            pnl_usd = float(
                ((net_quote - initial_quote) * eth_price_usd)
                / Decimal(10) ** quote_decimals
            )

        cycle_str = (
            f"{quote_sym} -> {base_sym} ({poolA.dex}) -> {quote_sym} ({poolB.dex})"
        )

        # Build LegInfo for BreakevenGuard validation
        # Leg 1: Buy base with quote on poolA
        # Notional in USD
        leg1_notional = float(self.config.max_position_usd)
        leg1_price = float(amount_in_leg1 / base_amount)
        leg1 = LegInfo(
            pair=f"{base_sym}/{quote_sym}@{poolA.dex}",
            side="buy",
            price_used=leg1_price,
            price_source="ask",
            vwap_levels=1,
            slippage_pct=float(poolA.fee * 100),
            fee_pct=float(poolA.fee * 100),
            notional_quote=leg1_notional,
            latency_ms=0,
        )

        # Leg 2: Sell base for quote on poolB
        # Notional is also max_position_usd since we're selling the same amount we bought
        leg2_notional = float(self.config.max_position_usd)
        leg2_price = float(final_quote_before_slip / base_amount)
        leg2 = LegInfo(
            pair=f"{base_sym}/{quote_sym}@{poolB.dex}",
            side="sell",
            price_used=leg2_price,
            price_source="bid",
            vwap_levels=1,
            slippage_pct=float(self.config.slippage_decimal * 100),
            fee_pct=float(poolB.fee * 100),
            notional_quote=leg2_notional,
            latency_ms=0,
        )

        # Validate with BreakevenGuard
        # Note: For DEX, we have 2 legs not 3, and gas is in the config
        gas_units = 0
        gas_usd = (
            float(self.config.gas_cost_usd_override)
            if self.config.gas_cost_usd_override
            else 0.0
        )
        total_notional = float(self.config.max_position_usd)

        try:
            be_line = self.breakeven_guard.compute(
                legs=[leg1, leg2],
                gross_pct=gross_pct,
                gas_units=gas_units,
                gas_price_quote=gas_usd / total_notional if total_notional > 0 else 0.0,
                total_notional_quote=total_notional,
                threshold_pct=float(self.config.threshold_net_pct),
            )
            # Update net_pct from validated calculation
            net_pct = be_line.net_pct
        except (ValueError, AssertionError) as e:
            # Validation failed, skip this opportunity
            logger.debug(
                f"Rejected by BreakevenGuard: {poolA.dex} -> {poolB.dex} {base_sym}/{quote_sym} "
                f"(gross={gross_pct:.4f}%, error={e})"
            )
            return None

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
        """Log startup banner with config summary."""
        cfg = self.config
        c = Colors

        print(f"\n{c.CYAN}{c.BOLD}{'═' * 80}{c.RESET}")
        print(
            f"{c.CYAN}{c.BOLD}  DEX ARBITRAGE SCANNER {c.RESET}{c.CYAN}— Real-time Cross-DEX Opportunity Detection{c.RESET}"
        )
        print(f"{c.CYAN}{'═' * 80}{c.RESET}\n")

        print(f"  {c.BOLD}Configuration:{c.RESET}")
        print(
            f"    {c.DIM}Pools:{c.RESET} {c.GREEN}{len(self.pools)}{c.RESET} | {c.DIM}Scan Interval:{c.RESET} {c.GREEN}{cfg.poll_sec}s{c.RESET} | {c.DIM}Mode:{c.RESET} {c.GREEN}{'Single Scan' if cfg.once else 'Continuous'}{c.RESET}"
        )
        print(
            f"    {c.DIM}Trade Size:{c.RESET} {c.GREEN}${cfg.max_position_usd}{c.RESET} | {c.DIM}Profit Threshold:{c.RESET} {c.GREEN}{cfg.threshold_net_pct:.2f}% NET{c.RESET}"
        )

        gas_str = ""
        if cfg.gas_cost_usd_override:
            gas_str = f" + {c.YELLOW}gas({cfg.gas_pct:.2f}%){c.RESET}"

        print(
            f"    {c.DIM}Breakeven:{c.RESET} {c.YELLOW}{cfg.breakeven_pct:.2f}%{c.RESET} = {c.DIM}threshold({cfg.threshold_net_pct:.2f}%) + slippage({cfg.slippage_pct:.2f}%){gas_str}{c.RESET}"
        )
        print(f"\n{c.CYAN}{'═' * 80}{c.RESET}\n")

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

        # Normal mode: log full details for every scan
        c = Colors
        header = f"Top Arbitrage Routes (Scan #{scan_num})"
        print(f"\n  {c.BOLD}{c.BLUE}{header:^72}{c.RESET}")
        print(f"  {c.BLUE}{'─' * 72}{c.RESET}")

        # Show top 10 opportunities (matching CEX style)
        topn = min(10, len(rows))
        if topn == 0:
            print(f"  {c.DIM}(no valid cycles found){c.RESET}")
        else:
            for i, row in enumerate(rows[:topn], 1):
                # Extract fee info from the row's dexes
                # Get fees from the specific pools used (0.3% per swap × 2 swaps = 0.6%)
                fees_pct = 0.0
                pools_counted = set()
                for pool in self.pools:
                    if pool.dex == row.dexA and row.dexA not in pools_counted:
                        fees_pct += float(pool.fee * 100)
                        pools_counted.add(row.dexA)
                    elif pool.dex == row.dexB and row.dexB not in pools_counted:
                        fees_pct += float(pool.fee * 100)
                        pools_counted.add(row.dexB)
                    if len(pools_counted) >= 2:
                        break

                slippage_impact = self.config.slippage_pct
                gas_impact = (
                    self.config.gas_pct if self.config.gas_cost_usd_override else 0.0
                )

                # Profit icon and color
                is_profitable = row.net_pct >= self.config.threshold_net_pct
                profit_icon = "✓" if is_profitable else "✗"
                profit_color = c.GREEN if is_profitable else c.RED
                net_color = c.GREEN if row.net_pct > 0 else c.RED

                # Format cycle string (show first 3 tokens)
                cycle_parts = row.cycle.split(" -> ")
                if len(cycle_parts) >= 3:
                    cycle_str = " → ".join(cycle_parts[:3])
                else:
                    cycle_str = " → ".join(cycle_parts)

                # Show breakdown: Raw (after fees) − Slippage − Gas = Net
                print(
                    f"  {profit_color}{profit_icon}{c.RESET} {c.BOLD}{i:2d}.{c.RESET} {c.WHITE}{cycle_str:28s}{c.RESET} "
                    f"{c.DIM}Raw:{c.RESET} {row.gross_pct:+.2f}% {c.DIM}({fees_pct:.2f}% fees){c.RESET}  "
                    f"{c.DIM}Slip:{c.RESET} {slippage_impact:.2f}%  "
                    f"{c.DIM}Gas:{c.RESET} {gas_impact:.2f}%  "
                    f"{c.BOLD}Net:{c.RESET} {net_color}{row.net_pct:+.2f}%{c.RESET}"
                )

        # Show why line if no profitable opportunities
        if rows and len(opportunities) == 0:
            best = rows[0]

            # Calculate fees for best route
            fees_pct = 0.0
            pools_counted = set()
            for pool in self.pools:
                if pool.dex == best.dexA and best.dexA not in pools_counted:
                    fees_pct += float(pool.fee * 100)
                    pools_counted.add(best.dexA)
                elif pool.dex == best.dexB and best.dexB not in pools_counted:
                    fees_pct += float(pool.fee * 100)
                    pools_counted.add(best.dexB)
                if len(pools_counted) >= 2:
                    break

            # Calculate breakeven gross
            slippage_impact = self.config.slippage_pct
            gas_impact = (
                self.config.gas_pct if self.config.gas_cost_usd_override else 0.0
            )
            breakeven_gross = (
                self.config.threshold_net_pct + slippage_impact + gas_impact
            )
            gross_gap = breakeven_gross - best.gross_pct

            print(f"\n  {c.BLUE}{'─' * 72}{c.RESET}")
            print(
                f"  {c.YELLOW}⚠{c.RESET}  {c.BOLD}No Profitable Opportunities{c.RESET}"
            )
            print(
                f"     {c.DIM}Best route would lose{c.RESET} {c.RED}{abs(best.net_pct):.2f}%{c.RESET} "
                f"{c.DIM}(need{c.RESET} {c.YELLOW}{gross_gap:+.2f}%{c.RESET} "
                f"{c.DIM}more to break even){c.RESET}"
            )
            breakdown_msg = (
                f"     {c.DIM}Breakdown: Raw{c.RESET} {best.gross_pct:+.2f}% "
                f"{c.DIM}(fees {fees_pct:.2f}%) − Slip {slippage_impact:.2f}% "
                f"− Gas {gas_impact:.2f}% = Net{c.RESET} {c.RED}{best.net_pct:+.2f}%{c.RESET}"
            )
            print(breakdown_msg)

        # Show summary footer
        print(f"\n  {c.BLUE}{'─' * 72}{c.RESET}")
        if len(opportunities) > 0:
            print(
                f"  {c.GREEN}✓{c.RESET} {c.BOLD}{len(opportunities)} PROFITABLE{c.RESET} routes found!"
            )
        else:
            print(
                f"  {c.DIM}Summary: Checked {len(rows)} routes, 0 profitable{c.RESET}"
            )

        # EV stats
        ev_scan = (
            sum(self.pnl_history) / len(self.pnl_history) if self.pnl_history else 0.0
        )
        if len(self.pnl_history) >= 10:
            ev_color = c.GREEN if ev_scan > 0 else c.RED
            print(
                f"  {c.DIM}Expected Value:{c.RESET} {ev_color}${ev_scan:+.2f}/scan{c.RESET}"
            )

        print()

    def _print_opportunity(self, row: ArbRow, scan_num: int) -> None:
        """Log a single opportunity (for quiet mode)."""
        # Calculate fees for this route
        fees_pct = 0.0
        pools_counted = set()
        for pool in self.pools:
            if pool.dex == row.dexA and row.dexA not in pools_counted:
                fees_pct += float(pool.fee * 100)
                pools_counted.add(row.dexA)
            elif pool.dex == row.dexB and row.dexB not in pools_counted:
                fees_pct += float(pool.fee * 100)
                pools_counted.add(row.dexB)
            if len(pools_counted) >= 2:
                break

        logger.info(f"\nOPPORTUNITY FOUND! (Scan {scan_num})")
        logger.info("=" * 80)
        logger.info(f"  {row.cycle}")

        gas_str = ""
        if self.config.gas_cost_usd_override:
            gas_str = f" | Gas: {self.config.gas_pct:.2f}%"

        logger.info(
            f"  Raw: {row.gross_pct:+.2f}% (incl. fees {fees_pct:.2f}%) | "
            f"Slip: {self.config.slippage_pct:.2f}%{gas_str} | Net: {row.net_pct:+.2f}%"
        )
        logger.info(
            f"  Expected profit: ${abs(row.pnl_usd):.2f} on ${self.config.max_position_usd}"
        )
        logger.info(
            f"  Would execute: YES (net={row.net_pct:.2f}% > threshold={self.config.threshold_net_pct:.2f}%)"
        )
        logger.info("=" * 80)

    def _print_batch_summary(self, start_scan: int, end_scan: int) -> None:
        """Log summary for a batch of scans (for quiet mode)."""
        ema_str = ""
        if self.ema_gross is not None:
            ema_str = (
                f" | avg_gross={self.ema_gross:+.2f}% avg_net={self.ema_net:+.2f}%"
            )

        best_str = ""
        if self.batch_best_net is not None:
            indicator = (
                "[BAD]"
                if self.batch_best_net < self.config.threshold_net_pct
                else "[GOOD]"
            )
            best_str = f" | best_net={self.batch_best_net:+.2f}% {indicator}"

        ev_str = ""
        if self.pnl_history:
            ev_scan = sum(self.pnl_history) / len(self.pnl_history)
            ev_str = f" | EV/scan=${ev_scan:.2f}"

        logger.info(
            f"Scans {start_scan}-{end_scan}: 0 opportunities{best_str}{ema_str}{ev_str}"
        )

    def run(self) -> None:
        """
        Main loop: scan, print, sleep (synchronous).

        Runs indefinitely unless config.once=True.
        """
        # Block until pools are loaded
        if not self.pools:
            raise RuntimeError(
                "No pools loaded. Call fetch_pools() before run(). "
                "Refusing to scan with 0 pools to avoid stale or invalid opportunities."
            )

        self.print_banner()

        scan_num = 0
        while True:
            scan_num += 1
            try:
                rows = self.scan()
                self.print_results(rows, scan_num)
            except KeyboardInterrupt:
                logger.info("\n\nInterrupted by user")
                sys.exit(0)
            except Exception as e:
                logger.error(f"\nScan {scan_num} failed: {e}", exc_info=True)
                if self.config.once:
                    raise

            if self.config.once:
                break

            time.sleep(self.config.poll_sec)

    async def run_async(self) -> None:
        """
        Main loop: scan, print, sleep (async with concurrent reserve fetching).

        Uses scan_async() for 20-40x speedup on reserve fetching.
        Runs indefinitely unless config.once=True.

        Implements periodic pool rotation to discover new opportunities.
        """
        # Block until pools are loaded
        if not self.pools:
            raise RuntimeError(
                "No pools loaded. Call fetch_pools() before run_async(). "
                "Refusing to scan with 0 pools to avoid stale or invalid opportunities."
            )

        self.print_banner()

        scan_num = 0
        POOL_REFRESH_INTERVAL = (
            50  # Refresh pool list every 50 scans (~8 minutes at 10s intervals)
        )

        while True:
            scan_num += 1

            # Periodically refresh pool list to discover new opportunities
            if scan_num > 1 and scan_num % POOL_REFRESH_INTERVAL == 0:
                c = Colors
                print(
                    f"\n{c.CYAN}♻{c.RESET}  {c.DIM}Refreshing pool list (scan #{scan_num})...{c.RESET}"
                )
                try:
                    old_pool_count = len(self.pools)
                    self.fetch_pools()
                    new_pool_count = len(self.pools)

                    if new_pool_count != old_pool_count:
                        print(
                            f"   {c.GREEN}✓{c.RESET} Discovered {new_pool_count} pools (was {old_pool_count})"
                        )
                    else:
                        print(
                            f"   {c.DIM}Pool count unchanged ({new_pool_count}){c.RESET}\n"
                        )

                    # Clear cache after pool rotation to force fresh data
                    self._reserve_cache = {}
                    logger.info(f"Rotated pools: {old_pool_count} → {new_pool_count}")
                except Exception as e:
                    print(f"   {c.RED}✗{c.RESET} Failed to refresh pools: {e}")
                    logger.error(f"Pool rotation failed: {e}")

            try:
                rows = await self.scan_async()
                self.print_results(rows, scan_num)
            except KeyboardInterrupt:
                # Re-raise to be handled by main() signal handler
                raise
            except Exception as e:
                logger.error(f"\nScan {scan_num} failed: {e}", exc_info=True)
                if self.config.once:
                    raise

            if self.config.once:
                break

            await asyncio.sleep(self.config.poll_sec)
