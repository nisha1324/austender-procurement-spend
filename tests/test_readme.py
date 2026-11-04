"""Every figure in the README's Part 1 must come from a generated result file."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text()
SOURCES = "\n".join(p.read_text() for p in (ROOT / "results").glob("*.md"))

# Numbers that are rules or thresholds, not results.
ALLOWED = {"10,000", "1,300", "80k", "42", "10k", "100m", "1,500", "2,500"}


def part1() -> str:
    return README.split("## Part 1", 1)[1].split("## Part 2", 1)[0]


def part2() -> str:
    return README.split("## Part 2", 1)[1].split("## Roadmap", 1)[0]


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


def test_part2_figures_appear_in_the_results():
    missing = sorted(f for f in figures(part2()) if f not in SOURCES and f.lstrip("$") not in ALLOWED)
    assert not missing, f"README figures not found in results/*.md: {missing}"


def test_part2_headline_phrases_are_tied_to_their_rows():
    cube = (ROOT / "results" / "SPEND_CUBE.md").read_text()
    pairs = [
        ("58,192 active contract notices", "58,192 active notices"),
        ("$62.21bn in total ($48.60bn at award)", "$62.21bn of committed\ncontract value** ($48.60bn at award)"),
        ("Services hold 75.9%", "Services take 75.9%"),
        ("holds 26.8% on its own", "holds 26.8% on its own"),
        ("Defence holds 86.1% of *Building and Construction and Maintenance Services* ($9.75bn)",
         "86.1% of building and construction ($9.75bn)"),
        ("Defence holds 43.5% of value", "Defence holds 43.5% of all\nvalue"),
        ("**58 of them hold half the committed value** and 391 hold 80%",
         "**58 of them hold half the committed value** and 391\nhold 80%"),
        ("10,103 suppliers (62.2%) won exactly one notice", "10,103 suppliers (62.2%) won exactly one notice"),
        ("| VENTIA AUSTRALIA PTY LTD | 37 | $3.44bn | 5.5% | 1 | 6 | 3 | 100.0% | 98.5% |",
         "($3.44bn), has 98.5% of it in one notice"),
        ("42 families, $55.78bn, 89.7% of value", "42 large categories"),
        ("25 of 42 large families are low ($31.41bn), 7 moderate ($17.47bn) and 10 high. Of the high ones, "
         "4 are one contract and 6 go beyond one contract ($4.17bn, 7.5% of large-family value)",
         "Only $4.17bn (7.5% of large-category value)"),
        ("| all agencies | high | one contract | 4 | $2.73bn |", "| High, but only because of one contract | 4 | $2.73bn |"),
        ("| all agencies | high | beyond one contract | 6 | $4.17bn |", "| High beyond one contract | 6 | $4.17bn |"),
        ("| all agencies | low |  | 25 | $31.41bn |", "| Low concentration (HHI under 1,500) | 25 | $31.41bn |"),
        ("| all agencies | moderate |  | 7 | $17.47bn |", "| Moderate (1,500 to 2,500) | 7 | $17.47bn |"),
        ("| 1510 | Fuels | $898.8m | 114 | 9 | 50 | VIVA ENERGY AUSTRALIA PTY LTD | 28 | 81.9% |",
         "fuels (one supplier, 81.9% from 28 notices)"),
        ("| UNIVERSAL MCCANN | 284 | 69.1% |", "advertising (one supplier, 69.1% from 284\nnotices)"),
        ("| Comcare | 22 | 42.7% |", "Comcare, the government's workers' compensation insurer, 42.7%"),
        ("| CEA TECHNOLOGIES PTY LTD | 1 | 79.6% |", "CEA Technologies: 79.6%\nand 62.7%"),
        ("| CEA TECHNOLOGIES PTY LTD | 2 | 62.7% |", "CEA Technologies: 79.6%\nand 62.7%"),
        ("29 large families: 18 low, 0 moderate, 11 high (6 one contract",
         "Without Defence, 11 of 29 large categories are highly concentrated,\n6 of them because of one contract"),
        ("| SECURE JOURNEYS PTY LTD | 1 | 60.6% |", "60.6%\nof non-Defence business administration"),
        ("12 families, $19.11bn", "12 large categories worth $19.11bn"),
        ("| 8011 | Human resources services | $2.98bn | 5,830 | 108 | 962 | 138 |",
         "108 agencies, 962 suppliers, 138 needed for 80%"),
        ("| 8111 | Computer services | $5.69bn | 4,656 | 112 | 1,517 |", "112 agencies, 1,517 suppliers"),
        ("4,672 notices ($2.39bn", "4,672 segment-only notices ($2.39bn)"),
    ]
    text = part2()
    for in_cube, in_readme in pairs:
        assert in_cube in cube, in_cube
        assert in_readme in text, in_readme
