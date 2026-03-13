import argparse, json
from pathlib import Path
from collections import Counter, defaultdict


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--file", required=True)
    args = p.parse_args()
    total = 0
    success = 0
    latency = []
    tokens = []
    error_codes = Counter()
    with Path(args.file).open("r", encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            total += 1
            if obj.get("ok"):
                success += 1
            else:
                error_codes[obj.get("error_code")] += 1
            if obj.get("latency_ms") is not None:
                latency.append(obj["latency_ms"])
            if obj.get("tokens") is not None:
                tokens.append(obj["tokens"])
    def avg(xs):
        return sum(xs) / len(xs) if xs else 0
    def p95(xs):
        if not xs:
            return 0
        xs_sorted = sorted(xs)
        idx = int(len(xs_sorted) * 0.95) - 1
        idx = max(0, min(idx, len(xs_sorted)-1))
        return xs_sorted[idx]
    print(f"file: {args.file}")
    print(f"total={total}, success={success}, ESR={success/total if total else 0:.3f}")
    print(f"avg_latency_ms={avg(latency):.1f}, p95_latency_ms={p95(latency):.1f}")
    print(f"avg_tokens={avg(tokens):.1f}, p95_tokens={p95(tokens):.1f}")
    print("error_code counts:")
    for k,v in error_codes.most_common():
        print(f"  {k}: {v}")

if __name__ == '__main__':
    main()
