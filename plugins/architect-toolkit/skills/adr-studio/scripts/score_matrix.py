#!/usr/bin/env python3
"""Weighted decision matrix with sensitivity analysis.

Usage: score_matrix.py input.json [--seed N] [--trials N] [--json]
Stdlib only.
"""
import json
import random
import sys


def load(path):
    with open(path) as f:
        data = json.load(f)
    crit = {c["name"]: float(c["weight"]) for c in data["criteria"]}
    if len(data["options"]) < 2:
        sys.exit("error: a decision needs at least two options")
    for o in data["options"]:
        missing = [c for c in crit if c not in o["scores"]]
        if missing:
            sys.exit(f"error: option '{o['name']}' missing scores for {missing}")
        for c, s in o["scores"].items():
            if not 1 <= s["score"] <= 5:
                sys.exit(f"error: score out of range 1-5 for '{o['name']}' / '{c}'")
    return data, crit


def totals(options, weights):
    out = {}
    for o in options:
        out[o["name"]] = sum(weights[c] * o["scores"][c]["score"] for c in weights)
    return out


def winner(t):
    return max(t, key=t.get)


def flip_threshold(options, weights, base_winner):
    """Smallest single-weight change (in weight points) that changes the winner."""
    best = None
    for c in weights:
        for direction in (-1, 1):
            for step in range(1, 21):
                w = dict(weights)
                w[c] = max(0.0, weights[c] + direction * step * 0.5)
                if winner(totals(options, w)) != base_winner:
                    delta = abs(w[c] - weights[c])
                    if best is None or delta < best[1]:
                        best = (c, delta, direction)
                    break
    return best


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    path = args[0]
    seed = int(args[args.index("--seed") + 1]) if "--seed" in args else 42
    trials = int(args[args.index("--trials") + 1]) if "--trials" in args else 1000
    as_json = "--json" in args

    data, weights = load(path)
    options = data["options"]
    t = totals(options, weights)
    max_total = 5 * sum(weights.values())
    ranked = sorted(t.items(), key=lambda kv: -kv[1])
    base = ranked[0][0]
    margin = (ranked[0][1] - ranked[1][1]) / max_total

    rng = random.Random(seed)
    wins = {n: 0 for n in t}
    for _ in range(trials):
        w = {c: max(0.1, v * rng.uniform(0.7, 1.3)) for c, v in weights.items()}
        wins[winner(totals(options, w))] += 1

    flip = flip_threshold(options, weights, base)
    assumed = {}
    for o in options:
        n = len(o["scores"])
        a = sum(1 for s in o["scores"].values() if s.get("assumed"))
        assumed[o["name"]] = (a, n)

    result = {
        "decision": data.get("decision", ""),
        "ranking": [
            {"option": n, "score": s, "pct_of_max": round(100 * s / max_total, 1),
             "win_share_pct": round(100 * wins[n] / trials, 1),
             "assumed_inputs": f"{assumed[n][0]}/{assumed[n][1]}"}
            for n, s in ranked
        ],
        "margin_pct_of_max": round(100 * margin, 1),
        "flip": None if not flip else {"criterion": flip[0], "weight_change": flip[1],
                                       "direction": "down" if flip[2] < 0 else "up"},
        "fragile": wins[base] / trials < 0.7 or margin < 0.05,
    }

    if as_json:
        print(json.dumps(result, indent=2))
        return

    print(f"Decision: {result['decision']}\n")
    print(f"{'Option':<34}{'Score':>8}{'% max':>8}{'Wins%':>8}{'Assumed':>9}")
    for r in result["ranking"]:
        print(f"{r['option']:<34}{r['score']:>8.1f}{r['pct_of_max']:>8}{r['win_share_pct']:>8}{r['assumed_inputs']:>9}")
    print(f"\nMargin over runner-up: {result['margin_pct_of_max']}% of max score")
    if flip:
        print(f"Winner flips if '{flip[0]}' weight moves {'down' if flip[2] < 0 else 'up'} by {flip[1]} points")
    else:
        print("No single-weight change of up to 10 points flips the winner")
    print("\nVERDICT: " + ("FRAGILE. Re-examine weights and assumed scores before deciding."
                           if result["fragile"] else "ROBUST under +/-30% weight perturbation."))


if __name__ == "__main__":
    main()
