"""Synthetic personal-auto policies and generated FNOL (first notice of loss) reports.

Everything here is synthetic and seeded. No real insurer or customer data is used.
"""
import random
from datetime import date, timedelta

FIRST = ["Ravi", "Anita", "Karan", "Meera", "Arjun", "Priya", "Vikram", "Neha", "Rohit", "Sana",
         "Aditya", "Kavya", "Imran", "Pooja", "Siddharth", "Lata"]
LAST = ["Mehta", "Sharma", "Iyer", "Reddy", "Khan", "Gupta", "Nair", "Joshi", "Das", "Patel"]
VEHICLES = [("Honda", "City"), ("Maruti", "Swift"), ("Hyundai", "Creta"), ("Tata", "Nexon"),
            ("Toyota", "Innova"), ("Kia", "Seltos"), ("Mahindra", "XUV700"), ("Skoda", "Slavia")]
CITIES = ["Pune", "Hyderabad", "Mumbai", "Chennai", "Bengaluru", "Jaipur"]

# loss type -> coverage that must exist on the policy
LOSS_TO_COVERAGE = {"collision": "collision", "theft": "comprehensive", "weather": "comprehensive",
                    "glass": "comprehensive", "vandalism": "comprehensive"}

LOSS_TEXT = {
    "collision": ["was hit from behind at a signal", "collided with a divider", "got rear-ended in traffic"],
    "theft": ["was stolen from the parking lot", "went missing overnight; police say it was stolen"],
    "weather": ["was damaged when a tree fell on it during the storm", "got flooded in the heavy rain"],
    "glass": ["has a cracked windshield after a stone hit it"],
    "vandalism": ["was scratched and keyed by someone at night"],
}


def make_policies(n=25, seed=7):
    rng = random.Random(seed)
    policies = []
    for i in range(n):
        holder = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        surname = holder.split()[1]
        eff = date(2025, 1, 1) + timedelta(days=rng.randint(0, 400))
        pol = {
            "policy_id": f"P-{1001 + i}",
            "holder": holder,
            "effective": eff.isoformat(),
            "expiry": (eff + timedelta(days=365)).isoformat(),
            "cancelled_on": None,
            "vehicles": [],
            "drivers": [{"name": holder, "excluded": False}],
            "coverages": [{"type": "liability", "limit": 1500000, "deductible": 0}],
            "exclusions": [],
        }
        for _ in range(rng.choice([1, 1, 2])):
            make, model = rng.choice(VEHICLES)
            pol["vehicles"].append({"vehicle_id": f"V-{1001 + i}-{len(pol['vehicles']) + 1}",
                                    "make": make, "model": model, "year": rng.randint(2016, 2025)})
        if rng.random() < 0.7:
            pol["drivers"].append({"name": f"{rng.choice(FIRST)} {surname}", "excluded": False})
        if rng.random() < 0.25:
            pol["drivers"].append({"name": f"{rng.choice(FIRST)} {surname}", "excluded": True})
        if rng.random() < 0.8:
            pol["coverages"].append({"type": "collision", "limit": 800000, "deductible": rng.choice([5000, 10000])})
        if rng.random() < 0.7:
            pol["coverages"].append({"type": "comprehensive", "limit": 800000, "deductible": rng.choice([2500, 5000])})
        if rng.random() < 0.3:
            pol["exclusions"].append("rideshare")
        if rng.random() < 0.15:
            pol["cancelled_on"] = (eff + timedelta(days=rng.randint(60, 300))).isoformat()
        policies.append(pol)
    return policies


def _fmt_date(d, rng):
    return rng.choice([d.strftime("%d %B %Y"), d.isoformat(), d.strftime("%d/%m/%Y")])


def make_fnols(policies, n=120, seed=11):
    """Generate FNOL texts with gold structured fields.

    Faults are injected on purpose (wrong vehicle, unlisted driver, lapsed policy, ...).
    Gold flags are not stored here: evaluate.py derives them by running the checker on the gold
    fields, so the dev set measures extraction errors. The checker logic itself is tested by the
    unit tests and by the hand-labelled flags in the blind set.
    """
    rng = random.Random(seed)
    out = []
    for k in range(n):
        pol = rng.choice(policies)
        eff, exp = date.fromisoformat(pol["effective"]), date.fromisoformat(pol["expiry"])
        fault = rng.choice(["none", "none", "none", "vehicle", "driver", "excluded", "lapsed",
                            "coverage", "rideshare", "unknown_policy"])
        loss_date = eff + timedelta(days=rng.randint(5, 330))
        veh = rng.choice(pol["vehicles"])
        make, model = veh["make"], veh["model"]
        listed = [d for d in pol["drivers"] if not d["excluded"]]
        driver = rng.choice(listed)["name"]
        loss_type = rng.choice(list(LOSS_TEXT))
        rideshare = False
        pid = pol["policy_id"]
        if fault == "vehicle":
            others = [v for v in VEHICLES if v != (make, model)]
            make, model = rng.choice(others)
            if any((v["make"], v["model"]) == (make, model) for v in pol["vehicles"]):
                fault = "none"
        elif fault == "driver":
            driver = f"{rng.choice(FIRST)} {rng.choice(['Verma', 'Bose', 'Kulkarni'])}"
        elif fault == "excluded":
            ex = [d for d in pol["drivers"] if d["excluded"]]
            if ex:
                driver = ex[0]["name"]
            else:
                fault = "none"
        elif fault == "lapsed":
            loss_date = exp + timedelta(days=rng.randint(3, 40))
        elif fault == "coverage":
            have = {c["type"] for c in pol["coverages"]}
            missing = [lt for lt, cov in LOSS_TO_COVERAGE.items() if cov not in have]
            if missing:
                loss_type = rng.choice(missing)
            else:
                fault = "none"
        elif fault == "rideshare":
            rideshare = True
        elif fault == "unknown_policy":
            pid = f"P-{rng.randint(5000, 5999)}"

        who = "I was driving" if driver == pol["holder"] else f"{driver} was driving"
        ride = " I was on an Uber trip with a passenger at the time." if rideshare else ""
        text = (f"Hello, this is {pol['holder']}, policy {pid}. On {_fmt_date(loss_date, rng)} my "
                f"{veh['year']} {make} {model} {rng.choice(LOSS_TEXT[loss_type])} in {rng.choice(CITIES)}. "
                f"{who}.{ride}")
        out.append({"fnol_id": f"F-{k + 1:03d}", "text": text,
                    "gold": {"policy_id": pid, "loss_date": loss_date.isoformat(), "make": make,
                             "model": model, "driver": driver, "loss_type": loss_type,
                             "rideshare": rideshare}})
    return out
