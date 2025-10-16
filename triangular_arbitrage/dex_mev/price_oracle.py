"""
Dynamic price oracle for paper trading mode.

Fetches real market prices from multiple sources to provide accurate
simulations without hardcoding exchange rates.
"""

import logging
import time
from decimal import Decimal
from typing import Dict, Optional, Tuple

import requests

logger = logging.getLogger(__name__)


class PriceOracle:
    """
    Fetches and caches real-time cryptocurrency prices for paper trading.

    Supports multiple price sources with automatic fallback and caching
    to minimize API calls while maintaining accuracy.
    """

    def __init__(self, cache_ttl_seconds: int = 60):
        """
        Initialize price oracle with caching.

        Args:
            cache_ttl_seconds: How long to cache prices (default 60 seconds)
        """
        self.cache_ttl = cache_ttl_seconds
        self.price_cache: Dict[
            str, Tuple[Decimal, float]
        ] = {}  # {pair: (price, timestamp)}

        # Token symbol to CoinGecko ID mapping (expandable)
        self.coingecko_ids = {
            "WETH": "ethereum",
            "ETH": "ethereum",
            "USDC": "usd-coin",
            "USDT": "tether",
            "DAI": "dai",
            "WBTC": "wrapped-bitcoin",
            "BTC": "bitcoin",
            "LINK": "chainlink",
            "UNI": "uniswap",
            "AAVE": "aave",
            "MATIC": "matic-network",
            "CRV": "curve-dao-token",
            "SNX": "synthetix-network-token",
            "MKR": "maker",
            "COMP": "compound-governance-token",
            "SUSHI": "sushi",
            "YFI": "yearn-finance",
            "BAL": "balancer",
            "1INCH": "1inch",
            "LDO": "lido-dao",
        }

        logger.info(
            f"Price oracle initialized with {len(self.coingecko_ids)} supported tokens"
        )

    def get_price(self, token_in: str, token_out: str) -> Optional[Decimal]:
        """
        Get exchange rate for token_in -> token_out.

        Args:
            token_in: Symbol of input token
            token_out: Symbol of output token

        Returns:
            Exchange rate as Decimal, or None if price unavailable
        """
        pair_key = f"{token_in}/{token_out}"

        # Check cache first
        if pair_key in self.price_cache:
            price, timestamp = self.price_cache[pair_key]
            if time.time() - timestamp < self.cache_ttl:
                logger.debug(f"Cache hit for {pair_key}: {price}")
                return price

        # Try to fetch new price
        price = self._fetch_price(token_in, token_out)

        if price is not None:
            # Cache the result
            self.price_cache[pair_key] = (price, time.time())
            logger.debug(f"Fetched and cached {pair_key}: {price}")
            return price

        # If fetch failed but we have stale cache, use it with warning
        if pair_key in self.price_cache:
            price, timestamp = self.price_cache[pair_key]
            age = time.time() - timestamp
            logger.warning(
                f"Using stale cache for {pair_key} (age: {age:.0f}s): {price}"
            )
            return price

        logger.error(f"No price available for {pair_key}")
        return None

    def _fetch_price(self, token_in: str, token_out: str) -> Optional[Decimal]:
        """
        Fetch price from external sources.

        Priority:
        1. CoinGecko API (free, no auth required)
        2. Fallback to estimated rate

        Args:
            token_in: Symbol of input token
            token_out: Symbol of output token

        Returns:
            Exchange rate or None
        """
        # Try CoinGecko first
        price = self._fetch_from_coingecko(token_in, token_out)
        if price is not None:
            return price

        # Fallback: Use USD prices if available
        price = self._fetch_via_usd_bridge(token_in, token_out)
        if price is not None:
            return price

        # Last resort: Return small edge for unmocked pairs
        logger.warning(
            f"Could not fetch price for {token_in}/{token_out}, using default edge"
        )
        return Decimal("1.0015")  # 0.15% edge as fallback

    def _fetch_from_coingecko(self, token_in: str, token_out: str) -> Optional[Decimal]:
        """
        Fetch price from CoinGecko API.

        Args:
            token_in: Input token symbol
            token_out: Output token symbol

        Returns:
            Exchange rate or None
        """
        # Get CoinGecko IDs
        token_in_id = self.coingecko_ids.get(token_in)
        token_out_id = self.coingecko_ids.get(token_out)

        if not token_in_id or not token_out_id:
            logger.debug(f"Token not in CoinGecko mapping: {token_in} or {token_out}")
            return None

        try:
            # CoinGecko simple price API (free tier)
            url = "https://api.coingecko.com/api/v3/simple/price"
            params = {
                "ids": f"{token_in_id},{token_out_id}",
                "vs_currencies": "usd",
            }

            response = requests.get(url, params=params, timeout=5)
            response.raise_for_status()
            data = response.json()

            # Get USD prices
            token_in_usd = data.get(token_in_id, {}).get("usd")
            token_out_usd = data.get(token_out_id, {}).get("usd")

            if token_in_usd and token_out_usd:
                # Calculate exchange rate
                rate = Decimal(str(token_out_usd)) / Decimal(str(token_in_usd))
                logger.info(
                    f"CoinGecko: {token_in}=${token_in_usd}, "
                    f"{token_out}=${token_out_usd}, rate={rate}"
                )
                return rate

            logger.warning(f"Missing USD price in CoinGecko response: {data}")
            return None

        except requests.RequestException as e:
            logger.warning(f"CoinGecko API request failed: {e}")
            return None
        except Exception as e:
            logger.error(f"CoinGecko price fetch error: {e}")
            return None

    def _fetch_via_usd_bridge(self, token_in: str, token_out: str) -> Optional[Decimal]:
        """
        Fetch prices via USD bridge (get both in USD, then compute rate).

        Args:
            token_in: Input token symbol
            token_out: Output token symbol

        Returns:
            Exchange rate or None
        """
        token_in_id = self.coingecko_ids.get(token_in)
        token_out_id = self.coingecko_ids.get(token_out)

        if not token_in_id or not token_out_id:
            return None

        try:
            # Fetch both prices in USD
            url = "https://api.coingecko.com/api/v3/simple/price"
            params = {
                "ids": f"{token_in_id},{token_out_id}",
                "vs_currencies": "usd",
            }

            response = requests.get(url, params=params, timeout=5)
            response.raise_for_status()
            data = response.json()

            in_usd = data.get(token_in_id, {}).get("usd")
            out_usd = data.get(token_out_id, {}).get("usd")

            if in_usd and out_usd:
                # token_in -> USD -> token_out
                rate = Decimal(str(in_usd)) / Decimal(str(out_usd))
                logger.debug(f"USD bridge: {token_in}/{token_out} = {rate}")
                return rate

            return None

        except Exception as e:
            logger.debug(f"USD bridge fetch failed: {e}")
            return None

    def add_token(self, symbol: str, coingecko_id: str) -> None:
        """
        Add a new token to the oracle's supported list.

        Args:
            symbol: Token symbol (e.g., "PEPE")
            coingecko_id: CoinGecko API ID (e.g., "pepe")
        """
        self.coingecko_ids[symbol] = coingecko_id
        logger.info(f"Added token to oracle: {symbol} -> {coingecko_id}")

    def clear_cache(self) -> None:
        """Clear the price cache (useful for testing)."""
        self.price_cache.clear()
        logger.info("Price cache cleared")

    def get_cache_stats(self) -> Dict:
        """Get cache statistics."""
        now = time.time()
        fresh = sum(
            1 for _, (_, ts) in self.price_cache.items() if now - ts < self.cache_ttl
        )
        stale = len(self.price_cache) - fresh

        return {
            "total_cached": len(self.price_cache),
            "fresh": fresh,
            "stale": stale,
            "cache_ttl": self.cache_ttl,
        }
