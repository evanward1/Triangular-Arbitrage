"""
Enhanced Failure Recovery Manager with Dynamic Multi-hop Routing

This module implements a sophisticated panic sell mechanism that uses graph algorithms
to find optimal liquidation paths through multiple market hops, considering liquidity,
slippage, and market conditions.
"""

import asyncio
import logging
import time
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from enum import Enum
import networkx as nx
from collections import defaultdict, deque
# heapq removed - not used in current implementation

logger = logging.getLogger(__name__)


class MarketCondition(Enum):
    """Market condition indicators"""

    STABLE = "stable"
    VOLATILE = "volatile"
    ILLIQUID = "illiquid"
    EXTREME = "extreme"


@dataclass
class MarketEdge:
    """Represents a market connection between two currencies"""

    symbol: str
    from_currency: str
    to_currency: str
    side: str  # 'buy' or 'sell'
    bid_price: float = 0
    ask_price: float = 0
    bid_volume: float = 0
    ask_volume: float = 0
    spread_bps: float = 0
    last_update: float = 0
    liquidity_score: float = 0
    slippage_estimate: float = 0


@dataclass
class LiquidationPath:
    """Represents a complete liquidation path"""

    path: List[str]  # List of currencies
    edges: List[MarketEdge]  # Market edges to traverse
    estimated_slippage: float  # Total estimated slippage in basis points
    estimated_output: float  # Expected final amount
    confidence_score: float  # Confidence in the path (0-1)
    total_fees: float  # Total fees in basis points
    execution_time_ms: float  # Estimated execution time
    risk_score: float  # Risk assessment (0-1, lower is better)


@dataclass
class ExecutionStep:
    """Single step in a multi-hop execution"""

    market_symbol: str
    side: str
    input_currency: str
    output_currency: str
    input_amount: float
    expected_output: float
    actual_output: float = 0
    slippage_bps: float = 0
    success: bool = False
    error_message: str = ""
    timestamp: float = 0


class EnhancedFailureRecoveryManager:
    """Advanced panic sell manager with dynamic routing and market analysis"""

    def __init__(self, exchange, config: Dict[str, Any]):
        self.exchange = exchange
        self.config = config
        self.panic_config = config.get("panic_sell", {})

        # Base configuration
        self.base_currencies = self.panic_config.get(
            "base_currencies", ["USDT", "USDC", "USD"]
        )
        self.preferred_intermediaries = self.panic_config.get(
            "preferred_intermediaries", ["BTC", "ETH", "BNB"]
        )

        # Slippage and risk parameters
        self.max_total_slippage_bps = self.panic_config.get(
            "max_total_slippage_bps", 200
        )
        self.max_hops = self.panic_config.get("max_hops", 4)
        self.min_liquidity_usd = self.panic_config.get("min_liquidity_usd", 1000)
        self.max_single_hop_slippage_bps = self.panic_config.get(
            "max_single_hop_slippage_bps", 100
        )

        # Path finding parameters
        self.path_timeout_ms = self.panic_config.get("path_timeout_ms", 5000)
        self.max_paths_to_evaluate = self.panic_config.get("max_paths_to_evaluate", 10)
        self.liquidity_weight = self.panic_config.get("liquidity_weight", 0.4)
        self.slippage_weight = self.panic_config.get("slippage_weight", 0.4)
        self.hop_penalty_weight = self.panic_config.get("hop_penalty_weight", 0.2)

        # Market condition parameters
        self.volatility_threshold_bps = self.panic_config.get(
            "volatility_threshold_bps", 500
        )
        self.extreme_spread_bps = self.panic_config.get("extreme_spread_bps", 200)

        # Execution parameters
        self.retry_attempts = self.panic_config.get("retry_attempts", 2)
        self.retry_delay_ms = self.panic_config.get("retry_delay_ms", 500)
        self.partial_fill_threshold = self.panic_config.get(
            "partial_fill_threshold", 0.95
        )

        # Caching
        self.market_graph = nx.DiGraph()
        self.market_cache = {}
        self.cache_ttl = self.panic_config.get("cache_ttl_ms", 10000) / 1000.0
        self.last_graph_update = 0

        # Tracking
        self.execution_history = deque(maxlen=100)
        self.blacklisted_markets = set()
        self.market_conditions = {}

    async def initialize(self):
        """Initialize the recovery manager with market data"""
        await self.build_market_graph()

    async def build_market_graph(self, force_refresh: bool = False):
        """Build a graph of all available market connections"""
        current_time = time.time()

        # Check if we need to refresh
        if not force_refresh and current_time - self.last_graph_update < self.cache_ttl:
            return

        try:
            markets = await self.exchange.load_markets()
            self.market_graph.clear()

            for symbol, market in markets.items():
                if not market.get("active", True):
                    continue

                base = market["base"]
                quote = market["quote"]

                # Skip blacklisted markets
                if symbol in self.blacklisted_markets:
                    continue

                # Create bidirectional edges
                edge_data = {
                    "symbol": symbol,
                    "base": base,
                    "quote": quote,
                    "weight": 1.0,  # Will be updated with liquidity data
                    "fees": market.get("taker", 0.001),  # Default 0.1%
                }

                # Add both directions
                self.market_graph.add_edge(quote, base, **edge_data, side="buy")
                self.market_graph.add_edge(base, quote, **edge_data, side="sell")

            self.last_graph_update = current_time
            logger.info(
                f"Market graph updated: {self.market_graph.number_of_nodes()} currencies, "
                f"{self.market_graph.number_of_edges()} market connections"
            )

        except Exception as e:
            logger.error(f"Failed to build market graph: {e}")

    async def analyze_market_conditions(
        self, currencies: List[str]
    ) -> Dict[str, MarketCondition]:
        """Analyze current market conditions for relevant currencies"""
        conditions = {}

        for currency in currencies:
            try:
                # Get recent trades and order book for volatility analysis
                relevant_markets = [
                    edge["symbol"]
                    for _, _, edge in self.market_graph.edges(currency, data=True)
                ][
                    :3
                ]  # Check top 3 markets

                volatility_scores = []
                liquidity_scores = []

                for symbol in relevant_markets:
                    ticker = await self.exchange.fetch_ticker(symbol)
                    order_book = await self.exchange.fetch_order_book(symbol, limit=10)

                    # Calculate volatility
                    if ticker.get("percentage"):
                        volatility = abs(ticker["percentage"])
                        volatility_scores.append(volatility)

                    # Calculate liquidity
                    bid_liquidity = sum(
                        bid[1] * bid[0] for bid in order_book["bids"][:5]
                    )
                    ask_liquidity = sum(
                        ask[1] * ask[0] for ask in order_book["asks"][:5]
                    )
                    liquidity_scores.append(min(bid_liquidity, ask_liquidity))

                # Determine market condition
                avg_volatility = (
                    sum(volatility_scores) / len(volatility_scores)
                    if volatility_scores
                    else 0
                )
                avg_liquidity = (
                    sum(liquidity_scores) / len(liquidity_scores)
                    if liquidity_scores
                    else 0
                )

                if avg_volatility > 20:
                    conditions[currency] = MarketCondition.EXTREME
                elif avg_volatility > 10:
                    conditions[currency] = MarketCondition.VOLATILE
                elif avg_liquidity < self.min_liquidity_usd:
                    conditions[currency] = MarketCondition.ILLIQUID
                else:
                    conditions[currency] = MarketCondition.STABLE

            except Exception as e:
                logger.warning(f"Could not analyze conditions for {currency}: {e}")
                conditions[currency] = (
                    MarketCondition.VOLATILE
                )  # Assume volatile if unknown

        return conditions

    async def calculate_slippage(self, symbol: str, side: str, amount: float) -> float:
        """Calculate expected slippage for a trade"""
        try:
            order_book = await self.exchange.fetch_order_book(symbol)

            if side == "buy":
                orders = order_book["asks"]
            else:
                orders = order_book["bids"]

            if not orders:
                return 999999  # No liquidity

            # Calculate weighted average price for the amount
            remaining = amount
            total_cost = 0

            for price, volume in orders:
                if remaining <= 0:
                    break

                filled = min(remaining, volume)
                total_cost += filled * price
                remaining -= filled

            if remaining > 0:
                # Not enough liquidity
                return 999999

            avg_price = total_cost / amount
            best_price = orders[0][0]

            # Calculate slippage in basis points
            slippage_bps = abs(avg_price - best_price) / best_price * 10000

            return slippage_bps

        except Exception as e:
            logger.error(f"Failed to calculate slippage for {symbol}: {e}")
            return 999999

    async def find_liquidation_paths(
        self,
        from_currency: str,
        amount: float,
        target_currencies: Optional[List[str]] = None,
    ) -> List[LiquidationPath]:
        """Find optimal liquidation paths using graph algorithms"""

        if target_currencies is None:
            target_currencies = self.base_currencies

        # Ensure graph is current
        await self.build_market_graph()

        # If already at target, return
        if from_currency in target_currencies:
            return [
                LiquidationPath(
                    path=[from_currency],
                    edges=[],
                    estimated_slippage=0,
                    estimated_output=amount,
                    confidence_score=1.0,
                    total_fees=0,
                    execution_time_ms=0,
                    risk_score=0,
                )
            ]

        paths = []

        # Find paths to each target currency
        for target in target_currencies:
            if target not in self.market_graph:
                continue

            try:
                # Find multiple shortest paths
                all_paths = list(
                    nx.all_shortest_paths(self.market_graph, from_currency, target)
                )[: self.max_paths_to_evaluate]

                # Also find paths through preferred intermediaries
                for intermediary in self.preferred_intermediaries:
                    if (
                        intermediary in self.market_graph
                        and intermediary != from_currency
                    ):
                        try:
                            path1 = nx.shortest_path(
                                self.market_graph, from_currency, intermediary
                            )
                            path2 = nx.shortest_path(
                                self.market_graph, intermediary, target
                            )
                            combined_path = (
                                path1 + path2[1:]
                            )  # Avoid duplicating intermediary
                            if len(combined_path) <= self.max_hops + 1:
                                all_paths.append(combined_path)
                        except nx.NetworkXNoPath:
                            continue

                # Evaluate each path
                for path in all_paths:
                    if len(path) - 1 > self.max_hops:
                        continue

                    evaluated_path = await self.evaluate_path(path, amount)
                    if evaluated_path:
                        paths.append(evaluated_path)

            except nx.NetworkXNoPath:
                logger.debug(f"No path found from {from_currency} to {target}")
                continue

        # Sort paths by combined score
        paths.sort(key=lambda p: self.score_path(p), reverse=True)

        return paths[: self.max_paths_to_evaluate]

    async def evaluate_path(
        self, path: List[str], initial_amount: float
    ) -> Optional[LiquidationPath]:
        """Evaluate a specific path for viability and expected outcome"""

        if len(path) < 2:
            return None

        edges = []
        current_amount = initial_amount
        total_slippage = 0
        total_fees = 0
        confidence = 1.0
        execution_time = 0

        for i in range(len(path) - 1):
            from_curr = path[i]
            to_curr = path[i + 1]

            # Find the market
            edge_data = self.market_graph.get_edge_data(from_curr, to_curr)
            if not edge_data:
                return None

            symbol = edge_data["symbol"]
            side = edge_data["side"]

            # Calculate slippage
            slippage = await self.calculate_slippage(symbol, side, current_amount)
            if slippage > self.max_single_hop_slippage_bps:
                return None  # Path not viable

            # Estimate output
            fee_bps = edge_data.get("fees", 0.001) * 10000
            effective_slippage = slippage + fee_bps
            output_amount = current_amount * (1 - effective_slippage / 10000)

            # Create edge
            market_edge = MarketEdge(
                symbol=symbol,
                from_currency=from_curr,
                to_currency=to_curr,
                side=side,
                slippage_estimate=slippage,
                liquidity_score=1.0 / (1 + slippage / 100),  # Simple liquidity score
            )

            edges.append(market_edge)
            current_amount = output_amount
            total_slippage += slippage
            total_fees += fee_bps
            confidence *= 0.95  # Reduce confidence with each hop
            execution_time += 1000  # Estimate 1 second per hop

        # Calculate risk score
        risk_score = self.calculate_risk_score(
            len(path) - 1, total_slippage, confidence
        )

        return LiquidationPath(
            path=path,
            edges=edges,
            estimated_slippage=total_slippage,
            estimated_output=current_amount,
            confidence_score=confidence,
            total_fees=total_fees,
            execution_time_ms=execution_time,
            risk_score=risk_score,
        )

    def score_path(self, path: LiquidationPath) -> float:
        """Score a path based on multiple factors"""

        # Normalize factors
        slippage_score = max(
            0, 1 - path.estimated_slippage / self.max_total_slippage_bps
        )
        liquidity_score = path.confidence_score
        hop_score = max(0, 1 - (len(path.path) - 1) / self.max_hops)
        risk_score = 1 - path.risk_score

        # Weighted combination
        score = (
            self.slippage_weight * slippage_score
            + self.liquidity_weight * liquidity_score
            + self.hop_penalty_weight * hop_score
            + (
                1
                - self.slippage_weight
                - self.liquidity_weight
                - self.hop_penalty_weight
            )
            * risk_score
        )

        return score

    def calculate_risk_score(
        self, hops: int, slippage: float, confidence: float
    ) -> float:
        """Calculate overall risk score for a path"""

        hop_risk = hops / self.max_hops
        slippage_risk = slippage / self.max_total_slippage_bps
        confidence_risk = 1 - confidence

        # Combine risks (higher is riskier)
        risk = hop_risk * 0.3 + slippage_risk * 0.5 + confidence_risk * 0.2

        return min(1.0, risk)

    async def execute_panic_sell(
        self,
        current_currency: str,
        amount: float,
        target_currencies: Optional[List[str]] = None,
        max_attempts: int = None,
    ) -> Tuple[bool, float, str, List[ExecutionStep]]:
        """
        Execute an intelligent panic sell with multi-hop routing

        Returns:
            Tuple of (success, final_amount, final_currency, execution_steps)
        """

        if max_attempts is None:
            max_attempts = self.retry_attempts

        execution_steps = []

        # Check if already at target
        if target_currencies is None:
            target_currencies = self.base_currencies

        if current_currency in target_currencies:
            logger.info(f"Already holding target currency {current_currency}")
            return True, amount, current_currency, []

        # Analyze market conditions
        relevant_currencies = (
            [current_currency] + list(target_currencies) + self.preferred_intermediaries
        )
        market_conditions = await self.analyze_market_conditions(
            relevant_currencies[:10]
        )

        # Adjust parameters based on market conditions
        if market_conditions.get(current_currency) in [
            MarketCondition.EXTREME,
            MarketCondition.VOLATILE,
        ]:
            logger.warning(
                f"Volatile market detected for {current_currency}, adjusting parameters"
            )
            # Temporarily increase slippage tolerance
            original_slippage = self.max_single_hop_slippage_bps
            self.max_single_hop_slippage_bps *= 1.5

        try:
            # Find optimal paths
            paths = await self.find_liquidation_paths(
                current_currency, amount, target_currencies
            )

            if not paths:
                logger.error(f"No liquidation path found from {current_currency}")
                return False, amount, current_currency, execution_steps

            # Try paths in order of preference
            for path_attempt, path in enumerate(paths[:max_attempts]):
                logger.info(
                    f"Attempting liquidation path {path_attempt + 1}: "
                    f"{' -> '.join(path.path)} "
                    f"(estimated slippage: {path.estimated_slippage:.1f} bps)"
                )

                success, final_amount, final_currency, steps = await self.execute_path(
                    path, amount
                )

                execution_steps.extend(steps)

                if success:
                    logger.info(
                        f"Successfully liquidated to {final_currency}: "
                        f"{final_amount:.8f} "
                        f"(actual slippage: {self.calculate_actual_slippage(amount, final_amount):.1f} bps)"
                    )

                    # Record successful path
                    self.execution_history.append(
                        {
                            "timestamp": time.time(),
                            "path": path.path,
                            "success": True,
                            "slippage": self.calculate_actual_slippage(
                                amount, final_amount
                            ),
                        }
                    )

                    return True, final_amount, final_currency, execution_steps

                # Wait before retry
                if path_attempt < len(paths) - 1:
                    await asyncio.sleep(self.retry_delay_ms / 1000.0)

            logger.error("All liquidation paths failed")
            return False, amount, current_currency, execution_steps

        finally:
            # Restore original parameters if modified
            if market_conditions.get(current_currency) in [
                MarketCondition.EXTREME,
                MarketCondition.VOLATILE,
            ]:
                self.max_single_hop_slippage_bps = original_slippage

    async def execute_path(
        self, path: LiquidationPath, initial_amount: float
    ) -> Tuple[bool, float, str, List[ExecutionStep]]:
        """Execute a specific liquidation path"""

        execution_steps = []
        current_amount = initial_amount
        current_currency = path.path[0]

        for i, edge in enumerate(path.edges):
            step = ExecutionStep(
                market_symbol=edge.symbol,
                side=edge.side,
                input_currency=edge.from_currency,
                output_currency=edge.to_currency,
                input_amount=current_amount,
                expected_output=0,
                timestamp=time.time(),
            )

            try:
                # Execute the trade
                logger.info(
                    f"Executing {edge.side} on {edge.symbol} for {current_amount:.8f}"
                )

                if edge.side == "buy":
                    order = await self.exchange.create_market_buy_order(
                        edge.symbol, current_amount
                    )
                else:
                    order = await self.exchange.create_market_sell_order(
                        edge.symbol, current_amount
                    )

                # Wait for order to fill
                await asyncio.sleep(1)

                # Check order status
                order_details = await self.exchange.fetch_order(
                    order["id"], edge.symbol
                )

                filled_amount = order_details.get("filled", 0)

                # Calculate actual output
                if edge.side == "buy":
                    actual_output = filled_amount
                else:
                    actual_output = order_details.get("cost", 0)

                step.actual_output = actual_output
                step.success = filled_amount > 0

                if not step.success:
                    step.error_message = "Order not filled"
                    execution_steps.append(step)
                    return False, current_amount, current_currency, execution_steps

                # Check for partial fill
                fill_ratio = (
                    filled_amount / current_amount
                    if edge.side == "sell"
                    else filled_amount / current_amount
                )
                if fill_ratio < self.partial_fill_threshold:
                    step.error_message = f"Insufficient fill: {fill_ratio:.1%}"
                    execution_steps.append(step)
                    return False, current_amount, current_currency, execution_steps

                # Calculate actual slippage
                expected_price = order.get("price", 0)
                actual_price = order_details.get("average", expected_price)
                if expected_price > 0:
                    step.slippage_bps = (
                        abs(actual_price - expected_price) / expected_price * 10000
                    )

                execution_steps.append(step)
                current_amount = actual_output
                current_currency = edge.to_currency

                logger.info(
                    f"Step {i+1} complete: {actual_output:.8f} {edge.to_currency} "
                    f"(slippage: {step.slippage_bps:.1f} bps)"
                )

            except Exception as e:
                logger.error(f"Failed to execute {edge.side} on {edge.symbol}: {e}")
                step.success = False
                step.error_message = str(e)
                execution_steps.append(step)

                # Try to recover if we have partial execution
                if i > 0:
                    # We're partway through, current_currency has changed
                    return False, current_amount, current_currency, execution_steps
                else:
                    # Failed on first step
                    return False, initial_amount, current_currency, execution_steps

        return True, current_amount, current_currency, execution_steps

    def calculate_actual_slippage(
        self, initial_amount: float, final_amount: float
    ) -> float:
        """Calculate actual slippage in basis points"""
        if initial_amount == 0:
            return 0
        return abs(initial_amount - final_amount) / initial_amount * 10000

    async def blacklist_market(self, symbol: str, duration_seconds: int = 300):
        """Temporarily blacklist a problematic market"""
        self.blacklisted_markets.add(symbol)
        logger.warning(f"Blacklisted market {symbol} for {duration_seconds} seconds")

        # Schedule removal
        async def remove_blacklist():
            await asyncio.sleep(duration_seconds)
            self.blacklisted_markets.discard(symbol)
            logger.info(f"Removed {symbol} from blacklist")

        asyncio.create_task(remove_blacklist())

    def get_execution_statistics(self) -> Dict[str, Any]:
        """Get statistics about recent panic sell executions"""
        if not self.execution_history:
            return {}

        successful = [e for e in self.execution_history if e["success"]]
        failed = [e for e in self.execution_history if not e["success"]]

        stats = {
            "total_executions": len(self.execution_history),
            "successful": len(successful),
            "failed": len(failed),
            "success_rate": (
                len(successful) / len(self.execution_history) * 100
                if self.execution_history
                else 0
            ),
            "average_slippage": (
                sum(e.get("slippage", 0) for e in successful) / len(successful)
                if successful
                else 0
            ),
            "most_used_paths": self._get_most_used_paths(),
            "blacklisted_markets": list(self.blacklisted_markets),
        }

        return stats

    def _get_most_used_paths(self) -> List[Tuple[List[str], int]]:
        """Get the most frequently used successful paths"""
        path_counts = defaultdict(int)

        for execution in self.execution_history:
            if execution.get("success"):
                path_tuple = tuple(execution["path"])
                path_counts[path_tuple] += 1

        # Sort by frequency
        sorted_paths = sorted(path_counts.items(), key=lambda x: x[1], reverse=True)

        return [(list(path), count) for path, count in sorted_paths[:5]]
