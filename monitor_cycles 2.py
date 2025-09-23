#!/usr/bin/env python3
"""
Cycle Monitor - View and manage trading cycle states

Usage:
    python monitor_cycles.py [--active] [--history] [--cleanup]
"""

import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from tabulate import tabulate

from triangular_arbitrage.execution_engine import (
    StateManager,
    CycleState,
    OrderState
)


def format_timestamp(ts):
    """Convert timestamp to readable datetime"""
    if ts:
        return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
    return 'N/A'


def format_amount(amount, currency=''):
    """Format amount with currency"""
    if amount is not None:
        return f"{amount:.6f} {currency}".strip()
    return 'N/A'


def show_active_cycles():
    """Display all active cycles"""
    state_manager = StateManager()
    cycles = state_manager.get_active_cycles()

    if not cycles:
        print("No active cycles found.")
        return

    print("\n=== ACTIVE CYCLES ===\n")

    for cycle in cycles:
        print(f"Cycle ID: {cycle.id}")
        print(f"Strategy: {cycle.strategy_name}")
        print(f"State: {cycle.state.value}")
        print(f"Path: {' -> '.join(cycle.cycle)} -> {cycle.cycle[0]}")
        print(f"Start Time: {format_timestamp(cycle.start_time)}")
        print(f"Current Step: {cycle.current_step + 1}/{len(cycle.cycle)}")
        print(f"Current Holdings: {format_amount(cycle.current_amount, cycle.current_currency)}")

        if cycle.orders:
            print("\nRecent Orders:")
            order_data = []
            for order in cycle.orders[-3:]:  # Show last 3 orders
                order_data.append([
                    order.market_symbol,
                    order.side,
                    f"{order.filled_amount:.6f}/{order.amount:.6f}",
                    order.state.value if isinstance(order.state, OrderState) else order.state
                ])

            print(tabulate(
                order_data,
                headers=['Market', 'Side', 'Filled/Total', 'Status'],
                tablefmt='grid'
            ))

        if cycle.error_message:
            print(f"Error: {cycle.error_message}")

        print("-" * 60)


def show_history(limit=20):
    """Display historical cycles"""
    conn = sqlite3.connect('trade_state.db')
    cursor = conn.cursor()

    cursor.execute('''
        SELECT id, strategy_name, state, start_time, end_time,
               initial_amount, current_amount, current_currency,
               profit_loss, error_message
        FROM cycles
        ORDER BY start_time DESC
        LIMIT ?
    ''', (limit,))

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        print("No cycle history found.")
        return

    print(f"\n=== CYCLE HISTORY (Last {limit}) ===\n")

    table_data = []
    for row in rows:
        cycle_id = row[0][:8] + '...' if len(row[0]) > 10 else row[0]
        strategy = row[1]
        state = row[2]
        start = format_timestamp(row[3])
        duration = f"{(row[4] - row[3]):.1f}s" if row[4] else 'N/A'
        profit = format_amount(row[8]) if row[8] else 'N/A'

        # Color code based on state
        if state == 'completed':
            state_display = f"✓ {state}"
        elif state == 'failed':
            state_display = f"✗ {state}"
        else:
            state_display = f"⟳ {state}"

        table_data.append([
            cycle_id,
            strategy,
            state_display,
            start,
            duration,
            profit
        ])

    print(tabulate(
        table_data,
        headers=['Cycle ID', 'Strategy', 'State', 'Start Time', 'Duration', 'P/L'],
        tablefmt='grid'
    ))

    # Summary statistics
    cursor = conn = sqlite3.connect('trade_state.db')
    cursor = conn.cursor()

    cursor.execute('''
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN state = 'completed' THEN 1 ELSE 0 END) as completed,
            SUM(CASE WHEN state = 'failed' THEN 1 ELSE 0 END) as failed,
            SUM(CASE WHEN state = 'completed' THEN profit_loss ELSE 0 END) as total_profit
        FROM cycles
    ''')

    stats = cursor.fetchone()
    conn.close()

    if stats[0] > 0:
        print(f"\n=== STATISTICS ===")
        print(f"Total Cycles: {stats[0]}")
        print(f"Completed: {stats[1]} ({stats[1]/stats[0]*100:.1f}%)")
        print(f"Failed: {stats[2]} ({stats[2]/stats[0]*100:.1f}%)")
        print(f"Total P/L: {stats[3]:.6f}" if stats[3] else "Total P/L: 0")


def show_cycle_details(cycle_id):
    """Show detailed information about a specific cycle"""
    conn = sqlite3.connect('trade_state.db')
    cursor = conn.cursor()

    cursor.execute('''
        SELECT * FROM cycles WHERE id = ?
    ''', (cycle_id,))

    row = cursor.fetchone()
    conn.close()

    if not row:
        print(f"Cycle {cycle_id} not found.")
        return

    print(f"\n=== CYCLE DETAILS: {cycle_id} ===\n")
    print(f"Strategy: {row[1]}")
    print(f"State: {row[6]}")
    print(f"Cycle Path: {json.loads(row[2])}")
    print(f"Initial Amount: {row[3]:.8f}")
    print(f"Current Amount: {row[4]:.8f}")
    print(f"Current Currency: {row[5]}")
    print(f"Current Step: {row[7]}")
    print(f"Start Time: {format_timestamp(row[9])}")
    print(f"End Time: {format_timestamp(row[10])}")

    if row[11]:
        print(f"Profit/Loss: {row[11]:.8f}")

    if row[12]:
        print(f"Error: {row[12]}")

    # Show orders
    orders = json.loads(row[8]) if row[8] else []
    if orders:
        print("\n=== ORDERS ===")
        order_data = []
        for i, order in enumerate(orders, 1):
            order_data.append([
                i,
                order.get('market_symbol'),
                order.get('side'),
                f"{order.get('filled_amount', 0):.6f}",
                f"{order.get('amount', 0):.6f}",
                order.get('average_price', 0),
                order.get('state')
            ])

        print(tabulate(
            order_data,
            headers=['#', 'Market', 'Side', 'Filled', 'Total', 'Avg Price', 'Status'],
            tablefmt='grid'
        ))

    # Show metadata
    metadata = json.loads(row[13]) if row[13] else {}
    if metadata:
        print("\n=== METADATA ===")
        for key, value in metadata.items():
            print(f"{key}: {value}")


def cleanup_database(days=7):
    """Clean up old completed/failed cycles"""
    state_manager = StateManager()
    state_manager.cleanup_old_cycles(days)
    print(f"Cleaned up cycles older than {days} days")


def main():
    parser = argparse.ArgumentParser(description='Monitor trading cycles')
    parser.add_argument(
        '--active',
        action='store_true',
        help='Show active cycles'
    )
    parser.add_argument(
        '--history',
        type=int,
        nargs='?',
        const=20,
        help='Show cycle history (default: last 20)'
    )
    parser.add_argument(
        '--details',
        type=str,
        help='Show details for a specific cycle ID'
    )
    parser.add_argument(
        '--cleanup',
        type=int,
        nargs='?',
        const=7,
        help='Clean up old cycles (default: 7 days)'
    )

    args = parser.parse_args()

    # Default to showing active cycles if no args
    if not any(vars(args).values()):
        args.active = True

    if args.active:
        show_active_cycles()

    if args.history:
        show_history(args.history)

    if args.details:
        show_cycle_details(args.details)

    if args.cleanup:
        cleanup_database(args.cleanup)


if __name__ == "__main__":
    main()