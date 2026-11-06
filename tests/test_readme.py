"""Every figure in the README (TL;DR, Parts 1-4, recommendations, limitations) must come from a generated result file."""
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
    return README.split("## Part 2", 1)[1].split("## Part 3", 1)[0]


def part3() -> str:
    return README.split("## Part 3", 1)[1].split("## Part 4", 1)[0]


def part4() -> str:
    return README.split("## Part 4", 1)[1].split("## Part 5", 1)[0]


def tldr() -> str:
    return README.split("## TL;DR", 1)[1].split("## Data", 1)[0]


def recommendations() -> str:
    return README.split("## Recommendations, ranked", 1)[1].split("## Limitations", 1)[0]


def limitations() -> str:
    return README.split("## Limitations", 1)[1].split("## Roadmap", 1)[0]


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


# Rules and thresholds quoted in Part 3, not results.
ALLOWED_3 = ALLOWED | {"400k", "7.5m", "125k", "1,000", "30k", "160k", "25k", "195k", "60k", "100k"}


def test_part3_figures_appear_in_the_results():
    comp = (ROOT / "results" / "COMPLIANCE.md").read_text()
    missing = sorted(f for f in figures(part3()) if f not in comp and f.lstrip("$") not in ALLOWED_3)
    assert not missing, f"README figures not found in results/COMPLIANCE.md: {missing}"


def test_part3_headline_phrases_are_tied_to_their_rows():
    comp = (ROOT / "results" / "COMPLIANCE.md").read_text()
    pairs = [
        ("23,860 active notices were worth $80k or more at award", "the 23,860 notices worth $80k or more at\naward"),
        ("8,687 of them (36.4%) were limited tenders, $18.73bn at award (39.4% of the value)",
         "8,687 of the 23,860 notices worth $80k or more at\naward (36.4%) were limited tenders, holding 39.4%"),
        ("Without Defence: 4,453 of 17,017 (26.2%), 25.0% of the value", "without Defence, 26.2% and 25.0%"),
        ("4,755 a 10.3 condition and 3,878 an exemption. **54 give neither**",
         "4,755 cite a 10.3 condition and 3,878 an exemption. Only 54 give neither"),
        ("All 54 have since been amended below $80k", "all 54 have since been\namended below $80k"),
        ("| exemption | AM | Paragraph 2.6 was applied in some part. | 862 | $6.63bn | $8.43bn | 12 | 95.3% |",
         "(`AM`, $6.63bn at award, 95.3% Defence)"),
        ("extensions and sole sources, 3,792 notices and $5.80bn together", "3,792 notices and $5.80bn together"),
        ("**At $80k the last $1,000 holds 345 notices, 2.31 times its neighbours**",
         "holds 345 notices, 2.31\ntimes the mean of its neighbouring bins"),
        ("At the other 13 round amounts the ratio is 0.82 to 1.52", "At the other 13 round amounts from $30k to $160k the ratio\nis 0.82 to 1.52"),
        ("across all 170 $1,000 bins from $25k to $195k", "of all 170 $1,000 bins from $25k to $195k"),
        ("That is about 196 more notices", "That is about 196 more notices than expected"),
        ("59.7% of the last $1,000 against 61.3% of its neighbours", "(59.7% against 61.3% next to them)"),
        ("**220 groups, 710 notices, $32.9m** at award, at 15 agencies", "220 groups: 710 notices and $32.9m at award at\n15 agencies"),
        ("**8,390 of 58,192 notices (14.4%) were published more than 42 days after the contract started**, $9.55bn",
         "8,390 notices (14.4%, $9.55bn) were published\nmore than 42 days after the contract started"),
        ("**51.6% of late notices (4,328 of 8,390) came out in catch-up batches**: 166 days",
         "51.6% of them came out on 166 days"),
        ("| Services Australia | 2024-09-16 | 363 | 77 | agent and access point | 360 | 2024-07-01 |",
         "on 2024-09-16, Services Australia published 363 late\nnotices, 360 of them agent and access point agreements starting 2024-07-01"),
        ("is 88 electorate office leases that started between 2004 and 2022",
         "reported 88 electorate office leases that started between 2004 and 2022"),
        ("Defence publishes 2,560 late notices", "most late notices (2,560)"),
        ("outside batches only 1.8% of its notices are late", "only 1.8% of its notices are late"),
        ("went from $48.60bn to $62.21bn (28.0% more", "$48.60bn at award to\n$62.21bn (28.0%)"),
        ("43.0% of open tenders grew (30.3% in value), against 14.9% of limited tenders under a 10.3 condition "
         "(10.3%) and 23.1% under an exemption", "43.0% of open tenders from $80k\ngrew, against 14.9% of limited "
         "tenders under a 10.3 condition and 23.1% under an exemption"),
        ("grew the most (413.1%)", "grew 413.1%"),
        ("CN4104389, Defence *Construction Services*, from $2.1m to $314.8m",
         "Defence construction contract (CN4104389) that went from $2.1m to $314.8m"),
        ("308 Veterans' Affairs notices were first published at exactly $10,000", "308 Veterans' Affairs notices\nwere published at exactly $10,000"),
        ("to $1.23bn in total", "later amended to $1.23bn"),
        ("1,814 notices were under $80k at award and are $80k or more now", "1,814 notices that were under $80k at award are now $80k or more"),
    ]
    text = part3()
    for in_report, in_readme in pairs:
        assert in_report in comp, in_report
        assert in_readme in text, in_readme


def test_part4_figures_appear_in_the_results():
    allowed = ALLOWED
    missing = sorted(f for f in figures(part4()) if f not in SOURCES and f.lstrip("$") not in allowed)
    assert not missing, f"README figures not found in results/*.md: {missing}"


def test_part4_headline_phrases_are_tied_to_their_rows():
    pairs = [
        ("**3,796 notices, $2.30bn**", "3,796 of them\n($2.30bn)"),
        ("7 vaccine notices ($1.30bn) are 99.8% of it", "7 vaccine notices make up 99.8% of the value"),
        ("All 88 notices of $1m or more were labelled (a census, 78.2% of the value)",
         "(88 notices, 78.2% of the value)"),
        ("| Program delivery, not staff training | 160 | 4.4% | $540.7m | 54.6% |",
         "| Programs delivered to the public | $540.7m | 54.6% | 160 |"),
        ("| Military and operational | 176 | 4.9% | $120.6m | 12.2% |",
         "| Military and operational training | $120.6m | 12.2% | 176 |"),
        ("| Staff development, topic known | 1,535 | 42.8% | $154.0m | 15.6% |",
         "| Staff development, topic known | $154.0m | 15.6% | 1,535 |"),
        ("| Topic unknown | 1,451 | 40.4% | $121.6m | 12.3% |", "| $121.6m | 12.3% | 1,451 |"),
        ("| Not training (miscoded) | 268 | 7.5% | $53.4m | 5.4% |", "| $53.4m | 5.4% | 268 |"),
        ("Employment program alone is 18 notices and $428.3m", "Employment program alone\nis 18 notices and $428.3m"),
        ("Foreign Military Sales account ($41.7m", "Foreign Military Sales account ($41.7m)"),
        ("41.0% in the sample (95% interval 34.4% to 47.9%)", "41.0%,\nwith a 95% interval of 34.4% to 47.9%"),
        ("| Random sample (typical notice) | 200 | 155 | 77.5% | 77.2% |", "| Random sample (200 notices) | 77.5% | 77.2% |"),
        ("| $1m+ notices (the money) | 88 | 65 | 73.9% | 87.0% |", "| $1m+ notices (88) | 73.9% | 87.0% |"),
        ("148 times out of 172 (86.0%)", "148 times out of\n172 (86.0%)"),
        ("51 of 288 labels (17.7%)", "51 of 288 labels, 17.7%"),
        ("outside knowledge, 8 of 51", "they get 8 of 51"),
        ("Of the 68 disagreements, 56 are", "of the 68 disagreements, 56 are"),
        ("For 9 of the 11 named categories, at least 85%", "for 9\nof the 11 named categories at least 85%"),
        ("leaves 2,047 notices ($178.5m) as 'unspecified', against about 1,039", "2,047 notices ($178.5m)"),
        ("2.0 times by count", "about twice the hand-label estimate\nof 1,039 by count"),
        ("about 90 calls", "about 90 calls"),
        ("staff development here at $275.6m at most", "at most $275.6m"),
        ("can't be placed at all", "40.4% of notices nobody can"),
        ("| Not training (miscoded) | 268 | 7.5% | $53.4m | 5.4% |", "and 5.4% isn't training at all"),
    ]
    for in_report, in_readme in pairs:
        assert in_report in SOURCES, in_report
        assert in_readme in part4(), in_readme
    assert "not run" in part4() and "Not run: no `ANTHROPIC_API_KEY`" in SOURCES


# ---- Part 5: the TL;DR, recommendations and limitations restate Parts 1-4 ----

def _tied(pairs, text):
    for in_report, in_readme in pairs:
        assert in_report in SOURCES, in_report
        assert in_readme in text, in_readme


def test_summary_sections_exist_and_are_not_empty():
    assert len(tldr().strip().splitlines()) == 8
    assert "Status: complete" in README
    rows = [line for line in recommendations().splitlines() if line.startswith("| ") and line[2].isdigit()]
    assert [int(r.split("|")[1]) for r in rows] == list(range(1, 9))
    assert all(r.rstrip().endswith("|") and r.split("|")[4].strip() for r in rows), "every recommendation needs an owner"


def test_summary_figures_appear_in_the_results():
    for name, text in [("TL;DR", tldr()), ("recommendations", recommendations()), ("limitations", limitations())]:
        missing = sorted(f for f in figures(text) if f not in SOURCES and f.lstrip("$") not in ALLOWED_3)
        assert not missing, f"{name} figures not found in results/*.md: {missing}"


def test_tldr_phrases_are_tied_to_their_rows():
    _tied([
        ("Summing every version gives $170.86bn, 2.6 times the $65.41bn",
         "overstates value 2.6 times ($170.86bn against $65.41bn)"),
        ("25,140 of the 34,100 (73.7%)", "three in four limited tenders (25,140 of 34,100)"),
        ("16,242, grouped by ABN", "58 of 16,242 suppliers hold half of the $62.21bn committed"),
        ("**58 of them hold half the committed value**", "58 of 16,242 suppliers hold half"),
        ("6 go beyond one contract ($4.17bn, 7.5% of large-family value)", "Only $4.17bn (7.5% of large-category value)"),
        ("12 families, $19.11bn", "12 large categories worth $19.11bn"),
        ("8,687 of them (36.4%) were limited tenders", "Only 54 of the 8,687 from $80k give none"),
        ("**54 give neither**", "Only 54 of the 8,687"),
        ("All 54 have since been amended below $80k", "all 54 were later amended below $80k"),
        ("extensions and sole sources, 3,792 notices and $5.80bn together",
         "$5.80bn of extensions and sole sources (3,792 notices)"),
        ("2.31 times its neighbours", "holds 2.31 times its neighbours (about 196 extra notices)"),
        ("That is about 196 more notices", "about 196 extra notices"),
        ("59.7% of the last $1,000 against 61.3% of its neighbours", "(59.7% against 61.3%)"),
        ("**8,390 of 58,192 notices (14.4%) were published more than 42 days after the contract started**",
         "8,390 notices (14.4%) were published more than 42 days after the contract started"),
        ("**51.6% of late notices (4,328 of 8,390) came out in catch-up batches**: 166 days",
         "51.6% of them came out on 166 batch days"),
        ("went from $48.60bn to $62.21bn (28.0% more", "grew 28.0% after award ($48.60bn to $62.21bn)"),
        ("308 Veterans' Affairs notices were first published at exactly $10,000",
         "308 Veterans' Affairs notices published at the $10,000 reporting threshold"),
        ("to $1.23bn in total", "now total $1.23bn"),
        ("| Program delivery, not staff training | 160 | 4.4% | $540.7m | 54.6% |",
         "Of its $990.2m, 54.6% is programs delivered to the public"),
        ("staff development here at $275.6m at most", "staff development is at most $275.6m"),
        ("| Topic unknown | 1,451 | 40.4% |", "40.4% of notices say too little"),
        ("| Random sample (typical notice) | 200 | 155 | 77.5% |", "77.5% of a random sample"),
        ("Not run: no `ANTHROPIC_API_KEY`", "A Claude backend is built and tested but not run"),
    ], tldr())


def test_recommendation_phrases_are_tied_to_their_rows():
    _tied([
        ("12 families, $19.11bn", "12 large categories, $19.11bn"),
        ("| 8111 | Computer services | $5.69bn | 4,656 | 112 | 1,517 |",
         "Computer services: $5.69bn, 112 agencies, 1,517 suppliers"),
        ("| 8011 | Human resources services | $2.98bn | 5,830 | 108 | 962 |", "Labour hire: 108 agencies, 962 suppliers"),
        ("extensions and sole sources, 3,792 notices and $5.80bn together", "3,792 notices, $5.80bn at award"),
        ("went from $48.60bn to $62.21bn (28.0% more", "Active notices grew 28.0% after award"),
        ("1,814 notices were under $80k at award and are $80k or more now",
         "1,814 notices under $80k at award are now $80k or more"),
        ("308 Veterans' Affairs notices were first published at exactly $10,000",
         "308 notices published at $10,000 now total $1.23bn"),
        ("to $1.23bn in total", "now total $1.23bn"),
        ("grew the most (413.1%)", "(`EU`) grew 413.1%"),
        ("**51.6% of late notices (4,328 of 8,390) came out in catch-up batches**: 166 days",
         "51.6% of late notices came out on 166 batch days"),
        ("| Services Australia | 2024-09-16 | 363 |", "Services Australia published 363 late notices on one day"),
        ("Summing every version gives $170.86bn, 2.6 times", "overstates value 2.6 times"),
        ("2,956 of 13,026 supplier ABNs", "2,956 ABNs appear under several names"),
        ("those ABNs hold 58.3% of value", "hold 58.3% of value"),
        ("1,272 notices are cancelled ($3.20bn)", "1,272 cancelled notices ($3.20bn)"),
        ("| all agencies | high | beyond one contract | 6 | $4.17bn |", "6 categories, $4.17bn"),
        ("| Topic unknown | 1,451 | 40.4% |", "40.4% of training notices"),
        ("staff development here at $275.6m at most", "at most $275.6m of the $990.2m"),
        ("outside knowledge, 8 of 51", "get 8 of 51 labels"),
        ("**At $80k the last $1,000 holds 345 notices, 2.31 times its neighbours**",
         "holds 345 notices, 2.31 times its neighbours"),
        ("**220 groups, 710 notices, $32.9m**", "220 possible split groups: 710 notices, $32.9m"),
    ], recommendations())


def test_limitation_phrases_are_tied_to_their_rows():
    _tied([
        ("4,670 notices have no ABN (4,107 of them with overseas suppliers)",
         "4,670 notices with no ABN (4,107 of them with overseas suppliers)"),
        ("41.0% in the sample (95% interval 34.4% to 47.9%)", "41.0%, with a 95% interval of 34.4% to 47.9%"),
        ("The AusTender Customised UNSPSC Codeset (1 July 2023", "AusTender codeset of 1 July 2023"),
        ("10 families in the codeset have codes under them but no family title", "10 family titles are written"),
    ], limitations())
