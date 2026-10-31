from fnol_kg.checker import check
from fnol_kg.data import make_fnols, make_policies
from fnol_kg.evaluate import evidence_grounded, run_eval
from fnol_kg.extract import LLMExtractor, RuleExtractor
from fnol_kg.graph import build_graph, triple_exists

POL = [{"policy_id": "P-0001", "holder": "Asha Rao", "effective": "2026-01-01", "expiry": "2026-12-31",
        "cancelled_on": None,
        "vehicles": [{"vehicle_id": "V-1", "make": "Honda", "model": "City", "year": 2022}],
        "drivers": [{"name": "Asha Rao", "excluded": False}, {"name": "Dev Rao", "excluded": True}],
        "coverages": [{"type": "liability", "limit": 1, "deductible": 0},
                      {"type": "collision", "limit": 1, "deductible": 5000}],
        "exclusions": ["rideshare"]}]
G = build_graph(POL)
BASE = {"policy_id": "P-0001", "loss_date": "2026-03-02", "make": "Honda", "model": "City",
        "driver": "Asha Rao", "loss_type": "collision", "rideshare": False}


def test_clean_claim_goes_straight_through():
    r = check(G, BASE)
    assert r["flags"] == [] and r["route"] == "STRAIGHT_THROUGH"


def test_each_fault_is_flagged_with_grounded_evidence():
    cases = {"POLICY_INACTIVE": {"loss_date": "2027-02-01"},
             "VEHICLE_NOT_ON_POLICY": {"model": "Swift", "make": "Maruti"},
             "DRIVER_EXCLUDED": {"driver": "Dev Rao"},
             "DRIVER_NOT_LISTED": {"driver": "Tom Paul"},
             "COVERAGE_MISSING": {"loss_type": "theft"},
             "EXCLUSION_APPLIES": {"rideshare": True}}
    for flag, change in cases.items():
        r = check(G, {**BASE, **change})
        assert r["flags"] == [flag], (flag, r["flags"])
        assert all(evidence_grounded(G, *t) for t in r["evidence"][flag])


def test_unknown_policy_and_missing_fields():
    assert check(G, {**BASE, "policy_id": "P-9999"})["flags"] == ["POLICY_NOT_FOUND"]
    assert "EXTRACTION_INCOMPLETE" in check(G, {**BASE, "loss_date": None})["flags"]


def test_rule_extractor_on_three_date_formats():
    ext = RuleExtractor()
    for t in ["policy P-0001. On 2026-03-02 my Honda City was hit. I was driving.",
              "policy P-0001. On 02/03/2026 my Honda City was hit. I was driving.",
              "policy P-0001. On 2 March 2026 my Honda City was hit. I was driving."]:
        f, _ = ext.extract("This is Asha Rao, " + t)
        assert f["loss_date"] == "2026-03-02" and f["driver"] == "Asha Rao" and f["loss_type"] == "collision"


def test_llm_extractor_validates_and_falls_back():
    good = LLMExtractor(lambda p: '{"policy_id": "P-0001", "loss_date": "2026-03-02", "make": "Honda", '
                                  '"model": "City", "driver": "Asha Rao", "loss_type": "collision", "rideshare": false}')
    assert good.extract("x")[0]["make"] == "Honda"
    bad = LLMExtractor(lambda p: "not json")
    f, _ = bad.extract("This is Asha Rao, policy P-0001, on 2026-03-02 my Honda City was hit. I was driving.")
    assert f["policy_id"] == "P-0001"


def test_dev_eval_runs_and_is_grounded():
    pols = make_policies()
    g = build_graph(pols)
    r = run_eval(g, make_fnols(pols, n=60), RuleExtractor())
    assert r["evidence_grounded"] == 1.0
    assert r["route_accuracy"] > 0.8
    assert triple_exists(g, pols[0]["policy_id"], "COVERS_VEHICLE", pols[0]["vehicles"][0]["vehicle_id"])
