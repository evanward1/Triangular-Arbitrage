# triangular_arbitrage/exchange.py

import ccxt.async_support as ccxt


async def get_exchange_data(exchange_name):
    """
    Connects to the specified exchange and fetches the latest market tickers.
    """
    # --- defensive check ---
    if not isinstance(exchange_name, str):
        from .exceptions import ValidationError

        raise ValidationError(
            f"FATAL: The exchange name must be a string (e.g., 'coinbase'), but received an object of type {type(exchange_name).__name__}."
        )

    # Dynamically get the exchange class from the ccxt library
    if not hasattr(ccxt, exchange_name):
        from .exceptions import ExchangeError

        raise ExchangeError(
            f"FATAL: The exchange '{exchange_name}' is not supported by the ccxt library.",
            exchange=exchange_name,
        )

    exchange_class = getattr(ccxt, exchange_name)

    # Instantiate the exchange
    exchange = exchange_class()

    try:
        # Load all available markets/trading pairs from the exchange
        markets = await exchange.load_markets()

        # Fetch the latest tickers for all markets
        tickers = await exchange.fetch_tickers()

        # Get the current time from the exchange server for logging
        exchange_time = exchange.iso8601(exchange.milliseconds())

        return tickers, exchange_time

    except Exception as e:
        # If something goes wrong, close the connection and raise the error.
        await exchange.close()
        raise e
    finally:
        # Always ensure the connection to the exchange is closed gracefully
        await exchange.close()
