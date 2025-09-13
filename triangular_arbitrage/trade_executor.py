# triangular_arbitrage/trade_executor.py
import asyncio

async def execute_cycle(exchange, cycle, initial_amount, is_dry_run=False):
    """
    Executes the series of trades for a profitable cycle.
    Includes checks for minimum order amount and minimum order cost.
    Safely handles both dry-run simulations and live trades.
    """
    if is_dry_run:
        print("\n--- INITIATING DRY RUN ---")
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

            # --- PRE-TRADE VALIDATION ---
            min_order_amount = market.get('limits', {}).get('amount', {}).get('min')
            min_order_cost = market.get('limits', {}).get('cost', {}).get('min')
            
            if order_side == 'sell' and min_order_amount and amount < min_order_amount:
                print(f"Error: Order amount is too small. Minimum is {min_order_amount} {market['base']}, but you are trying to trade {amount}.")
                return

            if order_side == 'buy' and min_order_cost and amount < min_order_cost:
                print(f"Error: Order value is too small. Minimum is {min_order_cost} {market['quote']}, but your order is only worth {amount} {market['quote']}.")
                return

            # --- ROBUST TRADE EXECUTION ---
            order = None
            if is_dry_run:
                print(f"DRY RUN: Would execute {order_side.upper()} order on {market['symbol']} for {amount:.8f} {from_currency}")
                # In a dry run, we simulate the trade by estimating the result
                # We'll use the last known price, minus a small "slippage" fee to be conservative
                ticker = await exchange.fetch_ticker(market['symbol'])
                price = ticker['last']
                if order_side == 'buy':
                    # Estimate how much 'to_currency' we would get
                    amount = (amount / price) * 0.999 # a little slippage
                else: # sell
                    # Estimate how much 'to_currency' we would get
                    amount = (amount * price) * 0.999 # a little slippage
            else:
                # --- LIVE TRADING ---
                if order_side == 'buy':
                    print(f"Placing MARKET BUY order for {to_currency} using {amount:.8f} {from_currency}")
                    order = await exchange.create_market_buy_order(market['symbol'], amount)
                elif order_side == 'sell':
                    print(f"Placing MARKET SELL order for {amount:.8f} {from_currency} to get {to_currency}")
                    order = await exchange.create_market_sell_order(market['symbol'], amount)
                
                print("Order placed. Fetching trade details to confirm...")
                
                # --- THIS IS THE CRITICAL FIX ---
                # Fetch the private trade details using the order ID to get the final, settled numbers
                # It might take a moment for the order to fill, so we try a few times.
                final_order_details = None
                for _ in range(5): # Try up to 5 times
                    trades = await exchange.fetch_my_trades(market['symbol'], limit=1)
                    if trades and trades[0]['order'] == order['id']:
                        final_order_details = trades[0]
                        break
                    await asyncio.sleep(1) # Wait 1 second before trying again

                if not final_order_details:
                    print("Error: Could not fetch final trade details after placing order. Halting cycle.")
                    return

                if order_side == 'buy':
                    amount = float(final_order_details['amount']) # The amount of the asset we received
                else: # sell
                    amount = float(final_order_details['cost']) # The total cost (in quote currency) we received

                print("Trade confirmed successfully.")

            from_currency = to_currency

        except Exception as e:
            print(f"An error occurred during trade execution: {e}")
            return
            
    print("\n--- TRADE CYCLE EXECUTION ATTEMPT COMPLETE ---")
    print(f"Finished with approximately {amount:.8f} {from_currency}")