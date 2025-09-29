#!/usr/bin/env python3
"""
Simple Clean Arbitrage Runner
Just run: python run_clean.py
"""

import os
import sqlite3
import subprocess
import time

from dotenv import load_dotenv


def clear_database():
    """Clear stuck cycles"""
    try:
        conn = sqlite3.connect("trade_state.db")
        conn.execute("DELETE FROM cycles")
        conn.commit()
        conn.close()
        print("🧹 Database cleared")
    except Exception:
        pass


def run_arbitrage():
    """Run arbitrage with 30-second feedback intervals"""
    # Load environment variables
    load_dotenv()

    clear_database()

    print("🚀 Initializing arbitrage trading system...")
    print()
    print("Choose trading mode:")
    print("1. 📝 Paper Trading (Simulation - Safe)")
    print("2. 💰 Live Trading (Real Money - Risk)")
    print()

    while True:
        choice = input("Enter your choice (1 or 2): ").strip()
        if choice == "1":
            trading_mode = "paper"
            print("📝 PAPER TRADING MODE - Simulation only")
            break
        elif choice == "2":
            trading_mode = "live"
            print("⚠️  LIVE TRADING MODE - Using real money!")
            print("🔑 Checking API keys...")

            # Check if API keys are configured
            kraken_key = os.getenv("KRAKEN_API_KEY")
            binance_key = os.getenv("BINANCE_API_KEY")
            coinbase_key = os.getenv("COINBASE_API_KEY")

            if not any([kraken_key, binance_key, coinbase_key]):
                print("❌ No API keys found!")
                print("Please set up your API keys in .env file first.")
                print("See TRADING_SETUP.md for instructions.")
                return

            print("✅ API keys configured")
            print()
            confirmation = input(
                "⚠️  Are you absolutely sure you want to proceed with LIVE "
                "trading? Type 'YES': "
            )
            if confirmation != "YES":
                print("❌ Trading cancelled for safety")
                return
            break
        else:
            print("❌ Invalid choice. Please enter 1 or 2.")

    max_position = os.getenv("MAX_POSITION_SIZE", "100")
    min_profit = os.getenv("MIN_PROFIT_THRESHOLD", "0.5")

    print(f"💰 Max position size: ${max_position}")
    print(f"📊 Min profit threshold: {min_profit}%")
    print("🎯 Monitoring markets for arbitrage opportunities...")
    print("📊 Reporting interval: 30 seconds\n")

    # Set environment variable for the subprocess
    env = os.environ.copy()
    env["TRADING_MODE"] = trading_mode

    cmd = [
        "python",
        "trading_arbitrage.py" if trading_mode == "live" else "fresh_arbitrage.py",
    ]

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        )

        # Track stats for 30-second intervals
        interval_start = time.time()
        cycles_considered = 0
        cycles_executed = 0
        cycles_rejected = []
        interval_count = 1
        current_balance = 10000.0  # Track running balance
        started_cycles = set()  # Track which cycles we've already shown as started
        pending_completions = []  # Track cycles waiting for balance confirmation

        # Metrics tracking
        total_profit = 0.0
        successful_trades = 0
        failed_trades = 0
        largest_profit = 0.0
        largest_loss = 0.0
        session_start_time = time.time()

        for line in process.stdout:
            line = line.strip()

            # Track cycles considered
            if "Testing cycle:" in line:
                cycles_considered += 1
                cycle_name = line.split("Testing cycle:")[1].split("Amount:")[0].strip()

            # Track cycle starts - only count Step 1 to avoid duplicates
            elif "Step 1: Trading" in line:
                # Only show cycles we haven't already started
                if cycle_name not in started_cycles:
                    cycles_executed += 1
                    started_cycles.add(cycle_name)
                    # Extract trading pair and amount
                    if " -> " in line and "Amount:" in line:
                        trading_part = (
                            line.split("Step 1: Trading")[1].split(",")[0].strip()
                        )
                        amount_part = line.split("Amount:")[1].strip()
                        print(f"💰 STARTING CYCLE: {cycle_name}")
                        amount_value = float(amount_part)
                        print(
                            f"   🔄 First trade: {trading_part} (${amount_value:,.2f})"
                        )
                    else:
                        print(f"💰 STARTING CYCLE: {cycle_name}")

            # Track cycle completions - but validate they actually completed
            elif "✅ Cycle completed:" in line:
                # Add to pending - we'll confirm completion when balance updates
                pending_completions.append(cycle_name)

            # Track cycle failures (log to file, don't show to user)
            elif (
                "❌ Cycle failed:" in line
                or "Cycle ended in" in line
                or "❌ Cycle incomplete:" in line
            ):
                if "Cycle incomplete:" in line:
                    reason = "Did not return to starting currency"
                else:
                    reason = (
                        line.split(":")[-1].strip() if ":" in line else "Unknown reason"
                    )

                # Log error to file instead of showing to user
                import logging

                # Set up error logging if not already done
                if not hasattr(logging.getLogger(), "_arbitrage_handler_added"):
                    log_dir = "logs"
                    os.makedirs(log_dir, exist_ok=True)
                    error_handler = logging.FileHandler(
                        f"{log_dir}/arbitrage_errors.log"
                    )
                    error_handler.setFormatter(
                        logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
                    )
                    logger = logging.getLogger("arbitrage_monitor")
                    logger.addHandler(error_handler)
                    logger.setLevel(logging.ERROR)
                    logger._arbitrage_handler_added = True

                logger = logging.getLogger("arbitrage_monitor")
                logger.error(f"Cycle failed: {cycle_name} - {reason}")

                # For rejected cycles counter
                cycles_rejected.append(f"{cycle_name}: {reason}")

            # Track real balance updates from the system
            elif "Current balances:" in line:
                # Extract balance from line
                try:
                    balance_part = line.split("Current balances:")[1].strip()

                    # Check if balance is actually in USD (successful completion)
                    if "USD" in balance_part and not any(
                        curr in balance_part
                        for curr in ["BTC", "COMP", "DASH", "XLM", "MASK"]
                    ):
                        # Extract USD balance using regex-like parsing
                        import re

                        match = re.search(r"'USD',\s*([\d.]+)", balance_part)
                        if match:
                            new_balance = float(match.group(1))
                            if (
                                abs(new_balance - current_balance) > 0.01
                            ):  # Only show if changed
                                profit = new_balance - current_balance

                                # Show any pending completions as actually completed
                                for completed_cycle in pending_completions:
                                    print(f"✅ COMPLETED: {completed_cycle}")
                                pending_completions.clear()

                                print("💰 REAL BALANCE UPDATE:")
                                print(
                                    f"   📊 Before: ${current_balance:,.2f} → "
                                    f"After: ${new_balance:,.2f}"
                                )
                                print(f"   💵 Real Profit/Loss: ${profit:+,.2f}")

                                # Update metrics
                                total_profit += profit
                                if profit > 0:
                                    successful_trades += 1
                                    largest_profit = max(largest_profit, profit)
                                else:
                                    failed_trades += 1
                                    largest_loss = min(largest_loss, profit)

                                current_balance = new_balance
                    else:
                        # Balance is in other currencies - incomplete
                        # Clear pending completions
                        pending_completions.clear()

                except Exception as e:
                    # Log parsing errors
                    import logging

                    if not hasattr(logging.getLogger(), "_arbitrage_handler_added"):
                        log_dir = "logs"
                        os.makedirs(log_dir, exist_ok=True)
                        error_handler = logging.FileHandler(
                            f"{log_dir}/arbitrage_errors.log"
                        )
                        error_handler.setFormatter(
                            logging.Formatter(
                                "%(asctime)s - %(levelname)s - %(message)s"
                            )
                        )
                        logger = logging.getLogger("arbitrage_monitor")
                        logger.addHandler(error_handler)
                        logger.setLevel(logging.ERROR)
                        logger._arbitrage_handler_added = True

                    logger = logging.getLogger("arbitrage_monitor")
                    logger.error(f"Could not parse balance from: {line} - Error: {e}")

            # Track rejections with reasons
            elif "❌ Cycle failed:" in line:
                reason = line.split("❌ Cycle failed:")[1].strip()
                cycles_rejected.append(f"{cycle_name}: {reason}")

            # Report every 30 seconds
            if time.time() - interval_start >= 30:
                session_runtime = time.time() - session_start_time
                win_rate = (
                    successful_trades / max(successful_trades + failed_trades, 1)
                ) * 100

                print(f"\n📊 Market Analysis Report #{interval_count}:")
                print(f"   🔍 Opportunities analyzed: {cycles_considered}")
                print(f"   ✅ Trades executed: {cycles_executed}")

                # Only show rejection count, not details (details go to logs)
                if cycles_rejected:
                    print(f"   📋 Opportunities skipped: {len(cycles_rejected)}")

                print(f"   ⏰ Analysis duration: {interval_count * 30} seconds")

                # Session metrics
                print("\n💼 Session Performance:")
                print(f"   📈 Total P&L: ${total_profit:+,.2f}")
                print(
                    f"   🎯 Win rate: {win_rate:.1f}% "
                    f"({successful_trades}W/{failed_trades}L)"
                )
                print(f"   🔥 Largest gain: ${largest_profit:+,.2f}")
                if largest_loss < 0:
                    print(f"   ⚠️  Largest loss: ${largest_loss:+,.2f}")
                print(f"   💰 Current balance: ${current_balance:,.2f}")
                print(f"   ⏳ Runtime: {session_runtime/60:.1f} minutes\n")

                # Reset for next interval
                cycles_considered = 0
                cycles_executed = 0
                cycles_rejected = []
                interval_start = time.time()
                interval_count += 1

            # Show final results
            if "🎯 EXECUTION COMPLETE" in line:
                print(f"\n{line}")
            elif "💰 Executed:" in line:
                print(line)
            elif "Final balances:" in line:
                print(line)
                break

        process.wait()
        print("\n✨ Scan complete!")

    except KeyboardInterrupt:
        print("\n🛑 Stopped by user")
        if "process" in locals():
            process.terminate()


if __name__ == "__main__":
    run_arbitrage()
