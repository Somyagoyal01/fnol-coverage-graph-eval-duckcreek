"""Evaluation harness: field accuracy, per-flag precision/recall/F1, routing safety, calibration and
evidence groundedness (does every cited triple actually exist in the policy graph?)."""
from .checker import FLAGS, check
from .graph import triple_exists

ATTR_RELS = {"EFFECTIVE": "effective", "EXPIRY": "expiry", "CANCELLED_ON": "cancelled_on"}


def evidence_grounded(g, s, rel, o):
    if s == "FNOL":
        return True                       # comes from the report itself, not the graph
    if rel in ATTR_RELS:
        return g.has_node(s) and g.nodes[s].get(ATTR_RELS[rel]) == o
    return triple_exists(g, s, rel, o)


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 1.0
    r = tp / (tp + fn) if tp + fn else 1.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return round(p, 3), round(r, 3), round(f, 3)


def ece(pairs, bins=5):
    """Expected calibration error over (confidence, correct) pairs."""
    total, err = len(pairs), 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        sel = [(c, y) for c, y in pairs if lo <= c < hi or (b == bins - 1 and c == 1.0)]
        if sel:
            acc = sum(y for _, y in sel) / len(sel)
            avg = sum(c for c, _ in sel) / len(sel)
            err += len(sel) / total * abs(acc - avg)
    return round(err, 3)


def run_eval(g, items, extractor, gold_flags_key=None):
    """items: dicts with text, gold fields and optionally hand-labelled gold flags.

    If an item has no hand-labelled flags, gold flags = checker run on the gold fields
    (this isolates extraction errors). Hand-labelled flags (blind set) also test the checker logic.
    """
    field_hits, field_n = {}, {}
    counts = {f: [0, 0, 0] for f in FLAGS}
    route_ok, unsafe, pairs, ev_total, ev_ok, rows = 0, 0, [], 0, 0, []
    for it in items:
        fields, conf = extractor.extract(it["text"], it.get("report_date"))
        pred = check(g, fields, conf)
        if gold_flags_key and gold_flags_key in it:
            gold = sorted(it[gold_flags_key])
        else:
            gold = check(g, it["gold"])["flags"]
        gold_route = "REVIEW" if gold else "STRAIGHT_THROUGH"
        for k, v in it["gold"].items():
            field_n[k] = field_n.get(k, 0) + 1
            field_hits[k] = field_hits.get(k, 0) + int(fields.get(k) == v)
        for f in FLAGS:
            a, b = f in pred["flags"], f in gold
            counts[f][0] += a and b
            counts[f][1] += a and not b
            counts[f][2] += b and not a
        ok = pred["route"] == gold_route
        route_ok += ok
        unsafe += pred["route"] == "STRAIGHT_THROUGH" and gold_route == "REVIEW"
        pairs.append((pred["confidence"], int(set(pred["flags"]) == set(gold))))
        for trip in [t for ts in pred["evidence"].values() for t in ts]:
            ev_total += 1
            ev_ok += evidence_grounded(g, *trip)
        rows.append({"id": it.get("fnol_id"), "pred": pred["flags"], "gold": gold, "route": pred["route"],
                     "gold_route": gold_route, "fields": fields})
    n = len(items)
    per_flag = {f: prf(*c) for f, c in counts.items() if sum(c)}
    tp, fp, fn = (sum(c[i] for c in counts.values()) for i in range(3))
    return {
        "n": n,
        "field_accuracy": {k: round(field_hits[k] / field_n[k], 3) for k in field_n},
        "flag_micro_prf": prf(tp, fp, fn),
        "per_flag_prf": per_flag,
        "route_accuracy": round(route_ok / n, 3),
        "unsafe_straight_through": unsafe,
        "exact_flag_match": round(sum(y for _, y in pairs) / n, 3),
        "ece": ece(pairs),
        "evidence_grounded": round(ev_ok / ev_total, 3) if ev_total else 1.0,
        "rows": rows,
    }
