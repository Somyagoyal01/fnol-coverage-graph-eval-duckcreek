"""Graph-grounded coverage checks for one FNOL.

Every flag carries evidence: the graph triples (subject, relation, object) it relied on, so an
adjuster (or an evaluator) can trace why the claim was routed to review.
"""
from datetime import date

from .graph import neighbours

LOSS_TO_COVERAGE = {"collision": "collision", "theft": "comprehensive", "weather": "comprehensive",
                    "glass": "comprehensive", "vandalism": "comprehensive"}
FLAGS = ["POLICY_NOT_FOUND", "POLICY_INACTIVE", "VEHICLE_NOT_ON_POLICY", "DRIVER_NOT_LISTED",
         "DRIVER_EXCLUDED", "COVERAGE_MISSING", "EXCLUSION_APPLIES", "EXTRACTION_INCOMPLETE"]
REVIEW_BELOW = 0.8   # route to a human when any field we relied on is less certain than this


def _same_name(a, b):
    a, b = a.lower().split(), b.lower().split()
    return a == b or (len(a) == 1 and a[0] == b[0])


def check(g, fields, conf=None):
    conf = conf or {k: 1.0 for k in fields}
    flags, evidence = [], {}
    pid = fields.get("policy_id")
    missing = [k for k in ("policy_id", "loss_date", "loss_type") if not fields.get(k)]
    if missing:
        flags.append("EXTRACTION_INCOMPLETE")
        evidence["EXTRACTION_INCOMPLETE"] = [("FNOL", "MISSING_FIELD", m) for m in missing]
    if not pid or not g.has_node(pid):
        if pid:
            flags.append("POLICY_NOT_FOUND")
            evidence["POLICY_NOT_FOUND"] = [("FNOL", "CLAIMS_POLICY", pid)]
        return _result(flags, evidence, conf)

    p = g.nodes[pid]
    if fields.get("loss_date"):
        ld = date.fromisoformat(fields["loss_date"])
        end = date.fromisoformat(p["cancelled_on"] or p["expiry"])
        if not (date.fromisoformat(p["effective"]) <= ld <= end):
            flags.append("POLICY_INACTIVE")
            evidence["POLICY_INACTIVE"] = [(pid, "EFFECTIVE", p["effective"]),
                                           (pid, "CANCELLED_ON" if p["cancelled_on"] else "EXPIRY", end.isoformat())]

    if fields.get("make") or fields.get("model"):
        vids = neighbours(g, pid, "COVERS_VEHICLE")
        match = [v for v in vids
                 if (not fields.get("make") or g.nodes[v]["make"] == fields["make"])
                 and (not fields.get("model") or g.nodes[v]["model"] == fields["model"])]
        if not match:
            flags.append("VEHICLE_NOT_ON_POLICY")
            evidence["VEHICLE_NOT_ON_POLICY"] = [(pid, "COVERS_VEHICLE", v) for v in vids]

    drv = fields.get("driver")
    if drv:
        listed = neighbours(g, pid, "LISTS_DRIVER")
        excluded = neighbours(g, pid, "EXCLUDES_DRIVER")
        ex_hit = [d for d in excluded if _same_name(drv, g.nodes[d]["name"])]
        if ex_hit:
            flags.append("DRIVER_EXCLUDED")
            evidence["DRIVER_EXCLUDED"] = [(pid, "EXCLUDES_DRIVER", d) for d in ex_hit]
        elif not any(_same_name(drv, g.nodes[d]["name"]) for d in listed):
            flags.append("DRIVER_NOT_LISTED")
            evidence["DRIVER_NOT_LISTED"] = [(pid, "LISTS_DRIVER", d) for d in listed]

    need = LOSS_TO_COVERAGE.get(fields.get("loss_type"))
    if need:
        covs = neighbours(g, pid, "HAS_COVERAGE")
        if not any(g.nodes[c]["type"] == need for c in covs):
            flags.append("COVERAGE_MISSING")
            evidence["COVERAGE_MISSING"] = [(pid, "HAS_COVERAGE", c) for c in covs]

    if fields.get("rideshare") and "EXCL:rideshare" in neighbours(g, pid, "HAS_EXCLUSION"):
        flags.append("EXCLUSION_APPLIES")
        evidence["EXCLUSION_APPLIES"] = [(pid, "HAS_EXCLUSION", "EXCL:rideshare")]
    return _result(flags, evidence, conf)


def _result(flags, evidence, conf):
    confidence = min(conf.values()) if conf else 0.0
    route = "REVIEW" if flags or confidence < REVIEW_BELOW else "STRAIGHT_THROUGH"
    return {"flags": sorted(flags), "evidence": evidence, "confidence": round(confidence, 2), "route": route}
