# triangular_arbitrage/trade_executor.py

async def execute_cycle(exchange, cycle, initial_amount):
    """
    Executes the series of trades for a profitable cycle.
    
    WARNING: This is a simplified example using market orders and does not
    include error handling, slippage checks, or order book analysis.
    Use with extreme caution.
    """
    print("\n--- ATTEMPTING TO EXECUTE TRADE CYCLE ---")
    print("WARNING: Using market orders. Slippage may occur.")
    
    from_currency = cycle[0]
    amount = initial_amount
    
    trade_path = cycle + [cycle[0]]
    markets = await exchange.load_markets()

    for i in range(len(trade_path) - 1):
        to_currency = trade_path[i+1]
        
        print("-" * 20)
        print(f"Step {i+1}: Trading {from_currency} -> {to_currency}")
        
        try:
            market_symbol_forward = f"{to_currency}/{from_currency}"
            market_symbol_backward = f"{from_currency}/{to_currency}"
            
            market = None
            order_side = None

            if market_symbol_forward in markets:
                market = markets[market_symbol_forward]
                order_side = 'buy'
            elif market_symbol_backward in markets:
                market = markets[market_symbol_backward]
                order_side = 'sell'
            else:
                print(f"Error: Could not find a valid market for {from_currency} -> {to_currency}")
                return

            # --- PRE-TRADE MINIMUM ORDER CHECK ---
            min_order_amount = market.get('limits', {}).get('amount', {}).get('min')
            if min_order_amount and amount < min_order_amount:
                print(f"Error: Order amount is too small. Minimum for {market['symbol']} is {min_order_amount}, but you are trying to trade {amount}.")
                return

            # Place the order based on the side
            if order_side == 'buy':
                print(f"Placing MARKET BUY order for {to_currency} using {amount:.8f} {from_currency}")
                order = await exchange.create_market_buy_order(market['symbol'], amount)
                print("Order successful.")
                amount = float(order['filled'])
                
            elif order_side == 'sell':
                print(f"Placing MARKET SELL order for {amount:.8f} {from_currency} to get {to_currency}")
                order = await exchange.create_market_sell_order(market['symbol'], amount)
                print("Order successful.")
                amount = float(order['cost'])

            from_currency = to_currency

        except Exception as e:
            print(f"An error occurred during trade execution: {e}")
            return
            
    print("\n--- TRADE CYCLE EXECUTION ATTEMPT COMPLETE ---")
    print(f"Finished with approximately {amount:.8f} {from_currency}")
