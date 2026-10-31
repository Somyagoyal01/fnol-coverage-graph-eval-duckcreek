"""Turn a free-text FNOL into structured fields.

Two extractors share one output schema:
- RuleExtractor: offline, no API key. Regex + small lexicons. This is what the tests and results use.
- LLMExtractor: wraps any `llm(prompt) -> str` callable (OpenAI, Gemini, Bedrock...) that returns JSON.
  The output is validated against the same schema; anything invalid falls back to the rule extractor.
Each field comes with a confidence (1.0 explicit, 0.6 inferred, 0.0 missing).
"""
import json
import re
from datetime import date, datetime, timedelta

FIELDS = ["policy_id", "loss_date", "make", "model", "driver", "loss_type", "rideshare"]

MAKES = {"honda": "Honda", "maruti": "Maruti", "suzuki": "Maruti", "hyundai": "Hyundai", "tata": "Tata",
         "toyota": "Toyota", "kia": "Kia", "mahindra": "Mahindra", "skoda": "Skoda", "mg": "MG",
         "renault": "Renault", "volkswagen": "Volkswagen", "vw": "Volkswagen"}
MODELS = {"city": "City", "amaze": "Amaze", "swift": "Swift", "baleno": "Baleno", "creta": "Creta",
          "venue": "Venue", "nexon": "Nexon", "punch": "Punch", "innova": "Innova", "fortuner": "Fortuner",
          "seltos": "Seltos", "sonet": "Sonet", "xuv700": "XUV700", "thar": "Thar", "slavia": "Slavia",
          "hector": "Hector", "kwid": "Kwid", "virtus": "Virtus"}
LOSS_WORDS = [
    ("theft", r"stolen|theft|stole|missing"),
    ("glass", r"windshield|windscreen|glass"),
    ("vandalism", r"keyed|vandal|scratched"),
    ("weather", r"flood|storm|hail|tree fell|cyclone|waterlogg"),
    ("collision", r"hit|collid|rear-ended|crash|accident|bumped|dent"),
]
RIDESHARE = r"\b(uber|ola|rapido|ride-?hail|rideshare|cab trip|passenger trip|on a trip with a passenger)\b"
RELATIONS = r"(?:son|daughter|wife|husband|brother|sister|father|mother)"
MONTHS = "january february march april may june july august september october november december".split()


def _parse_date(text, report_date=None):
    t = text.lower()
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", t)
    if m:
        return date(int(m[1]), int(m[2]), int(m[3])).isoformat(), 1.0
    m = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", t)
    if m:
        return date(int(m[3]), int(m[2]), int(m[1])).isoformat(), 1.0
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(" + "|".join(MONTHS) + r")\s+(\d{4})\b", t)
    if m:
        return date(int(m[3]), MONTHS.index(m[2]) + 1, int(m[1])).isoformat(), 1.0
    if report_date and re.search(r"\byesterday\b|last night", t):
        return (date.fromisoformat(report_date) - timedelta(days=1)).isoformat(), 0.6
    return None, 0.0


def _caller(text):
    m = re.search(r"(?i:this is|my name is|i am|i'm)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", text)
    return m[1] if m else None


def _driver(text, caller):
    if re.search(r"\bi was (?:driving|behind the wheel|at the wheel)\b", text, re.I):
        return caller, (1.0 if caller else 0.0)
    m = re.search(r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?) was (?:driving|behind the wheel)", text) \
        or re.search(r"driven by (?:my " + RELATIONS + r"\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", text)
    if m:
        name = m[1]
        if " " not in name and caller and " " in caller:
            return f"{name} {caller.split()[1]}", 0.6   # surname inferred from the caller
        return name, 1.0
    return None, 0.0


class RuleExtractor:
    def extract(self, text, report_date=None):
        out, conf = {}, {}
        m = re.search(r"\bP-?\s?(\d{4})\b", text, re.I)
        out["policy_id"], conf["policy_id"] = (f"P-{m[1]}", 1.0) if m else (None, 0.0)
        out["loss_date"], conf["loss_date"] = _parse_date(text, report_date)
        low = text.lower()
        mk = next((MAKES[w] for w in re.findall(r"[a-z0-9]+", low) if w in MAKES), None)
        md = next((MODELS[w] for w in re.findall(r"[a-z0-9]+", low) if w in MODELS), None)
        out["make"], conf["make"] = mk, 1.0 if mk else 0.0
        out["model"], conf["model"] = md, 1.0 if md else 0.0
        out["driver"], conf["driver"] = _driver(text, _caller(text))
        lt = next((name for name, pat in LOSS_WORDS if re.search(pat, low)), None)
        out["loss_type"], conf["loss_type"] = lt, 1.0 if lt else 0.0
        out["rideshare"] = bool(re.search(RIDESHARE, low))
        conf["rideshare"] = 1.0
        return out, conf


class LLMExtractor:
    """Real-LLM path. `llm` is any callable taking a prompt and returning a JSON string."""
    PROMPT = ("Extract these fields from the first-notice-of-loss text as JSON with keys "
              + ", ".join(FIELDS) + ". loss_date as YYYY-MM-DD; loss_type one of collision, theft, weather, "
              "glass, vandalism; rideshare true/false; use null when not stated. Text:\n")

    def __init__(self, llm, fallback=None):
        self.llm, self.fallback = llm, fallback or RuleExtractor()

    def extract(self, text, report_date=None):
        try:
            data = json.loads(self.llm(self.PROMPT + text))
            if set(FIELDS) - set(data):
                raise ValueError("missing keys")
            if data["loss_date"]:
                datetime.strptime(data["loss_date"], "%Y-%m-%d")
            return {k: data[k] for k in FIELDS}, {k: (0.9 if data[k] is not None else 0.0) for k in FIELDS}
        except (ValueError, KeyError, TypeError):
            return self.fallback.extract(text, report_date)
