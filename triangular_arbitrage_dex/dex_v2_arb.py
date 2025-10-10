#!/usr/bin/env python3
import os
import time
from dataclasses import dataclass
from decimal import Decimal, getcontext
from typing import Tuple

from dotenv import load_dotenv
from web3 import Web3

# high precision
getcontext().prec = 50

# ---- hardcoded mainnet pools: USDC/WETH on UniV2 + SushiV2 ----
UNIV2_USDC_WETH = Web3.to_checksum_address("0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc")
SUSHI_USDC_WETH = Web3.to_checksum_address("0x397FF1542f962076d0BFE58eA045FfA2d347ACa0")
USDC = Web3.to_checksum_address("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48")
WETH = Web3.to_checksum_address("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2")
USDC_DEC, WETH_DEC = 6, 18
V2_FEE = Decimal("0.003")  # 0.30%

PAIR_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "token0",
        "outputs": [{"name": "", "type": "address"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "token1",
        "outputs": [{"name": "", "type": "address"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "getReserves",
        "outputs": [
            {"name": "_reserve0", "type": "uint112"},
            {"name": "_reserve1", "type": "uint112"},
            {"name": "_blockTimestampLast", "type": "uint32"},
        ],
        "type": "function",
    },
]


def d(x):
    return Decimal(str(x))


def to_units(raw: Decimal, decimals: int) -> Decimal:
    return raw / (Decimal(10) ** decimals)


def to_wei(human: Decimal, decimals: int) -> Decimal:
    return (human * (Decimal(10) ** decimals)).quantize(Decimal(1))


def fmt_money(x: Decimal) -> str:
    return f"${x:,.2f}"


@dataclass
class PairInfo:
    name: str
    address: str
    token0: str
    token1: str
    r0: Decimal
    r1: Decimal


def amount_out_v2(
    amount_in: Decimal,
    reserve_in: Decimal,
    reserve_out: Decimal,
    fee=V2_FEE,
) -> Decimal:
    if amount_in <= 0 or reserve_in <= 0 or reserve_out <= 0:
        return Decimal(0)
    ain = amount_in * (Decimal(1) - fee)
    return (ain * reserve_out) / (reserve_in + ain)


def fetch_pair(w3: Web3, addr: str) -> PairInfo:
    c = w3.eth.contract(address=addr, abi=PAIR_ABI)
    t0 = Web3.to_checksum_address(c.functions.token0().call())
    t1 = Web3.to_checksum_address(c.functions.token1().call())
    r0, r1, _ = c.functions.getReserves().call()
    return PairInfo(
        name=("UniswapV2" if addr == UNIV2_USDC_WETH else "SushiV2"),
        address=addr,
        token0=t0,
        token1=t1,
        r0=d(r0),
        r1=d(r1),
    )


def reserves_in_out(
    p: PairInfo, token_in: str, token_out: str
) -> Tuple[Decimal, Decimal]:
    if token_in == p.token0 and token_out == p.token1:
        return p.r0, p.r1
    if token_in == p.token1 and token_out == p.token0:
        return p.r1, p.r0
    raise ValueError("Token pair mismatch")


def simulate_cycle_usdc(
    pair_buy: PairInfo, pair_sell: PairInfo, size_usdc: Decimal
) -> Decimal:
    # USDC -> WETH on pair_buy
    r_in1, r_out1 = reserves_in_out(pair_buy, USDC, WETH)
    a1_raw = to_wei(size_usdc, USDC_DEC)
    out_weth_raw = amount_out_v2(a1_raw, r_in1, r_out1)
    # WETH -> USDC on pair_sell
    r_in2, r_out2 = reserves_in_out(pair_sell, WETH, USDC)
    out_usdc_raw = amount_out_v2(out_weth_raw, r_in2, r_out2)
    return to_units(out_usdc_raw, USDC_DEC)


def gas_cost_usd(gwei: Decimal, gas_limit: Decimal, eth_usd: Decimal) -> Decimal:
    return gas_limit * (gwei * Decimal(1e-9)) * eth_usd


def eth_usd_from_pair(p: PairInfo) -> Decimal:
    # USDC per WETH from reserves orientation
    if p.token0 == WETH and p.token1 == USDC:
        w, u = p.r0, p.r1
    else:
        w, u = p.r1, p.r0
    # reserves are raw; adjust decimals: (u/10^6) / (w/10^18)
    return (u / (Decimal(10) ** USDC_DEC)) / (w / (Decimal(10) ** WETH_DEC))


class DexV2Paper:
    def __init__(self):
        load_dotenv()
        rpc = os.getenv("RPC_URL")
        if not rpc:
            raise RuntimeError("Set RPC_URL in .env")
        self.w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 20}))
        if not self.w3.is_connected():
            raise RuntimeError("Web3 not connected; bad RPC_URL?")
        self.gas_gwei = d(os.getenv("GAS_PRICE_GWEI", "12"))
        self.gas_limit = d(os.getenv("GAS_LIMIT", "180000"))
        self.scan_sec = float(os.getenv("SCAN_SEC", "10"))
        self.cash_usdc = d(os.getenv("START_CASH_USDC", "1000"))
        self.grid_lo = d(os.getenv("GRID_LO_USDC", "10"))
        self.grid_hi = min(self.cash_usdc, d(os.getenv("GRID_HI_USDC", "10000")))
        self.grid_steps = int(os.getenv("GRID_STEPS", "40"))

    def _best_cycle(self, uni: PairInfo, sushi: PairInfo):
        best = {
            "dir": "",
            "size": d(0),
            "gross": d("-1e18"),
            "final": d(0),
        }
        for i in range(1, self.grid_steps + 1):
            sz = self.grid_lo + (self.grid_hi - self.grid_lo) * d(i) / d(
                self.grid_steps
            )
            fwd_final = simulate_cycle_usdc(uni, sushi, sz)
            rev_final = simulate_cycle_usdc(sushi, uni, sz)
            if (fwd_final - sz) > best["gross"]:
                best = {
                    "dir": "UNI→SUSHI",
                    "size": sz,
                    "gross": (fwd_final - sz),
                    "final": fwd_final,
                }
            if (rev_final - sz) > best["gross"]:
                best = {
                    "dir": "SUSHI→UNI",
                    "size": sz,
                    "gross": (rev_final - sz),
                    "final": rev_final,
                }
        return best

    def run(self):
        print("📝 DEX ARB PAPER MODE (V2↔V2 USDC/WETH) | fees=0.30% per pool")
        print(
            f"Gas≈{self.gas_gwei} gwei × {self.gas_limit} | "
            f"Start cash={fmt_money(self.cash_usdc)}\n"
        )

        eq_start = self.cash_usdc
        eq = self.cash_usdc
        scans = 0
        try:
            while True:
                scans += 1
                t0 = time.time()
                uni = fetch_pair(self.w3, UNIV2_USDC_WETH)
                sushi = fetch_pair(self.w3, SUSHI_USDC_WETH)

                eth_uni = eth_usd_from_pair(uni)
                eth_sushi = eth_usd_from_pair(sushi)
                eth_mid = (eth_uni + eth_sushi) / 2

                best = self._best_cycle(uni, sushi)
                gas_usd = gas_cost_usd(self.gas_gwei, self.gas_limit, eth_mid)
                net = best["gross"] - gas_usd

                executed = False
                if net > 0 and best["size"] <= eq:
                    eq += net
                    executed = True

                print(
                    f"🔍 Scan {scans:>3} | UNI ${eth_uni:.2f} | "
                    f"SUSHI ${eth_sushi:.2f} "
                    f"| dir={best['dir'] or '(no edge)'} | "
                    f"size={fmt_money(best['size'])} "
                    f"| gross={fmt_money(best['gross'])} "
                    f"gas={fmt_money(gas_usd)} net={fmt_money(net)} "
                    f"| {'EXEC' if executed else 'skip'}"
                )
                if scans % 5 == 0:
                    delta = eq - eq_start
                    pct = (delta / eq_start * 100) if eq_start > 0 else d(0)
                    print(
                        f"💼 Equity: {fmt_money(eq)} "
                        f"(Δ {fmt_money(delta)}, {pct:+.2f}%)"
                    )

                # sleep to cadence
                dt = time.time() - t0
                time.sleep(max(0.0, self.scan_sec - dt))

        except KeyboardInterrupt:
            delta = eq - eq_start
            pct = (delta / eq_start * 100) if eq_start > 0 else d(0)
            print("\n🛑 Stopped")
            print(
                f"Start: {fmt_money(eq_start)}  End: {fmt_money(eq)}  "
                f"P&L: {fmt_money(delta)} ({pct:+.2f}%)"
            )
