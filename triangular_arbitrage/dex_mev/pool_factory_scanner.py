"""
Dynamic pool discovery for DEX aggregators.

Automatically discovers all pools from factory contracts on-chain,
eliminating the need for hardcoded pool configurations.
"""

import logging
import time
from decimal import Decimal
from typing import Dict, List, Optional, Set, Tuple

from web3 import Web3

logger = logging.getLogger(__name__)


class PoolFactoryScanner:
    """
    Discovers pools dynamically from DEX factory contracts.

    Supports Uniswap V2-style factories that emit PairCreated events.
    Automatically filters by liquidity to focus on active pools.
    """

    # Uniswap V2 Factory ABI (minimal - just what we need)
    FACTORY_ABI = [
        {
            "constant": True,
            "inputs": [],
            "name": "allPairsLength",
            "outputs": [{"name": "", "type": "uint256"}],
            "type": "function",
        },
        {
            "constant": True,
            "inputs": [{"name": "", "type": "uint256"}],
            "name": "allPairs",
            "outputs": [{"name": "", "type": "address"}],
            "type": "function",
        },
        {
            "constant": True,
            "inputs": [
                {"name": "", "type": "address"},
                {"name": "", "type": "address"},
            ],
            "name": "getPair",
            "outputs": [{"name": "", "type": "address"}],
            "type": "function",
        },
        {
            "anonymous": False,
            "inputs": [
                {"indexed": True, "name": "token0", "type": "address"},
                {"indexed": True, "name": "token1", "type": "address"},
                {"indexed": False, "name": "pair", "type": "address"},
                {"indexed": False, "name": "", "type": "uint256"},
            ],
            "name": "PairCreated",
            "type": "event",
        },
    ]

    # Uniswap V2 Pair ABI (minimal)
    PAIR_ABI = [
        {
            "constant": True,
            "inputs": [],
            "name": "token0",
            "outputs": [{"name": "", "type": "address"}],
            "type": "function",
        },
        {
            "constant": True,
            "inputs": [],
            "name": "token1",
            "outputs": [{"name": "", "type": "address"}],
            "type": "function",
        },
        {
            "constant": True,
            "inputs": [],
            "name": "getReserves",
            "outputs": [
                {"name": "reserve0", "type": "uint112"},
                {"name": "reserve1", "type": "uint112"},
                {"name": "blockTimestampLast", "type": "uint32"},
            ],
            "type": "function",
        },
    ]

    # ERC20 ABI (minimal - for token info)
    ERC20_ABI = [
        {
            "constant": True,
            "inputs": [],
            "name": "symbol",
            "outputs": [{"name": "", "type": "string"}],
            "type": "function",
        },
        {
            "constant": True,
            "inputs": [],
            "name": "decimals",
            "outputs": [{"name": "", "type": "uint8"}],
            "type": "function",
        },
    ]

    def __init__(
        self,
        w3: Web3,
        min_liquidity_usd: Decimal = Decimal("10000"),
        eth_price_usd: Decimal = Decimal("2500"),
    ):
        """
        Initialize pool factory scanner.

        Args:
            w3: Web3 instance connected to RPC
            min_liquidity_usd: Minimum pool liquidity in USD (default $10k)
            eth_price_usd: ETH price for liquidity calculations (default $2500)
        """
        self.w3 = w3
        self.min_liquidity_usd = min_liquidity_usd
        self.eth_price_usd = eth_price_usd

        # Cache for discovered pools and tokens
        self.discovered_pools: Dict[str, Dict] = {}
        self.token_info_cache: Dict[str, Dict] = {}

        logger.info(
            f"Pool factory scanner initialized (min liquidity: ${min_liquidity_usd})"
        )

    def scan_factory(
        self,
        factory_address: str,
        dex_name: str,
        fee_bps: int = 30,
        max_pools: Optional[int] = None,
        token_whitelist: Optional[Set[str]] = None,
        max_scan_pools: Optional[int] = None,
    ) -> List[Dict]:
        """
        Scan a factory contract and discover all pools.

        Args:
            factory_address: Factory contract address
            dex_name: Name of the DEX (e.g., "uniswap_v2")
            fee_bps: Trading fee in basis points (default 30 = 0.3%)
            max_pools: Maximum number of pools to return (sorted by liquidity)
            token_whitelist: Only include pools with these tokens (optional)
            max_scan_pools: Maximum number of pools to scan (optimization - stops early)

        Returns:
            List of pool configurations with:
                - address: Pool contract address
                - token0: First token address
                - token1: Second token address
                - symbol0: First token symbol
                - symbol1: Second token symbol
                - decimals0: First token decimals
                - decimals1: Second token decimals
                - reserve0: Current reserve of token0
                - reserve1: Current reserve of token1
                - liquidity_usd: Estimated liquidity in USD
        """
        logger.info(f"Scanning {dex_name} factory at {factory_address}")
        print(f"\r  {dex_name}: Querying factory contract...", end="", flush=True)
        logger.debug(f"Querying {dex_name} factory contract for total pair count...")

        try:
            factory = self.w3.eth.contract(
                address=Web3.to_checksum_address(factory_address),
                abi=self.FACTORY_ABI,
            )

            # Get total number of pairs (this RPC call can be slow)
            logger.debug(f"Calling {dex_name}.allPairsLength()...")
            try:
                total_pairs = factory.functions.allPairsLength().call()
                print(
                    f"\r  {dex_name}: Found {total_pairs:,} pairs, scanning...",
                    end="",
                    flush=True,
                )
                logger.info(
                    f"✓ Found {total_pairs:,} total pairs in {dex_name} factory"
                )
            except Exception as e:
                print(f"\r  {dex_name}: ✗ Failed ({e})")
                logger.error(f"Failed to get pair count from {dex_name}: {e}")
                raise

            # Apply max_scan_pools limit if specified
            scan_limit = (
                min(total_pairs, max_scan_pools) if max_scan_pools else total_pairs
            )

            if max_scan_pools and scan_limit < total_pairs:
                logger.info(
                    f"Limiting {dex_name} scan to first {scan_limit} pools (out of {total_pairs:,})"
                )

            # Log initial status
            logger.debug(f"Scanning {dex_name} pools (this may take 1-2 minutes)...")

            pools = []
            for i in range(scan_limit):
                try:
                    pair_address = factory.functions.allPairs(i).call()
                    pool_info = self._scan_pool(
                        pair_address, dex_name, fee_bps, token_whitelist
                    )

                    if pool_info:
                        pools.append(pool_info)

                    # Log progress every 20 pools (reduced noise)
                    if (i + 1) % 20 == 0:
                        pct = ((i + 1) / scan_limit) * 100
                        # Use \r to overwrite previous line (cleaner output)
                        print(
                            f"\r  {dex_name}: {i + 1}/{scan_limit} ({pct:.0f}%) - {len(pools)} pools qualify",
                            end="",
                            flush=True,
                        )
                        logger.debug(
                            f"{dex_name} progress: {i + 1}/{scan_limit} ({pct:.1f}%) - {len(pools)} pools qualify so far"
                        )

                    # Small delay every 10 calls to avoid rate limiting (increased to 0.2s)
                    if (i + 1) % 10 == 0:
                        time.sleep(0.2)

                except Exception as e:
                    logger.debug(f"Error scanning pool {i}: {e}")
                    continue

            # Sort by liquidity (highest first)
            pools.sort(key=lambda p: p.get("liquidity_usd", 0), reverse=True)

            # Apply max_pools limit if specified
            if max_pools and len(pools) > max_pools:
                logger.info("Limiting to top %d pools by liquidity", max_pools)
                pools = pools[:max_pools]

            # Clear the progress line and show final result
            print(
                f"\r  {dex_name}: ✓ Discovered {len(pools)} pools (>${self.min_liquidity_usd:,.0f} liquidity)"
            )
            logger.info(
                f"Discovered {len(pools)} pools from {dex_name} "
                f"(filtered by liquidity >= ${self.min_liquidity_usd})"
            )

            return pools

        except Exception as e:
            logger.error(f"Error scanning factory {factory_address}: {e}")
            return []

    def _scan_pool(
        self,
        pair_address: str,
        dex_name: str,
        fee_bps: int,
        token_whitelist: Optional[Set[str]],
    ) -> Optional[Dict]:
        """
        Scan a single pool and extract information.

        Args:
            pair_address: Pool contract address
            dex_name: Name of the DEX
            fee_bps: Trading fee in basis points
            token_whitelist: Optional token whitelist

        Returns:
            Pool info dict or None if pool doesn't meet criteria
        """
        try:
            pair = self.w3.eth.contract(
                address=Web3.to_checksum_address(pair_address),
                abi=self.PAIR_ABI,
            )

            # Get token addresses
            token0_addr = pair.functions.token0().call()
            token1_addr = pair.functions.token1().call()

            # Apply whitelist filter if specified
            if token_whitelist:
                if (
                    token0_addr.lower() not in token_whitelist
                    and token1_addr.lower() not in token_whitelist
                ):
                    return None

            # Get token info
            token0_info = self._get_token_info(token0_addr)
            token1_info = self._get_token_info(token1_addr)

            if not token0_info or not token1_info:
                return None

            # Get reserves
            reserves = pair.functions.getReserves().call()
            reserve0 = Decimal(reserves[0])
            reserve1 = Decimal(reserves[1])

            # Skip pools with zero reserves
            if reserve0 == 0 or reserve1 == 0:
                return None

            # Estimate liquidity in USD
            liquidity_usd = self._estimate_liquidity_usd(
                reserve0, reserve1, token0_info, token1_info
            )

            # Filter by minimum liquidity
            if liquidity_usd < self.min_liquidity_usd:
                return None

            return {
                "address": pair_address,
                "dex_name": dex_name,
                "fee_bps": fee_bps,
                "token0": token0_addr,
                "token1": token1_addr,
                "symbol0": token0_info["symbol"],
                "symbol1": token1_info["symbol"],
                "decimals0": token0_info["decimals"],
                "decimals1": token1_info["decimals"],
                "reserve0": str(reserve0),
                "reserve1": str(reserve1),
                "liquidity_usd": float(liquidity_usd),
            }

        except Exception as e:
            logger.debug(f"Error scanning pool {pair_address}: {e}")
            return None

    def _get_token_info(self, token_address: str) -> Optional[Dict]:
        """
        Get token symbol and decimals.

        Args:
            token_address: Token contract address

        Returns:
            Dict with symbol and decimals, or None if error
        """
        # Check cache first
        addr_lower = token_address.lower()
        if addr_lower in self.token_info_cache:
            return self.token_info_cache[addr_lower]

        try:
            token = self.w3.eth.contract(
                address=Web3.to_checksum_address(token_address),
                abi=self.ERC20_ABI,
            )

            symbol = token.functions.symbol().call()
            decimals = token.functions.decimals().call()

            info = {"symbol": symbol, "decimals": decimals}
            self.token_info_cache[addr_lower] = info

            return info

        except Exception as e:
            logger.debug(f"Error getting token info for {token_address}: {e}")
            return None

    def _estimate_liquidity_usd(
        self,
        reserve0: Decimal,
        reserve1: Decimal,
        token0_info: Dict,
        token1_info: Dict,
    ) -> Decimal:
        """
        Estimate pool liquidity in USD.

        Uses simple heuristics:
        - If one token is WETH, use ETH price
        - If one token is stablecoin (USDC/USDT/DAI), use 1:1 USD
        - Otherwise, use reserve1 * 2 as rough estimate

        Args:
            reserve0: Reserve of token0 (raw units)
            reserve1: Reserve of token1 (raw units)
            token0_info: Token0 info (symbol, decimals)
            token1_info: Token1 info (symbol, decimals)

        Returns:
            Estimated liquidity in USD
        """
        # Adjust for decimals
        adj_reserve0 = reserve0 / Decimal(10 ** token0_info["decimals"])
        adj_reserve1 = reserve1 / Decimal(10 ** token1_info["decimals"])

        symbol0 = token0_info["symbol"]
        symbol1 = token1_info["symbol"]

        # Check if WETH is involved
        if symbol0 in ["WETH", "ETH"]:
            return adj_reserve0 * self.eth_price_usd * 2
        if symbol1 in ["WETH", "ETH"]:
            return adj_reserve1 * self.eth_price_usd * 2

        # Check if stablecoin is involved
        stablecoins = ["USDC", "USDT", "DAI", "BUSD", "FRAX"]
        if symbol0 in stablecoins:
            return adj_reserve0 * 2
        if symbol1 in stablecoins:
            return adj_reserve1 * 2

        # Fallback: assume token1 is worth ~$1 (very rough)
        return adj_reserve1 * 2

    def scan_multiple_factories(
        self,
        factories: List[Tuple[str, str, int]],
        max_pools_per_factory: Optional[int] = None,
        token_whitelist: Optional[Set[str]] = None,
        max_scan_pools: Optional[int] = None,
    ) -> Dict[str, List[Dict]]:
        """
        Scan multiple factory contracts.

        Args:
            factories: List of (factory_address, dex_name, fee_bps) tuples
            max_pools_per_factory: Max pools per factory
            token_whitelist: Only include pools with these tokens
            max_scan_pools: Maximum number of pools to scan per factory

        Returns:
            Dict mapping dex_name to list of pool configs
        """
        results = {}

        print(f"\n  Scanning {len(factories)} DEX factories...")
        logger.info(f"Starting scan of {len(factories)} factories...")

        for i, (factory_address, dex_name, fee_bps) in enumerate(factories, 1):
            print(f"  [{i}/{len(factories)}] ", end="")
            logger.info(f"[{i}/{len(factories)}] Scanning {dex_name}...")
            pools = self.scan_factory(
                factory_address=factory_address,
                dex_name=dex_name,
                fee_bps=fee_bps,
                max_pools=max_pools_per_factory,
                token_whitelist=token_whitelist,
                max_scan_pools=max_scan_pools,
            )
            results[dex_name] = pools

        total_pools = sum(len(pools) for pools in results.values())
        print(f"\n  ✓ Total: {total_pools} pools discovered\n")
        logger.info(f"Total pools discovered across all factories: {total_pools}")

        return results

    def get_common_tokens(self, pools: List[Dict], top_n: int = 20) -> List[str]:
        """
        Get most common tokens across discovered pools.

        Args:
            pools: List of pool configs
            top_n: Return top N tokens by frequency

        Returns:
            List of token symbols sorted by frequency
        """
        token_counts: Dict[str, int] = {}

        for pool in pools:
            for symbol_key in ["symbol0", "symbol1"]:
                symbol = pool.get(symbol_key)
                if symbol:
                    token_counts[symbol] = token_counts.get(symbol, 0) + 1

        # Sort by frequency
        sorted_tokens = sorted(token_counts.items(), key=lambda x: x[1], reverse=True)

        return [token for token, _ in sorted_tokens[:top_n]]
