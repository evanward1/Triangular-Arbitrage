#!/usr/bin/env python3
"""
Opportunity Tracker - Monitor how often positive arbitrage opportunities appear
"""

import asyncio
import time
from datetime import datetime

from dotenv import load_dotenv

from trading_arbitrage import RealTriangularArbitrage

load_dotenv()


async def track_opportunities(duration_minutes=60):
    """Track arbitrage opportunities over time"""

    print(f"🔍 Starting {duration_minutes}-minute opportunity tracking session")
    print(f"⏰ Started at: {datetime.now().strftime('%H:%M:%S')}")
    print("=" * 60)

    trader = RealTriangularArbitrage("binanceus", "paper")

    stats = {
        "total_scans": 0,
        "scans_with_opportunities": 0,
        "total_opportunities": 0,
        "best_profit": -999.0,
        "best_cycle": None,
        "positive_opportunities": [],
    }

    start_time = time.time()
    end_time = start_time + (duration_minutes * 60)

    try:
        while time.time() < end_time:
            stats["total_scans"] += 1
            elapsed = time.time() - start_time

            # Find opportunities
            opportunities = await trader.find_arbitrage_opportunities()

            if opportunities:
                stats["scans_with_opportunities"] += 1
                stats["total_opportunities"] += len(opportunities)

                # Track best opportunity
                for opp in opportunities:
                    profit = opp["profit_percent"]
                    if profit > stats["best_profit"]:
                        stats["best_profit"] = profit
                        stats["best_cycle"] = " -> ".join(opp["cycle"])

                    # Track all positive opportunities
                    if profit > 0:
                        stats["positive_opportunities"].append(
                            {
                                "time": elapsed,
                                "profit": profit,
                                "cycle": " -> ".join(opp["cycle"]),
                            }
                        )

                print(
                    f"\n✅ Scan #{stats['total_scans']} ({elapsed:.0f}s): Found {len(opportunities)} opportunities"
                )
                print(
                    f"   Best: {opportunities[0]['cycle'][0]} -> ... -> {opportunities[0]['profit_percent']:+.4f}%"
                )
            else:
                print(
                    f"❌ Scan #{stats['total_scans']} ({elapsed:.0f}s): No opportunities",
                    end="\r",
                )

            await asyncio.sleep(2)  # Scan every 2 seconds

    except KeyboardInterrupt:
        print("\n\n🛑 Tracking stopped by user")

    # Print summary
    elapsed_total = time.time() - start_time
    print("\n" + "=" * 60)
    print("📊 OPPORTUNITY TRACKING SUMMARY")
    print("=" * 60)
    print(f"⏱️  Total runtime: {elapsed_total/60:.1f} minutes")
    print(f"🔍 Total scans: {stats['total_scans']}")
    print(f"✅ Scans with opportunities: {stats['scans_with_opportunities']}")
    print(f"📈 Total opportunities found: {stats['total_opportunities']}")

    if stats["scans_with_opportunities"] > 0:
        frequency = elapsed_total / stats["scans_with_opportunities"]
        print(f"⏰ Opportunity frequency: Every {frequency:.1f} seconds")
        print(f"💰 Best profit seen: {stats['best_profit']:+.4f}%")
        print(f"🔄 Best cycle: {stats['best_cycle']}")

    # Show positive opportunities
    positive_count = len(stats["positive_opportunities"])
    if positive_count > 0:
        print(f"\n🎯 Positive opportunities (above threshold): {positive_count}")
        for i, opp in enumerate(stats["positive_opportunities"][:10], 1):
            print(
                f"   {i}. At {opp['time']:.0f}s: {opp['cycle']} = {opp['profit']:+.4f}%"
            )
        if positive_count > 10:
            print(f"   ... and {positive_count - 10} more")
    else:
        print("\n⚠️  No opportunities above profit threshold detected")
        print(
            "   This is normal - triangular arbitrage opportunities are extremely rare"
        )
        print("   Consider:")
        print("   - Lower MIN_PROFIT_THRESHOLD (currently 0.1%)")
        print("   - Use multiple exchanges simultaneously")
        print("   - Add cross-exchange arbitrage (not just triangular)")

    print("=" * 60)


if __name__ == "__main__":
    import sys

    duration = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    asyncio.run(track_opportunities(duration))
