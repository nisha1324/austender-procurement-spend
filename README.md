# Australian Government procurement spend analytics (AusTender)

[![CI](https://github.com/nisha1324/austender-procurement-spend/actions/workflows/ci.yml/badge.svg)](https://github.com/nisha1324/austender-procurement-spend/actions/workflows/ci.yml)

> **Status: complete** (all 5 parts: source profile; spend cube; competition and compliance; categorisation; CI and this write-up). See the [recommendations](#recommendations-ranked) and [limitations](#limitations).

The Australian Government publishes a notice for every contract worth $10,000 or more on
AusTender. That makes it one of the few places where you can see how a large organisation really
buys: from whom, for what, how competitively, and how far contracts grow after they're signed.

This project analyses **one financial year of contract notices (FY2024-25)** with Python and DuckDB
SQL. It asks the questions a procurement lead, a category manager or an audit committee would ask:

1. **Spend:** where does the money go, by agency, category and supplier?
2. **Concentration:** in which categories do a few suppliers hold most of the spend?
3. **Competition and compliance:** how much is bought without an open approach, why, and are
   notices published on time?
4. **Categorisation:** many notices are coded only to a broad category. Can an LLM-assisted
   categoriser (with an offline fallback) sort them into useful spend categories?

## TL;DR

- **A dashboard built straight from the feed would mislead.** Summing every row overstates value 2.6 times ($170.86bn against $65.41bn), and three in four limited tenders (25,140 of 34,100) are under the $80k line, where an open approach isn't required. Four cheap rules fix it: latest version only, ABN as the supplier key, cancelled notices out, and the $80k line.
- **The money is concentrated, but supplier dependence isn't the main risk.** 58 of 16,242 suppliers hold half of the $62.21bn committed. Only $4.17bn (7.5% of large-category value) sits in categories concentrated beyond one contract.
- **Fragmentation is the bigger lever.** 12 large categories worth $19.11bn, such as computer services, management advice and labour hire, are bought by 20 or more agencies from long supplier tails.
- **Limited tenders almost always cite an allowed reason.** Only 54 of the 8,687 from $80k give none, and all 54 were later amended below $80k. The money to check is the $5.80bn of extensions and sole sources (3,792 notices).
- **Values bunch just under $80k, but not to avoid competition.** The last $1,000 before the line holds 2.31 times its neighbours (about 196 extra notices), and those notices aren't more often limited tenders (59.7% against 61.3%).
- **Late reporting is mostly catch-up batches.** 8,390 notices (14.4%) were published more than 42 days after the contract started, and 51.6% of them came out on 166 batch days, led by annual agreements that start on 1 July.
- **Award values understate what's committed.** Active notices grew 28.0% after award ($48.60bn to $62.21bn), and 308 Veterans' Affairs notices published at the $10,000 reporting threshold now total $1.23bn.
- **"Education and Training" is mostly not staff training.** Of its $990.2m, 54.6% is programs delivered to the public, staff development is at most $275.6m, and 40.4% of notices say too little for anyone to place. Keyword rules match the hand labels on 77.5% of a random sample. A Claude backend is built and tested but not run, as no API key is set up.

## Data

| | |
|---|---|
| Dataset | [AusTender OCDS API](https://github.com/austender/austender-ocds-api), `findByDates/contractPublished` |
| Publisher | Australian Government Department of Finance |
| Licence | [CC BY 3.0 AU](https://creativecommons.org/licenses/by/3.0/au/), stated in every API response. Contains AusTender data © Commonwealth of Australia. |
| Scope | Contract notices first published 1 Jul 2024 to 30 Jun 2025 (Canberra time), with every amendment published up to the download date |
| In this repo | `data/releases.csv.gz`: one row per notice version, flattened by `scripts/build_snapshot.py`. `data/SNAPSHOT.json` records the counts, download dates and SHA-256. |

No key or sign-up is needed. `scripts/download_data.py` asks the API for one Canberra day at a
time, follows its cursor pages and saves each day to `data/raw/` (not committed). Officer names,
email addresses, phone numbers and street addresses are left out of the snapshot; they aren't
needed for spend analysis.

Supplier names in the data include some sole traders. This project reports on agencies,
categories and the largest suppliers, all published by the government for transparency, and
doesn't single out individuals.

## Part 1: what the data can and can't tell us

Full results: [`results/SOURCE_PROFILE.md`](results/SOURCE_PROFILE.md) (generated; every figure comes
from the snapshot) and [`results/AMENDMENT_CHECK.md`](results/AMENDMENT_CHECK.md).

The snapshot holds **59,464 contract notices** first published in FY2024-25 and **22,513
amendments** to them, published up to 4 Nov 2026. Before asking what the government buys, this part
checks what the data means. Several plausible readings turn out to be wrong:

| Trap | What the data shows | Rule from here on |
|---|---|---|
| **Adding up every row** | An amendment's value is the contract's *new total*, not the change. The API doesn't say so; it was settled by matching two amendments of a Defence contract against the government's older bulk export, where the step between versions equals the published change to the cent. Summing every row gives $170.86bn, 2.6 times the $65.41bn from each notice's latest version. | One row per notice, its latest version. |
| **Sorting amendments as text** | Up to 36 amendments on one notice, and every amendment points back at the original notice rather than the one before it. As text, A10 sorts before A9. | Order by amendment number, as a number. |
| **Value at award = value now** | $51.86bn when first published, $65.41bn after amendments (26.1% more), and still rising: amendments to these notices were still being published in Nov 2026. | Say which value a figure uses; judge thresholds on the value at award. |
| **"57.3% limited tenders" as a red flag** | 25,140 of the 34,100 limited tenders (73.7%) were under $80k at award, where an open approach isn't required. | Judge limited tenders from $80k up, by their reason or exemption code. |
| **Grouping suppliers by name** | 2,956 of 13,026 supplier ABNs appear under more than one name (one under 52); those ABNs hold 58.3% of value. | Group by ABN (or the API's supplier id where there's no ABN). |
| **Counting cancelled notices** | 1,272 notices are cancelled ($3.20bn). Some come back under a new number, including a $2.34bn Home Affairs contract published twice, the first copy since cancelled. | Leave cancelled notices out of spend. |
| **Comparing fine-grained categories** | 57.4% of notices (60.3% of value) are coded only to a broad UNSPSC segment or family. | Compare at family level, or recategorise (Part 4). |

![Share of notices and of value by value band](results/charts/01_value_bands.png)

Other things worth knowing before building on this data:

- **The money is concentrated.** The top 1% of notices (595) hold 68.6% of value and the 84
  notices of $100m and over hold 45.6%, while 56.4% of notices are under $80k and hold 1.6%.
  Defence alone holds 41.8%. Every later result is shown with counts and medians as well as totals.
- **Amendment dates come in batches.** On the busiest day, 8 May 2025, 766 amendments were
  published, 95.0% from Defence, so an amendment's publish date isn't the date it was agreed.
- **The API carries less than the AusTender website.** There's no panel, consultancy or
  confidentiality flag, amendments almost never change the dates (so term extensions can't be
  seen), and agency branch and division sit on the supplier record next to the officer's
  contact details. The snapshot keeps branch and division and drops the personal details.
- **Late publication is common.** The rules ask for a contract to be reported within 42 days of
  entering into it. The API has no signing date, so the start date stands in:
  8,737 notices (14.7%) were published more than 42 days after it. Part 3 finds that half the late notices
  come in catch-up batches.

![Value at first publication and after amendments, by month](results/charts/02_award_vs_current.png)

**So what for the business?** Anyone building a procurement dashboard straight from this feed
would overstate spend about 2.6 times, flag three in four limited tenders as a compliance
problem although they're under the $80k line where an open approach isn't required, and split major suppliers into dozens of names. The fixes are cheap (latest version only, ABN as
the supplier key, cancelled notices out, the $80k line), but they have to be decided before the
first chart, which is what this part does. Two questions stay open for the agencies themselves:
why so many contracts grow after award, and why one notice in seven is published late.

## Part 2: where the money goes, and who it goes to

Full results: [`results/SPEND_CUBE.md`](results/SPEND_CUBE.md) (generated), plus BI-ready CSVs in
[`results/`](results/): the agency × category cube, concentration by category, suppliers and agencies.

Category names come from the government's own **AusTender Customised UNSPSC Codeset** (data.gov.au,
CC BY 3.0 AU), which every one of the 537 codes on these notices matches. Following Part 1's rules,
this part counts the **58,192 active notices**, each at its latest value: **$62.21bn of committed
contract value** ($48.60bn at award). Committed value is what contracts are worth over their life,
not what was paid this year.

**Where it goes.** Services take 75.9% of the money. One segment, *Management and Business
Professionals and Administrative Services*, holds 26.8% on its own. Defence holds 43.5% of all
value and 86.1% of building and construction ($9.75bn), so every concentration result is shown with
and without Defence.

![Committed value by UNSPSC segment, Defence and other agencies](results/charts/03_spend_by_segment.png)

**Who it goes to.** 16,242 suppliers, but **58 of them hold half the committed value** and 391
hold 80%. At the other end, 10,103 suppliers (62.2%) won exactly one notice. Big totals are often
a single contract: Ventia, the largest supplier ($3.44bn), has 98.5% of it in one notice.

**Is any category dependent on one supplier?** For each of the 42 large categories (UNSPSC
families of $100m or more with at least 20 notices; 89.7% of value), the analysis measures the top
supplier's share and the Herfindahl-Hirschman Index (HHI). One year of notices is lumpy, so each
category is measured again **without its single largest notice**. That separates "one big
contract" from concentration that goes beyond it:

| Large categories, all agencies | Categories | Committed value |
|---|---:|---:|
| Low concentration (HHI under 1,500) | 25 | $31.41bn |
| Moderate (1,500 to 2,500) | 7 | $17.47bn |
| High, but only because of one contract | 4 | $2.73bn |
| High beyond one contract | 6 | $4.17bn |

![Top supplier share and its single largest notice in the 20 largest categories](results/charts/04_family_concentration.png)

Only $4.17bn (7.5% of large-category value) sits in categories concentrated beyond one contract.
They are fuels (one supplier, 81.9% from 28 notices), advertising (one supplier, 69.1% from 284
notices), insurance (Comcare, the government's workers' compensation insurer, 42.7%), light weapons
and ammunition, and two categories led by one Defence electronics supplier (CEA Technologies: 79.6%
and 62.7%). Without Defence, 11 of 29 large categories are highly concentrated,
6 of them because of one contract (e.g. a $2.34bn Home Affairs detention services contract, 60.6%
of non-Defence business administration).

**The opposite pattern is bigger.** 12 large categories worth $19.11bn are bought by 20 or more
agencies from a long tail of suppliers, where it takes 30 or more suppliers to reach 80% of the
value. Human resources services (labour hire): 108 agencies, 962 suppliers, 138 needed for 80%.
Computer services: 112 agencies, 1,517 suppliers.

**So what for the business?** For a procurement lead, the headline isn't supplier dependence.
The concentrated categories are few, small and mostly explainable (one large contract, a statutory
insurer, or what looks like a central arrangement), so the job there is to confirm each one is
deliberate and to manage the big contracts well. The larger lever is fragmentation: $19.11bn of
common services, such as labour hire and IT, bought separately by dozens of agencies from hundreds of
suppliers. That is where pooled demand and whole-of-government panels pay off. The API has no
panel flag, so the first step is to check how much of it already goes through panels. Two more
lessons for anyone building a spend dashboard: measure concentration with and without the largest
contract, or one award will look like a monopoly; and keep the 4,672 segment-only notices ($2.39bn)
visible rather than dropping them, since Part 4 tries to place them.

## Part 3: competition and compliance

Full results: [`results/COMPLIANCE.md`](results/COMPLIANCE.md) (generated), plus review lists in
[`results/`](results/): limited tenders and late publication by agency, and the 200 contracts that grew most.

The rules are the Commonwealth Procurement Rules of 1 July 2024. From $80k (GST inclusive; $400k
for prescribed corporate entities, $7.5m for construction) an agency has to approach the open market
unless a paragraph 10.3 condition or an Appendix A exemption applies, and every contract of $10k or more has
to be reported within 42 days of entering into it. The API has no expected value, signing date or entity
type, so the value at award, the contract start date and the $80k line stand in for them. The same
58,192 active notices as Part 2.

**Limited tenders almost always give a reason.** 8,687 of the 23,860 notices worth $80k or more at
award (36.4%) were limited tenders, holding 39.4% of that value; without Defence, 26.2% and 25.0%.
4,755 cite a 10.3 condition and 3,878 an exemption. Only 54 give neither, and all 54 have since been
amended below $80k, which looks like a value keyed wrongly at award. The biggest routes are Defence's
own exemption (`AM`, $6.63bn at award, 95.3% Defence), then extensions with the original supplier
(`AD`) and sole sources for technical reasons (`TR`): 3,792 notices and $5.80bn together.

**Values pile up just under $80k.** The last $1,000 before the threshold holds 345 notices, 2.31
times the mean of its neighbouring bins. At the other 13 round amounts from $30k to $160k the ratio
is 0.82 to 1.52, and of all 170 $1,000 bins from $25k to $195k (leaving out whole-thousand values),
the one under $80k is furthest above its neighbours. That is about 196 more notices than expected.
But the extra notices aren't more often limited tenders (59.7% against 61.3% next to them), so the
data doesn't show the threshold being dodged to avoid competition. Budgets and approval limits set at
$80k would give the same pattern.

![Notices by value at award, $60k to $100k](results/charts/05_threshold_bunching.png)

A check for split purchases (limited tenders under $80k to one supplier, same description and start,
published within 30 days, $80k or more together) finds 220 groups: 710 notices and $32.9m at award at
15 agencies. Most will have ordinary explanations, so it's a sample list for internal audit, not a finding.

**Late reporting is mostly a few catch-up batches.** 8,390 notices (14.4%, $9.55bn) were published
more than 42 days after the contract started. 51.6% of them came out on 166 days when one agency
published 10 or more late notices. The largest: on 2024-09-16, Services Australia published 363 late
notices, 360 of them agent and access point agreements starting 2024-07-01; Veterans' Affairs
published its 1 July hospital, day procedure and community nursing agreements in December; Finance
reported 88 electorate office leases that started between 2004 and 2022 in one day. Defence has the
most late notices (2,560), but outside its batches only 1.8% of its notices are late.

![Late publication by agency](results/charts/06_late_by_agency.png)

**Value at award understates what's committed.** Active notices grew from $48.60bn at award to
$62.21bn (28.0%), and open tenders grow more often than limited ones: 43.0% of open tenders from $80k
grew, against 14.9% of limited tenders under a 10.3 condition and 23.1% under an exemption. The
outliers are the ones to explain. Contracts let for extreme urgency (`EU`) grew 413.1%, mostly through one
Defence construction contract (CN4104389) that went from $2.1m to $314.8m. 308 Veterans' Affairs notices
were published at exactly $10,000, the reporting threshold, and later amended to $1.23bn. In all,
1,814 notices that were under $80k at award are now $80k or more.

**So what for the business?** The compliance basics hold up: above the line, almost every limited
tender cites an allowed reason, so the work is checking that the reason fits, starting with the $5.80bn
of extensions and sole sources, where the most money rides on whether the market was tested. Bunching under $80k is
real but small and not tied to avoiding competition. It points to budgets or delegations set at the
threshold, which is worth a look now that the line has moved to $125k (from 17 Nov 2025). Late
reporting is mostly a process problem: half of all late notices come in catch-up batches, and the
largest batches are annual agreements that start on 1 July and are signed or reported months
later. Moving those renewals earlier in a few agencies is the biggest single fix. And because award values can be placeholders, a transparency
dashboard should track current value and flag contracts that grew past a threshold or more than
tenfold, not just the value at award.

## Part 4: what "Education and Training" buys, and can a categoriser tell?

Full results: [`results/CATEGORISER.md`](results/CATEGORISER.md) (generated), plus
[`results/training_categories.csv`](results/training_categories.csv) (every notice with its label and the
rule that fired) and [`results/training_category_mix.csv`](results/training_category_mix.csv).

**Why training.** 4,672 active notices ($2.39bn) are coded only to a UNSPSC segment. 3,796 of them
($2.30bn) sit in segments where the AusTender codeset has no family-level code at all, so this isn't
lazy coding: an agency buying a course can only pick *Education and Training Services*. In drugs and
pharmaceuticals, 7 vaccine notices make up 99.8% of the value and say what they are. That leaves
Education and Training: **3,589 notices, $990.2m**, many described only as "Training Services".

**Method.** A 12-category taxonomy built around a category manager's questions: is this staff
development, operational training, a program delivered to the public, or not training at all? A check
set of 288 notices, every notice of $1m or more (88 notices, 78.2% of the value) plus 200 at random from
the rest, was labelled by hand from the description, supplier and agency, following a written
[labelling guide](data/check_set/LABELLING_GUIDE.md). The labels were committed before any rules were
written. Each label also records what it rests on: the description, the supplier's name, outside
knowledge of the supplier, or nothing.

**What the money buys** (hand labels; notices under $1m are estimated from the random sample):

| Group | Value | Share of value | Notices (est.) |
|---|---:|---:|---:|
| Programs delivered to the public | $540.7m | 54.6% | 160 |
| Military and operational training | $120.6m | 12.2% | 176 |
| Staff development, topic known | $154.0m | 15.6% | 1,535 |
| Topic unknown (university/TAFE or unknown firm, generic description) | $121.6m | 12.3% | 1,451 |
| Not training (catering, venues, school fees, care services, consulting) | $53.4m | 5.4% | 268 |

![What Education and Training spend buys](results/charts/07_training_mix.png)

Over half the value isn't training staff at all. The Skills for Education and Employment program alone
is 18 notices and $428.3m. Military and operational training is mostly a few large contracts, led by
what appears to be the US Foreign Military Sales account ($41.7m). Staff development with a known topic
is about $154.0m, spread across about 1,535 notices. A further $121.6m, in about 1,451 notices (40.4%),
can't be placed by anyone reading the notice: the share of small notices with no known topic is 41.0%,
with a 95% interval of 34.4% to 47.9%.

**Can a categoriser do it?** `scripts/categorise.py` applies ordered keyword rules to the description
and supplier name and records which rule fired. It was scored once against the check set, and the rules
weren't changed after seeing the score:

| Check set | Accuracy | Accuracy by value |
|---|---:|---:|
| Random sample (200 notices) | 77.5% | 77.2% |
| $1m+ notices (88) | 73.9% | 87.0% |

![Baseline accuracy by what the label rests on](results/charts/08_baseline_by_basis.png)

Where the notice's own words name the category, the rules agree with the hand label 148 times out of
172 (86.0%). Where the label needs outside knowledge (51 of 288 labels, 17.7%: what SANS, Cubic or
QinetiQ sell, or that *Be Connected* is a program for older Australians), they get 8 of 51. The rules
are cautious rather than wrong: of the 68 disagreements, 56 are a fall-back to "unspecified", and for 9
of the 11 named categories at least 85% of the rules' labels agree with the hand label. Run on every
notice, the rules leave 2,047 notices ($178.5m) as "unspecified", about twice the hand-label estimate
of 1,039 by count.

**The Claude backend** sends the same taxonomy and decision order as a prompt, forces a tool call
with the category as an enum, and falls back to the rules on any invalid answer. It is built and tested
with a fake client but **not run: no API key is set up**, so no LLM score is published. One run over
all notices is about 90 calls. The check set says where it could help: the 51 labels that rest on
outside knowledge.

**So what for the business?** Don't benchmark "training spend" from this code. More than half of it
is program delivery that belongs with the policy program it funds, and 5.4% isn't training at all.
Agencies' staff development is at most $275.6m (the $154.0m with a known topic plus the $121.6m
that can't be placed), not $990.2m. The bigger fix is upstream: for 40.4% of notices nobody can
tell what the training was, and no categoriser can recover what was never published. A short
description standard for training notices (topic, audience, format), or finer training codes in the
codeset, would cost agencies a few words per notice. Until then, the keyword rules are a cheap,
explainable first pass: trust the categories they name and send the "unspecified" remainder to an LLM
or a person.

## Part 5: CI on every push

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs on every push and pull request:

1. Installs the exact package versions from [`requirements-lock.txt`](requirements-lock.txt), the ones the committed outputs were made with.
2. Reruns all 4 reports offline from the committed snapshot, and fails if any report, CSV or chart changes by a single byte. It makes no API calls, so it never downloads data or spends money.
3. Runs `pytest`, including the check that every figure in the [TL;DR](#tldr), the [recommendations](#recommendations-ranked) and Parts 1 to 4 still appears in a generated report. Only the raw codeset test skips, because `data/raw/` isn't in the repo.

**So what for the business:** a figure in this README can't drift away from the code that produced it
without the badge turning red, so a procurement lead or auditor can quote it without rerunning anything.

## Recommendations, ranked

For the Department of Finance (which runs AusTender and whole-of-government procurement), agency chief
procurement officers, internal audit and anyone building spend reporting on this feed. Ranked by the
committed value a fix touches and how directly the evidence points at it. Every figure is from Parts 1 to 4.

| # | Recommendation | Evidence | Owner |
|---|---|---|---|
| 1 | **Check how much of the fragmented common spend already goes through panels, then pool the rest.** Start with computer services and labour hire. | 12 large categories, $19.11bn, bought by 20 or more agencies from long supplier tails. Computer services: $5.69bn, 112 agencies, 1,517 suppliers. Labour hire: 108 agencies, 962 suppliers. The API has no panel flag. | Finance (whole-of-government procurement), category managers |
| 2 | **Test whether the stated reason fits for extensions and sole sources.** | Almost every limited tender from $80k cites an allowed reason, so the question is whether it fits. Extensions (`AD`) and sole sources for technical reasons (`TR`): 3,792 notices, $5.80bn at award. | Internal audit, agency chief procurement officers |
| 3 | **Report and approve on current value, and flag contracts that grow past a threshold or tenfold.** | Active notices grew 28.0% after award. 1,814 notices under $80k at award are now $80k or more. 308 notices published at $10,000 now total $1.23bn. Contracts let for extreme urgency (`EU`) grew 413.1%. | Agency CFOs, Finance (AusTender reporting) |
| 4 | **Sign and report 1 July renewals before they start,** beginning with the agencies behind the largest catch-up batches. | 51.6% of late notices came out on 166 batch days. Services Australia published 363 late notices on one day; Veterans' Affairs published its 1 July hospital and nursing agreements in December. | Procurement teams at Services Australia, Veterans' Affairs and Finance |
| 5 | **Build any spend dashboard on this feed with the four data rules:** latest version only, ABN as the supplier key, cancelled notices out, and limited tenders judged from $80k. | Summing every row overstates value 2.6 times. 2,956 ABNs appear under several names and hold 58.3% of value. 1,272 cancelled notices ($3.20bn). | Procurement analytics and BI teams |
| 6 | **Confirm each concentrated category is deliberate, and manage its large contracts closely.** | 6 categories, $4.17bn, are concentrated beyond one contract: fuels, advertising, insurance (Comcare), light weapons and ammunition, and two led by CEA Technologies. | Category managers |
| 7 | **Ask for a short description standard for training notices (topic, audience, format), or finer training codes.** | 40.4% of training notices can't be placed by anyone reading them, so staff development is at most $275.6m of the $990.2m. The keyword rules get 8 of 51 labels that need outside knowledge. | Finance (owner of AusTender and its codeset) |
| 8 | **Review budgets and delegations set at $80k now that the line is $125k, and use the split-purchase list as an audit sample.** | The last $1,000 before $80k holds 345 notices, 2.31 times its neighbours, but they aren't more often limited tenders. 220 possible split groups: 710 notices, $32.9m. | Internal audit, finance teams that set delegations |

**Data to ask for first,** because each one turns a stand-in here into a fact: the signing date and
expected value of each contract, which agencies are prescribed corporate entities, a panel (standing
offer) flag, payments actually made against each contract, and a topic for each training notice.

## Limitations

- **Committed value, not money paid.** A notice records what a contract is worth over its life, so nothing here is spend in one year, and there are no payment records to check it against.
- **One year of notices, still changing.** These are notices first published in FY2024-25, with amendments up to 4 Nov 2026. Later amendments will move current values. One year is also lumpy, which is why each category's concentration is measured again without its largest notice.
- **Stand-ins for missing fields.** The API has no signing date, expected value or entity type. The start date, the value at award and the $80k line stand in for them, so prescribed corporate entities ($400k line) and construction ($7.5m line) are judged too strictly.
- **No panel, consultancy or confidentiality flags,** so fragmented spend can't be netted of panel use, and consultancy spend can't be measured.
- **Suppliers are grouped by ABN.** Related companies with different ABNs count separately, and the 4,670 notices with no ABN (4,107 of them with overseas suppliers) use the API's supplier id.
- **Patterns, not findings.** Bunching, possible split purchases, late batches and contract growth show where to look. Each needs the agency's own file to explain it.
- **The training labels are one person's reading.** Estimates for notices under $1m rest on a random sample of 200: the share with no known topic is 41.0%, with a 95% interval of 34.4% to 47.9%.
- **No LLM score.** The Claude backend is tested with a fake client only, until an API key is set up.
- **Category names come from the AusTender codeset of 1 July 2023.** All 537 codes in use match it; 10 family titles are written from the codes under them and marked as such.

Each report's own Limits section has the full detail.

## Roadmap

- [x] **Part 1: source and profile.** Download, snapshot, the traps in the data and the rules they set.
- [x] **Part 2: spend cube.** Category names from the AusTender UNSPSC codeset, spend by agency, category and supplier, supplier concentration by category (with and without Defence, and without the largest contract), and a BI-ready cube.
- [x] **Part 3: competition and compliance.** Limited tenders from $80k by reason and agency, value bunching under thresholds, possible split purchases, late publication and catch-up batches, and growth after award.
- [x] **Part 4: LLM-assisted categoriser.** A training spend taxonomy, a 288-notice hand-labelled check set, an explainable keyword baseline scored against it, and a Claude backend (built and tested; needs a key to run).
- [x] **Part 5: write-up.** CI on every push, TL;DR, ranked recommendations, limitations.

## How to run

```bash
python -m venv .venv && source .venv/bin/activate   # or: uv venv
pip install -r requirements-lock.txt

# Optional: rebuild the snapshot from the API (about 1,300 requests; ~15 minutes)
python -m scripts.download_data --fy 2024
python -m scripts.build_snapshot

python -m scripts.check_amendment_values   # live API cross-check (network)
python -m scripts.profile_releases         # Part 1 report and charts, offline
python -m scripts.build_categories         # optional: rebuild the UNSPSC lookup (downloads 80 KB)
python -m scripts.spend_cube               # Part 2 report, charts and CSVs, offline
python -m scripts.compliance               # Part 3 report, charts and CSVs, offline
python -m scripts.categorise               # Part 4 report, charts and CSVs, offline (keyword baseline)
pytest

# Optional: the Claude backend for Part 4 (paid API; nothing runs without a key)
pip install anthropic && cp .env.example .env   # then put your key in .env
python -m scripts.categorise --backend claude
```

## Tests

112 tests. The SQL behind every part runs on small hand-written notices with answers worked out by
hand, including amendments numbered past A9, cancelled copies, placeholder values and catch-up batches.
The downloader is tested against fake API answers, including its two quirks (an empty day answers
HTTP 400, and notices at exactly midnight come back twice). The categoriser's rules, prompt and fake
Claude client are tested without network or a key. The committed snapshot must match its manifest,
every report and CSV must match a fresh run, and every figure in this README must appear in a
generated report, with the headline phrases tied to their exact report rows. To check that the tests
can fail, 97 errors were planted one at a time in the code and in this README, such as `= 10000` turned
into `<= 10000` in the placeholder check, or a mistyped figure in the TL;DR. 93 were caught straight away; the
other 4 got new tests and are now caught too.

## Project structure

```
data/            releases.csv.gz (the snapshot), SNAPSHOT.json, unspsc_categories.csv; raw/ is not committed
data/check_set/  training_labels.csv (288 hand-labelled notices) and LABELLING_GUIDE.md
scripts/         download_data.py, build_snapshot.py, check_amendment_values.py, profile_releases.py,
                 build_categories.py, spend_cube.py, compliance.py, training_taxonomy.py,
                 draw_check_set.py, categorise.py (baseline + Claude backend), categoriser_report.py
sql/             00_load.sql (typed views), profile.sql (Part 1), 01_spend.sql + spend.sql (Part 2),
                 02_compliance.sql + compliance.sql (Part 3), 03_training.sql (Part 4)
results/         SOURCE_PROFILE.md, AMENDMENT_CHECK.md, SPEND_CUBE.md, COMPLIANCE.md, CATEGORISER.md, CSVs, charts/
tests/           unit tests on hand-written releases, plus checks on the committed snapshot and this README
.github/         CI: rerun every report and the tests on each push
```
