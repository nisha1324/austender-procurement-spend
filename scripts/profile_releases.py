"""Part 1: profile the snapshot and write `results/SOURCE_PROFILE.md` plus two charts.

    python -m scripts.profile_releases
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "releases.csv.gz"
SNAPSHOT = ROOT / "data" / "SNAPSHOT.json"
SQL_DIR = ROOT / "sql"
RESULTS = ROOT / "results"
CHARTS = RESULTS / "charts"

# Validated with the dataviz skill's palette checker (categorical slots 1 and 2, light mode).
BLUE, ORANGE = "#2a78d6", "#eb6834"
INK, INK_2, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#8a8984", "#e6e5e1", "#fcfcfb"


def connect(csv: Path = DATA) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")
    con.execute((SQL_DIR / "00_load.sql").read_text().replace("{releases_csv}", str(csv)))
    return con


def named_queries(path: Path) -> dict[str, str]:
    text = path.read_text()
    return {m.group(1): m.group(2).strip()
            for m in re.finditer(r"-- name: (\w+)\n(.*?)(?=\n-- name: |\Z)", text, re.S)}


def run_all(con, path: Path) -> dict[str, pd.DataFrame]:
    return {name: con.sql(q).df() for name, q in named_queries(path).items()}


# ---------- formatting ----------
def n(x) -> str:
    return f"{int(x):,}"


def pct(a, b, dp: int = 1) -> str:
    return f"{100 * float(a) / float(b):.{dp}f}%"


def money(x) -> str:
    x = float(x)
    if x < 0:
        return "-" + money(-x)
    if abs(x) >= 1e9:
        return f"${x / 1e9:,.2f}bn"
    if abs(x) >= 1e6:
        return f"${x / 1e6:,.1f}m"
    if abs(x) >= 1e3:
        return f"${x / 1e3:,.0f}k"
    return f"${x:,.0f}"


def table(df: pd.DataFrame, money_cols=(), pct_cols=(), int_cols=()) -> str:
    out = df.copy()
    for c in money_cols:
        out[c] = out[c].map(money)
    for c in pct_cols:
        out[c] = out[c].map(lambda v: f"{100 * float(v):.1f}%")
    for c in int_cols:
        out[c] = out[c].map(n)
    head = "| " + " | ".join(out.columns) + " |"
    sep = "|" + "|".join("---" for _ in out.columns) + "|"
    rows = ["| " + " | ".join(str(v).replace("|", "/") for v in r) + " |" for r in out.itertuples(index=False)]
    return "\n".join([head, sep, *rows])


# ---------- charts ----------
def _style(ax):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=INK_2, length=0)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def chart_value_bands(bands: pd.DataFrame, out: Path) -> None:
    labels = [b.split(". ", 1)[1].replace("$", r"\$") for b in bands["band"]]  # no mathtext
    share_n = 100 * bands["notices"] / bands["notices"].sum()
    share_v = 100 * bands["current_value"].astype(float) / bands["current_value"].astype(float).sum()
    fig, ax = plt.subplots(figsize=(9, 4.8), dpi=150, facecolor=SURFACE)
    _style(ax)
    y = range(len(labels))
    h = 0.36
    ax.barh([i - h / 2 - 0.02 for i in y], share_n, height=h, color=BLUE, label="Share of notices")
    ax.barh([i + h / 2 + 0.02 for i in y], share_v, height=h, color=ORANGE, label="Share of contract value")
    for i, (a, b) in enumerate(zip(share_n, share_v)):
        ax.text(a + 0.8, i - h / 2 - 0.02, f"{a:.1f}%", va="center", fontsize=8.5, color=INK_2)
        ax.text(b + 0.8, i + h / 2 + 0.02, f"{b:.1f}%", va="center", fontsize=8.5, color=INK_2)
    ax.set_yticks(list(y), labels, color=INK, fontsize=9.5)
    ax.invert_yaxis()
    ax.set_xlim(0, max(share_n.max(), share_v.max()) * 1.15)
    ax.set_xlabel("Share of all FY2024-25 notices, by value band (%)", color=INK_2, fontsize=9)
    ax.set_title("Most notices are small; most of the money is in a few large contracts",
                 loc="left", color=INK, fontsize=12, pad=26)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2, frameon=False, fontsize=9,
              labelcolor=INK_2, handlelength=1.2, borderaxespad=0.2)
    fig.text(0.01, 0.01, "Source: AusTender OCDS API (Department of Finance), CC BY 3.0 AU. "
             "Value = latest amended value of each notice.", fontsize=7.5, color=MUTED)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(out, facecolor=SURFACE)
    plt.close(fig)


def chart_award_vs_current(monthly: pd.DataFrame, as_of: str, out: Path) -> None:
    months = pd.to_datetime(monthly["month"] + "-01")
    labels = [m.strftime("%b\n%Y") if m.month in (7, 1) else m.strftime("%b") for m in months]
    award = monthly["value_at_award"].astype(float) / 1e9
    current = monthly["current_value"].astype(float) / 1e9
    fig, ax = plt.subplots(figsize=(9, 4.6), dpi=150, facecolor=SURFACE)
    _style(ax)
    ax.grid(axis="x", visible=False)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    x = range(len(labels))
    w = 0.38
    ax.bar([i - w / 2 - 0.02 for i in x], award, width=w, color=BLUE, label="Value when first published")
    ax.bar([i + w / 2 + 0.02 for i in x], current, width=w, color=ORANGE, label=f"Value after amendments (as of {as_of})")
    ax.set_xticks(list(x), labels, fontsize=8.5, color=INK_2)
    ax.set_ylabel("$ billion", color=INK_2, fontsize=9)
    ax.set_title("Amendments keep adding value long after a notice is published",
                 loc="left", color=INK, fontsize=12, pad=26)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2, frameon=False, fontsize=9,
              labelcolor=INK_2, handlelength=1.2, borderaxespad=0.2)
    fig.text(0.01, 0.01, "Active notices (cancelled left out), by the month they were first published "
             "(Canberra time). Source: AusTender OCDS API, CC BY 3.0 AU.", fontsize=7.5, color=MUTED)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(out, facecolor=SURFACE)
    plt.close(fig)


# ---------- report ----------
def write_report(r: dict[str, pd.DataFrame], snap: dict) -> str:
    cov, chain = r["coverage"].iloc[0], r["chain"].iloc[0]
    steps, dc = r["amendment_steps"].iloc[0], r["double_count"].iloc[0]
    conc, sup = r["concentration"].iloc[0], r["suppliers"].iloc[0]
    abnv, sid = r["abn_variant_summary"].iloc[0], r["supplier_id_meaning"].iloc[0]
    ag, dates = r["agencies"].iloc[0], r["dates"].iloc[0]
    look, codes = r["lookalikes"].iloc[0], r["unspsc_codes"].iloc[0]
    as_of = snap["fetched_to"][:10]
    notices = int(cov.notices)

    lp = r["limited_patterns"].copy()
    lim_total = int(lp.notices.sum())

    def lim(flag, reason, exempt, big):
        m = lp[(lp.exemption_flag == flag) & (lp.has_reason_code == reason)
               & (lp.has_exemption_code == exempt) & (lp.award_80k_plus == big)]
        return int(m.notices.sum())

    below = lim("1", False, False, False)
    reason_big = lim("0", True, False, True)
    exempt_big = lim("1", False, True, True)
    lim_under = int(lp[~lp.award_80k_plus.astype(bool)].notices.sum())
    lim_big = lim_total - lim_under
    big_uncoded = int(lp[lp.award_80k_plus.astype(bool) & ~lp.has_reason_code.astype(bool)
                         & ~lp.has_exemption_code.astype(bool)].notices.sum())
    under_note = (f"{pct(below, lim_under)} of those carry the exemption flag and no code; "
                  f"{n(lim_under - below)} carry a reason or exemption code anyway.")

    methods = r["methods"].set_index("method_details")
    bands = r["value_bands"]
    under_80k = bands[bands.band.str.startswith(("1.", "2."))]
    big = bands[bands.band.str.startswith("6.")].iloc[0]
    top_agency = r["top_agencies"].iloc[0]
    busiest = r["busiest_amendment_days"]
    status = r["status"].set_index("status")
    depth = r["unspsc_depth"].set_index("depth")
    coarse = depth.loc[["1. segment only", "2. family"]]
    total_value = float(dc.sum_current_value)

    L = []
    L += [
        "# Source profile: what the AusTender data can and can't tell us",
        "",
        "Generated by `scripts/profile_releases.py` from `sql/profile.sql`. Every number below is",
        "computed from `data/releases.csv.gz`; nothing is typed in by hand.",
        "",
        "## The snapshot",
        "",
        "| | |",
        "|---|---|",
        "| Source | AusTender OCDS API (`findByDates/contractPublished`), Department of Finance |",
        "| Licence | CC BY 3.0 AU (stated in every API response; the download stops if it changes) |",
        f"| Notices covered | Contract notices first published {cov.first_published:%-d %b %Y} to "
        f"{cov.last_published:%-d %b %Y} (Canberra time), i.e. FY2024-25 |",
        f"| Downloaded | {snap['fetched_from'][:10]} to {snap['fetched_to'][:10]}, "
        f"{n(snap['day_files'])} day files, {n(snap['api_pages'])} API pages |",
        f"| Rows | {n(cov.releases)} releases = {n(cov.notices)} notices + {n(cov.amendments)} amendments |",
        f"| Agencies | {n(cov.agencies)} agency names |",
        f"| Repeats dropped | {n(snap['boundary_repeats_dropped'])} releases published at exactly "
        "Canberra midnight, which the API returns for both days |",
        "",
        f"The API also returns every **later amendment** of these notices, up to the download date. "
        f"The latest amendment in the snapshot was published on {cov.last_release:%-d %b %Y}. "
        f"So \"current value\" in this project means *as of {as_of}*; a later download would show more.",
        "",
        "## Traps, and the rule each one sets",
        "",
        "| Trap | What the data shows | Rule from here on |",
        "|---|---|---|",
        f"| **Amendment values are running totals** | Checked against the government's own export "
        f"(see [`AMENDMENT_CHECK.md`](AMENDMENT_CHECK.md)): the step between two API versions equals the "
        f"export's change to the cent. Summing every version gives {money(dc.sum_every_version)}, "
        f"{float(dc.overstatement):.1f} times the {money(dc.sum_current_value)} you get from each notice's "
        f"latest version. | One row per notice: its latest version. Never sum releases. |",
        f"| **Amendments are numbered, and text sorts them wrongly** | Up to {n(chain.most_amendments)} "
        f"amendments on one notice; every one of the {n(chain.amendments)} amendments points at the "
        f"original notice ({n(chain.amendments_point_to_notice)}), not the amendment before it. | "
        "Order by the number after `-A`, as a number (A10 comes after A9). |",
        f"| **Value at award is not the value now** | Notices were worth {money(dc.sum_value_at_award)} "
        f"when first published and {money(dc.sum_current_value)} after amendments "
        f"({pct(float(dc.sum_current_value) - float(dc.sum_value_at_award), dc.sum_value_at_award)} more). "
        f"{n(steps.decrease)} of {n(steps.amendments)} amendments lowered the value. | "
        "Say which one a figure uses. Thresholds use the value at award. |",
        f"| **Amendment dates come in batches** | The busiest day, {busiest.day.iloc[0]:%-d %b %Y}, "
        f"has {n(busiest.amendments.iloc[0])} amendments, {busiest.main_agency_pct.iloc[0]:.1f}% from "
        f"{busiest.main_agency.iloc[0]}. | Don't read an amendment's publish date as the date it was agreed. |",
        f"| **\"Limited tender\" is not a red flag by itself** | {pct(methods.loc['Limited tender', 'notices'], notices)} "
        f"of notices are limited tenders, but {n(lim_under)} of the {n(lim_total)} "
        f"({pct(lim_under, lim_total)}) were under $80k at award, where an open approach isn't required. "
        f"{under_note} | Judge limited tenders from $80k up, by their "
        "reason or exemption code. |",
        f"| **A few contracts hold most of the money** | The top 10 notices hold "
        f"{float(conc.top10_share) * 100:.1f}% of current value, the top 1% ({n(conc.top1pct_notices)} notices) "
        f"{float(conc.top1pct_share) * 100:.1f}%. {top_agency.agency} holds "
        f"{float(top_agency.value_share) * 100:.1f}%. Median notice {money(conc.median_value)}, mean "
        f"{money(conc.mean_value)}. | Report counts and medians next to totals; show results with and "
        "without Defence. |",
        f"| **One supplier, many spellings** | {n(abnv.abns_several_names)} of {n(abnv.abns)} supplier ABNs "
        f"appear under more than one name (up to {n(r['abn_name_variants'].names.iloc[0])}); those ABNs hold "
        f"{float(abnv.value_share_in_those) * 100:.1f}% of value. `supplier_id` never splits an ABN "
        f"({n(sid.abns_several_ids)} ABNs with more than one id). | Group suppliers by ABN, falling back to "
        "`supplier_id`. Never by name. |",
        f"| **Some suppliers have no ABN** | {n(sup.no_abn)} notices ({pct(sup.no_abn, notices)}); "
        f"{n(sup.no_abn_overseas)} of them are overseas suppliers. Country is spelt "
        f"{n(sup.country_spellings)} ways for {n(sup.countries)} countries (\"AUSTRALIA\" and \"Australia\"). | "
        "Use `supplier_id` for these; upper-case the country. |",
        f"| **Agencies change names, and some have no ABN** | {n(ag.agency_abns)} agency ABNs carry "
        f"{n(ag.names_with_abn)} names, for example after a machinery-of-government change (Health and Aged Care "
        f"became Health, Disability and Ageing in May 2025, and notices amended later carry the new name). "
        f"{n(ag.names_without_abn)} agencies have no ABN. | "
        "Group agencies by ABN, labelled with the latest name; by name where there's no ABN. |",
        f"| **Cancelled notices can come back under a new number** | {n(status.loc['cancelled', 'notices'])} "
        f"notices are cancelled ({money(status.loc['cancelled', 'current_value'])}). {n(look.groups_with_cancelled)} "
        f"of {n(look.groups)} lookalike groups include one, among them a "
        f"{money(r['largest_lookalikes'].original_value_aud.iloc[0])} Home Affairs contract published twice, "
        "the first copy since cancelled. Summing all notices would count it twice. | "
        "Leave cancelled notices out of spend. |",
        f"| **Categories are often coded coarsely** | {pct(coarse.notices.sum(), notices)} of notices "
        f"({pct(coarse.current_value.astype(float).sum(), total_value)} of value) are coded only to a UNSPSC "
        f"segment or family. | Compare categories at family level (4 digits) or above. |",
        f"| **Some start dates are placeholders** | {n(dates.start_before_2000)} notices start before 2000 "
        f"({n(dates.start_1900_01_01)} on 1 Jan 1900). | Exclude them from any reporting-lag figure. |",
        f"| **Amendments almost never change the dates** | In all but {n(chain.amended_notices_dates_change)} of "
        f"the {n(cov.notices_amended)} amended notices, every version has the original start and end date. | "
        "Use the dates at award. The API can't show term extensions, only value changes. |",
        "",
    ]

    L += [
        "## Coverage and the amendment chain",
        "",
        f"- {n(cov.notices)} notices, one OCDS id each ({n(cov.ocids)} ocids); "
        f"{n(cov.notices_amended)} ({pct(cov.notices_amended, cov.notices)}) have been amended.",
        f"- Every amended notice has its original version ({n(chain.notices_missing_parent)} missing) and "
        f"no gaps in its amendment numbers ({n(chain.notices_with_gaps)} with gaps).",
        f"- The publish date is the same on every version of a notice "
        f"({n(chain.notices_publish_date_varies)} differ). AusTender puts it in the OCDS `dateSigned` "
        "field; it is not a signing date.",
        f"- Of {n(steps.amendments)} amendments: {n(steps.increase)} raised the value, {n(steps.no_change)} "
        f"left it unchanged and {n(steps.decrease)} lowered it. No value is negative "
        f"({n(steps.negative_values)}) or zero ({n(steps.zero_values)}).",
        "",
        "Busiest days for amendments (by Canberra publish date):",
        "",
        table(busiest.assign(day=busiest.day.map(lambda d: f"{d:%Y-%m-%d}")),
              int_cols=("amendments", "agencies")),
        "",
        "## Value",
        "",
        "![Share of notices and of value by value band](charts/01_value_bands.png)",
        "",
        table(bands.assign(share_of_value=bands.current_value.astype(float) / total_value),
              money_cols=("current_value",), pct_cols=("share_of_value",), int_cols=("notices",)),
        "",
        f"{n(under_80k.notices.sum())} notices ({pct(under_80k.notices.sum(), notices)}) are under $80k and hold "
        f"{pct(under_80k.current_value.astype(float).sum(), total_value)} of value; the {n(big.notices)} of "
        f"$100m and over hold {pct(big.current_value, total_value)}. "
        f"{n(bands[bands.band.str.startswith('1.')].notices.iloc[0])} notices are under the $10k reporting "
        "threshold (agencies may publish below it).",
        "",
        "![Value at first publication and after amendments, by month](charts/02_award_vs_current.png)",
        "",
        "The ten largest notices by current value:",
        "",
        table(r["largest"][["cn_id", "agency", "supplier_name", "description", "original_value_aud",
                            "value_aud", "n_amendments", "method_details"]],
              money_cols=("original_value_aud", "value_aud"), int_cols=("n_amendments",)),
        "",
        "## Procurement method and limited-tender coding",
        "",
        table(r["methods"], money_cols=("current_value",), int_cols=("notices", "notices_80k_plus")),
        "",
        f"How limited tenders are coded, split at $80k on the value at award. The method and codes "
        f"changed between first and latest version in {n(r['code_changes'].changed.iloc[0])} of "
        f"{n(r['code_changes'].amended_notices.iloc[0])} amended notices. Of {n(lim_big)} limited tenders of $80k and over, {n(reason_big)} "
        f"give a limited-tender reason (CPRs 10.3, flag 0) and {n(exempt_big)} an exemption (CPRs "
        f"Appendix A or paragraph 2.6, flag 1); {n(big_uncoded)} give neither. Of {n(lim_under)} under $80k, "
        f"{n(below)} ({pct(below, lim_under)}) have the flag set to 1 and no code, which reads as \"below the "
        "threshold, Division 2 doesn't apply\".",
        "",
        table(lp, money_cols=("current_value",), int_cols=("notices",)),
        "",
        "Reason and exemption codes used (latest version of each notice):",
        "",
        table(r["limited_codes"].assign(meaning=r["limited_codes"].meaning.str.slice(0, 90)),
              money_cols=("current_value",), int_cols=("notices",)),
        "",
        f"Status: {n(status.loc['active', 'notices'])} active, {n(status.loc['cancelled', 'notices'])} "
        f"cancelled ({money(status.loc['cancelled', 'current_value'])}). Cancelled notices are included in "
        "this profile's totals; the spend analysis from Part 2 leaves them out.",
        "",
        "## Suppliers and agencies",
        "",
        f"- {n(sup.distinct_abns)} supplier ABNs, {n(sup.distinct_supplier_ids)} supplier ids, "
        f"{n(sup.distinct_names)} exact names ({n(sup.distinct_names_upper)} ignoring case).",
        f"- {n(sid.names_several_ids)} exact names map to more than one `supplier_id`, so a name isn't a key either.",
        f"- {n(sup.overseas)} notices ({pct(sup.overseas, notices)}) go to suppliers outside Australia.",
        f"- Branch is filled on {pct(ag.with_branch, ag.notices)} of notices and division on "
        f"{pct(ag.with_division, ag.notices)}. The API puts them, with the agency officer's contact details, "
        "on the *supplier* party; the snapshot keeps branch and division and drops the personal details.",
        "",
        "Supplier ABNs with the most spellings:",
        "",
        table(r["abn_name_variants"].assign(spellings=r["abn_name_variants"].spellings.str.slice(0, 110) + " ..."),
              money_cols=("current_value",), int_cols=("names", "notices")),
        "",
        "Agency ABNs used under more than one name:",
        "",
        table(r["agency_abn_variants"].assign(agency_abn=r["agency_abn_variants"].agency_abn.fillna("(none)"))),
        "",
        "Largest agencies by current value:",
        "",
        table(r["top_agencies"], money_cols=("current_value",), pct_cols=("value_share",), int_cols=("notices",)),
        "",
        "## Categories (UNSPSC)",
        "",
        f"{n(codes.codes)} distinct codes in {n(codes.segments)} segments and {n(codes.families)} families; "
        f"{n(codes.malformed)} malformed. AusTender doesn't send category names, so Part 2 adds them.",
        "",
        table(r["unspsc_depth"], money_cols=("current_value",), int_cols=("notices",)),
        "",
        "## Dates and reporting lag",
        "",
        f"- Median gap from contract start to publication: {float(dates.median_lag_days):.0f} days; "
        f"{n(dates.published_over_42d_after_start)} notices ({pct(dates.published_over_42d_after_start, notices)}) "
        f"were published more than 42 days after the contract started, {n(dates.published_over_1y_after_start)} "
        "more than a year after (placeholder start dates before 2000 left out). Part 3 looks closer.",
        f"- {n(dates.starts_after_publish)} notices were published before the contract started.",
        f"- Median term {float(dates.median_term_days):.0f} days; {n(dates.terms_over_10y)} run over 10 years.",
        "",
        table(r["lag_by_value"], int_cols=("notices", "over_42d")),
        "",
        "## Possible duplicates",
        "",
        f"{n(look.groups)} groups of notices share agency, supplier, value at award, start date and description "
        f"under different notice numbers: {n(look.extra_notices)} notices beyond the first in each group, worth "
        f"{money(look.extra_value)} at award. **{n(look.groups_with_cancelled)} of the {n(look.groups)} groups "
        "include a cancelled notice**: a notice cancelled and published again under a new number. Among active "
        f"notices only, {n(look.active_groups)} groups remain, with {n(look.active_extra_notices)} extra notices "
        f"worth {money(look.active_extra_value)} ({pct(look.active_extra_value, look.active_value_at_award, 2)} of "
        "active value at award). Some of those will be real repeat orders, so they're kept and flagged, not removed.",
        "",
        "Largest groups by value beyond the first notice:",
        "",
        table(r["largest_lookalikes"], money_cols=("original_value_aud",), int_cols=("notices",)),
        "",
        "## What this data can't tell us",
        "",
        "- **Money spent.** A notice records a contract's value, not payments. Spend here means *committed contract value*.",
        "- **Why an amendment happened**, or whether it extended the term (dates don't change between versions).",
        "- **Panels and standing offers, consultancy, confidentiality.** AusTender's website shows these, but the "
        "API doesn't send them.",
        "- **Contracts under $10k**, which agencies don't have to publish.",
        "- **The order of same-day amendments.** When several amendments go up on one day, the value can go down "
        "and back up between them. The highest-numbered version is taken as current.",
        "",
    ]
    return "\n".join(L)


def main() -> None:
    CHARTS.mkdir(parents=True, exist_ok=True)
    snap = json.loads(SNAPSHOT.read_text())
    con = connect()
    r = run_all(con, SQL_DIR / "profile.sql")
    chart_value_bands(r["value_bands"], CHARTS / "01_value_bands.png")
    chart_award_vs_current(r["monthly"], snap["fetched_to"][:10], CHARTS / "02_award_vs_current.png")
    r["value_bands"].to_csv(RESULTS / "value_bands.csv", index=False)
    r["limited_codes"].to_csv(RESULTS / "limited_codes.csv", index=False)
    r["monthly"].to_csv(RESULTS / "monthly_notices.csv", index=False)
    (RESULTS / "SOURCE_PROFILE.md").write_text(write_report(r, snap))
    print(f"wrote {RESULTS / 'SOURCE_PROFILE.md'}")


if __name__ == "__main__":
    main()
