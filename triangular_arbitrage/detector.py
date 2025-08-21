# triangular_arbitrage/detector.py

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
    Finds the best trading cycles in the graph using negative cycle detection.
    """
    for node in graph.nodes:
        try:
            # nx.find_negative_cycle finds a single profitable arbitrage opportunity.
            negative_cycle = nx.find_negative_cycle(graph, source=node, weight='weight')
            
            edges = list(zip(negative_cycle, negative_cycle[1:]))
            
            cycle_weight = sum(graph[u][v]['weight'] for u, v in edges)
            profit_percentage = (math.exp(-cycle_weight) - 1) * 100
            
            # Return the cycle for display (without the repeated end node) and the profit
            return (negative_cycle[:-1], profit_percentage)
            
        except nx.NetworkXError:
            # This error means no negative cycle was found from the current starting node.
            continue
            
    # If the loop completes without finding any negative cycles
    return None

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
        return None

    # --- Step 2: Building Graph ---
    print("  -> Step 2: Building currency graph...")
    filtered_tickers = {
        s: t for s, t in tickers.items()
        if (not whitelisted_symbols or s in whitelisted_symbols) and s not in ignored_symbols
    }

    if not filtered_tickers:
        print("Error: No valid trading pairs found after filtering. Check your symbol configuration.")
        return None

    graph = build_graph(filtered_tickers, trade_fee)
    print(f"  -> Graph built with {len(graph.nodes)} currencies and {len(graph.edges)} potential trades.")

    # --- Step 3: Finding Opportunities ---
    print("  -> Step 3: Analyzing graph for best trading cycles...")
    opportunity = find_opportunities(graph)
    print("  -> Analysis complete.")

    if opportunity:
        cycle, profit = opportunity
        fee_percentage = trade_fee * 100
        
        print("\n" + "=" * 70)
        print(f"Found Potential Trade Path on {exchange_name.capitalize()}")
        print(f"(Includes {fee_percentage:.2f}% fee per trade)")
        print("=" * 70)

        status = "Profit" if profit > 0 else "Loss"
        print(f"\nEstimated {status}: {profit:.4f}%")
        print(f"  Path: {' -> '.join(cycle)} -> {cycle[0]}")
        
        print("\n" + "=" * 70 + "\n")
        return opportunity
    else:
        print(f"\nNo trading cycles found on {exchange_name} at this time.\n")
        return None
