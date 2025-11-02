import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, Any, List, Tuple


def load_picks(picks_path: Path) -> Dict[str, List[Dict[str, Any]]]:
    with picks_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def aggregate_by_player(picks_by_day: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Dict[str, Any]]:
    player_stats: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "bets": 0,
        "wins": 0,
        "losses": 0,
        "pushes": 0,
        "units": 0.0,
        "stake_units": 0.0,
        "avg_odds": 0.0,
    })

    for _date, picks in picks_by_day.items():
        for p in picks:
            player = str(p.get("player", "UNKNOWN"))
            odds = float(p.get("odds", 0))
            stake = float(p.get("stake", 1))
            profit = float(p.get("profit", 0))

            s = player_stats[player]
            s["bets"] += 1
            s["stake_units"] += stake
            s["units"] += profit

            if profit > 1e-9:
                s["wins"] += 1
            elif profit < -1e-9:
                s["losses"] += 1
            else:
                s["pushes"] += 1

            n = s.get("_odds_count", 0) + 1
            s["avg_odds"] = (s["avg_odds"] * (n - 1) + odds) / n
            s["_odds_count"] = n

    for player, s in player_stats.items():
        stake_units = s["stake_units"]
        s["roi"] = s["units"] / stake_units if stake_units > 0 else float("nan")
        if "_odds_count" in s:
            del s["_odds_count"]

    return player_stats


def print_worst_players(player_stats: Dict[str, Dict[str, Any]], min_bets: int, top: int) -> None:
    players = [
        (player, stats)
        for player, stats in player_stats.items()
        if stats["bets"] >= min_bets
    ]

    if not players:
        print(f"No players with at least {min_bets} bets.")
        return

    by_units = sorted(players, key=lambda kv: kv[1]["units"])[:top]
    by_roi = sorted(players, key=lambda kv: (math.isnan(kv[1]["roi"]), kv[1]["roi"]))[:top]

    def fmt_row(name: str, s: Dict[str, Any]) -> str:
        return (
            f"{name:25} | bets: {s['bets']:4d} | W-L-P: {s['wins']:3d}-{s['losses']:3d}-{s['pushes']:3d} "
            f"| units: {s['units']:7.2f} | ROI: {s['roi']*100:6.2f}% | avg_odds: {s['avg_odds']:7.2f}"
        )

    print("\nWorst players by total units (min_bets >=", min_bets, f", top {top}):")
    for name, s in by_units:
        print("  ", fmt_row(name, s))

    print("\nWorst players by ROI (min_bets >=", min_bets, f", top {top}):")
    for name, s in by_roi:
        print("  ", fmt_row(name, s))


def write_csv(player_stats: Dict[str, Dict[str, Any]], out_path: Path, min_bets: int) -> None:
    import csv

    rows: List[Tuple[str, Dict[str, Any]]] = [
        (player, s) for player, s in player_stats.items() if s["bets"] >= min_bets
    ]
    rows.sort(key=lambda kv: kv[1]["units"])

    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "player", "bets", "wins", "losses", "pushes", "units", "stake_units", "roi", "avg_odds",
        ])
        for player, s in rows:
            writer.writerow([
                player,
                s["bets"], s["wins"], s["losses"], s["pushes"],
                f"{s['units']:.2f}", f"{s['stake_units']:.2f}", f"{s['roi']:.6f}", f"{s['avg_odds']:.2f}",
            ])


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="Analyze worst-performing players from picks.json")
    parser.add_argument(
        "--picks",
        type=Path,
        default=Path("backtest/picks.json"),
        help="Path to picks.json (date -> list of picks)",
    )
    parser.add_argument("--min-bets", type=int, default=10, help="Minimum bets per player to include")
    parser.add_argument("--top", type=int, default=25, help="How many worst players to show")
    parser.add_argument("--csv", type=Path, default=None, help="Optional output CSV path for full table")

    args = parser.parse_args(argv)

    picks_path = args.picks
    if not picks_path.exists():
        print(f"picks file not found: {picks_path}", file=sys.stderr)
        return 1

    picks = load_picks(picks_path)
    stats = aggregate_by_player(picks)
    print_worst_players(stats, min_bets=args.min_bets, top=args.top)

    if args.csv is not None:
        write_csv(stats, args.csv, min_bets=args.min_bets)
        print(f"\nWrote CSV to {args.csv}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

