#!/usr/bin/env python3
"""
Unified Arbitrage Runner (CEX + DEX)

Examples:
  # Interactive menu
  python run_clean.py

  # CEX paper / live
  python run_clean.py cex --paper
  python run_clean.py cex --live

  # DEX paper mode (default if neither --paper nor --live specified)
  python run_clean.py dex --paper --quiet --once
  python run_clean.py dex --quiet --once  # same as above, --paper is default

  # DEX live mode (private, simulate-first assumed by your config)
  python run_clean.py dex --live --config configs/dex_mev.example.yaml
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

# ---------- helpers ----------

REPO = Path(__file__).resolve().parent


def file_exists(*paths):
    """Check if any of the given paths exist, return first match."""
    for p in paths:
        full = REPO / p
        if full.exists():
            return full
    return None


def run(cmd):
    """Run a command and return its exit code."""
    try:
        return subprocess.run(cmd, check=False).returncode
    except KeyboardInterrupt:
        print("\n⏸ Stopped by user")
        return 0


# ---------- DEX wrapper ----------


def run_dex(args):
    """
    Prefer the 'run_dex_paper.py' in repo root, then 'backtests/run_dex_paper.py'.
    Pass through --quiet/--once and config path. For --live we just remove paper-guards;
    your config/env governs private submission & simulation.
    """
    entry = file_exists("run_dex_paper.py", "backtests/run_dex_paper.py")
    if not entry:
        print(
            "❌ Could not find run_dex_paper.py (tried ./ and ./backtests/).",
            file=sys.stderr,
        )
        return 1

    cmd = [sys.executable, str(entry)]
    if args.quiet:
        cmd.append("--quiet")
    if args.once:
        cmd.append("--once")
    if args.config:
        # most runners read from configs/dex_mev.example.yaml by default;
        # expose a standard env to point at another file.
        os.environ["DEX_MEV_CONFIG"] = args.config
    if args.live:
        os.environ["DEX_LIVE_MODE"] = "true"  # your executor can check this
    # Note: --paper flag is accepted but doesn't need special handling (paper is default)

    print(f"▶ DEX runner: {' '.join(cmd)}")
    return run(cmd)


# ---------- CEX wrapper ----------


def run_cex(args):
    """
    Preserve your current CEX flow. We try to call the same thing your
    existing run_clean menu used to, with explicit flags.
    """
    # Your project likely has a main CEX entry (keep this adaptive):
    # Try to find the trading_arbitrage module first
    try:
        # Import check - if this works, we can use the async method
        import asyncio

        from dotenv import load_dotenv

        from trading_arbitrage import RealTriangularArbitrage

        load_dotenv()

        mode = "paper" if args.paper else "live"

        if mode == "live":
            print("\n" + "⚠️ " * 20)
            print("  LIVE TRADING MODE - REAL MONEY AT RISK!")
            print("⚠️ " * 20 + "\n")

            # Check API keys
            kraken_key = os.getenv("KRAKEN_API_KEY")
            binance_key = os.getenv("BINANCE_API_KEY")
            coinbase_key = os.getenv("COINBASE_API_KEY")

            if not any([kraken_key, binance_key, coinbase_key]):
                print("❌ No API keys found!")
                print("   Please set up your API keys in .env file first.")
                return 1

            confirmation = input(
                "⚠️  Type 'YES' in CAPS to proceed with LIVE trading: "
            )
            if confirmation != "YES":
                print("✅ Trading cancelled for safety")
                return 0

        mode_icon = "📝" if mode == "paper" else "💰"
        print(f"\n{mode_icon} Starting {mode.upper()} trading mode...\n")

        # Run the trading session
        async def run_session():
            exchanges_to_try = ["binanceus", "kraken", "kucoin", "coinbase"]
            for exchange_name in exchanges_to_try:
                print(f"🔄 Connecting to {exchange_name.upper()}...")
                try:
                    trader = RealTriangularArbitrage(exchange_name, mode)
                    await trader.run_trading_session()
                    break
                except Exception as e:
                    print(f"❌ {exchange_name.upper()} connection failed: {e}")
                    print("   Trying next exchange...\n")
                    continue

        try:
            asyncio.run(run_session())
        except KeyboardInterrupt:
            print("\n\n✋ Stopped by user")
            print("📊 Session ended gracefully")
        return 0

    except ImportError:
        # Fallback to subprocess approach
        candidates = [
            ["python3", "run.py", "--paper" if args.paper else "--live"],
            [sys.executable, "run.py", "--paper" if args.paper else "--live"],
            [sys.executable, "main.py", "--paper" if args.paper else "--live"],
        ]

        for cmd in candidates:
            if file_exists(cmd[1]):
                print(f"▶ CEX runner: {' '.join(cmd)}")
                return run(cmd)

        print(
            "❌ Could not find a CEX entrypoint (tried run.py/main.py).", file=sys.stderr
        )
        return 1


# ---------- argparse ----------


def build_parser():
    """Build argument parser with subcommands."""
    p = argparse.ArgumentParser(description="Unified Arbitrage Runner")
    sub = p.add_subparsers(dest="mode")

    # CEX
    cex = sub.add_parser("cex", help="Run CEX arbitrage")
    g = cex.add_mutually_exclusive_group()
    g.add_argument("--paper", action="store_true", help="CEX paper mode")
    g.add_argument("--live", action="store_true", help="CEX live mode")
    cex.set_defaults(func=run_cex)

    # DEX
    dex = sub.add_parser("dex", help="Run DEX MEV arbitrage")
    dex.add_argument("--quiet", "-q", action="store_true", help="Less noisy output")
    dex.add_argument("--once", action="store_true", help="Single scan and exit")
    dex.add_argument("--config", type=str, help="Path to DEX config YAML")
    dex_mode = dex.add_mutually_exclusive_group()
    dex_mode.add_argument("--paper", action="store_true", help="Paper mode (default)")
    dex_mode.add_argument(
        "--live", action="store_true", help="Live mode (private submission)"
    )
    dex.set_defaults(func=run_dex)

    return p


def interactive_menu():
    """Show interactive menu for mode selection."""
    print("\n" + "=" * 70)
    print("🤖  ARBITRAGE TRADING BOT")
    print("=" * 70)
    print("\nSelect Trading Mode:\n")
    print("  1) 📝 CEX Paper Trading  (practice with simulated money)")
    print("  2) 💰 CEX Live Trading   (real money - requires API keys)")
    print("  3) 📝 DEX Paper Trading  (practice with DeFi arbitrage)")
    print("  4) 💰 DEX Live Trading   (real money on blockchain)")
    print("\n" + "-" * 70)
    choice = input("Choose [1-4]: ").strip()
    if choice == "1":
        return run_cex(argparse.Namespace(paper=True, live=False))
    if choice == "2":
        return run_cex(argparse.Namespace(paper=False, live=True))
    if choice == "3":
        return run_dex(
            argparse.Namespace(
                quiet=False, once=False, config=None, paper=False, live=False
            )
        )
    if choice == "4":
        return run_dex(
            argparse.Namespace(
                quiet=False, once=False, config=None, paper=False, live=True
            )
        )
    print("Unknown choice.")
    return 1


def main():
    """Main entry point."""
    parser = build_parser()
    if len(sys.argv) == 1:
        return interactive_menu()
    args = parser.parse_args()
    if hasattr(args, "func"):
        return args.func(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
