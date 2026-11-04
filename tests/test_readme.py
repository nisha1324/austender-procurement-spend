"""Every figure in the README's Part 1 must come from a generated result file."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text()
SOURCES = "\n".join(p.read_text() for p in (ROOT / "results").glob("*.md"))

# Numbers that are rules or thresholds, not results.
ALLOWED = {"10,000", "1,300", "80k", "42", "10k"}


def part1() -> str:
    return README.split("## Part 1", 1)[1].split("## Roadmap", 1)[0]


def figures(text: str) -> set[str]:
    # $ amounts, percentages, numbers with a thousands comma or a decimal point.
    pat = r"\$\d[\d,]*(?:\.\d+)?(?:bn|m|k)?|\d+(?:\.\d+)?%|\d{1,3}(?:,\d{3})+|\d+\.\d+"
    return set(re.findall(pat, text))


def test_part1_figures_appear_in_the_results():
    missing = sorted(f for f in figures(part1()) if f not in SOURCES and f.lstrip("$") not in ALLOWED)
    assert not missing, f"README figures not found in results/*.md: {missing}"


def test_overstatement_ratio_matches_the_profile():
    m = re.search(r"Summing every version gives (\$[\d.]+bn), ([\d.]+) times the (\$[\d.]+bn)", SOURCES)
    assert m, "profile wording changed"
    assert f"Summing every row gives {m.group(1)}, {m.group(2)} times the {m.group(3)}" in part1()
    assert f"about {m.group(2)} times" in part1()


def test_headline_phrases_are_tied_to_their_rows():
    pairs = [
        ("25,140 of the 34,100 (73.7%)", "25,140 of the 34,100 limited tenders (73.7%)"),
        ("2,956 of 13,026 supplier ABNs", "2,956 of 13,026 supplier ABNs"),
        ("top 1% (595 notices) 68.6%", "top 1% of notices (595) hold 68.6%"),
        ("8 May 2025, has 766 amendments, 95.0%", "8 May 2025, 766 amendments"),
        ("8,737 notices (14.7%)", "8,737 notices (14.7%)"),
        ("Up to 36 amendments", "Up to 36 amendments"),
        ("among them a $2.34bn Home Affairs contract", "including a $2.34bn Home Affairs contract"),
        ("1,272 notices are cancelled ($3.20bn)", "1,272 notices are cancelled ($3.20bn)"),
        ("57.4% of notices (60.3% of value)", "57.4% of notices (60.3% of value)"),
        ("the 84 of $100m and over hold 45.6%", "84\n  notices of $100m and over hold 45.6%"),
        ("$51.86bn when first published and $65.41bn after amendments (26.1% more)",
         "$51.86bn when first published, $65.41bn after amendments (26.1% more)"),
    ]
    for in_profile, in_readme in pairs:
        assert in_profile in SOURCES, in_profile
        assert in_readme in part1(), in_readme
