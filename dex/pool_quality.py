"""
Pool quality scoring and filtering for arbitrage opportunities.

Scores pools based on liquidity depth, fee structure, historical reliability,
and other factors that impact execution success.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List

from triangular_arbitrage.utils import get_logger

from .types import DexPool

logger = get_logger(__name__)


@dataclass
class PoolQualityScore:
    """
    Quality score for a pool.

    Attributes:
        pool_addr: Pool address
        total_score: Overall quality score (0-100)
        liquidity_score: Score based on pool depth (0-40)
        fee_score: Score based on fee competitiveness (0-20)
        balance_score: Score based on reserve balance (0-20)
        stability_score: Score based on price stability (0-20)
        details: Human-readable scoring breakdown
    """

    pool_addr: str
    total_score: float
    liquidity_score: float
    fee_score: float
    balance_score: float
    stability_score: float
    details: str


def calculate_pool_quality(
    pool: DexPool,
    usd_price_estimate: Decimal = Decimal("1.0"),
    min_liquidity_usd: Decimal = Decimal("10000"),
) -> PoolQualityScore:
    """
    Calculate quality score for a pool.

    Args:
        pool: Pool to score
        usd_price_estimate: Estimated USD value of base token (for liquidity calc)
        min_liquidity_usd: Minimum acceptable liquidity in USD

    Returns:
        PoolQualityScore with breakdown
    """
    # 1. Liquidity Score (0-40 points)
    # Higher liquidity = lower slippage, better execution
    # Estimate liquidity: min(r0, r1) * 2 * price_estimate
    min_reserve = min(pool.r0, pool.r1)
    estimated_liquidity_usd = float(min_reserve * usd_price_estimate * Decimal("2"))

    if estimated_liquidity_usd >= 1_000_000:  # $1M+
        liquidity_score = 40.0
    elif estimated_liquidity_usd >= 500_000:  # $500k+
        liquidity_score = 35.0
    elif estimated_liquidity_usd >= 100_000:  # $100k+
        liquidity_score = 30.0
    elif estimated_liquidity_usd >= 50_000:  # $50k+
        liquidity_score = 25.0
    elif estimated_liquidity_usd >= 10_000:  # $10k+
        liquidity_score = 20.0
    else:
        liquidity_score = 10.0  # Below minimum, risky

    # 2. Fee Score (0-20 points)
    # Lower fees = more profit potential
    fee_bps = float(pool.fee * Decimal("10000"))

    if fee_bps <= 10:  # 0.10% or less (excellent)
        fee_score = 20.0
    elif fee_bps <= 20:  # 0.20% (good)
        fee_score = 18.0
    elif fee_bps <= 30:  # 0.30% (standard)
        fee_score = 15.0
    elif fee_bps <= 50:  # 0.50% (high)
        fee_score = 10.0
    else:  # >0.50% (very high)
        fee_score = 5.0

    # 3. Balance Score (0-20 points)
    # Well-balanced pools have less slippage
    # Ideal ratio is 1:1 in value terms
    if pool.r0 > 0 and pool.r1 > 0:
        ratio = float(pool.r0 / pool.r1)
        # Normalize to 0-1 range (1.0 = perfectly balanced)
        # Use log scale to handle wide ratios
        import math

        balance_factor = 1.0 / (1.0 + abs(math.log10(ratio)))
        balance_score = balance_factor * 20.0
    else:
        balance_score = 0.0

    # 4. Stability Score (0-20 points)
    # Penalize pools with extreme reserve ratios (likely low quality/scam tokens)
    MAX_RATIO = 1000  # 1000:1 max acceptable ratio

    if pool.r0 > 0 and pool.r1 > 0:
        ratio = max(float(pool.r0 / pool.r1), float(pool.r1 / pool.r0))

        if ratio < 10:  # Very stable
            stability_score = 20.0
        elif ratio < 50:  # Moderately stable
            stability_score = 15.0
        elif ratio < 100:  # Somewhat stable
            stability_score = 10.0
        elif ratio < MAX_RATIO:  # Risky
            stability_score = 5.0
        else:  # Extreme ratio (likely scam)
            stability_score = 0.0
    else:
        stability_score = 0.0

    # Total score
    total_score = liquidity_score + fee_score + balance_score + stability_score

    # Generate details string
    details = (
        f"Liquidity: {liquidity_score:.0f}/40 (${estimated_liquidity_usd:,.0f}), "
        f"Fee: {fee_score:.0f}/20 ({fee_bps:.2f}bps), "
        f"Balance: {balance_score:.0f}/20, "
        f"Stability: {stability_score:.0f}/20"
    )

    return PoolQualityScore(
        pool_addr=pool.pair_addr,
        total_score=total_score,
        liquidity_score=liquidity_score,
        fee_score=fee_score,
        balance_score=balance_score,
        stability_score=stability_score,
        details=details,
    )


def filter_low_quality_pools(
    pools: List[DexPool],
    min_score: float = 50.0,
    usd_price_estimate: Decimal = Decimal("1.0"),
) -> List[DexPool]:
    """
    Filter out low-quality pools based on quality score.

    Args:
        pools: List of pools to filter
        min_score: Minimum quality score (0-100)
        usd_price_estimate: Estimated USD value of base token

    Returns:
        Filtered list of high-quality pools
    """
    filtered = []
    scores: Dict[str, PoolQualityScore] = {}

    for pool in pools:
        score = calculate_pool_quality(pool, usd_price_estimate)
        scores[pool.pair_addr] = score

        if score.total_score >= min_score:
            filtered.append(pool)
        else:
            logger.debug(
                f"Filtered out {pool.dex}/{pool.pair_name}: "
                f"score {score.total_score:.1f} < {min_score} ({score.details})"
            )

    if len(filtered) < len(pools):
        logger.info(
            f"Pool quality filter: kept {len(filtered)}/{len(pools)} pools "
            f"(min_score={min_score})"
        )

    return filtered


def rank_opportunity_by_pool_quality(
    pools: List[DexPool],
    usd_price_estimate: Decimal = Decimal("1.0"),
) -> List[tuple[DexPool, PoolQualityScore]]:
    """
    Rank pools by quality score (highest first).

    Args:
        pools: List of pools to rank
        usd_price_estimate: Estimated USD value of base token

    Returns:
        List of (pool, score) tuples sorted by score descending
    """
    scored_pools = []

    for pool in pools:
        score = calculate_pool_quality(pool, usd_price_estimate)
        scored_pools.append((pool, score))

    # Sort by total score descending
    scored_pools.sort(key=lambda x: x[1].total_score, reverse=True)

    return scored_pools


def estimate_execution_success_rate(
    pool1: DexPool,
    pool2: DexPool,
    trade_size_fraction: float,
    usd_price_estimate: Decimal = Decimal("1.0"),
) -> float:
    """
    Estimate probability of successful execution for a 2-leg arbitrage.

    Factors considered:
    - Pool quality scores
    - Trade size relative to liquidity
    - Fee structure

    Args:
        pool1: First pool in route
        pool2: Second pool in route
        trade_size_fraction: Trade size as fraction of reserves (e.g., 0.05 = 5%)
        usd_price_estimate: Estimated USD value of base token

    Returns:
        Estimated success probability (0.0-1.0)
    """
    # Score both pools
    score1 = calculate_pool_quality(pool1, usd_price_estimate)
    score2 = calculate_pool_quality(pool2, usd_price_estimate)

    # Average pool quality (normalized to 0-1)
    avg_quality = (score1.total_score + score2.total_score) / 200.0

    # Penalize large trades (higher chance of revert/frontrun)
    if trade_size_fraction > 0.10:  # >10% of reserves
        size_penalty = 0.5  # 50% success rate
    elif trade_size_fraction > 0.05:  # >5% of reserves
        size_penalty = 0.7  # 70% success rate
    elif trade_size_fraction > 0.02:  # >2% of reserves
        size_penalty = 0.9  # 90% success rate
    else:  # <2% of reserves
        size_penalty = 1.0  # 100% (no penalty)

    # Combined success rate
    success_rate = avg_quality * size_penalty

    logger.debug(
        f"Execution success estimate: {success_rate*100:.1f}% "
        f"(quality: {avg_quality*100:.1f}%, size_penalty: {size_penalty*100:.1f}%)"
    )

    return success_rate
