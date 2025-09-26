"""
Triangular arbitrage opportunity detection using graph algorithms.

This module implements the core arbitrage detection logic using NetworkX graphs
to identify profitable trading cycles across currency pairs.
"""

import math
from typing import Dict, Any, List, Optional, Tuple
import networkx as nx
from triangular_arbitrage.exchange import get_exchange_data
from triangular_arbitrage.utils import is_positive_number


def build_graph(tickers: Dict[str, Dict[str, Any]], trade_fee: float) -> nx.DiGraph:
    """
    Build a directed graph from exchange tickers with edge weights for arbitrage detection.

    Args:
        tickers: Dictionary of trading pair symbols to ticker data
        trade_fee: Trading fee as a decimal (e.g., 0.001 for 0.1%)

    Returns:
        NetworkX directed graph with logarithmic edge weights
    """
    graph = nx.DiGraph()
    for symbol, ticker in tickers.items():
        last_price = ticker.get("last")
        if not last_price or not is_positive_number(last_price):
            continue
        try:
            symbol_1, symbol_2 = symbol.split("/")
        except ValueError:
            continue

        price = float(last_price)

        # Add edges with logarithmic weights for arbitrage detection
        graph.add_edge(
            symbol_2, symbol_1, weight=-math.log((1 / price) * (1 - trade_fee))
        )
        graph.add_edge(symbol_1, symbol_2, weight=-math.log(price * (1 - trade_fee)))
    return graph


def find_opportunities(
    graph: nx.DiGraph, owned_assets: Optional[List[str]] = None
) -> Optional[List[Tuple[str, str]]]:
    """
    Find the best triangular arbitrage opportunities in the graph.

    Args:
        graph: NetworkX directed graph with currency exchange rates
        owned_assets: Optional list of assets that must be included in the cycle

    Returns:
        List of trading pairs representing the profitable cycle, or None if none found
    """
    temp_graph = graph.copy()

    # Loop until we find a valid cycle or exhaust all possibilities
    while True:
        cycle = None
        try:
            # Find any negative cycle in the graph
            # We can start from an arbitrary node; the algorithm will find a cycle if one exists
            start_node = list(temp_graph.nodes)[0]
            cycle = nx.find_negative_cycle(temp_graph, source=start_node)
        except (nx.NetworkXError, IndexError):
            # This means no more negative cycles can be found in the graph
            return None

        # If in actionable mode, check if the cycle starts with an owned asset
        if owned_assets:
            if cycle[0] in owned_assets:
                # This is a valid, actionable cycle. We're done.
                break
            else:
                # This cycle is not actionable. "Disqualify" it by removing an edge
                # and loop again to find the next best one.
                u, v = cycle[0], cycle[1]
                temp_graph.remove_edge(u, v)
                continue
        else:
            # Not in actionable mode, so any cycle is fine.
            break

    # If we have a valid cycle, calculate its profit
    if cycle:
        edges = list(zip(cycle, cycle[1:]))
        cycle_weight = sum(graph[u][v]["weight"] for u, v in edges)
        profit_percentage = (math.exp(-cycle_weight) - 1) * 100
        return (cycle[:-1], profit_percentage)

    return None


async def run_detection(
    exchange_name,
    trade_fee,
    owned_assets=None,
    ignored_symbols=None,
    whitelisted_symbols=None,
):
    """
    The main function to run the arbitrage detection process. It fetches data,
    builds the graph, finds opportunities, and prints the results.
    """
    if ignored_symbols is None:
        ignored_symbols = []

    try:
        print("  -> Step 1: Fetching market data from exchange...")
        tickers, exchange_time = await get_exchange_data(exchange_name)
        print(f"  -> Found {len(tickers)} available trading pairs.")

    except Exception as e:
        print(f"Error: Could not fetch data from {exchange_name}. Details: {e}")
        return None

    print("  -> Step 2: Building currency graph...")
    filtered_tickers = {
        s: t
        for s, t in tickers.items()
        if (not whitelisted_symbols or s in whitelisted_symbols)
        and s not in ignored_symbols
    }

    if not filtered_tickers:
        print("Error: No valid trading pairs found after filtering.")
        return None

    graph = build_graph(filtered_tickers, trade_fee)
    print(
        f"  -> Graph built with {len(graph.nodes)} currencies and {len(graph.edges)} potential trades."
    )

    search_type = "actionable" if owned_assets else "general"
    print(f"  -> Step 3: Analyzing graph for {search_type} trading cycles...")
    opportunity = find_opportunities(graph, owned_assets)
    print("  -> Analysis complete.")

    if opportunity:
        cycle, profit = opportunity
        fee_percentage = trade_fee * 100

        print("\n" + "=" * 70)
        header = (
            f"Actionable Trade Path Found on {exchange_name.capitalize()}"
            if owned_assets
            else f"Profitable Trade Path Found on {exchange_name.capitalize()}"
        )
        print(header)
        print(f"(Includes {fee_percentage:.2f}% fee per trade)")
        print("=" * 70)

        status = "Profit" if profit > 0 else "Loss"
        print(f"\nEstimated {status}: {profit:.4f}%")
        print(f"  Path: {' -> '.join(cycle)} -> {cycle[0]}")

        print("\n" + "=" * 70 + "\n")
        return opportunity
    else:
        message = (
            "No profitable trading cycles found that start with your available assets."
            if owned_assets
            else "No profitable trading cycles found at this time."
        )
        print(f"\n{message}\n")
        return None
