import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Any


def load_picks(picks_path: Path) -> Dict[str, List[Dict[str, Any]]]:
    with picks_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def analyze_by_market(picks_by_day: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Dict[str, Any]]:
    market_stats = defaultdict(lambda: {
        "bets": 0,
        "wins": 0,
        "losses": 0,
        "pushes": 0,
        "total_profit": 0.0,
        "total_stake": 0.0,
        "odds_sum": 0.0,
        "win_profit": 0.0,
        "loss_profit": 0.0,
    })

    for date, picks in picks_by_day.items():
        for pick in picks:
            market = pick.get("market", "unknown")
            odds = float(pick.get("odds", 0))
            stake = float(pick.get("stake", 1))
            profit = float(pick.get("profit", 0))

            stats = market_stats[market]
            stats["bets"] += 1
            stats["total_stake"] += stake
            stats["total_profit"] += profit
            stats["odds_sum"] += odds

            if profit > 1e-9:
                stats["wins"] += 1
                stats["win_profit"] += profit
            elif profit < -1e-9:
                stats["losses"] += 1
                stats["loss_profit"] += profit
            else:
                stats["pushes"] += 1

    for market, stats in market_stats.items():
        bets = stats["bets"]
        stake = stats["total_stake"]
        
        stats["roi"] = (stats["total_profit"] / stake) * 100 if stake > 0 else 0.0
        stats["win_rate"] = (stats["wins"] / bets) * 100 if bets > 0 else 0.0
        stats["avg_odds"] = stats["odds_sum"] / bets if bets > 0 else 0.0
        stats["avg_profit_per_bet"] = stats["total_profit"] / bets if bets > 0 else 0.0
        stats["avg_win_profit"] = stats["win_profit"] / stats["wins"] if stats["wins"] > 0 else 0.0
        stats["avg_loss_profit"] = stats["loss_profit"] / stats["losses"] if stats["losses"] > 0 else 0.0

    return dict(market_stats)


def print_market_analysis(market_stats: Dict[str, Dict[str, Any]]) -> None:
    print("\n" + "="*100)
    print("MARKET ANALYSIS - picks.json")
    print("="*100)
    
    sorted_markets = sorted(
        market_stats.items(),
        key=lambda x: x[1]["bets"],
        reverse=True
    )
    
    print(f"\n{'Market':<12} {'Bets':<8} {'W':<6} {'L':<6} {'P':<6} {'Win%':<8} "
          f"{'ROI%':<10} {'Profit':<12} {'Avg Odds':<10} {'Avg$/Bet':<12}")
    print("-" * 100)
    
    for market, stats in sorted_markets:
        print(
            f"{market:<12} "
            f"{stats['bets']:<8} "
            f"{stats['wins']:<6} "
            f"{stats['losses']:<6} "
            f"{stats['pushes']:<6} "
            f"{stats['win_rate']:>6.1f}% "
            f"{stats['roi']:>8.2f}% "
            f"${stats['total_profit']:>10.2f} "
            f"{stats['avg_odds']:>8.1f} "
            f"${stats['avg_profit_per_bet']:>10.2f}"
        )
    
    print("\n" + "-" * 100)
    total_bets = sum(s["bets"] for s in market_stats.values())
    total_wins = sum(s["wins"] for s in market_stats.values())
    total_losses = sum(s["losses"] for s in market_stats.values())
    total_profit = sum(s["total_profit"] for s in market_stats.values())
    total_stake = sum(s["total_stake"] for s in market_stats.values())
    
    overall_roi = (total_profit / total_stake * 100) if total_stake > 0 else 0.0
    overall_win_rate = (total_wins / total_bets * 100) if total_bets > 0 else 0.0
    
    print(f"\nOVERALL SUMMARY:")
    print(f"  Total Bets: {total_bets}")
    print(f"  Wins: {total_wins} | Losses: {total_losses} | Pushes: {sum(s['pushes'] for s in market_stats.values())}")
    print(f"  Win Rate: {overall_win_rate:.2f}%")
    print(f"  Total Profit: ${total_profit:.2f}")
    print(f"  Total Staked: ${total_stake:.2f}")
    print(f"  Overall ROI: {overall_roi:.2f}%")
    
    print("\n" + "-" * 100)
    print("TOP MARKETS BY ROI (min 10 bets):")
    sorted_by_roi = sorted(
        [(m, s) for m, s in market_stats.items() if s["bets"] >= 10],
        key=lambda x: x[1]["roi"],
        reverse=True
    )
    for market, stats in sorted_by_roi[:5]:
        print(f"  {market}: {stats['roi']:.2f}% ROI ({stats['bets']} bets, "
              f"{stats['wins']}-{stats['losses']}, ${stats['total_profit']:.2f})")
    
    print("\n" + "-" * 100)
    print("WORST MARKETS BY ROI (min 10 bets):")
    for market, stats in sorted_by_roi[-5:]:
        print(f"  {market}: {stats['roi']:.2f}% ROI ({stats['bets']} bets, "
              f"{stats['wins']}-{stats['losses']}, ${stats['total_profit']:.2f})")


def main(argv: List[str]) -> int:
    picks_path = Path("backtest/picks.json")
    
    if len(argv) > 0:
        picks_path = Path(argv[0])
    
    if not picks_path.exists():
        print(f"Error: picks file not found: {picks_path}", file=sys.stderr)
        return 1
    
    picks = load_picks(picks_path)
    market_stats = analyze_by_market(picks)
    print_market_analysis(market_stats)
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

