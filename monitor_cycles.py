#!/usr/bin/env python3
"""
Cycle Monitor - View and manage trading cycle states

Usage:
    python monitor_cycles.py [--active] [--history] [--cleanup]
"""

import argparse
import json
import sqlite3
import sys
import os
import platform
import socket
from datetime import datetime
from pathlib import Path
from tabulate import tabulate

from triangular_arbitrage.execution_engine import (
    StateManager,
    CycleState,
    OrderState
)

try:
    from triangular_arbitrage.risk_controls import RiskControlManager
    RISK_CONTROLS_AVAILABLE = True
except ImportError:
    RISK_CONTROLS_AVAILABLE = False


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


def show_history(limit=20, mode_filter=None):
    """Display historical cycles with optional mode filtering"""
    conn = sqlite3.connect('trade_state.db')
    cursor = conn.cursor()

    # Build query with optional mode filtering
    query = '''
        SELECT id, strategy_name, state, start_time, end_time,
               initial_amount, current_amount, current_currency,
               profit_loss, error_message, metadata
        FROM cycles
    '''
    params = []

    if mode_filter:
        query += " WHERE json_extract(metadata, '$.execution_mode') = ?"
        params.append(mode_filter)

    query += " ORDER BY start_time DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()

    if not rows:
        mode_text = f" ({mode_filter} mode)" if mode_filter else ""
        print(f"No cycle history found{mode_text}.")
        return

    mode_text = f" ({mode_filter.upper()} mode)" if mode_filter else ""
    print(f"\n=== CYCLE HISTORY (Last {limit}){mode_text} ===\n")

    table_data = []
    for row in rows:
        cycle_id = row[0][:8] + '...' if len(row[0]) > 10 else row[0]
        strategy = row[1]
        state = row[2]
        start = format_timestamp(row[3])
        duration = f"{(row[4] - row[3]):.1f}s" if row[4] else 'N/A'
        profit = format_amount(row[8]) if row[8] else 'N/A'

        # Extract execution mode from metadata
        execution_mode = 'live'  # default
        if row[10]:  # metadata column
            try:
                import json
                metadata = json.loads(row[10])
                execution_mode = metadata.get('execution_mode', 'live')
            except:
                pass

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
            execution_mode,
            state_display,
            start,
            duration,
            profit
        ])

    print(tabulate(
        table_data,
        headers=['Cycle ID', 'Strategy', 'Mode', 'State', 'Start Time', 'Duration', 'P/L'],
        tablefmt='grid'
    ))

    # Enhanced summary statistics with mode breakdown
    show_execution_mode_summary(mode_filter)


def show_execution_mode_summary(mode_filter=None):
    """Show execution mode statistics"""
    conn = sqlite3.connect('trade_state.db')
    cursor = conn.cursor()

    # Base query for all modes
    if mode_filter:
        cursor.execute('''
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN state = 'completed' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN state = 'failed' THEN 1 ELSE 0 END) as failed,
                SUM(CASE WHEN state = 'partial_filled' THEN 1 ELSE 0 END) as partial,
                SUM(CASE WHEN state = 'completed' THEN profit_loss ELSE 0 END) as total_profit,
                AVG(CASE WHEN state = 'completed' AND end_time IS NOT NULL
                    THEN (end_time - start_time) ELSE NULL END) as avg_duration
            FROM cycles
            WHERE json_extract(metadata, '$.execution_mode') = ?
        ''', (mode_filter,))
        stats = cursor.fetchone()

        print(f"\n=== {mode_filter.upper()} MODE STATISTICS ===")
    else:
        # Show breakdown by mode
        cursor.execute('''
            SELECT
                COALESCE(json_extract(metadata, '$.execution_mode'), 'live') as mode,
                COUNT(*) as total,
                SUM(CASE WHEN state = 'completed' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN state = 'failed' THEN 1 ELSE 0 END) as failed,
                SUM(CASE WHEN state = 'partial_filled' THEN 1 ELSE 0 END) as partial,
                SUM(CASE WHEN state = 'completed' THEN profit_loss ELSE 0 END) as total_profit
            FROM cycles
            GROUP BY COALESCE(json_extract(metadata, '$.execution_mode'), 'live')
        ''')

        mode_stats = cursor.fetchall()

        if mode_stats:
            print(f"\n=== EXECUTION MODE BREAKDOWN ===")
            mode_table = []
            for mode_stat in mode_stats:
                mode, total, completed, failed, partial, profit = mode_stat
                success_rate = (completed / total * 100) if total > 0 else 0
                mode_table.append([
                    mode.upper(),
                    total,
                    completed,
                    failed,
                    partial,
                    f"{success_rate:.1f}%",
                    f"{profit:.6f}" if profit else "0.000000"
                ])

            print(tabulate(
                mode_table,
                headers=['Mode', 'Total', 'Completed', 'Failed', 'Partial', 'Success Rate', 'Total P/L'],
                tablefmt='grid'
            ))

        # Overall statistics
        cursor.execute('''
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN state = 'completed' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN state = 'failed' THEN 1 ELSE 0 END) as failed,
                SUM(CASE WHEN state = 'partial_filled' THEN 1 ELSE 0 END) as partial,
                SUM(CASE WHEN state = 'completed' THEN profit_loss ELSE 0 END) as total_profit
            FROM cycles
        ''')
        stats = cursor.fetchone()
        print(f"\n=== OVERALL STATISTICS ===")

    conn.close()

    if stats and stats[0] > 0:
        total, completed, failed, partial, total_profit = stats[:5]
        print(f"Total Cycles: {total}")
        print(f"Completed: {completed} ({completed/total*100:.1f}%)")
        print(f"Failed: {failed} ({failed/total*100:.1f}%)")
        if partial:
            print(f"Partial: {partial} ({partial/total*100:.1f}%)")
        print(f"Total P/L: {total_profit:.6f}" if total_profit else "Total P/L: 0.000000")

        if len(stats) > 5 and stats[5]:  # avg_duration
            print(f"Average Duration: {stats[5]:.1f}s")


def show_mode_performance():
    """Show performance comparison across execution modes"""
    conn = sqlite3.connect('trade_state.db')
    cursor = conn.cursor()

    cursor.execute('''
        SELECT
            COALESCE(json_extract(metadata, '$.execution_mode'), 'live') as mode,
            COUNT(*) as total_cycles,
            SUM(CASE WHEN state = 'completed' THEN 1 ELSE 0 END) as completed,
            AVG(CASE WHEN state = 'completed' AND profit_loss IS NOT NULL
                THEN profit_loss ELSE 0 END) as avg_profit,
            SUM(CASE WHEN state = 'completed' THEN profit_loss ELSE 0 END) as total_profit,
            AVG(CASE WHEN state = 'completed' AND end_time IS NOT NULL
                THEN (end_time - start_time) ELSE NULL END) as avg_duration,
            MIN(start_time) as first_trade,
            MAX(start_time) as last_trade
        FROM cycles
        WHERE start_time > strftime('%s', 'now', '-30 days')
        GROUP BY COALESCE(json_extract(metadata, '$.execution_mode'), 'live')
        ORDER BY total_cycles DESC
    ''')

    results = cursor.fetchall()
    conn.close()

    if not results:
        print("No cycle data found for the last 30 days.")
        return

    print("\n=== 30-DAY EXECUTION MODE PERFORMANCE ===\n")

    table_data = []
    for row in results:
        mode, total, completed, avg_profit, total_profit, avg_duration, first, last = row

        success_rate = (completed / total * 100) if total > 0 else 0
        avg_profit_display = f"{avg_profit:.6f}" if avg_profit else "0.000000"
        total_profit_display = f"{total_profit:.6f}" if total_profit else "0.000000"
        avg_duration_display = f"{avg_duration:.1f}s" if avg_duration else "N/A"

        # Calculate trading frequency
        if first and last and total > 1:
            days_active = (last - first) / 86400  # Convert to days
            freq = f"{total/max(days_active, 1):.1f}/day" if days_active > 0 else "N/A"
        else:
            freq = "N/A"

        table_data.append([
            mode.upper(),
            total,
            completed,
            f"{success_rate:.1f}%",
            avg_profit_display,
            total_profit_display,
            avg_duration_display,
            freq
        ])

    print(tabulate(
        table_data,
        headers=['Mode', 'Cycles', 'Completed', 'Success Rate', 'Avg Profit', 'Total Profit', 'Avg Duration', 'Frequency'],
        tablefmt='grid'
    ))
    print()


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


def show_risk_stats(time_window_hours=24):
    """Display risk control statistics"""
    if not RISK_CONTROLS_AVAILABLE:
        print("Risk controls module not available.")
        return

    risk_manager = RiskControlManager(
        max_leg_latency_ms=1000,
        max_slippage_bps=20
    )

    stats = risk_manager.get_stats(time_window_seconds=time_window_hours * 3600)

    print(f"\n=== RISK CONTROL STATISTICS (Last {time_window_hours}h) ===\n")

    print(f"Total Violations: {stats['violations']['total_violations']}")
    print(f"Active Cooldowns: {stats['active_cooldowns']}\n")

    if stats['violations']['by_type']:
        print("Violations by Type:")
        for vtype, count in stats['violations']['by_type'].items():
            print(f"  {vtype}: {count}")
        print()

    if stats['violations']['by_strategy']:
        print("Violations by Strategy:")
        for strategy, count in stats['violations']['by_strategy'].items():
            print(f"  {strategy}: {count}")
        print()

    if stats['violations']['by_cycle']:
        print("Top Violating Cycles:")
        sorted_cycles = sorted(
            stats['violations']['by_cycle'].items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]
        for cycle, count in sorted_cycles:
            print(f"  {cycle}: {count}")
        print()

    print("Configuration:")
    for key, value in stats['config'].items():
        print(f"  {key}: {value}")

    if 'suppression' in stats:
        print("\nDuplicate Suppression:")
        print(f"  Total Duplicates Suppressed: {stats['suppression']['total_duplicates_suppressed']}")
        print(f"  Cache Size: {stats['suppression']['cache_size']}")
        print(f"  Suppression Window: {stats['suppression']['suppression_window_seconds']}s")


def show_cooldowns():
    """Display active cooldowns"""
    if not RISK_CONTROLS_AVAILABLE:
        print("Risk controls module not available.")
        return

    risk_manager = RiskControlManager(
        max_leg_latency_ms=1000,
        max_slippage_bps=20
    )

    risk_manager.load_cooldowns()

    active_cooldowns = risk_manager.get_active_cooldowns()

    print("\n=== ACTIVE COOLDOWNS ===\n")

    if not active_cooldowns:
        print("✓ No active cooldowns - all trading pairs are available")
        print()
        return

    table_data = []
    for cycle_key, remaining_seconds in active_cooldowns:
        minutes = int(remaining_seconds // 60)
        seconds = int(remaining_seconds % 60)
        time_str = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"
        table_data.append([cycle_key, time_str])

    print(tabulate(
        table_data,
        headers=['Cycle', 'Remaining'],
        tablefmt='grid'
    ))
    print(f"\nTotal: {len(active_cooldowns)} cycle(s) in cooldown\n")


def clear_cooldown(pair):
    """Clear a specific cooldown with confirmation"""
    if not RISK_CONTROLS_AVAILABLE:
        print("Risk controls module not available.")
        return

    risk_manager = RiskControlManager(
        max_leg_latency_ms=1000,
        max_slippage_bps=20
    )

    risk_manager.load_cooldowns()

    if pair not in risk_manager.slippage_tracker.cooldown_cycles:
        print(f"Cooldown not found for {pair}")
        return

    response = input(f"Confirm clear cooldown for {pair}? [y/N]: ").strip().lower()

    if response == 'y':
        success = risk_manager.clear_cooldown(pair)
        if success:
            print(f"Cleared cooldown for {pair}")
        else:
            print(f"Failed to clear cooldown for {pair}")
    else:
        print("Canceled")

    show_cooldowns()


def format_time(seconds):
    """Format seconds as Xm Ys or Xs"""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    if minutes > 0:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def extend_cooldown(pair, seconds):
    """Extend or shorten a cooldown by N seconds with confirmation"""
    if not RISK_CONTROLS_AVAILABLE:
        print("Risk controls module not available.")
        return

    risk_manager = RiskControlManager(
        max_leg_latency_ms=1000,
        max_slippage_bps=20
    )

    risk_manager.load_cooldowns()

    if pair not in risk_manager.slippage_tracker.cooldown_cycles:
        print(f"Cooldown not found for {pair}")
        return

    current_remaining = risk_manager.get_cycle_cooldown_remaining([p for p in pair.split('->')])
    new_remaining = max(current_remaining + seconds, 1.0)

    sign = '+' if seconds >= 0 else ''
    print(f"Current remaining: {format_time(current_remaining)}")
    print(f"Proposed new remaining: {format_time(new_remaining)}")

    response = input(f"Confirm adjust cooldown for {pair} by {sign}{seconds}s? [y/N]: ").strip().lower()

    if response == 'y':
        success = risk_manager.extend_cooldown(pair, seconds)
        if success:
            final_remaining = risk_manager.get_cycle_cooldown_remaining([p for p in pair.split('->')])
            print(f"Adjusted cooldown for {pair} → New remaining: {format_time(final_remaining)}")
        else:
            print(f"Failed to adjust cooldown for {pair}")
    else:
        print("Canceled")

    show_cooldowns()


def clear_all_cooldowns():
    """Clear all active cooldowns with confirmation"""
    if not RISK_CONTROLS_AVAILABLE:
        print("Risk controls module not available.")
        return

    risk_manager = RiskControlManager(
        max_leg_latency_ms=1000,
        max_slippage_bps=20
    )

    risk_manager.load_cooldowns()

    active_count = len(risk_manager.slippage_tracker.cooldown_cycles)

    if active_count == 0:
        print("No active cooldowns to clear")
        return

    response = input(f"Confirm clear ALL cooldowns ({active_count} total)? [y/N]: ").strip().lower()

    if response == 'y':
        cleared_count = risk_manager.clear_all_cooldowns()
        print(f"Cleared {cleared_count} cooldowns")
    else:
        print("Canceled")

    show_cooldowns()


def show_suppressed(limit=10):
    """Display recently suppressed duplicate events"""
    if not RISK_CONTROLS_AVAILABLE:
        print("Risk controls module not available.")
        return

    risk_manager = RiskControlManager(
        max_leg_latency_ms=1000,
        max_slippage_bps=20
    )

    suppressed = risk_manager.logger.get_recent_suppressed(limit)

    print(f"\n=== RECENTLY SUPPRESSED DUPLICATES (Last {limit}) ===\n")

    if not suppressed:
        print("No suppressed duplicates recorded")
        print()
        return

    table_data = []
    for event in suppressed:
        cycle_id = event['cycle_id'][:20] + '...' if len(event['cycle_id']) > 22 else event['cycle_id']
        first_seen = datetime.fromtimestamp(event['first_seen']).strftime('%H:%M:%S')
        last_seen = datetime.fromtimestamp(event['last_seen']).strftime('%H:%M:%S')

        table_data.append([
            cycle_id,
            event['stop_reason'],
            event['duplicate_count'],
            first_seen,
            last_seen
        ])

    print(tabulate(
        table_data,
        headers=['Cycle ID', 'Reason', 'Count', 'First Seen', 'Last Seen'],
        tablefmt='grid'
    ))
    print(f"\nTotal suppressed events shown: {len(suppressed)}\n")


def snapshot_ops(out_dir="logs/ops", recent=10, window=300):
    """Capture current risk state snapshot"""
    if not RISK_CONTROLS_AVAILABLE:
        print("Risk controls module not available.")
        return

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_file = out_path / f"ops_snapshot_{timestamp_str}.json"
    md_file = out_path / f"ops_snapshot_{timestamp_str}.md"

    risk_manager = RiskControlManager(
        max_leg_latency_ms=1000,
        max_slippage_bps=20
    )
    risk_manager.load_cooldowns()

    snapshot = {
        'metadata': {
            'timestamp': datetime.now().isoformat(),
            'hostname': socket.gethostname(),
            'python_version': platform.python_version(),
            'platform': platform.platform()
        },
        'config': {
            'max_slippage_bps': 20,
            'max_leg_latency_ms': 1000,
            'duplicate_suppression_window_seconds': risk_manager.logger.suppression_window
        },
        'active_cooldowns': [],
        'suppression_summary': {},
        'recent_suppressed': []
    }

    active_cooldowns = risk_manager.get_active_cooldowns()
    for cycle_key, remaining in active_cooldowns:
        snapshot['active_cooldowns'].append({
            'pair': cycle_key,
            'seconds_remaining': round(remaining, 2)
        })

    summary = risk_manager.logger.get_suppression_summary(window_seconds=window)
    snapshot['suppression_summary'] = summary

    recent_suppressed = risk_manager.logger.get_recent_suppressed(limit=recent)
    for event in recent_suppressed:
        snapshot['recent_suppressed'].append({
            'cycle_id': event['cycle_id'],
            'stop_reason': event['stop_reason'],
            'duplicate_count': event['duplicate_count'],
            'first_seen': datetime.fromtimestamp(event['first_seen']).isoformat(),
            'last_seen': datetime.fromtimestamp(event['last_seen']).isoformat()
        })

    with open(json_file, 'w') as f:
        json.dump(snapshot, f, indent=2)

    with open(md_file, 'w') as f:
        f.write(f"# Operations Snapshot\n\n")
        f.write(f"**Generated:** {snapshot['metadata']['timestamp']}  \n")
        f.write(f"**Hostname:** {snapshot['metadata']['hostname']}  \n")
        f.write(f"**Python:** {snapshot['metadata']['python_version']}  \n")
        f.write(f"**Platform:** {snapshot['metadata']['platform']}  \n\n")

        f.write(f"## Configuration\n\n")
        f.write(f"| Parameter | Value |\n")
        f.write(f"|-----------|-------|\n")
        for key, value in snapshot['config'].items():
            f.write(f"| {key} | {value} |\n")
        f.write(f"\n")

        f.write(f"## Active Cooldowns\n\n")
        if snapshot['active_cooldowns']:
            f.write(f"| Pair | Remaining (s) |\n")
            f.write(f"|------|---------------|\n")
            for cd in snapshot['active_cooldowns']:
                f.write(f"| {cd['pair']} | {cd['seconds_remaining']} |\n")
        else:
            f.write(f"✓ No active cooldowns\n")
        f.write(f"\n")

        f.write(f"## Suppression Summary (Last {window}s)\n\n")
        s = snapshot['suppression_summary']
        f.write(f"- **Total Suppressed:** {s['total_suppressed']}\n")
        f.write(f"- **Unique Pairs:** {s['unique_pairs']}\n")
        f.write(f"- **Suppression Rate:** {s['suppression_rate']:.2f}%\n\n")
        if s['top_pairs']:
            f.write(f"### Top Offenders\n\n")
            f.write(f"| Cycle ID | Reason | Count |\n")
            f.write(f"|----------|--------|-------|\n")
            for pair in s['top_pairs']:
                f.write(f"| {pair['cycle_id']} | {pair['stop_reason']} | {pair['count']} |\n")
            f.write(f"\n")

        f.write(f"## Recent Suppressed Events (Last {recent})\n\n")
        if snapshot['recent_suppressed']:
            f.write(f"| Cycle ID | Reason | Count | First Seen | Last Seen |\n")
            f.write(f"|----------|--------|-------|------------|----------|\n")
            for event in snapshot['recent_suppressed']:
                f.write(f"| {event['cycle_id']} | {event['stop_reason']} | {event['duplicate_count']} | {event['first_seen']} | {event['last_seen']} |\n")
        else:
            f.write(f"✓ No recent suppressed events\n")

    print(f"\nSnapshot saved:")
    print(f"  JSON: {json_file}")
    print(f"  MD:   {md_file}\n")


def health_check(window=300, max_suppression_rate=95):
    """Health check with exit code"""
    if not RISK_CONTROLS_AVAILABLE:
        print("FAIL: Risk controls module not available")
        return 1

    try:
        log_dir = Path("logs/ops")
        log_dir.mkdir(parents=True, exist_ok=True)
        test_file = log_dir / ".health_check_test"
        test_file.write_text("test")
        test_file.unlink()
    except Exception as e:
        print(f"FAIL: Logs directory not writable: {e}")
        return 1

    risk_manager = RiskControlManager(
        max_leg_latency_ms=1000,
        max_slippage_bps=20
    )

    try:
        risk_manager.load_cooldowns()
    except Exception as e:
        print(f"FAIL: Cooldown state file error: {e}")
        return 1

    active_cooldowns = risk_manager.get_active_cooldowns()
    for cycle_key, remaining in active_cooldowns:
        if remaining < 0:
            print(f"FAIL: Negative remaining time for {cycle_key}: {remaining}s")
            return 1

    summary = risk_manager.logger.get_suppression_summary(window_seconds=window)
    if summary['suppression_rate'] > max_suppression_rate:
        print(f"FAIL: Suppression rate {summary['suppression_rate']:.2f}% exceeds threshold {max_suppression_rate}%")
        return 1

    print("OK")
    return 0


def show_suppression_summary(window_seconds=300):
    """Display suppression summary metrics"""
    if not RISK_CONTROLS_AVAILABLE:
        print("Risk controls module not available.")
        return

    risk_manager = RiskControlManager(
        max_leg_latency_ms=1000,
        max_slippage_bps=20
    )

    summary = risk_manager.logger.get_suppression_summary(window_seconds)

    minutes = window_seconds // 60
    window_display = f"{minutes}m" if minutes > 0 else f"{window_seconds}s"

    print(f"\n=== SUPPRESSION SUMMARY (Last {window_display}) ===\n")

    if summary['total_suppressed'] == 0:
        print(f"No suppressed duplicates in last {window_seconds} seconds")
        print()
        return

    print(f"Total Suppressed: {summary['total_suppressed']}")
    print(f"Unique Pairs: {summary['unique_pairs']}")
    print(f"Suppression Rate: {summary['suppression_rate']:.2f}%")

    if summary['top_pairs']:
        print("\nTop Offenders:")
        table_data = []
        for pair in summary['top_pairs']:
            cycle_id = pair['cycle_id'][:30] + '...' if len(pair['cycle_id']) > 32 else pair['cycle_id']
            table_data.append([
                cycle_id,
                pair['stop_reason'],
                pair['count']
            ])

        print(tabulate(
            table_data,
            headers=['Cycle ID', 'Reason', 'Count'],
            tablefmt='grid'
        ))

    print()


def main():
    parser = argparse.ArgumentParser(description='Monitor trading cycles with execution mode support')
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
        '--mode',
        choices=['live', 'paper', 'backtest'],
        help='Filter results by execution mode'
    )
    parser.add_argument(
        '--mode-performance',
        action='store_true',
        help='Show performance comparison across execution modes'
    )
    parser.add_argument(
        '--mode-summary',
        action='store_true',
        help='Show execution mode breakdown and statistics'
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
    parser.add_argument(
        '--risk-stats',
        type=int,
        nargs='?',
        const=24,
        help='Show risk control statistics (default: last 24 hours)'
    )
    parser.add_argument(
        '--cooldowns',
        action='store_true',
        help='Show active cooldown pairs and remaining time'
    )
    parser.add_argument(
        '--clear-cooldown',
        type=str,
        metavar='PAIR',
        help='Clear cooldown for specific pair (e.g., BTC->ETH->USDT)'
    )
    parser.add_argument(
        '--extend-cooldown',
        nargs=2,
        metavar=('PAIR', 'SECONDS'),
        help='Extend cooldown by N seconds (e.g., BTC->ETH->USDT 60)'
    )
    parser.add_argument(
        '--shorten-cooldown',
        nargs=2,
        metavar=('PAIR', 'SECONDS'),
        help='Shorten cooldown by N seconds (e.g., BTC->ETH->USDT 30)'
    )
    parser.add_argument(
        '--clear-all-cooldowns',
        action='store_true',
        help='Clear all active cooldowns (with confirmation)'
    )
    parser.add_argument(
        '--suppressed',
        type=int,
        nargs='?',
        const=10,
        metavar='N',
        help='Show recently suppressed duplicate events (default: last 10)'
    )
    parser.add_argument(
        '--suppression-summary',
        type=int,
        nargs='?',
        const=300,
        metavar='WINDOW',
        help='Show suppression summary metrics (default: last 300 seconds)'
    )
    parser.add_argument(
        'subcommand',
        nargs='?',
        choices=['snapshot', 'health'],
        help='Subcommand: snapshot or health'
    )
    parser.add_argument(
        '--out-dir',
        type=str,
        default='logs/ops',
        help='Output directory for snapshot (default: logs/ops)'
    )
    parser.add_argument(
        '--recent',
        type=int,
        default=10,
        help='Number of recent suppressed events for snapshot (default: 10)'
    )
    parser.add_argument(
        '--window',
        type=int,
        default=300,
        help='Time window in seconds for summary/health (default: 300)'
    )
    parser.add_argument(
        '--max-suppression-rate',
        type=float,
        default=95.0,
        help='Max suppression rate threshold for health check (default: 95)'
    )

    args = parser.parse_args()

    if args.subcommand == 'snapshot':
        snapshot_ops(out_dir=args.out_dir, recent=args.recent, window=args.window)
        return

    if args.subcommand == 'health':
        exit_code = health_check(window=args.window, max_suppression_rate=args.max_suppression_rate)
        sys.exit(exit_code)

    # Default to showing active cycles if no args
    if not any(vars(args).values()):
        args.active = True

    if args.active:
        show_active_cycles()

    if args.history:
        show_history(args.history, mode_filter=args.mode)

    if args.mode_performance:
        show_mode_performance()

    if args.mode_summary:
        show_execution_mode_summary()

    if args.details:
        show_cycle_details(args.details)

    if args.cleanup:
        cleanup_database(args.cleanup)

    if args.risk_stats:
        show_risk_stats(args.risk_stats)

    if args.cooldowns:
        show_cooldowns()

    if args.clear_cooldown:
        clear_cooldown(args.clear_cooldown)

    if args.extend_cooldown:
        pair, seconds = args.extend_cooldown
        extend_cooldown(pair, int(seconds))

    if args.shorten_cooldown:
        pair, seconds = args.shorten_cooldown
        extend_cooldown(pair, -int(seconds))

    if args.clear_all_cooldowns:
        clear_all_cooldowns()

    if args.suppressed is not None:
        show_suppressed(args.suppressed)

    if args.suppression_summary is not None:
        show_suppression_summary(args.suppression_summary)


if __name__ == "__main__":
    main()