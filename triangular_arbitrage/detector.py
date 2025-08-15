import math
import networkx as nx
from . import trade_executor

def build_graph(tickers):
    """Builds a directed graph from the ticker data."""
    graph = nx.DiGraph()
    for symbol, ticker in tickers.items():
        if ticker['last'] is None or ticker['last'] == 0:
            continue
        
        base_currency, quote_currency = symbol.split('/')
        price = ticker['last']
        
        # Add edges for both trading directions
        graph.add_edge(base_currency, quote_currency, weight=-math.log(price))
        graph.add_edge(quote_currency, base_currency, weight=-math.log(1 / price))
        
    return graph

def find_opportunities(graph):
    """Finds profitable arbitrage cycles in the graph."""
    profitable_cycles = []
    
    # Using Bellman-Ford to find negative cycles, which correspond to arbitrage opportunities
    for node in graph.nodes:
        try:
            # Look for negative cycles starting from each node
            pred, dist = nx.bellman_ford_predecessor_and_distance(graph, node)
            for u, v, data in graph.edges(data=True):
                if dist[u] + data['weight'] < dist[v]:
                    # Negative cycle found
                    cycle = [u, v]
                    p = u
                    while p != v and p not in cycle[:-1]:
                        p = pred[p]
                        if p is None:  # Disconnected component
                            break
                        cycle.insert(0, p)
                    
                    if p == v: # Ensure it's a cycle
                        cycle.append(v)
                        
                        # Calculate profit
                        profit = 1
                        for i in range(len(cycle) - 1):
                            profit *= math.exp(-graph[cycle[i]][cycle[i+1]]['weight'])
                        
                        # Add to list if it's a new, profitable cycle
                        if profit > 1 and not any(set(cycle) == set(c) for c, p in profitable_cycles):
                            profitable_cycles.append((cycle, (profit - 1) * 100))
                            
        except nx.NetworkXUnbounded:
            # This exception is raised when a negative cycle is found
            continue
            
    # Sort opportunities by profit
    profitable_cycles.sort(key=lambda x: x[1], reverse=True)
    return profitable_cycles


async def run_detection(exchange, trade_fee, ignored_symbols=None, whitelisted_symbols=None):
    """
    The main function to run the arbitrage detection process.
    """
    if ignored_symbols is None:
        ignored_symbols = []

    try:
        print("  -> Step 1: Fetching market data from exchange...")
        tickers = await exchange.fetch_tickers()
        print(f"  -> Found {len(tickers)} available trading pairs.")

    except Exception as e:
        print(f"Error: Could not fetch data from {exchange.id}. Details: {e}")
        return

    print("  -> Step 2: Building currency graph...")
    graph = build_graph(tickers)
    
    print("  -> Step 3: Analyzing graph for profitable cycles...")
    opportunities = find_opportunities(graph)
    print("  -> Analysis complete.")

    if opportunities:
        best_cycle, best_profit = opportunities[0]
        
        # Remove the last element if it's the same as the first to clean up the path display
        if best_cycle[0] == best_cycle[-1]:
            best_cycle = best_cycle[:-1]
            
        print("\n" + "=" * 70)
        print(f"Success! Arbitrage Opportunity Found on {exchange.id.capitalize()}!")
        print(f"  Estimated Profit: {best_profit:.4f}%")
        print(f"  Path: {' -> '.join(best_cycle)} -> {best_cycle[0]}")
        print("=" * 70 + "\n")
        
        # --- EXECUTE THE TRADE ---
        # Define how much of the starting currency you want to trade
        # initial_amount = 0.01 # Example: 0.01 of the starting currency
        # await trade_executor.execute_cycle(exchange, best_cycle, initial_amount)
        # -------------------------

    else:
        print(f"\nNo arbitrage opportunities found on {exchange.id} at this time.\n")