# FNOL coverage checks over a policy knowledge graph, with an honest evaluation harness

> Personal project by Somya Goyal, built while applying to Duck Creek Technologies. Not affiliated with or endorsed by Duck Creek Technologies; uses public/synthetic data only.

## Why this matters for Duck Creek

**Problem.** When a claimant reports a loss in free text, someone has to check it against the policy: was the policy in force on that date, is that car on it, is the driver listed or excluded, does the policy carry the coverage this loss needs, does an exclusion (e.g. rideshare use) apply? Errors here either push clean claims into manual review or wave a bad one through.

**Who feels it.** Claims intake teams and adjusters at P&C carriers, and the platform teams who must show *why* an AI routed a claim.

**What this shows.** A small pipeline that extracts FNOL fields, checks them against a **policy knowledge graph**, and returns flags with **evidence triples** taken from the graph, plus an **evaluation harness** (golden set, per-flag precision/recall/F1, calibration, unsafe-routing count, evidence groundedness) and a **blind hand-written test set**.

Public context (no internal knowledge claimed):
- Duck Creek announced Agentic FNOL on 28 Sep 2026; per the release it verifies coverage and cross-references the loss description against policy data, logging AI determinations and sending exceptions to human review ([press release](https://www.duckcreek.com/resource/press-releases/duck-creek-launches-agentic-fnol-to-transform-claims-intake-with-intelligent-real-time-automation/)).
- Its Agentic AI Platform (28 Apr 2026) describes an intelligence layer built on insurance domain models and knowledge graphs, and an assurance layer for decision tracing and audit ([press release](https://www.duckcreek.com/resource/press-releases/launch-agentic-ai-platform-underwriting-claims/)).
- The Associate Software Engineer JD asks for LLM evaluation harnesses (golden datasets, precision/recall/F1, calibration, LLM-as-judge) and knowledge graphs.

Expected impact (estimate, assumptions stated): if roughly half of clean claims could skip manual coverage lookup and each lookup takes a few minutes, a carrier with thousands of FNOLs a month saves adjuster hours. **This repo does not reach that yet**: on the blind set it sends 8 of 9 clean claims to review (see results). What it does show is zero unsafe auto-approvals and fully traceable flags, which is the precondition for automating more.

## How it works

```
FNOL text ──► extractor (offline rules, or any LLM returning JSON) ──► fields + confidence
                                                                         │
policies ──► knowledge graph (NetworkX)                                  ▼
   Policy ─COVERS_VEHICLE─► Vehicle                         graph checks ──► flags + evidence triples ──► route
   Policy ─LISTS_DRIVER / EXCLUDES_DRIVER─► Driver                                                  (STRAIGHT_THROUGH / REVIEW)
   Policy ─HAS_COVERAGE─► Coverage(type, limit, deductible)
   Policy ─HAS_EXCLUSION─► Exclusion
```

Flags: `POLICY_NOT_FOUND`, `POLICY_INACTIVE`, `VEHICLE_NOT_ON_POLICY`, `DRIVER_NOT_LISTED`, `DRIVER_EXCLUDED`, `COVERAGE_MISSING`, `EXCLUSION_APPLIES`, `EXTRACTION_INCOMPLETE`. Any flag, or any field confidence below 0.8, routes the claim to REVIEW.

| File | What it does |
|---|---|
| `fnol_kg/data.py` | Seeded synthetic personal-auto policies and template-generated FNOLs with injected faults |
| `fnol_kg/graph.py` | Builds the policy knowledge graph; triple lookups |
| `fnol_kg/extract.py` | `RuleExtractor` (offline) and `LLMExtractor` (any LLM callable; JSON validated, falls back to rules) |
| `fnol_kg/checker.py` | Graph traversals that produce flags, evidence triples, confidence and route |
| `fnol_kg/evaluate.py` | Field accuracy, per-flag P/R/F1, routing accuracy, unsafe straight-throughs, ECE, evidence groundedness |
| `data/blind_fnol.jsonl` | 20 hand-written FNOLs with hand-labelled fields and flags, written **after the code was frozen** |
| `run.py` | Runs everything and writes `results/metrics.json` |

## Results (from `python run.py`)

Graph: 25 policies, 37 vehicles, 41 drivers, 62 coverages (166 nodes, 158 edges).

| Metric | Dev set (120 generated) | Blind set (20 hand-written) |
|---|---|---|
| Flag micro P / R / F1 | 1.00 / 1.00 / 1.00 | 0.71 / 0.83 / 0.77 |
| Exact flag match | 1.00 | 0.75 |
| Routing accuracy | 1.00 | 0.60 |
| Unsafe straight-throughs (flagged claim auto-approved) | 0 | **0** |
| Clean claims sent straight through | all | 1 of 9 |
| Evidence triples that exist in the graph | 100% | 100% |
| Calibration error (ECE) | 0.00 | 0.75 |

The dev set uses the same templates the extractor was written against, so its 1.00 says little. The blind set is the real number. What failed on it:
- **Date formats**: "3rd Feb 2026" and "Mar 22, 2026" were not parsed → `EXTRACTION_INCOMPLETE` (one of these hid a real `POLICY_INACTIVE`, still safely routed to review).
- **Negation**: "I drive for Uber on weekends but this was a family trip" triggered the rideshare exclusion (false positive).
- **Driver phrasing**: "my friend Sameer Ali borrowed my Creta and crashed" has no "was driving" → unlisted driver missed (the claim still went to review because the driver field was empty).
- **Vocabulary**: "scraped" is not in the collision lexicon.
- **Over-caution**: parked-car losses (theft, storm, vandalism) have no driver, and the confidence rule treats the empty driver field as uncertainty, so 8 of 9 clean claims went to review. The 0.75 ECE says the same thing: `min(field confidence)` is a poor confidence score.
- **Make**: claimants usually name only the model ("my Swift"), so make accuracy was 0.35. It did not cause wrong flags because the vehicle check falls back to the model.

## Run it

```bash
pip install -r requirements.txt
python run.py          # offline, no API keys
pytest -q              # 6 tests
```

Real-LLM path: wrap your client in a function `llm(prompt) -> str` that returns JSON and pass it to `LLMExtractor(llm)`. Output is checked against the schema, and anything invalid falls back to the rule extractor. The evaluation harness works unchanged with either extractor, which is the point: you can compare them on the same blind set.

## Limitations and next steps

- Make "driver required" depend on loss type (a parked-car theft needs no driver), and derive confidence per check instead of `min()` over all fields. This should fix most over-caution.
- Use an LLM extractor (or a date parser like `dateparser`) for free-form dates and negation, then re-run the same blind set and compare.
- Add an LLM-as-judge step that scores the adjuster note against the evidence triples, and calibrate it against human labels.
- Move the graph to Neo4j/Cypher for multi-hop questions (e.g. household drivers across policies, prior claims on a VIN).
- Synthetic data only. Real policy forms carry endorsements, limits per peril and state rules that this model ignores.
