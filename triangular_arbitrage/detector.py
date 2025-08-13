import math
import networkx as nx
from triangular_arbitrage.exchange import get_exchange_data

def build_graph(tickers, trade_fee):
    """
    Builds a directed graph from exchange tickers, with edge weights calculated
    for arbitrage detection.
    """
    graph = nx.DiGraph()
    for symbol, ticker in tickers.items():
        if ticker.get('last') is None or ticker['last'] == 0:
            continue
        try:
            symbol_1, symbol_2 = symbol.split('/')
        except ValueError:
            continue

        price = ticker['last']
        
        graph.add_edge(
            symbol_2,
            symbol_1,
            weight=-math.log((1 / price) * (1 - trade_fee))
        )
        graph.add_edge(
            symbol_1,
            symbol_2,
            weight=-math.log(price * (1 - trade_fee))
        )
    return graph

def find_opportunities(graph):
    """
    Finds profitable arbitrage cycles in the graph by checking all simple cycles.
    """
    profitable_cycles = []
    
    # This is the most time-consuming part. We are iterating through all possible cycles.
    for cycle in nx.simple_cycles(graph):
        if len(cycle) < 2:
            continue

        path = cycle + [cycle[0]]
        cycle_weight = sum(graph[u][v]['weight'] for u, v in zip(path, path[1:]))

        if cycle_weight < 0:
            profit_percentage = (math.exp(-cycle_weight) - 1) * 100
            profitable_cycles.append((cycle, profit_percentage))

    profitable_cycles.sort(key=lambda x: x[1], reverse=True)
    return profitable_cycles

async def run_detection(exchange_name, trade_fee, ignored_symbols=None, whitelisted_symbols=None):
    """
    The main function to run the arbitrage detection process. It fetches data,
    builds the graph, finds opportunities, and prints the results.
    """
    if ignored_symbols is None:
        ignored_symbols = []

    try:
        # --- Step 1: Fetching Data ---
        print("  -> Step 1: Fetching market data from exchange...")
        tickers, exchange_time = await get_exchange_data(exchange_name)
        print(f"  -> Found {len(tickers)} available trading pairs.")

    except Exception as e:
        print(f"Error: Could not fetch data from {exchange_name}. Details: {e}")
        return

    # --- Step 2: Building Graph ---
    print("  -> Step 2: Building currency graph...")
    filtered_tickers = {
        s: t for s, t in tickers.items()
        if (not whitelisted_symbols or s in whitelisted_symbols) and s not in ignored_symbols
    }

    if not filtered_tickers:
        print("Error: No valid trading pairs found after filtering. Check your symbol configuration.")
        return

    graph = build_graph(filtered_tickers, trade_fee)
    print(f"  -> Graph built with {len(graph.nodes)} currencies and {len(graph.edges)} potential trades.")

    # --- Step 3: Finding Opportunities ---
    print("  -> Step 3: Analyzing graph for profitable cycles (this may take a while)...")
    opportunities = find_opportunities(graph)
    print("  -> Analysis complete.")

    if opportunities:
        fee_percentage = trade_fee * 100
        best_cycle, best_profit = opportunities[0]
        
        print("\n" + "=" * 70)
        print(f"Success! Arbitrage Opportunity Found on {exchange_name.capitalize()}!")
        print(f"  Estimated Profit: {best_profit:.4f}% (after {fee_percentage:.2f}% fee per trade)")
        print(f"  Path: {' -> '.join(best_cycle)} -> {best_cycle[0]}")
        print("=" * 70 + "\n")
    else:
        print(f"\nNo arbitrage opportunities found on {exchange_name} at this time.\n")
