"""Part 4: keyword rules, the Claude backend (with a fake client), the estimates and the committed results."""
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from scripts import categorise as cat
from scripts import categoriser_report as cr
from scripts.training_taxonomy import CATEGORIES, KEYS

ROOT = Path(__file__).resolve().parent.parent


# ---------- keyword rules ----------
@pytest.mark.parametrize("desc, supplier, defence, expected", [
    ("Skills for Education and Employment (SEE) Program", "TAFE SA", False, "public_program"),
    ("SEE Project Delivery", "Anyone", False, "public_program"),
    ("Please see attached", "Anyone", False, "unspecified"),          # 'see' isn't the program
    ("Rations", "Anyone", True, "not_training"),
    ("Illustrations and design", "Anyone", False, "unspecified"),     # not 'rations'
    ("Training Services", "KNOX GRAMMAR SCHOOL", True, "not_training"),
    ("Training Services", "CUBIC DEFENCE AUSTRALIA PTY LTD", True, "military_operational"),
    ("Training Services", "KOOLARDIE AVIATION PTY LTD", True, "military_operational"),
    ("Training Services", "KOOLARDIE AVIATION PTY LTD", False, "unspecified"),  # flying: Defence only
    ("Executive Coaching EL1", "Anyone", False, "leadership_coaching"),
    ("Language Training", "University of New South Wales", False, "language"),  # topic beats provider
    ("Software Training", "Anyone", False, "digital_it"),
    ("First Aid Training", "Anyone", True, "safety_compliance"),
    ("Strategic Writing Training", "Anyone", False, "professional_technical"),
    ("Innovative Project", "TECHNICAL AND FURTHER EDUCATION", False, "tertiary"),  # not 'technical'
    ("Training Licences", "COURSERA", True, "elearning"),
    ("Annual Membership", "Anyone", False, "events_memberships"),
    ("Training Services", "UNIVERSITY OF MELBOURNE", True, "tertiary"),
    ("Training Services", "THE HATCHERY (HUB)", True, "unspecified"),
])
def test_rules(desc, supplier, defence, expected):
    got = cat.classify(desc, supplier, defence)
    assert got.category == expected, got
    assert got.rule == "fallback" if expected == "unspecified" else got.rule.startswith("r")


def test_rule_order_follows_the_taxonomy():
    order = [c for c, _, _ in cat.RULES]
    ranks = [KEYS.index(c) for c in order]
    assert ranks == sorted(ranks), "rules must be checked in the taxonomy's decision order"


# ---------- Claude backend ----------
class FakeClient:
    """Answers like the API: a tool_use block. `answer(ids)` decides the labels per batch."""

    def __init__(self, answer):
        self.answer, self.calls = answer, []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.calls.append(kw)
        items = json.loads(kw["messages"][0]["content"].split("\n", 1)[1])
        block = SimpleNamespace(type="tool_use", input={"labels": self.answer([i["cn_id"] for i in items])})
        return SimpleNamespace(content=[SimpleNamespace(type="text", text="ok"), block])


def frame(k: int) -> pd.DataFrame:
    return pd.DataFrame({"cn_id": [f"CN{i}" for i in range(k)], "description": ["Training Services"] * k,
                         "supplier_name": ["UNIVERSITY OF X"] * k, "agency": ["Dept"] * k,
                         "is_defence": [False] * k})


def test_claude_batches_forces_the_tool_and_keeps_valid_answers():
    fake = FakeClient(lambda ids: [{"cn_id": i, "category": "language"} for i in ids])
    out = cat.label_claude(frame(5), client=fake, batch_size=2)
    assert len(fake.calls) == 3
    assert all(c["tool_choice"] == {"type": "tool", "name": "record_categories"} for c in fake.calls)
    assert all(c["tools"][0]["input_schema"]["properties"]["labels"]["items"]["properties"]["category"]["enum"]
               == KEYS for c in fake.calls)
    assert list(out.label) == ["language"] * 5 and set(out.rule) == {"claude"}


def test_claude_bad_answers_fall_back_to_the_baseline_and_are_marked():
    def answer(ids):
        return [{"cn_id": ids[0], "category": "astrology"},           # not a category
                {"cn_id": "CN999", "category": "language"},           # not in this batch
                {"cn_id": ids[1], "category": "digital_it"},
                {"cn_id": ids[1], "category": "language"}]            # duplicate: first kept
    out = cat.label_claude(frame(3), client=FakeClient(answer), batch_size=3)
    assert list(out.label) == ["tertiary", "digital_it", "tertiary"]  # baseline says tertiary
    assert list(out.rule) == ["fallback:r13:s:universit", "claude", "fallback:r13:s:universit"]


def test_parse_labels_survives_garbage():
    assert cat.parse_labels("nonsense", ["A"]) == {"A": None}
    assert cat.parse_labels({"labels": [None, {"cn_id": "A"}]}, ["A"]) == {"A": None}


def test_claude_refuses_without_a_key(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(cat, "ROOT", tmp_path)  # no .env there
    monkeypatch.setattr(cat, "load_dotenv", lambda path=tmp_path / ".env": None)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        cat.label_claude(frame(1))
    with pytest.raises(SystemExit):
        cat.main(["--backend", "claude"])


def test_dotenv_reader(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    (tmp_path / ".env").write_text("# comment\nANTHROPIC_API_KEY='sk-test'\n")
    cat.load_dotenv(tmp_path / ".env")
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-test"
    monkeypatch.delenv("ANTHROPIC_API_KEY")


def test_prompt_lists_every_category_in_order():
    pos = [cat.SYSTEM.index(f"- {k}: ") for k, _, _ in CATEGORIES]
    assert pos == sorted(pos)


# ---------- estimates and scoring, worked by hand ----------
def test_category_mix_and_score_by_hand():
    # Population: two $1m+ notices (census) and four small ones totalling $100k.
    pop = pd.DataFrame({"cn_id": list("ABCDEF"),
                        "value_aud": [2e6, 3e6, 10e3, 20e3, 30e3, 40e3]})
    # Sample of two small notices: C (10k, language) and F (40k, unspecified).
    gold = pd.DataFrame({"cn_id": list("ABCF"), "stratum": ["large", "large", "random", "random"],
                         "value_aud": [2e6, 3e6, 10e3, 40e3],
                         "label": ["public_program", "language", "language", "unspecified"],
                         "basis": ["description", "description", "description", "none"]})
    mix = cr.category_mix(pop, gold).set_index("category")
    # Small stratum: 4 notices, $100k. Language: 1 of 2 sampled -> 2 notices; 10k of 50k -> $20k.
    assert mix.loc["language", "est_notices"] == 1 + 2
    assert mix.loc["language", "est_value"] == pytest.approx(3e6 + 20e3)
    assert mix.loc["unspecified", "est_value"] == pytest.approx(80e3)
    assert mix.est_value.sum() == pytest.approx(pop.value_aud.sum())
    assert mix.est_notices.sum() == pytest.approx(len(pop))

    pred = pd.DataFrame({"cn_id": list("ABCF"), "label": ["public_program", "unspecified", "language", "unspecified"]})
    sc = cr.score(gold, pred)
    assert sc["large"] == {"n": 2, "correct": 1, "value_correct": 2e6, "value": 5e6}
    assert sc["random"]["correct"] == 2
    assert sc["by_basis"].loc["description"].tolist() == [2, 3]
    assert sc["confusions"].iloc[0].tolist() == ["language", "unspecified", 1]


def test_wilson_interval():
    lo, hi = cr.wilson(82, 200)
    assert (round(lo, 3), round(hi, 3)) == (0.344, 0.479)


# ---------- committed results ----------
@pytest.fixture(scope="module")
def real():
    con = cr.training_connection()
    pop = cr.population(con)
    gold = cr.load_labels()
    base_pop = pop[["cn_id", "value_aud"]].merge(cat.label_offline(pop), on="cn_id")
    return con, pop, gold, base_pop


def test_report_and_csvs_regenerate_identically(real, tmp_path, monkeypatch):
    con, pop, gold, base_pop = real
    snap = json.loads(cr.SNAPSHOT.read_text())
    mix = cr.category_mix(pop, gold)
    report = cr.write_report(pop, gold, mix, cr.score(gold, base_pop), cr.segment_context(con), base_pop, snap)
    assert report == (ROOT / "results" / "CATEGORISER.md").read_text()
    monkeypatch.setattr(cr, "RESULTS", tmp_path)
    cr.write_csvs(pop, base_pop, mix)
    for name in ("training_categories.csv", "training_category_mix.csv"):
        assert (tmp_path / name).read_text() == (ROOT / "results" / name).read_text(), name


def test_committed_labels_match_the_rules_and_add_up(real):
    _, pop, _, _ = real
    out = pd.read_csv(ROOT / "results" / "training_categories.csv", dtype={"cn_id": str})
    assert len(out) == len(pop) == 3589
    again = cat.label_offline(pop).set_index("cn_id")
    assert (out.set_index("cn_id").offline_label == again.label).all()
    mix = pd.read_csv(ROOT / "results" / "training_category_mix.csv")
    assert mix.est_value.sum() == pytest.approx(float(pop.value_aud.sum()), abs=1)
    assert mix.est_notices.sum() == pytest.approx(len(pop), abs=0.5)
