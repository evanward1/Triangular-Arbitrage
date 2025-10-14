import octobot_commons.symbols as symbols
import pytest

from triangular_arbitrage.detector import (
    ShortTicker,
    get_best_opportunity,
    get_best_triangular_opportunity,
)


@pytest.fixture
def sample_tickers():
    return [
        ShortTicker(symbol=symbols.Symbol("BTC/USDT"), last_price=30000),
        ShortTicker(symbol=symbols.Symbol("ETH/USDT"), last_price=2000),
        ShortTicker(symbol=symbols.Symbol("XRP/USDT"), last_price=0.5),
        ShortTicker(symbol=symbols.Symbol("LTC/USDT"), last_price=100),
        ShortTicker(symbol=symbols.Symbol("BCH/USDT"), last_price=200),
    ]


def test_get_best_triangular_opportunity_handles_empty_tickers():
    best_opportunity, best_profit = get_best_triangular_opportunity([])
    assert best_profit == 1
    assert best_opportunity is None


def test_get_best_triangular_opportunity_handles_no_cycle_opportunity(sample_tickers):
    sample_tickers.append(
        ShortTicker(symbol=symbols.Symbol("DOT/USDT"), last_price=0.05)
    )
    best_opportunity, best_profit = get_best_triangular_opportunity(sample_tickers)
    assert best_profit == 1
    assert best_opportunity is None


def test_get_best_opportunity_handles_empty_tickers():
    best_opportunity, best_profit = get_best_opportunity([])
    assert best_profit == 1
    assert best_opportunity is None


def test_get_best_opportunity_handles_no_triplet_opportunity(sample_tickers):
    sample_tickers.append(
        ShortTicker(symbol=symbols.Symbol("DOT/USDT"), last_price=0.05)
    )
    best_opportunity, best_profit = get_best_opportunity(sample_tickers)
    assert best_profit == 1
    assert best_opportunity is None


def test_get_best_opportunity_returns_correct_triplet_with_correct_tickers():
    tickers = [
        ShortTicker(symbol=symbols.Symbol("BTC/USDT"), last_price=30000),
        ShortTicker(symbol=symbols.Symbol("ETH/BTC"), last_price=0.3),
        ShortTicker(symbol=symbols.Symbol("ETH/USDT"), last_price=2000),
    ]
    best_opportunity, best_profit = get_best_triangular_opportunity(tickers)
    assert len(best_opportunity) == 3
    assert best_profit == 4.5
    assert all(isinstance(ticker, ShortTicker) for ticker in best_opportunity)


def test_get_best_opportunity_returns_correct_triplet_with_multiple_tickers():
    tickers = [
        ShortTicker(symbol=symbols.Symbol("BTC/USDT"), last_price=30000),
        ShortTicker(symbol=symbols.Symbol("ETH/BTC"), last_price=0.3),
        ShortTicker(symbol=symbols.Symbol("ETH/USDT"), last_price=2000),
        ShortTicker(symbol=symbols.Symbol("ETH/USDC"), last_price=1900),
        ShortTicker(symbol=symbols.Symbol("BTC/USDC"), last_price=35000),
        ShortTicker(symbol=symbols.Symbol("USDC/USDT"), last_price=1.1),
        ShortTicker(symbol=symbols.Symbol("USDC/TUSD"), last_price=0.95),
        ShortTicker(symbol=symbols.Symbol("ETH/TUSD"), last_price=1950),
        ShortTicker(symbol=symbols.Symbol("BTC/TUSD"), last_price=32500),
    ]
    best_opportunity, best_profit = get_best_triangular_opportunity(tickers)
    assert len(best_opportunity) == 3
    assert round(best_profit, 3) == 5.526  # 5.526315789473684
    assert all(isinstance(ticker, ShortTicker) for ticker in best_opportunity)


def test_get_best_opportunity_returns_correct_cycle_with_correct_tickers():
    tickers = [
        ShortTicker(symbol=symbols.Symbol("BTC/USDT"), last_price=30000),
        ShortTicker(symbol=symbols.Symbol("ETH/BTC"), last_price=0.3),
        ShortTicker(symbol=symbols.Symbol("ETH/USDT"), last_price=2000),
    ]
    best_opportunity, best_profit = get_best_opportunity(tickers)
    assert len(best_opportunity) >= 3  # Handling cycles with more than 3 tickers
    # Expected profit with 0.1% fee per leg: ~4.486 (was 4.5 without fees)
    assert round(best_profit, 2) == 4.49
    assert all(isinstance(ticker, ShortTicker) for ticker in best_opportunity)


def test_get_best_opportunity_returns_correct_cycle_with_multiple_tickers():
    tickers = [
        ShortTicker(symbol=symbols.Symbol("BTC/USDT"), last_price=30000),
        ShortTicker(symbol=symbols.Symbol("ETH/BTC"), last_price=0.3),
        ShortTicker(symbol=symbols.Symbol("ETH/USDT"), last_price=2000),
        ShortTicker(symbol=symbols.Symbol("ETH/USDC"), last_price=1900),
        ShortTicker(symbol=symbols.Symbol("BTC/USDC"), last_price=35000),
        ShortTicker(symbol=symbols.Symbol("USDC/USDT"), last_price=1.1),
        ShortTicker(symbol=symbols.Symbol("USDC/TUSD"), last_price=0.95),
        ShortTicker(symbol=symbols.Symbol("ETH/TUSD"), last_price=1950),
        ShortTicker(symbol=symbols.Symbol("BTC/TUSD"), last_price=32500),
    ]
    best_opportunity, best_profit = get_best_opportunity(tickers)
    assert len(best_opportunity) >= 3  # Handling cycles with more than 3 tickers
    # Expected profit with 0.1% fee per leg: ~5.51 (was 5.775 without fees)
    assert round(best_profit, 2) == 5.51
    assert all(isinstance(ticker, ShortTicker) for ticker in best_opportunity)


def test_bid_ask_mode_produces_lower_profit_than_last_price():
    """Test that bid/ask mode gives more conservative profit estimates than last price."""
    # Create tickers with bid/ask spread
    tickers = [
        ShortTicker(
            symbol=symbols.Symbol("BTC/USDT"),
            last_price=30000,
            bid=29900,  # Lower bid
            ask=30100,  # Higher ask
        ),
        ShortTicker(
            symbol=symbols.Symbol("ETH/BTC"),
            last_price=0.3,
            bid=0.299,
            ask=0.301,
        ),
        ShortTicker(
            symbol=symbols.Symbol("ETH/USDT"),
            last_price=2000,
            bid=1990,
            ask=2010,
        ),
    ]

    # Get profit with last price
    _, profit_last = get_best_opportunity(tickers, use_bid_ask=False)

    # Get profit with bid/ask (more conservative)
    _, profit_bid_ask = get_best_opportunity(tickers, use_bid_ask=True)

    # Bid/ask profit should be lower or equal to last price profit
    assert profit_bid_ask <= profit_last
    # Should be noticeably lower due to spreads
    assert profit_bid_ask < profit_last * 0.99  # At least 1% lower
