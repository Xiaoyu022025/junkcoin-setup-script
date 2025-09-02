#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
监控 bonk.fun（Pump 风格）代币在 Solana 上的 SOL 底池交易对。

实现思路（无需私有/付费 API）：
- 使用 DexScreener 公共 API 按代币 Mint 查询所有可用交易对
- 过滤报价币为 SOL（WSOL: So11111111111111111111111111111111111111112）的交易对
- 定时轮询，打印价格、FDV、池子流动性、成交统计等核心指标

适用场景：
- 你在 bonk.fun（或类似 Pump 平台）看到某个代币，复制其 Mint 地址后使用本脚本监控其 SOL 底池

用法示例：
  python3 monitor_bonk_fun_pools.py --mints <MINT_ADDRESS> [<MINT_ADDRESS> ...] \
      --interval 5 --min-sol-liq 5 --sort fdv --dex pumpswap

参数说明：
- --mints: 一个或多个代币的 Mint 地址
- --interval: 轮询周期（秒）。若省略或设为 0 则只查询一次
- --min-sol-liq: 仅显示底池中 SOL 数量大于等于该阈值的交易对
- --sort: 排序字段，可选: price, fdv, solLiq, usdLiq, volume24h
- --json: 以 JSON 行打印，方便程序对接
 - --dex: 仅展示指定 DEX 的交易对。默认 pumpswap（bonk.fun / pump 风格）。传 any 关闭过滤

注意：
- DexScreener 数据聚合了 Raydium、Meteora、Orca、Pump 等，足够用来观察 SOL 底池
- 如果你的目标是逐笔交易级别的监听（链上交易订阅），请结合 Helius/Shyft/Jito 等服务做高级订阅
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


DEXSCREENER_BASE = "https://api.dexscreener.com/latest/dex"
WSOL_MINT = "So11111111111111111111111111111111111111112"


@dataclass
class Pair:
    chain_id: str
    dex_id: str
    pair_address: str
    base_address: str
    base_symbol: str
    quote_address: str
    quote_symbol: str
    price_native: Optional[float]
    price_usd: Optional[float]
    fdv: Optional[float]
    liquidity_usd: Optional[float]
    liquidity_base: Optional[float]
    liquidity_quote: Optional[float]
    volume24h: Optional[float]
    txns_m5: Optional[int]
    txns_h1: Optional[int]
    txns_h24: Optional[int]
    created_at: Optional[int]

    @property
    def sol_liquidity(self) -> float:
        # 以 quote 为 SOL 的池子中，liquidity_quote 代表 SOL 数量
        return float(self.liquidity_quote or 0.0)


def http_get_json(url: str, timeout: int = 15) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "pool-monitor/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} for {url}")
        data = resp.read()
        return json.loads(data.decode("utf-8"))


def fetch_pairs_for_token(mint: str) -> List[Pair]:
    # DexScreener: /latest/dex/tokens/{tokenAddress}
    url = f"{DEXSCREENER_BASE}/tokens/{urllib.parse.quote(mint)}"
    try:
        payload = http_get_json(url)
    except urllib.error.HTTPError as e:
        print(f"[warn] fetch token pairs failed {mint}: {e}", file=sys.stderr)
        return []
    except Exception as e:  # noqa: BLE001
        print(f"[warn] fetch token pairs failed {mint}: {e}", file=sys.stderr)
        return []

    raw_pairs = payload.get("pairs") or []
    pairs: List[Pair] = []
    for p in raw_pairs:
        try:
            chain_id = p.get("chainId")
            base_token = p.get("baseToken") or {}
            quote_token = p.get("quoteToken") or {}
            liquidity = p.get("liquidity") or {}
            txns = p.get("txns") or {}
            txns_h24 = (txns.get("h24") or {}).get("buys", 0) + (txns.get("h24") or {}).get("sells", 0)
            pair = Pair(
                chain_id=str(chain_id),
                dex_id=str(p.get("dexId") or ""),
                pair_address=str(p.get("pairAddress") or ""),
                base_address=str(base_token.get("address") or ""),
                base_symbol=str(base_token.get("symbol") or ""),
                quote_address=str(quote_token.get("address") or ""),
                quote_symbol=str(quote_token.get("symbol") or ""),
                price_native=safe_float(p.get("priceNative")),
                price_usd=safe_float(p.get("priceUsd")),
                fdv=safe_float(p.get("fdv")),
                liquidity_usd=safe_float(liquidity.get("usd")),
                liquidity_base=safe_float(liquidity.get("base")),
                liquidity_quote=safe_float(liquidity.get("quote")),
                volume24h=safe_float(p.get("volume"), default=None),
                txns_m5=try_sum_txns(txns.get("m5")),
                txns_h1=try_sum_txns(txns.get("h1")),
                txns_h24=txns_h24 if isinstance(txns_h24, int) else None,
                created_at=int(p.get("pairCreatedAt")) if p.get("pairCreatedAt") else None,
            )
            pairs.append(pair)
        except Exception as e:  # noqa: BLE001
            print(f"[warn] bad pair entry for {mint}: {e}", file=sys.stderr)
            continue
    return pairs


def try_sum_txns(x: Optional[Dict[str, Any]]) -> Optional[int]:
    if not x:
        return None
    try:
        return int((x.get("buys") or 0) + (x.get("sells") or 0))
    except Exception:  # noqa: BLE001
        return None


def safe_float(x: Any, default: Optional[float] = 0.0) -> Optional[float]:
    try:
        if x is None:
            return default
        return float(x)
    except Exception:  # noqa: BLE001
        return default


def filter_sol_quote_pairs(pairs: List[Pair]) -> List[Pair]:
    result: List[Pair] = []
    for p in pairs:
        if (p.quote_address or "").lower() == WSOL_MINT.lower() or (p.quote_symbol or "").upper() == "SOL":
            result.append(p)
    return result


def sort_pairs(pairs: List[Pair], key: str) -> List[Pair]:
    key = key.lower()
    if key == "price":
        return sorted(pairs, key=lambda x: (x.price_native or 0.0), reverse=True)
    if key == "fdv":
        return sorted(pairs, key=lambda x: (x.fdv or 0.0), reverse=True)
    if key == "solliq":
        return sorted(pairs, key=lambda x: (x.sol_liquidity or 0.0), reverse=True)
    if key == "usdliq":
        return sorted(pairs, key=lambda x: (x.liquidity_usd or 0.0), reverse=True)
    if key == "volume24h":
        return sorted(pairs, key=lambda x: (x.volume24h or 0.0), reverse=True)
    return pairs


def print_pairs_human(pairs: List[Pair], mint: str) -> None:
    if not pairs:
        print(f"[info] {mint}: 未找到 SOL 底池交易对")
        return
    print(f"\n=== {mint} 的 SOL 交易对（共 {len(pairs)} 个）===")
    for p in pairs:
        price_native = f"{p.price_native:.12f}" if p.price_native is not None else "-"
        price_usd = f"${p.price_usd:.8f}" if p.price_usd is not None else "-"
        fdv = f"${human_number(p.fdv)}" if p.fdv is not None else "-"
        liq_sol = f"{p.sol_liquidity:.4f} SOL"
        liq_usd = f"${human_number(p.liquidity_usd)}" if p.liquidity_usd is not None else "-"
        vol24 = f"${human_number(p.volume24h)}" if p.volume24h is not None else "-"
        txns_desc = f"m5:{p.txns_m5 or 0} h1:{p.txns_h1 or 0} h24:{p.txns_h24 or 0}"
        created = str(p.created_at) if p.created_at else "-"

        print(
            "\n".join(
                [
                    f"dex={p.dex_id} chain={p.chain_id} pair={p.pair_address}",
                    f"base={p.base_symbol}({p.base_address}) / quote={p.quote_symbol}({p.quote_address})",
                    f"price={price_native} SOL  ({price_usd})  FDV={fdv}",
                    f"liquidity={liq_sol}  ({liq_usd})  24hVol={vol24}",
                    f"txns {txns_desc}  createdAt={created}",
                ]
            )
        )


def print_pairs_json(pairs: List[Pair], mint: str) -> None:
    for p in pairs:
        print(
            json.dumps(
                {
                    "mint": mint,
                    "dexId": p.dex_id,
                    "pairAddress": p.pair_address,
                    "priceNative": p.price_native,
                    "priceUsd": p.price_usd,
                    "fdv": p.fdv,
                    "solLiquidity": p.sol_liquidity,
                    "liquidityUsd": p.liquidity_usd,
                    "volume24h": p.volume24h,
                    "txns": {
                        "m5": p.txns_m5,
                        "h1": p.txns_h1,
                        "h24": p.txns_h24,
                    },
                    "createdAt": p.created_at,
                },
                ensure_ascii=False,
            )
        )


def human_number(x: Optional[float]) -> str:
    if x is None:
        return "-"
    n = float(x)
    if n >= 1_000_000_000:
        return f"{n/1_000_000_000:.2f}B"
    if n >= 1_000_000:
        return f"{n/1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n/1_000:.2f}K"
    return f"{n:.2f}"


def run_once(
    mints: List[str],
    min_sol_liq: float,
    sort_key: str,
    as_json: bool,
    dex_filter: Optional[str],
) -> None:
    for mint in mints:
        all_pairs = fetch_pairs_for_token(mint)
        sol_pairs = filter_sol_quote_pairs(all_pairs)
        if dex_filter and dex_filter.lower() != "any":
            sol_pairs = [p for p in sol_pairs if (p.dex_id or "").lower() == dex_filter.lower()]
        sol_pairs = [p for p in sol_pairs if p.sol_liquidity >= min_sol_liq]
        sol_pairs = sort_pairs(sol_pairs, sort_key)
        if as_json:
            print_pairs_json(sol_pairs, mint)
        else:
            print_pairs_human(sol_pairs, mint)


def main() -> None:
    parser = argparse.ArgumentParser(description="监控 bonk.fun 代币的 SOL 底池交易对（基于 DexScreener）")
    parser.add_argument("--mints", nargs="+", help="代币 Mint 地址（支持多个）", required=True)
    parser.add_argument("--interval", type=int, default=0, help="轮询周期（秒），0 表示只查询一次")
    parser.add_argument("--min-sol-liq", type=float, default=0.0, help="底池最小 SOL 数量过滤阈值")
    parser.add_argument(
        "--sort",
        type=str,
        default="fdv",
        choices=["price", "fdv", "solLiq", "usdLiq", "volume24h"],
        help="排序字段",
    )
    parser.add_argument("--json", action="store_true", help="以 JSON 行输出，便于程序对接")
    parser.add_argument("--dex", type=str, default="pumpswap", help="仅展示指定 DEX（默认 pumpswap；传 any 关闭过滤）")
    args = parser.parse_args()

    if args.interval and args.interval < 0:
        print("[error] --interval 不能为负数", file=sys.stderr)
        sys.exit(2)

    if args.interval == 0:
        run_once(args.mints, args.min_sol_liq, args.sort, args.json, args.dex)
        return

    # 连续模式
    try:
        while True:
            run_once(args.mints, args.min_sol_liq, args.sort, args.json, args.dex)
            if not args.json:
                print(f"\n[info] 下一次刷新将在 {args.interval}s 后……")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

