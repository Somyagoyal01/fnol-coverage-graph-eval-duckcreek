"""Build the policy graph, run the extractor + checker on the generated dev set and the hand-written
blind set, and write results/. Runs offline (no API keys)."""
import json
import os

from fnol_kg.data import make_fnols, make_policies
from fnol_kg.evaluate import run_eval
from fnol_kg.extract import RuleExtractor
from fnol_kg.graph import build_graph, stats

HERE = os.path.dirname(os.path.abspath(__file__))


def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def summary(name, r):
    keep = {k: v for k, v in r.items() if k != "rows"}
    print(f"\n== {name} (n={r['n']}) ==")
    for k, v in keep.items():
        print(f"  {k}: {v}")
    return keep


def main():
    policies = make_policies()
    g = build_graph(policies)
    print("graph:", stats(g))
    ext = RuleExtractor()
    out = {"graph": stats(g)}
    out["dev_generated"] = summary("dev (generated)", run_eval(g, make_fnols(policies), ext))
    blind_path = os.path.join(HERE, "data", "blind_fnol.jsonl")
    if os.path.exists(blind_path):
        blind = load_jsonl(blind_path)
        r = run_eval(g, blind, ext, gold_flags_key="gold_flags")
        out["blind_handwritten"] = summary("blind (hand-written)", r)
        misses = [row for row in r["rows"] if row["pred"] != row["gold"]]
        out["blind_misses"] = misses
        print(f"\n  blind misses: {len(misses)}")
        for m in misses:
            print(f"   {m['id']}: pred={m['pred']} gold={m['gold']}")
    os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
    with open(os.path.join(HERE, "results", "metrics.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    with open(os.path.join(HERE, "data", "policies.json"), "w", encoding="utf-8") as f:
        json.dump(policies, f, indent=1)


if __name__ == "__main__":
    main()
