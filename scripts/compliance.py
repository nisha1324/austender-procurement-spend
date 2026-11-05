"""Part 3: competition and compliance. Writes `results/COMPLIANCE.md`, two charts and CSVs.

    python -m scripts.compliance
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from scripts.profile_releases import (  # noqa: E402
    BLUE, CHARTS, INK, INK_2, MUTED, ORANGE, RESULTS, SNAPSHOT, SQL_DIR, SURFACE,
    _style, money, n, pct, run_all, table,
)
from scripts.spend_cube import CATEGORIES, _head, no_math, share, spend_connection, wrap  # noqa: E402

SOURCE_NOTE = "Source: AusTender OCDS API (Department of Finance), CC BY 3.0 AU."


def compliance_connection(releases_csv: Path | None = None, categories_csv: Path = CATEGORIES):
    con = spend_connection(releases_csv, categories_csv)
    con.execute((SQL_DIR / "02_compliance.sql").read_text())
    return con


def results(con=None) -> dict[str, pd.DataFrame]:
    return run_all(con or compliance_connection(), SQL_DIR / "compliance.sql")


def x(v, dp: int = 1) -> str:
    return f"{float(v):.{dp}f}"


# ---------- charts ----------
def chart_bunching(bins: pd.DataFrame, ratio: float, out: Path) -> None:
    b = bins.copy()
    labels = [f"{int(v) // 1000}" for v in b.bin]
    is_last = b.bin == 79000
    fig, ax = plt.subplots(figsize=(9.5, 5.3), dpi=150, facecolor=SURFACE)
    _style(ax)
    ax.grid(axis="x", visible=False)
    ax.grid(axis="y", color="#e6e5e1", linewidth=0.8)
    xs = list(range(len(b)))
    ax.bar([i for i, m in zip(xs, is_last) if not m], b.notices[~is_last], width=0.8, color=BLUE,
           label=no_math("Notices per $1,000 of value at award"))
    ax.bar([i for i, m in zip(xs, is_last) if m], b.notices[is_last], width=0.8, color=ORANGE,
           label=no_math("The last $1,000 before the $80k threshold"))
    i79 = xs[int(is_last.values.argmax())]
    ax.axvline(i79 + 0.5, color=INK_2, linewidth=1, linestyle=(0, (3, 3)))
    ax.text(i79 + 0.7, b.notices.max() * 0.97, no_math("$80k: an open approach is required from here"),
            fontsize=8.3, color=INK_2, va="top")
    ax.text(i79 - 0.7, int(b.notices[is_last].iloc[0]) - 4, f"{ratio:.1f}x its\nneighbours", ha="right",
            va="top", fontsize=8.3, color=INK)
    ax.set_xticks(xs[::5], labels[::5], fontsize=8.5, color=INK_2)
    ax.set_xlim(-0.7, len(b) - 0.3)
    ax.set_ylim(0, b.notices.max() * 1.12)
    ax.set_xlabel(no_math("Value at award, $ thousand (each bar is a $1,000 bin, GST inclusive)"),
                  color=INK_2, fontsize=9)
    ax.set_ylabel("Active notices", color=INK_2, fontsize=9)
    fig.text(0.01, 0.036, no_math("Spikes at whole amounts ($60k, $70k, $75k, $80k) are round-number pricing and "
             "$62k is one agency's standard fee. Of all $1,000 bins from $25k to $195k, $79k"), fontsize=7, color=MUTED)
    fig.text(0.01, 0.019, "is the furthest above its neighbours. Active FY2024-25 notices. " + SOURCE_NOTE,
             fontsize=7, color=MUTED)
    _head(fig, ax, no_math("Contract values pile up just under the $80k open-approach threshold"), 0.93)
    fig.tight_layout(rect=(0, 0.05, 1, 0.93))
    fig.savefig(out, facecolor=SURFACE)
    plt.close(fig)


def chart_late(late: pd.DataFrame, out: Path, top: int = 14) -> None:
    d = late.head(top)
    batch = 100 * d.late_in_batches / d.notices
    other = 100 * d.late_share_outside_batches.astype(float)
    labels = [wrap(a, 44) for a in d.agency]
    fig, ax = plt.subplots(figsize=(9.5, 6.6), dpi=150, facecolor=SURFACE)
    _style(ax)
    y = list(range(len(d)))
    ax.barh(y, other, height=0.66, color=BLUE, label="Other late notices")
    ax.barh(y, batch, left=other + 0.15, height=0.66, color=ORANGE,
            label="Late notices published in a batch (10+ late on one day)")
    for i, (a, b) in enumerate(zip(other, batch)):
        ax.text(a + b + 0.5, i, f"{a + b:.1f}%", va="center", fontsize=8.3, color=INK_2)
    ax.set_yticks(y, labels, color=INK, fontsize=8.3)
    ax.invert_yaxis()
    ax.set_xlim(0, float((other + batch).max()) * 1.12)
    ax.set_xlabel("Share of the agency's notices published more than 42 days after the contract start (%)",
                  color=INK_2, fontsize=9)
    fig.text(0.01, 0.022, "Agencies with 300+ active FY2024-25 notices, the 14 with the highest share. The API has "
             "no signing date, so the start date stands in for it.", fontsize=7, color=MUTED)
    fig.text(0.01, 0.006, SOURCE_NOTE, fontsize=7, color=MUTED)
    _head(fig, ax, "Most late reporting comes in catch-up batches from a few agencies", 0.93)
    fig.savefig(out, facecolor=SURFACE)
    plt.close(fig)


# ---------- report ----------
def write_report(r: dict[str, pd.DataFrame], snap: dict) -> str:
    t = r["totals"].iloc[0]
    routes = r["routes"].set_index("route")
    codes = r["limited_codes"]
    ag = r["limited_by_agency"]
    bp = r["bunching_points"]
    b80 = bp[bp.amount == 80000].iloc[0]
    others = bp[bp.amount != 80000]
    rel = r["bunching_relative"]
    rel88 = rel.set_index("amount").loc[88000]
    rel75 = rel.set_index("amount").loc[7500000]
    scan = r["bunching_scan"]
    assert scan.bin.iloc[0] == 79000, "the $79k bin is no longer the largest spike; rewrite section 2"
    second = scan.iloc[1]
    bd = r["bunching_detail"].iloc[0]
    ss = r["split_summary"].iloc[0]
    lt = r["late_totals"].iloc[0]
    lb = r["late_batches"].iloc[0]
    la = r["late_by_agency"]
    gt = r["growth_totals"].iloc[0]
    gr = r["growth_by_route"].set_index("route")
    top = r["growth_top"]
    ph = r["placeholders"]
    dva = ph.iloc[0]
    ct = r["crossed_threshold"].set_index("method")
    as_of = snap["fetched_to"][:10]

    cond, exem = routes.loc["3. Limited: a 10.3 condition"], routes.loc["4. Limited: an exemption"]
    nocode = routes.loc["5. Limited: no reason or exemption code"]
    excess = float(b80.last_1k) - float(b80.neighbour_mean)
    defence = ag[ag.agency == "Department of Defence"].iloc[0]
    eu = r["growth_by_code"].set_index("code").loc["EU"]
    eu_top = top[top.route.str.startswith("3.")].iloc[0]
    vm = r["growth_by_code"].set_index("code").loc["VM"]
    def_late = la[la.agency == "Department of Defence"].iloc[0]
    batches = r["late_top_batches"]
    fin = batches[batches.agency == "Department of Finance"].iloc[0]
    top_b = batches.iloc[0]
    assert top_b.main_start == "2024-07-01" and batches.iloc[1:4].main_start.eq("2024-07-01").all(), \
        "the largest batches no longer start on 1 July; reword section 3"
    mix = r["placeholder_mix"]
    home_care = int(mix[mix.description.str.contains("home care")].notices.sum())
    assert home_care == dva.notices - mix.notices.iloc[0], "placeholder mix changed; reword section 4"
    ct_total = int(ct.notices.sum())
    ct_from_10k = int(ct.from_10000.sum())

    L = [
        "# Competition and compliance",
        "",
        "Generated by `scripts/compliance.py` from `sql/02_compliance.sql` and `sql/compliance.sql`. Every",
        "number below is computed from `data/releases.csv.gz`.",
        "",
        "## Scope and rules",
        "",
        "| | |",
        "|---|---|",
        f"| Notices | {n(t.notices)} active notices first published in FY2024-25, as in Part 2 |",
        "| Rules | The Commonwealth Procurement Rules (CPRs) of 1 July 2024, in force for the whole year. From "
        "$80,000 (non-corporate entities; $400,000 for prescribed corporate entities, $7.5 million for "
        "construction), GST inclusive, an open approach is needed unless a paragraph 10.3 condition or an "
        "Appendix A exemption applies. The $80,000 line rose to $125,000 on 17 November 2025, after this year. |",
        "| Threshold value | The CPRs judge the threshold on the *expected* value. The API doesn't carry it, so "
        "the value at award (each notice's first version) stands in for it. |",
        "| Entity type | The API doesn't say which agencies are corporate entities, so the $80,000 line is applied "
        "to all of them. For a corporate entity it may be the wrong line. |",
        "| Late publication | The CPRs ask for a contract to be reported within 42 days of entering into it. "
        "The API has no signing date (its `dateSigned` is the publish date), so the lag is measured from the "
        "contract start date. A contract signed after it started looks late here even if it was reported on "
        f"time. All {n(lt.with_start)} active notices have a usable start date (the 1900 placeholders are all "
        "on cancelled notices). |",
        f"| Values | Thresholds use the value at award; spend and growth use the latest value as of {as_of}. |",
        "",
        "## 1. Limited tenders from $80k",
        "",
        f"{n(t.notices_80k)} active notices were worth $80k or more at award ({money(t.award_value_80k)}). "
        f"{n(t.limited_80k)} of them ({pct(t.limited_80k, t.notices_80k)}) were limited tenders, "
        f"{money(t.limited_award_value_80k)} at award ({pct(t.limited_award_value_80k, t.award_value_80k)} of the "
        f"value). Without Defence: {n(t.limited_80k_ex_defence)} of {n(t.notices_80k_ex_defence)} "
        f"({pct(t.limited_80k_ex_defence, t.notices_80k_ex_defence)}), "
        f"{pct(t.limited_award_value_80k_ex_defence, t.award_value_80k_ex_defence)} of the value. Below $80k, "
        f"{n(t.limited_under_80k)} of {n(t.notices_under_80k)} notices are limited tenders, which the rules allow.",
        "",
        table(r["routes"], money_cols=("award_value", "current_value", "award_value_ex_defence"),
              pct_cols=("notice_share", "award_value_share"), int_cols=("notices", "notices_ex_defence")),
        "",
        f"- Almost every limited tender from $80k gives a reason: {n(cond.notices)} a 10.3 condition and "
        f"{n(exem.notices)} an exemption. **{n(nocode.notices)} give neither** "
        f"({money(nocode.award_value)} at award). "
        + (f"All {n(t.no_code_80k)}" if t.no_code_80k_amended_below == t.no_code_80k
           else f"{n(t.no_code_80k_amended_below)} of the {n(t.no_code_80k)}") + " have since "
        f"been amended below $80k ({money(nocode.current_value)} in total now): probably a value keyed wrongly at "
        "award, not a missing reason.",
        f"- {share(defence.limited_share)} of Defence's notices from $80k are limited tenders "
        f"({share(defence.limited_value_share)} of the value); its largest code is "
        f"`{defence.top_code}` (paragraph 2.6 applied in part).",
        "",
        "By condition or exemption (limited tenders from $80k, value at award):",
        "",
        table(codes.head(15), money_cols=("award_value", "current_value"), pct_cols=("defence_share",),
              int_cols=("notices", "agencies")),
        "",
        f"The two largest 10.3 conditions are `AD` (additional deliveries from the original supplier, "
        f"{money(codes[codes.code == 'AD'].award_value.iloc[0])}) and `TR` (only one supplier for technical "
        f"reasons, {money(codes[codes.code == 'TR'].award_value.iloc[0])}): extensions and sole sources, "
        f"{n(t.ad_tr_80k)} notices and {money(t.ad_tr_award_value_80k)} together. "
        f"`EU` (extreme urgency) is small at award ({money(eu.award_value)}) but grew to "
        f"{money(codes[codes.code == 'EU'].current_value.iloc[0])}; see section 4.",
        "",
        "Agencies with at least 100 notices from $80k, by the share of that value bought by limited tender:",
        "",
        table(ag.head(15), money_cols=("award_value_80k",), pct_cols=("limited_share", "limited_value_share",
              "top_code_share"), int_cols=("notices_80k", "limited", "by_condition", "by_exemption", "no_code")),
        "",
        "A high share isn't a breach: leases (`LP`), research and development (`RD`), buying from other "
        "governments (`GE`) and Defence's own exemptions (`AM`, `DI`) are all allowed routes. The question for "
        "each agency is whether its main code fits what it buys.",
        "",
        "## 2. Bunching under the $80k threshold",
        "",
        "If contracts are shaped to stay under a threshold, values pile up just below it. The test: notices in "
        "the last $1,000 before an amount, against the mean of the 8 neighbouring $1,000 bins. The bin that "
        "starts at the amount is left out, because whole amounts like $80,000.00 pile up there anyway.",
        "",
        table(bp[["amount", "is_threshold", "last_1k", "neighbour_mean", "ratio", "ratio_not_round",
                  "last_1k_limited_share", "neighbour_limited_share"]],
              pct_cols=("last_1k_limited_share", "neighbour_limited_share")),
        "",
        f"- **At $80k the last $1,000 holds {n(b80.last_1k)} notices, {x(b80.ratio, 2)} times its neighbours** "
        f"({x(b80.ratio_not_round, 2)} without whole-thousand values). At the other 13 round amounts the ratio is "
        f"{x(others.ratio.min(), 2)} to {x(others.ratio.max(), 2)}. That is about {n(round(excess))} more notices "
        "than the neighbours would suggest.",
        f"- **Not just round amounts:** across all {n(len(scan))} $1,000 bins from $25k to $195k, leaving out "
        "whole-thousand values (they fill every bin that starts at a round amount), the $79k bin is the furthest "
        f"above its neighbours ({x(scan.ratio_not_round.iloc[0], 2)}). The next, ${n(second.bin // 1000)}k "
        f"({x(second.ratio_not_round, 2)}), is lifted by one exact value repeated {n(second.same_value_max)} times, a standard fee.",
        f"- The extra notices aren't more often limited tenders: {share(b80.last_1k_limited_share)} of the last "
        f"$1,000 against {share(b80.neighbour_limited_share)} of its neighbours. {n(bd.open)} of the "
        f"{n(bd.notices)} are open tenders (which can include orders from a panel set up by open tender). So the "
        "data doesn't show bunching being used to skip competition; budgets and approval limits set at the "
        "threshold would give the same pattern.",
        f"- {n(bd.at_79200)} notices are exactly $79,200 ($72,000 plus GST). {n(bd.at_80000)} are exactly "
        f"$80,000; {n(bd.at_80000_limited)} of those are limited tenders, and {n(bd.at_80000_limited_coded)} of "
        "them give a reason or exemption, as they should at the threshold.",
        "",
        "The 8 bins furthest above their neighbours, on values that aren't whole thousands:",
        "",
        table(scan.head(8), int_cols=("notices", "same_value_max")),
        "",
        "Other thresholds and policy amounts, with bins of 1.25% of the amount:",
        "",
        table(rel),
        "",
        f"None reaches the $80k ratio. $88,000 ($80k plus GST) shows no second pile ({x(rel88.ratio, 2)}), so "
        "there's no sign of agencies applying the threshold before GST. The $7.5m construction line "
        f"({x(rel75.ratio, 2)}) rests on {n(rel75.last_bin)} notices, too few to judge.",
        "",
        "![Notices by value at award, $60k to $100k](charts/05_threshold_bunching.png)",
        "",
        "Agencies with at least 8 notices in the last $1,000 before $80k, against their own neighbouring bins "
        "(`same_value_max`: most notices sharing one exact value):",
        "",
        table(r["bunching_agencies"], int_cols=("last_1k", "same_value_max")),
        "",
        f"Services Australia's {n(r['bunching_agencies'].set_index('agency').loc['Services Australia', 'last_1k'])} "
        "are mostly one standard amount for its agent and access point agreements "
        f"({n(r['bunching_agencies'].set_index('agency').loc['Services Australia', 'same_value_max'])} at the same "
        "value), a fee schedule rather than a series of choices.",
        "",
        "### Possible split purchases",
        "",
        "The CPRs bar dividing a procurement to get under a threshold. The check: limited tenders each under $80k "
        "at award, from one agency to one supplier, with the same description and start date, published within "
        "30 days of each other and adding up to $80k or more.",
        "",
        f"- **{n(ss.groups)} groups, {n(ss.notices)} notices, {money(ss.award_value)}** at award, at "
        f"{n(ss.agencies)} agencies ({n(ss.defence_groups)} groups at Defence). That is out of "
        f"{n(ss.limited_under_80k)} limited tenders under $80k, and the median group is "
        f"{n(ss.median_notices)} notices.",
        "- Most have ordinary explanations: one notice per person, site or period under one arrangement. It is "
        "a list for an internal auditor to sample, not a finding. Suppliers aren't named because some are "
        "individuals.",
        "",
        table(r["split_by_agency"], money_cols=("award_value", "largest_group_value"),
              int_cols=("groups", "notices", "largest_group_notices")),
        "",
        "## 3. Late publication",
        "",
        f"- **{n(lt.late)} of {n(lt.with_start)} notices ({share(lt.late_share)}) were published more than 42 days "
        f"after the contract started**, {money(lt.late_value)} of value. {n(lt.late_43_90)} were 43 to 90 days, "
        f"{n(lt.late_91_365)} 91 to 365 days and {n(lt.late_over_1y)} more than a year. Median lag "
        f"{n(lt.median_lag)} days; {n(lt.starts_after_publish)} notices were published before the contract started.",
        f"- Limited tenders are late more often ({share(lt.late_share_limited)}) than open tenders "
        f"({share(lt.late_share_open)}).",
        f"- **{share(lb.batch_share)} of late notices ({n(lb.late_in_batches)} of {n(lb.late)}) came out in "
        f"catch-up batches**: {n(lb.batch_days)} days on which one agency published 10 or more late notices, at "
        f"{n(lb.batch_agencies)} agencies.",
        "",
        "The largest batches:",
        "",
        table(batches, int_cols=("late", "main_description_notices", "median_lag", "main_start_notices")),
        "",
        f"The biggest are agreements that mostly start on 1 July 2024 and were published months later: Services "
        f"Australia's agent and access point agreements ({n(top_b.main_start_notices)} of {n(top_b.late)} on "
        f"{top_b.published} start on {top_b.main_start}) and Veterans' Affairs' day procedure, hospital and "
        "community nursing agreements in December. The Department of "
        f"Finance batch on {fin.published} is {n(fin.main_description_notices)} {fin.main_description}s that "
        f"started between {fin.earliest_start[:4]} and {fin.latest_start[:4]}, reported in one go (median lag "
        f"{n(fin.median_lag)} days).",
        "",
        "![Late publication by agency](charts/06_late_by_agency.png)",
        "",
        "Agencies with at least 300 notices:",
        "",
        table(la, pct_cols=("late_share", "late_share_outside_batches"),
              int_cols=("notices", "late", "late_in_batches", "over_1y")),
        "",
        f"Defence publishes {n(def_late.late)} late notices, the most of any agency, but "
        f"{n(def_late.late_in_batches)} of them in batches; outside batches only "
        f"{share(def_late.late_share_outside_batches)} of its notices are late.",
        "",
        "By month of publication:",
        "",
        table(r["late_by_month"], pct_cols=("late_share",), int_cols=("notices", "late")),
        "",
        "## 4. Growth after award",
        "",
        f"- {n(gt.grew)} of {n(gt.notices)} active notices grew after award; together the active notices went "
        f"from {money(gt.award_value)} to {money(gt.current_value)} ({share(gt.growth)} more, as of {as_of}). "
        f"{n(gt.doubled)} at least doubled and {n(gt.tenfold)} grew tenfold or more "
        f"({money(gt.tenfold_added)} added).",
        f"- **Open tenders grow more than limited ones.** From $80k at award, {share(gr.loc['1. Open tender', 'share_grew'])} "
        f"of open tenders grew ({share(gr.loc['1. Open tender', 'growth'])} in value), against "
        f"{share(gr.loc['3. Limited: a 10.3 condition', 'share_grew'])} of limited tenders under a 10.3 condition "
        f"({share(gr.loc['3. Limited: a 10.3 condition', 'growth'])}) and "
        f"{share(gr.loc['4. Limited: an exemption', 'share_grew'])} under an exemption "
        f"({share(gr.loc['4. Limited: an exemption', 'growth'])}).",
        "",
        table(r["growth_by_route"], money_cols=("award_value", "added"), pct_cols=("growth", "share_grew",
              "share_doubled"), int_cols=("notices",)),
        "",
        "By condition or exemption (limited tenders from $80k with a code, 20+ notices):",
        "",
        table(r["growth_by_code"], money_cols=("award_value", "added"), pct_cols=("growth",), int_cols=("notices",)),
        "",
        f"- `EU`, extreme urgency, grew the most ({share(eu.growth)}), and most of that is one contract: "
        f"{eu_top.cn_id}, Defence *{eu_top.description}*, from {money(eu_top.award_value)} to "
        f"{money(eu_top.current_value)} in {n(eu_top.n_amendments)} amendments. An urgent award that becomes a "
        "$300m-plus contract is the kind of change an audit committee would want explained.",
        f"- `VM` (no value-for-money submissions) fell {share(-vm.growth)}: values reduced after award.",
        "",
        "The 12 notices that grew most after award:",
        "",
        table(top, money_cols=("award_value", "current_value", "added"), int_cols=("n_amendments",)),
        "",
        "### Placeholder values at award",
        "",
        f"{n(dva.notices)} Veterans' Affairs notices were first published at exactly $10,000, the reporting "
        f"threshold, and later amended up: {n(dva.tenfold)} of them tenfold or more, to "
        f"{money(dva.current_value)} in total. {n(mix.notices.iloc[0])} are *{mix.description.iloc[0]}* notices "
        f"({money(mix.current_value.iloc[0])}) and the other {n(home_care)} are Veterans' Home Care services: "
        "services paid as they are used, so $10,000 reads as a placeholder for a value that depends on demand.",
        "",
        table(ph.head(8), money_cols=("award_value", "current_value"), int_cols=("notices", "tenfold")),
        "",
        f"More broadly, {n(ct_total)} notices were under $80k at award and are $80k or more now "
        f"({ct_from_10k} of them from exactly $10,000). For these, any threshold decision was made on a value "
        "the contract outgrew.",
        "",
        table(r["crossed_threshold"], money_cols=("award_value", "current_value"),
              int_cols=("notices", "from_10000", "now_1m_plus")),
        "",
        "## Files",
        "",
        "- `limited_by_agency.csv`: every agency with notices from $80k, by route.",
        "- `late_by_agency.csv`: every agency, late share inside and outside batches.",
        "- `growth_review.csv`: the 200 notices that grew most after award, with route and amendments.",
        "",
        "## Limits",
        "",
        "- **No expected value, signing date or entity type** in the API: the value at award, the start date "
        "and the $80k line for every agency are stand-ins, as set out above.",
        "- **Patterns, not breaches.** Bunching, split groups, late batches and growth are where to look; "
        "each has ordinary explanations the notice doesn't record.",
        "- **Amendments are still arriving**, so growth after award will keep rising for the later notices.",
        "",
    ]
    return "\n".join(L)


def write_csvs(con) -> None:
    con.sql("""
        SELECT agency, count(*) AS notices_80k, sum(award_value) AS award_value_80k,
               count(*) FILTER (method = 'limited') AS limited,
               count(*) FILTER (route LIKE '3.%') AS by_condition,
               count(*) FILTER (route LIKE '4.%') AS by_exemption,
               count(*) FILTER (route LIKE '5.%') AS no_code,
               coalesce(sum(award_value) FILTER (method = 'limited'), 0) AS limited_award_value
        FROM comp WHERE award_80k_plus GROUP BY agency_key, agency ORDER BY award_value_80k DESC, agency
    """).df().to_csv(RESULTS / "limited_by_agency.csv", index=False)
    con.sql("""
        WITH d AS (SELECT agency_key, published_au, count(*) FILTER (lag_days > 42) AS late_that_day
                   FROM comp GROUP BY 1, 2)
        SELECT any_value(c.agency) AS agency, count(c.lag_days) AS notices,
               count(*) FILTER (c.lag_days > 42) AS late,
               count(*) FILTER (c.lag_days > 42 AND d.late_that_day >= 10) AS late_in_batches,
               count(*) FILTER (c.lag_days > 365) AS over_1y, median(c.lag_days) AS median_lag
        FROM comp c JOIN d USING (agency_key, published_au)
        GROUP BY c.agency_key ORDER BY notices DESC, agency
    """).df().to_csv(RESULTS / "late_by_agency.csv", index=False)
    con.sql("""
        SELECT cn_id, published_au, agency, description, route, award_value, current_value,
               current_value - award_value AS added, n_amendments
        FROM comp ORDER BY added DESC, cn_id LIMIT 200
    """).df().to_csv(RESULTS / "growth_review.csv", index=False)


def main() -> None:
    CHARTS.mkdir(parents=True, exist_ok=True)
    snap = json.loads(SNAPSHOT.read_text())
    con = compliance_connection()
    r = results(con)
    b80 = r["bunching_points"].set_index("amount").loc[80000]
    chart_bunching(r["bunching_bins"], float(b80.ratio), CHARTS / "05_threshold_bunching.png")
    chart_late(r["late_by_agency"], CHARTS / "06_late_by_agency.png")
    write_csvs(con)
    (RESULTS / "COMPLIANCE.md").write_text(write_report(r, snap))
    print(f"wrote {RESULTS / 'COMPLIANCE.md'}")


if __name__ == "__main__":
    main()
