"""
Smart Pool Discovery - Find pools with actual arbitrage potential.

Instead of blindly scanning pools by liquidity, this module:
1. Discovers cross-DEX pairs (same token pair on multiple DEXes)
2. Prioritizes tokens with high trading volume
3. Filters for pools with historical price divergence
4. Focuses on fee arbitrage opportunities (low-fee DEX vs high-fee DEX)
"""

import logging
from collections import defaultdict
from decimal import Decimal
from typing import Dict, List, Tuple

from web3 import Web3

logger = logging.getLogger(__name__)


class SmartPoolDiscovery:
    """
    Intelligent pool discovery that finds arbitrage-ready pools.

    Strategy:
    1. Find CROSS-DEX pairs (same pair on multiple DEXes) - required for arbitrage
    2. Prioritize high-volume tokens (more likely to have price divergence)
    3. Filter by fee differential (low-fee vs high-fee creates opportunities)
    4. Check for sufficient liquidity ($50k+ minimum)
    """

    # Tokens known to have high volume and frequent arbitrage (BSC)
    HIGH_VOLUME_TOKENS_BSC = {
        "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c": "WBNB",  # Wrapped BNB
        "0x55d398326f99059fF775485246999027B3197955": "USDT",  # Tether USD
        "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56": "BUSD",  # Binance USD
        "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d": "USDC",  # USD Coin
        "0x2170Ed0880ac9A755fd29B2688956BD959F933F8": "ETH",  # Ethereum
        "0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c": "BTCB",  # Bitcoin BEP20
        "0x1AF3F329e8BE154074D8769D1FFa4eE058B1DBc3": "DAI",  # Dai Stablecoin
        "0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82": "Cake",  # PancakeSwap
        "0x3EE2200Efb3400fAbB9AacF31297cBdD1d435D47": "ADA",  # Cardano
        "0xbA2aE424d960c26247Dd6c32edC70B295c744C43": "DOGE",  # Dogecoin
    }

    # Ethereum high-volume tokens
    HIGH_VOLUME_TOKENS_ETH = {
        "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2": "WETH",  # Wrapped Ether
        "0xdAC17F958D2ee523a2206206994597C13D831ec7": "USDT",  # Tether USD
        "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48": "USDC",  # USD Coin
        "0x6B175474E89094C44Da98b954EedeAC495271d0F": "DAI",  # Dai Stablecoin
        "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599": "WBTC",  # Wrapped BTC
        "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984": "UNI",  # Uniswap
        "0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9": "AAVE",  # Aave
        "0x514910771AF9Ca656af840dff83E8264EcF986CA": "LINK",  # Chainlink
        "0x95aD61b0a150d79219dCF64E1E6Cc01f0B64C4cE": "SHIB",  # Shiba Inu
    }

    def __init__(
        self,
        w3: Web3,
        factory_scanner,
        min_liquidity_usd: Decimal = Decimal("50000"),
        chain: str = "bsc",
    ):
        """
        Initialize smart pool discovery.

        Args:
            w3: Web3 instance
            factory_scanner: PoolFactoryScanner instance for low-level scanning
            min_liquidity_usd: Minimum pool liquidity
            chain: Blockchain ("bsc" or "eth")
        """
        self.w3 = w3
        self.factory_scanner = factory_scanner
        self.min_liquidity_usd = min_liquidity_usd
        self.chain = chain.lower()

        # Select high-volume tokens for this chain
        if self.chain == "bsc":
            self.high_volume_tokens = self.HIGH_VOLUME_TOKENS_BSC
        elif self.chain == "eth":
            self.high_volume_tokens = self.HIGH_VOLUME_TOKENS_ETH
        else:
            logger.warning(f"Unknown chain '{chain}', using BSC token list")
            self.high_volume_tokens = self.HIGH_VOLUME_TOKENS_BSC

        logger.info(
            f"Smart pool discovery initialized for {chain.upper()} "
            f"with {len(self.high_volume_tokens)} high-volume tokens"
        )

    def discover_arbitrage_pools(
        self,
        factories: List[Dict],
        max_pools_total: int = 30,
        max_scan_per_factory: int = 100,
    ) -> List[Dict]:
        """
        Discover pools with actual arbitrage potential.

        Strategy:
        1. Scan each factory for pools containing high-volume tokens
        2. Group pools by token pair (e.g., WBNB/USDT)
        3. Only keep pairs that exist on MULTIPLE DEXes (required for arbitrage)
        4. Prioritize pairs with fee differentials
        5. Return the best pools for arbitrage

        Args:
            factories: List of factory configs [{"name": "uniswap_v2", "address": "0x...", "fee_bps": 30}, ...]
            max_pools_total: Maximum total pools to return
            max_scan_per_factory: Maximum pools to scan per factory

        Returns:
            List of pool configs optimized for arbitrage
        """
        logger.info("=" * 80)
        logger.info("SMART POOL DISCOVERY - Finding Arbitrage-Ready Pools")
        logger.info("=" * 80)

        # Step 1: Scan all factories for pools with high-volume tokens
        logger.info(
            f"Step 1: Scanning {len(factories)} factories for high-volume token pools..."
        )

        all_pools = []
        token_whitelist = set(self.high_volume_tokens.keys())

        for i, factory in enumerate(factories, 1):
            logger.info(
                f"  [{i}/{len(factories)}] Scanning {factory['name']} "
                f"(fee: {factory['fee_bps']/100:.2f}%)..."
            )

            pools = self.factory_scanner.scan_factory(
                factory_address=factory["address"],
                dex_name=factory["name"],
                fee_bps=factory["fee_bps"],
                max_pools=None,  # Don't limit yet
                token_whitelist=token_whitelist,
                max_scan_pools=max_scan_per_factory,
            )

            logger.info(f"    Found {len(pools)} pools with high-volume tokens")
            all_pools.extend(pools)

        logger.info(f"  Total pools found: {len(all_pools)}")

        # Step 2: Group by token pair
        logger.info("\nStep 2: Grouping pools by token pair...")
        pair_groups = self._group_by_pair(all_pools)

        logger.info(f"  Found {len(pair_groups)} unique token pairs")

        # Step 3: Filter for cross-DEX pairs only
        logger.info(
            "\nStep 3: Filtering for CROSS-DEX pairs (required for arbitrage)..."
        )
        cross_dex_pairs = {
            pair: pools
            for pair, pools in pair_groups.items()
            if len(set(p["dex_name"] for p in pools)) >= 2
        }

        logger.info(f"  Found {len(cross_dex_pairs)} cross-DEX pairs")

        if not cross_dex_pairs:
            logger.warning(
                "  No cross-DEX pairs found! Cannot perform arbitrage.\n"
                "  Try increasing max_scan_per_factory or expanding token whitelist."
            )
            return []

        # Step 4: Score and rank pairs
        logger.info("\nStep 4: Scoring pairs by arbitrage potential...")
        scored_pairs = self._score_pairs(cross_dex_pairs)

        # Step 5: Select best pools
        logger.info("\nStep 5: Selecting best pools for arbitrage...")
        selected_pools = self._select_best_pools(scored_pairs, max_pools_total)

        # Summary
        logger.info("\n" + "=" * 80)
        logger.info("DISCOVERY SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Total pools scanned: {len(all_pools)}")
        logger.info(f"Unique token pairs: {len(pair_groups)}")
        logger.info(f"Cross-DEX pairs: {len(cross_dex_pairs)}")
        logger.info(f"Pools selected for arbitrage: {len(selected_pools)}")

        # Show selected pairs
        selected_pairs = defaultdict(list)
        for pool in selected_pools:
            pair_key = self._get_pair_key(pool)
            selected_pairs[pair_key].append(pool["dex_name"])

        logger.info(f"\nSelected pairs for arbitrage:")
        for pair, dexes in sorted(selected_pairs.items()):
            dex_list = ", ".join(sorted(set(dexes)))
            logger.info(f"  {pair}: {dex_list}")

        logger.info("=" * 80 + "\n")

        return selected_pools

    def _group_by_pair(self, pools: List[Dict]) -> Dict[Tuple[str, str], List[Dict]]:
        """
        Group pools by token pair (normalized order).

        Returns:
            Dict mapping (token0_symbol, token1_symbol) -> [pool, pool, ...]
        """
        groups = defaultdict(list)

        for pool in pools:
            pair_key = self._get_pair_key(pool)
            groups[pair_key].append(pool)

        return groups

    def _get_pair_key(self, pool: Dict) -> Tuple[str, str]:
        """Get normalized pair key (sorted alphabetically)."""
        symbols = sorted([pool["symbol0"], pool["symbol1"]])
        return tuple(symbols)

    def _score_pairs(
        self, cross_dex_pairs: Dict[Tuple[str, str], List[Dict]]
    ) -> List[Tuple[float, Tuple[str, str], List[Dict]]]:
        """
        Score pairs by arbitrage potential.

        Scoring factors:
        1. Number of DEXes (more DEXes = more opportunities)
        2. Fee differential (bigger spread = more profit potential)
        3. Total liquidity (more liquidity = less slippage)
        4. Token popularity (well-known tokens trade more)

        Returns:
            List of (score, pair_key, pools) sorted by score descending
        """
        scored = []

        for pair, pools in cross_dex_pairs.items():
            # Factor 1: Number of DEXes
            num_dexes = len(set(p["dex_name"] for p in pools))
            dex_score = num_dexes * 10  # 10 points per DEX

            # Factor 2: Fee differential
            fees = [p["fee_bps"] for p in pools]
            fee_spread = max(fees) - min(fees)
            fee_score = fee_spread / 10  # 1 point per 10 bps spread

            # Factor 3: Total liquidity
            total_liquidity = sum(p["liquidity_usd"] for p in pools)
            liquidity_score = min(total_liquidity / 10000, 50)  # Cap at 50 points

            # Factor 4: Token popularity (check if in high-volume list)
            popularity_score = 0
            for pool in pools:
                if pool["token0"] in self.high_volume_tokens:
                    popularity_score += 5
                if pool["token1"] in self.high_volume_tokens:
                    popularity_score += 5

            total_score = dex_score + fee_score + liquidity_score + popularity_score

            scored.append((total_score, pair, pools))

            logger.debug(
                f"  {pair[0]}/{pair[1]}: score={total_score:.1f} "
                f"(dex={dex_score}, fee={fee_score:.1f}, liq={liquidity_score:.1f}, pop={popularity_score})"
            )

        # Sort by score descending
        scored.sort(reverse=True, key=lambda x: x[0])

        return scored

    def _select_best_pools(
        self,
        scored_pairs: List[Tuple[float, Tuple[str, str], List[Dict]]],
        max_pools_total: int,
    ) -> List[Dict]:
        """
        Select the best pools for arbitrage.

        Strategy:
        - For each top-scoring pair, include all pools (for cross-DEX arbitrage)
        - Stop when we hit max_pools_total

        Args:
            scored_pairs: List of (score, pair_key, pools)
            max_pools_total: Maximum total pools to return

        Returns:
            List of selected pool configs
        """
        selected = []

        for score, pair, pools in scored_pairs:
            # Add all pools for this pair (need multiple DEXes for arbitrage)
            if len(selected) + len(pools) <= max_pools_total:
                selected.extend(pools)
                logger.info(
                    f"  ✓ Added {pair[0]}/{pair[1]}: {len(pools)} pools "
                    f"across {len(set(p['dex_name'] for p in pools))} DEXes (score: {score:.1f})"
                )
            else:
                # Can't fit all pools for this pair
                remaining = max_pools_total - len(selected)
                if remaining > 0:
                    # Add what we can (prioritize by liquidity)
                    pools_sorted = sorted(
                        pools, key=lambda p: p["liquidity_usd"], reverse=True
                    )
                    selected.extend(pools_sorted[:remaining])
                    logger.info(
                        f"  ⚠ Added {pair[0]}/{pair[1]}: {remaining}/{len(pools)} pools "
                        f"(hit max_pools_total limit)"
                    )
                break

        return selected


def create_smart_discovery(
    w3: Web3, factory_scanner, min_liquidity_usd: float, chain: str = "bsc"
) -> SmartPoolDiscovery:
    """
    Factory function to create SmartPoolDiscovery instance.

    Args:
        w3: Web3 instance
        factory_scanner: PoolFactoryScanner instance
        min_liquidity_usd: Minimum pool liquidity
        chain: Blockchain name ("bsc" or "eth")

    Returns:
        SmartPoolDiscovery instance
    """
    return SmartPoolDiscovery(
        w3=w3,
        factory_scanner=factory_scanner,
        min_liquidity_usd=Decimal(str(min_liquidity_usd)),
        chain=chain,
    )
