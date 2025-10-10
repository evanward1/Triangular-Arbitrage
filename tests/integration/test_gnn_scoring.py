import sys

from triangular_arbitrage.gnn_optimizer import GNNArbitrageOptimizer


def test_gnn_blocks_bad_cycles():
    gnn = GNNArbitrageOptimizer()

    good_cycles = [
        ["BTC", "ETH", "USDT"],
        ["ETH", "BNB", "USDT"],
        ["BTC", "BNB", "USDT"],
        ["LTC", "ETH", "USDT"],
        ["XRP", "BTC", "USDT"],
    ]

    bad_cycles = [
        ["DOGE", "SHIB", "USDT"],
        ["TRX", "XLM", "USDT"],
        ["ADA", "DOT", "USDT"],
        ["MATIC", "ATOM", "USDT"],
        ["LINK", "UNI", "USDT"],
    ]

    for cycle in good_cycles:
        for _ in range(3):
            gnn.add_trade_result(
                cycle, expected_profit=2.0, actual_profit=1.8, execution_time=0.5
            )

    for cycle in bad_cycles:
        for _ in range(3):
            gnn.add_trade_result(
                cycle, expected_profit=2.0, actual_profit=-0.5, execution_time=0.5
            )

    gnn.save_state()

    gnn2 = GNNArbitrageOptimizer()

    bad_scores = [gnn2.get_cycle_score(c) for c in bad_cycles]

    blocked_count = sum(1 for score in bad_scores if score < 1.0)

    if blocked_count >= 3:
        print("GNN TEST: PASS")
        return True
    else:
        print("GNN TEST: FAIL")
        return False


if __name__ == "__main__":
    result = test_gnn_blocks_bad_cycles()
    sys.exit(0 if result else 1)
