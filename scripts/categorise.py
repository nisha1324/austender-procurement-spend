"""Part 4: sort Education and Training notices into spend categories.

Two backends, one interface (`label_many`):

- **offline** (default): ordered keyword rules on the description and the supplier's name, in the
  taxonomy's decision order. No supplier lists: only words any reader would act on ("coaching",
  "university", "language"). Every label records the rule that fired, so each one can be explained.
- **claude**: the same taxonomy and decision order as a prompt, answered through a forced tool call
  with the category as an enum, in batches. Needs `ANTHROPIC_API_KEY` in the environment or in a
  gitignored `.env`; nothing paid runs without one. Unknown or missing answers fall back to the
  offline label and are counted.

    python -m scripts.categorise                  # offline: labels, check-set score, report, chart
    python -m scripts.categorise --backend claude # needs a key; adds the Claude labels and score
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from scripts.training_taxonomy import CATEGORIES, KEYS

ROOT = Path(__file__).resolve().parent.parent

# ---------- offline baseline ----------
# (category, field, pattern). Fields: d = description, s = supplier name, ds = either.
# Checked in this order; the first match wins. `defence_only` rules apply to Defence notices only.
RULES: list[tuple[str, str, str]] = [
    ("public_program", "d", r"skills for education and employment|scholarship|clinical placement|"
                            r"transition to practice|pre-employment|launch into work|community education|"
                            r"teacher resource|industry initiative|to industry|skills development program"),
    ("not_training", "d", r"catering|hospitality|venue|\bhire\b|\brations\b|printing|quality assurance|"
                          r"subscription|textbook|\bbooks?\b|recruit|internship|outreach|consultation|"
                          r"event management|events management|copyedit|graphic design|professional advice"),
    ("not_training", "s", r"grammar|hospitality"),
    ("military_operational", "ds", r"defen[cs]e|military|training system|simulat|weapon|tactical|\bk9\b"),
    ("military_operational", "defence_only", r"flying|\bfly\b|flight|aviation|helicopter|aircraft|test pilot|"
                                             r"sailing|vessel|strength and conditioning"),
    ("leadership_coaching", "ds", r"leader|coach|mentor|\bses\b|manager|executive development|"
                                  r"institute of management|management educ|institute of mgt|team workshop|"
                                  r"team development|management program|management development"),
    ("language", "d", r"language"),
    ("digital_it", "ds", r"cyber|software|\bdata\b|digital|excel|\bweb\b|computer|\bgis\b|\bi2\b|analytics|"
                         r"information security|threat model|osint|\bcloud\b"),
    ("safety_compliance", "ds", r"safety|first aid|\bfire\b|\bwhs\b|work health|mental health|life ?saving|"
                                r"ambulance|radiation|fraud|ethics|compliance|suicide|advanced driving|"
                                r"search and rescue"),
    ("professional_technical", "d", r"writ(e|ing)|\bmedia\b|communicat|project manag|procurement|financ|"
                                    r"account|\bcpa\b|\blaw\b|legal|policy|payment|\brisk\b|investigat|"
                                    r"director|governance|standards|psycholog|\btrades?\b|technical|refrigeration|"
                                    r"vocational|clinical|x-?ray|forensic|briefs|complain|negotiat|"
                                    r"presentation|public information|\bhr\b"),
    # Supplier names: only words that name a topic. ("Technical and Further Education" is a TAFE.)
    ("professional_technical", "s", r"writ(e|ing)|\bmedia\b|communicat|project manag|account|\bcpa\b|"
                                    r"legal|\blaw\b|director|forensic|psycholog|refrigeration|standards|\bhr\b"),
    ("elearning", "ds", r"e-?learning|online|virtual|\blms\b|learning management|learning platform|"
                        r"content library|coursera|licen[cs]e"),
    ("events_memberships", "d", r"conference|membership|summit|forum|symposium|network|tickets|registration"),
    ("tertiary", "s", r"universit|\btafe\b|technical and further education|polytechnic|institute of technology|"
                      r"school of government|business school|\banu\b|\bunsw\b|anzsog"),
]
_COMPILED = [(cat, field, re.compile(p, re.IGNORECASE)) for cat, field, p in RULES]
# The Skills for Education and Employment program's acronym, matched case-sensitively ("see" isn't it).
_SEE = re.compile(r"\bSEE\b")


@dataclass(frozen=True)
class Label:
    category: str
    rule: str


def classify(description: str, supplier: str, is_defence: bool = False) -> Label:
    d, s = description or "", supplier or ""
    for i, (cat, field, rx) in enumerate(_COMPILED):
        if i == 0:
            hit = rx.search(d) or _SEE.search(d)
        elif field == "d":
            hit = rx.search(d)
        elif field == "s":
            hit = rx.search(s)
        elif field == "ds":
            hit = rx.search(d) or rx.search(s)
        else:  # defence_only: flying, sailing etc. are operational only for Defence
            hit = is_defence and (rx.search(d) or rx.search(s))
        if hit:
            return Label(cat, f"r{i:02d}:{field}:{hit.group(0).lower()}")
    return Label("unspecified", "fallback")


def label_offline(df: pd.DataFrame) -> pd.DataFrame:
    out = [classify(r.description, r.supplier_name, bool(r.is_defence)) for r in df.itertuples()]
    return pd.DataFrame({"cn_id": df.cn_id.values, "label": [o.category for o in out],
                         "rule": [o.rule for o in out]})


# ---------- Claude backend ----------
MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-5-5")
BATCH_SIZE = 40

SYSTEM = (
    "You sort Australian Government contract notices coded as 'Education and Training Services' into "
    "spend categories for a procurement analyst. Each notice has a short description, the supplier's "
    "name and the buying agency. Pick exactly ONE category per notice. Go down the list in order and "
    "take the FIRST category that fits. You may use general knowledge of what a well-known supplier or "
    "program does, but only when it has one clear line of business; if neither the notice nor the "
    "supplier tells you the topic, answer 'tertiary' for universities and TAFEs and 'unspecified' "
    "otherwise. Being a Defence notice is not enough for 'military_operational'.\n\nCategories, in order:\n"
    + "\n".join(f"- {k}: {d}" for k, _, d in CATEGORIES)
)

TOOL = {
    "name": "record_categories",
    "description": "Record one category per notice id.",
    "input_schema": {
        "type": "object",
        "properties": {
            "labels": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "cn_id": {"type": "string"},
                        "category": {"type": "string", "enum": KEYS},
                    },
                    "required": ["cn_id", "category"],
                },
            }
        },
        "required": ["labels"],
    },
}


def load_dotenv(path: Path = ROOT / ".env") -> None:
    """Read KEY=VALUE lines from a gitignored .env into the environment (no extra dependency)."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("'\""))


def has_key() -> bool:
    load_dotenv()
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def build_user_message(batch: pd.DataFrame) -> str:
    items = [{"cn_id": r.cn_id, "description": r.description, "supplier": r.supplier_name,
              "agency": r.agency} for r in batch.itertuples()]
    return "Categorise each notice:\n" + json.dumps(items, ensure_ascii=False)


def parse_labels(tool_input: dict, expected_ids: list[str]) -> dict[str, str | None]:
    """The model's answer, checked: unknown categories, unknown ids and missing ids become None."""
    got: dict[str, str] = {}
    for item in tool_input.get("labels", []) if isinstance(tool_input, dict) else []:
        if isinstance(item, dict) and item.get("category") in KEYS and item.get("cn_id") in expected_ids:
            got.setdefault(item["cn_id"], item["category"])
    return {cid: got.get(cid) for cid in expected_ids}


def label_claude(df: pd.DataFrame, client=None, batch_size: int = BATCH_SIZE) -> pd.DataFrame:
    """Label with Claude; any notice without a valid answer keeps its offline label (rule 'fallback:...')."""
    if client is None:
        if not has_key():
            raise RuntimeError("No ANTHROPIC_API_KEY (environment or .env); use the offline backend.")
        import anthropic
        client = anthropic.Anthropic()
    offline = label_offline(df).set_index("cn_id")
    labels, rules = [], []
    for start in range(0, len(df), batch_size):
        batch = df.iloc[start:start + batch_size]
        resp = client.messages.create(
            model=MODEL, max_tokens=4096, system=SYSTEM, tools=[TOOL],
            tool_choice={"type": "tool", "name": TOOL["name"]},
            messages=[{"role": "user", "content": build_user_message(batch)}],
        )
        block = next((b for b in resp.content if getattr(b, "type", None) == "tool_use"), None)
        answers = parse_labels(block.input if block else {}, list(batch.cn_id))
        for cid in batch.cn_id:
            if answers[cid] is None:
                labels.append(offline.at[cid, "label"])
                rules.append("fallback:" + offline.at[cid, "rule"])
            else:
                labels.append(answers[cid])
                rules.append("claude")
    return pd.DataFrame({"cn_id": df.cn_id.values, "label": labels, "rule": rules})


def estimate_calls(n_notices: int, batch_size: int = BATCH_SIZE) -> dict[str, int]:
    """Rough size of one Claude run: calls and input/output tokens (about 4 characters a token)."""
    calls = -(-n_notices // batch_size)
    system_tokens = len(SYSTEM + json.dumps(TOOL)) // 4
    per_notice_in, per_notice_out = 45, 20
    return {"calls": calls, "input_tokens": calls * system_tokens + n_notices * per_notice_in,
            "output_tokens": n_notices * per_notice_out}


def main(argv: list[str] | None = None) -> None:
    from scripts import categoriser_report

    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--backend", choices=["offline", "claude"], default="offline")
    args = p.parse_args(argv)
    if args.backend == "claude" and not has_key():
        sys.exit("No ANTHROPIC_API_KEY found (environment or .env). Copy .env.example to .env and add a key, "
                 "or run the offline backend.")
    categoriser_report.main(backend=args.backend)


if __name__ == "__main__":
    main()
