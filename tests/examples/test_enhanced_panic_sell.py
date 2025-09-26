#!/usr/bin/env python3
"""
Comprehensive test suite for Enhanced Failure Recovery Manager

Tests various market conditions and asset positions to verify that the panic sell
logic correctly and efficiently liquidates positions to stablecoins.
"""

import asyncio
import random
import time
from typing import Dict, List, Tuple, Optional
import yaml
import networkx as nx
from collections import defaultdict

# Import the enhanced recovery manager
from triangular_arbitrage.enhanced_recovery_manager import (
    EnhancedFailureRecoveryManager,
    MarketCondition,
    MarketEdge,
    LiquidationPath,
    ExecutionStep
)


class MockExchange:
    """Mock exchange for testing panic sell functionality"""

    def __init__(self, scenario: str = "normal"):
        self.scenario = scenario
        self.api_calls = 0
        self.orders_placed = []
        self.markets = self._create_mock_markets()
        self.order_books = self._create_mock_order_books()
        self.tickers = self._create_mock_tickers()

    def _create_mock_markets(self):
        """Create mock market data based on scenario"""
        base_markets = {
            # Direct paths to stables
            'BTC/USDT': {'base': 'BTC', 'quote': 'USDT', 'active': True, 'taker': 0.001},
            'ETH/USDT': {'base': 'ETH', 'quote': 'USDT', 'active': True, 'taker': 0.001},
            'BNB/USDT': {'base': 'BNB', 'quote': 'USDT', 'active': True, 'taker': 0.001},
            'ETH/BTC': {'base': 'ETH', 'quote': 'BTC', 'active': True, 'taker': 0.001},
            'BNB/BTC': {'base': 'BNB', 'quote': 'BTC', 'active': True, 'taker': 0.001},

            # Altcoin markets
            'ADA/USDT': {'base': 'ADA', 'quote': 'USDT', 'active': True, 'taker': 0.001},
            'ADA/BTC': {'base': 'ADA', 'quote': 'BTC', 'active': True, 'taker': 0.001},
            'DOT/USDT': {'base': 'DOT', 'quote': 'USDT', 'active': True, 'taker': 0.001},
            'DOT/ETH': {'base': 'DOT', 'quote': 'ETH', 'active': True, 'taker': 0.001},
            'MATIC/USDT': {'base': 'MATIC', 'quote': 'USDT', 'active': True, 'taker': 0.001},
            'MATIC/BNB': {'base': 'MATIC', 'quote': 'BNB', 'active': True, 'taker': 0.001},

            # Exotic pairs requiring multi-hop
            'ALGO/BTC': {'base': 'ALGO', 'quote': 'BTC', 'active': True, 'taker': 0.001},
            'XLM/ETH': {'base': 'XLM', 'quote': 'ETH', 'active': True, 'taker': 0.001},
            'ATOM/BNB': {'base': 'ATOM', 'quote': 'BNB', 'active': True, 'taker': 0.001},

            # USDC pairs
            'BTC/USDC': {'base': 'BTC', 'quote': 'USDC', 'active': True, 'taker': 0.001},
            'ETH/USDC': {'base': 'ETH', 'quote': 'USDC', 'active': True, 'taker': 0.001},
            'USDT/USDC': {'base': 'USDT', 'quote': 'USDC', 'active': True, 'taker': 0.0005},
        }

        # Modify based on scenario
        if self.scenario == "illiquid":
            # Remove some markets to test path finding
            del base_markets['ADA/USDT']
            del base_markets['DOT/USDT']
            del base_markets['MATIC/USDT']

        elif self.scenario == "volatile":
            # Markets are all active but volatile
            pass

        elif self.scenario == "partial":
            # Some markets have reduced liquidity
            pass

        return base_markets

    def _create_mock_order_books(self):
        """Create mock order book data"""
        books = {}

        for symbol in self.markets:
            base_price = self._get_base_price(symbol)

            if self.scenario == "illiquid":
                depth = 3
                volume_multiplier = 0.1
            elif self.scenario == "volatile":
                depth = 10
                volume_multiplier = 0.5
                price_spread = 0.02  # 2% spread
            else:
                depth = 10
                volume_multiplier = 1.0
                price_spread = 0.001  # 0.1% spread

            # Create bids and asks
            bids = []
            asks = []

            for i in range(depth):
                bid_price = base_price * (1 - (i + 1) * 0.001)
                ask_price = base_price * (1 + (i + 1) * 0.001)

                bid_volume = random.uniform(0.5, 2.0) * volume_multiplier
                ask_volume = random.uniform(0.5, 2.0) * volume_multiplier

                bids.append([bid_price, bid_volume])
                asks.append([ask_price, ask_volume])

            books[symbol] = {
                'bids': bids,
                'asks': asks,
                'timestamp': time.time()
            }

        return books

    def _create_mock_tickers(self):
        """Create mock ticker data"""
        tickers = {}

        for symbol in self.markets:
            base_price = self._get_base_price(symbol)

            if self.scenario == "volatile":
                change_pct = random.uniform(-15, 15)
            else:
                change_pct = random.uniform(-2, 2)

            tickers[symbol] = {
                'symbol': symbol,
                'bid': base_price * 0.999,
                'ask': base_price * 1.001,
                'last': base_price,
                'percentage': change_pct,
                'baseVolume': random.uniform(100, 10000),
                'quoteVolume': random.uniform(100000, 10000000)
            }

        return tickers

    def _get_base_price(self, symbol):
        """Get base price for a symbol"""
        prices = {
            'BTC/USDT': 45000, 'BTC/USDC': 45000,
            'ETH/USDT': 3000, 'ETH/USDC': 3000, 'ETH/BTC': 0.0667,
            'BNB/USDT': 320, 'BNB/BTC': 0.0071,
            'ADA/USDT': 0.45, 'ADA/BTC': 0.00001,
            'DOT/USDT': 7.5, 'DOT/ETH': 0.0025,
            'MATIC/USDT': 0.9, 'MATIC/BNB': 0.0028,
            'ALGO/BTC': 0.000004,
            'XLM/ETH': 0.00004,
            'ATOM/BNB': 0.025,
            'USDT/USDC': 1.0001
        }
        return prices.get(symbol, 1.0)

    async def load_markets(self):
        """Mock load markets"""
        self.api_calls += 1
        return self.markets

    async def fetch_ticker(self, symbol):
        """Mock fetch ticker"""
        self.api_calls += 1
        if symbol not in self.tickers:
            raise Exception(f"Market {symbol} not found")
        return self.tickers[symbol]

    async def fetch_order_book(self, symbol, limit=10):
        """Mock fetch order book"""
        self.api_calls += 1
        if symbol not in self.order_books:
            raise Exception(f"Market {symbol} not found")

        book = self.order_books[symbol]
        return {
            'bids': book['bids'][:limit],
            'asks': book['asks'][:limit],
            'timestamp': book['timestamp']
        }

    async def create_market_buy_order(self, symbol, amount):
        """Mock market buy order"""
        self.api_calls += 1
        order_id = f"buy_{symbol}_{len(self.orders_placed)}"

        if self.scenario == "failure":
            raise Exception("Exchange error")

        order = {
            'id': order_id,
            'symbol': symbol,
            'side': 'buy',
            'type': 'market',
            'amount': amount,
            'status': 'closed',
            'filled': amount * (0.98 if self.scenario == "partial" else 1.0)
        }

        self.orders_placed.append(order)
        return order

    async def create_market_sell_order(self, symbol, amount):
        """Mock market sell order"""
        self.api_calls += 1
        order_id = f"sell_{symbol}_{len(self.orders_placed)}"

        if self.scenario == "failure":
            raise Exception("Exchange error")

        base_price = self._get_base_price(symbol)
        filled_amount = amount * (0.97 if self.scenario == "partial" else 1.0)

        order = {
            'id': order_id,
            'symbol': symbol,
            'side': 'sell',
            'type': 'market',
            'amount': amount,
            'status': 'closed',
            'filled': filled_amount,
            'cost': filled_amount * base_price * 0.999  # Slight slippage
        }

        self.orders_placed.append(order)
        return order

    async def fetch_order(self, order_id, symbol):
        """Mock fetch order"""
        self.api_calls += 1

        for order in self.orders_placed:
            if order['id'] == order_id:
                # Add additional fields
                order['average'] = self._get_base_price(symbol) * 0.999
                return order

        raise Exception(f"Order {order_id} not found")


class TestEnhancedPanicSell:
    """Test suite for enhanced panic sell functionality"""

    def __init__(self):
        self.test_results = []
        self.config = self._load_test_config()

    def _load_test_config(self):
        """Load test configuration"""
        return {
            'name': 'test_strategy',
            'panic_sell': {
                'enabled': True,
                'use_enhanced_routing': True,
                'base_currencies': ['USDT', 'USDC'],
                'preferred_intermediaries': ['BTC', 'ETH', 'BNB'],
                'max_total_slippage_bps': 300,
                'max_single_hop_slippage_bps': 150,
                'max_hops': 4,
                'min_liquidity_usd': 100,
                'path_timeout_ms': 5000,
                'max_paths_to_evaluate': 10,
                'liquidity_weight': 0.4,
                'slippage_weight': 0.4,
                'hop_penalty_weight': 0.2,
                'retry_attempts': 2,
                'retry_delay_ms': 100,
                'partial_fill_threshold': 0.9
            }
        }

    async def run_all_tests(self):
        """Run all test scenarios"""
        print("=" * 80)
        print("ENHANCED PANIC SELL TEST SUITE")
        print("=" * 80)
        print()

        # Test scenarios
        test_cases = [
            ("normal", "BTC", 0.1, "Normal market conditions with BTC"),
            ("normal", "ETH", 1.5, "Normal market conditions with ETH"),
            ("normal", "ADA", 1000, "Normal market - direct path available"),
            ("normal", "ALGO", 500, "Normal market - multi-hop required"),
            ("normal", "XLM", 2000, "Normal market - complex routing"),

            ("illiquid", "ADA", 1000, "Illiquid market - must find alternative"),
            ("illiquid", "DOT", 100, "Illiquid market - forced multi-hop"),

            ("volatile", "BTC", 0.05, "Volatile market conditions"),
            ("volatile", "MATIC", 1000, "Volatile altcoin market"),

            ("partial", "ETH", 2.0, "Partial fill scenario"),
            ("partial", "ATOM", 50, "Partial fill with multi-hop"),

            # Edge cases
            ("normal", "USDT", 1000, "Already in target currency"),
            ("normal", "USDC", 1000, "Already in alternative target"),
        ]

        for scenario, currency, amount, description in test_cases:
            result = await self.test_panic_sell(scenario, currency, amount, description)
            self.test_results.append(result)
            print()

        # Print summary
        self.print_summary()

    async def test_panic_sell(self, scenario: str, currency: str, amount: float, description: str):
        """Test a specific panic sell scenario"""
        print(f"Test: {description}")
        print(f"  Scenario: {scenario}, Currency: {currency}, Amount: {amount}")

        # Create mock exchange
        exchange = MockExchange(scenario)

        # Create recovery manager
        recovery_manager = EnhancedFailureRecoveryManager(exchange, self.config)

        # Initialize
        await recovery_manager.initialize()

        start_time = time.time()
        api_calls_before = exchange.api_calls

        try:
            # Execute panic sell
            result = await recovery_manager.execute_panic_sell(
                currency,
                amount
            )

            success, final_amount, final_currency, execution_steps = result

            elapsed_time = time.time() - start_time
            api_calls = exchange.api_calls - api_calls_before

            if success:
                slippage = recovery_manager.calculate_actual_slippage(amount, final_amount)
                print(f"  ✓ SUCCESS: {final_amount:.4f} {final_currency}")
                print(f"    Path: {' -> '.join([currency] + [s.output_currency for s in execution_steps])}")
                print(f"    Slippage: {slippage:.1f} bps")
                print(f"    Steps: {len(execution_steps)}")
                print(f"    API calls: {api_calls}")
                print(f"    Time: {elapsed_time:.2f}s")

                return {
                    'test': description,
                    'success': True,
                    'slippage': slippage,
                    'steps': len(execution_steps),
                    'api_calls': api_calls,
                    'time': elapsed_time
                }
            else:
                print(f"  ✗ FAILED: Could not liquidate {currency}")
                print(f"    API calls: {api_calls}")
                print(f"    Time: {elapsed_time:.2f}s")

                return {
                    'test': description,
                    'success': False,
                    'api_calls': api_calls,
                    'time': elapsed_time
                }

        except Exception as e:
            print(f"  ✗ ERROR: {e}")
            return {
                'test': description,
                'success': False,
                'error': str(e)
            }

    async def test_path_finding(self):
        """Test path finding algorithm specifically"""
        print("\n" + "=" * 80)
        print("PATH FINDING TESTS")
        print("=" * 80)
        print()

        exchange = MockExchange("normal")
        recovery_manager = EnhancedFailureRecoveryManager(exchange, self.config)
        await recovery_manager.initialize()

        test_paths = [
            ("BTC", ["USDT", "USDC"], "Direct paths available"),
            ("ALGO", ["USDT"], "Multi-hop required"),
            ("XLM", ["USDC"], "Complex routing needed"),
            ("ATOM", ["USDT", "USDC"], "Multiple targets"),
        ]

        for from_curr, targets, description in test_paths:
            print(f"Finding paths: {from_curr} -> {targets} ({description})")

            paths = await recovery_manager.find_liquidation_paths(
                from_curr,
                100,
                targets
            )

            if paths:
                print(f"  Found {len(paths)} paths:")
                for i, path in enumerate(paths[:3]):  # Show top 3
                    score = recovery_manager.score_path(path)
                    print(f"    {i+1}. {' -> '.join(path.path)}")
                    print(f"       Score: {score:.3f}, Slippage: {path.estimated_slippage:.1f} bps")
                    print(f"       Risk: {path.risk_score:.3f}, Confidence: {path.confidence_score:.3f}")
            else:
                print(f"  No paths found!")

            print()

    async def test_market_analysis(self):
        """Test market condition analysis"""
        print("\n" + "=" * 80)
        print("MARKET CONDITION ANALYSIS")
        print("=" * 80)
        print()

        scenarios = ["normal", "volatile", "illiquid"]
        currencies = ["BTC", "ETH", "ADA", "ALGO"]

        for scenario in scenarios:
            print(f"\nScenario: {scenario}")
            exchange = MockExchange(scenario)
            recovery_manager = EnhancedFailureRecoveryManager(exchange, self.config)
            await recovery_manager.initialize()

            conditions = await recovery_manager.analyze_market_conditions(currencies)

            for curr, condition in conditions.items():
                print(f"  {curr}: {condition.value}")

    def print_summary(self):
        """Print test summary"""
        print("\n" + "=" * 80)
        print("TEST SUMMARY")
        print("=" * 80)

        successful = [r for r in self.test_results if r.get('success')]
        failed = [r for r in self.test_results if not r.get('success')]

        print(f"\nTotal tests: {len(self.test_results)}")
        print(f"Successful: {len(successful)} ({len(successful)/len(self.test_results)*100:.1f}%)")
        print(f"Failed: {len(failed)} ({len(failed)/len(self.test_results)*100:.1f}%)")

        if successful:
            avg_slippage = sum(r.get('slippage', 0) for r in successful) / len(successful)
            avg_steps = sum(r.get('steps', 0) for r in successful) / len(successful)
            avg_api_calls = sum(r.get('api_calls', 0) for r in successful) / len(successful)
            avg_time = sum(r.get('time', 0) for r in successful) / len(successful)

            print(f"\nSuccessful liquidations:")
            print(f"  Average slippage: {avg_slippage:.1f} bps")
            print(f"  Average steps: {avg_steps:.1f}")
            print(f"  Average API calls: {avg_api_calls:.1f}")
            print(f"  Average time: {avg_time:.3f}s")

        if failed:
            print(f"\nFailed liquidations:")
            for r in failed:
                print(f"  - {r['test']}")
                if 'error' in r:
                    print(f"    Error: {r['error']}")


async def main():
    """Main test runner"""
    tester = TestEnhancedPanicSell()

    # Run main test suite
    await tester.run_all_tests()

    # Run specialized tests
    await tester.test_path_finding()
    await tester.test_market_analysis()

    print("\n" + "=" * 80)
    print("✓ ALL TESTS COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())