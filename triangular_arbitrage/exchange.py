import ccxt.async_support as ccxt

async def get_exchange_data(exchange_name):
    """
    Connects to the specified exchange and fetches the latest market tickers.
    """
    # Dynamically get the exchange class from the ccxt library
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
        # If something goes wrong (e.g., network error, invalid API key),
        # close the connection and raise the error.
        await exchange.close()
        raise e
    finally:
        # Always ensure the connection to the exchange is closed gracefully
        await exchange.close()
