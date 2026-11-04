"""Part 2: the spend cube. Writes `results/SPEND_CUBE.md`, two charts and the cube CSVs.

    python -m scripts.spend_cube

Needs `data/unspsc_categories.csv` (from `scripts/build_categories.py`, committed).
"""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from scripts.profile_releases import (  # noqa: E402
    BLUE, CHARTS, GRID, INK, INK_2, MUTED, RESULTS, ROOT, SNAPSHOT, SQL_DIR, SURFACE,
    ORANGE, _style, connect, money, n, pct, run_all, table,
)

CATEGORIES = ROOT / "data" / "unspsc_categories.csv"
LARGE = "$100m or more and at least 20 notices"
SOURCE_NOTE = "Source: AusTender OCDS API (Department of Finance), CC BY 3.0 AU; UNSPSC names from the AusTender codeset."


def spend_connection(releases_csv: Path | None = None, categories_csv: Path = CATEGORIES):
    con = connect(releases_csv) if releases_csv else connect()
    con.execute((SQL_DIR / "01_spend.sql").read_text().replace("{categories_csv}", str(categories_csv)))
    return con


def results(con=None) -> dict[str, pd.DataFrame]:
    return run_all(con or spend_connection(), SQL_DIR / "spend.sql")


def share(x) -> str:
    return f"{100 * float(x):.1f}%"


def wrap(label: str, width: int = 46) -> str:
    return textwrap.fill(label, width=width, max_lines=2, placeholder=" ...")


def no_math(s: str) -> str:
    return s.replace("$", r"\$")


# ---------- charts ----------
def _head(fig, ax, title: str, top: float) -> None:
    """Title and legend across the whole figure, left-aligned, above the plot."""
    fig.suptitle(title, x=0.01, y=0.985, ha="left", color=INK, fontsize=11.5)
    handles, labels = ax.get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper left", bbox_to_anchor=(0.005, 0.965), ncol=2, frameon=False,
               fontsize=9, labelcolor=INK_2, handlelength=1.2)
    fig.tight_layout(rect=(0, 0.03, 1, top))


def chart_segments(seg: pd.DataFrame, out: Path, top: int = 12) -> None:
    head = seg.head(top).copy()
    rest = seg.iloc[top:]
    head.loc[len(head)] = {"segment_title": f"All other {len(rest)} segments",
                           "value": rest.value.sum(), "defence_value": rest.defence_value.sum()}
    defence = head.defence_value.astype(float) / 1e9
    other = (head.value.astype(float) - head.defence_value.astype(float)) / 1e9
    labels = [wrap(t) for t in head.segment_title]
    fig, ax = plt.subplots(figsize=(9.5, 7.2), dpi=150, facecolor=SURFACE)
    _style(ax)
    y = list(range(len(labels)))
    ax.barh(y, other, height=0.68, color=BLUE, label="Other agencies")
    ax.barh(y, defence, left=other + 0.04, height=0.68, color=ORANGE, label="Department of Defence")
    for i, (a, b) in enumerate(zip(other, defence)):
        ax.text(a + b + 0.15, i, no_math(f"${a + b:.2f}bn"), va="center", fontsize=8.5, color=INK_2)
    ax.set_yticks(y, labels, color=INK, fontsize=8.3)
    ax.invert_yaxis()
    ax.set_xlim(0, (other + defence).max() * 1.12)
    ax.set_xlabel("Committed contract value, $ billion", color=INK_2, fontsize=9)
    fig.text(0.01, 0.01, "Active FY2024-25 notices, latest amended value, by UNSPSC segment. " + SOURCE_NOTE,
             fontsize=6.8, color=MUTED)
    _head(fig, ax, "Services hold three-quarters of the money; Defence dominates building and vehicles", 0.93)
    fig.savefig(out, facecolor=SURFACE)
    plt.close(fig)


def chart_concentration(conc: pd.DataFrame, out: Path, top: int = 20) -> None:
    d = conc.head(top)
    labels = [no_math(f"{wrap(t, 44)} ({money(v)})") for t, v in zip(d.family_title, d.value)]
    sup = 100 * d.top1_share.astype(float)
    big = 100 * d.top_supplier_largest_notice_share.astype(float)
    fig, ax = plt.subplots(figsize=(9.5, 9.2), dpi=150, facecolor=SURFACE)
    _style(ax)
    y = list(range(len(labels)))
    h = 0.36
    ax.barh([i - h / 2 - 0.02 for i in y], sup, height=h, color=BLUE, label="Top supplier's share of the family")
    ax.barh([i + h / 2 + 0.02 for i in y], big, height=h, color=ORANGE, label="Its single largest notice")
    for i, (a, b) in enumerate(zip(sup, big)):
        ax.text(a + 0.8, i - h / 2 - 0.02, f"{a:.0f}%", va="center", fontsize=7.5, color=INK_2)
        ax.text(b + 0.8, i + h / 2 + 0.02, f"{b:.0f}%", va="center", fontsize=7.5, color=INK_2)
    ax.set_yticks(y, labels, color=INK, fontsize=7.8)
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xlabel("Share of the family's committed value (%)", color=INK_2, fontsize=9)
    fig.text(0.01, 0.022, "20 largest UNSPSC families, all agencies, active FY2024-25 notices, latest value. "
             "Two bars of equal length: the top supplier's share rests on one notice.", fontsize=7, color=MUTED)
    fig.text(0.01, 0.006, SOURCE_NOTE, fontsize=7, color=MUTED)
    _head(fig, ax, "Where one supplier holds a large share of a category, it is often a single contract", 0.945)
    fig.savefig(out, facecolor=SURFACE)
    plt.close(fig)


# ---------- report ----------
CONC_COLS = ["family", "family_title", "value", "notices", "agencies", "suppliers", "top_supplier",
             "top_supplier_notices", "top1_share", "largest_notice_share", "hhi", "hhi_without_largest"]


def conc_table(d: pd.DataFrame) -> str:
    out = d[CONC_COLS + ["driver"]].rename(columns={"top_supplier_notices": "its notices",
                                                    "largest_notice_share": "family's largest notice",
                                                    "top1_share": "top supplier share",
                                                    "hhi_without_largest": "HHI without largest",
                                                    "hhi": "HHI"})
    return table(out, money_cols=("value",), pct_cols=("top supplier share", "family's largest notice"),
                 int_cols=("notices", "agencies", "suppliers", "its notices", "HHI", "HHI without largest"))


def write_report(r: dict[str, pd.DataFrame], snap: dict) -> str:
    t = r["totals"].iloc[0]
    total = float(t.value)
    gs = r["goods_services"].set_index("goods_services")
    seg = r["segments"]
    fam = r["families"]
    ag = r["agencies"]
    sup = r["suppliers"]
    base = r["supplier_base"].iloc[0]
    ca, cx = r["concentration_all"], r["concentration_ex_defence"]
    bands = r["concentration_bands"]
    frag = r["fragmented"]
    as_of = snap["fetched_to"][:10]

    def band(scope, b, driver=""):
        m = bands[(bands.scope == scope) & (bands.hhi_band == b) & (bands.driver == driver)]
        return (int(m.families.sum()), float(m.value.sum())) if len(m) else (0, 0.0)

    hi_one, hi_beyond = band("all agencies", "high", "one contract"), band("all agencies", "high", "beyond one contract")
    lo, mod = band("all agencies", "low"), band("all agencies", "moderate")
    x_one, x_beyond = band("without Defence", "high", "one contract"), band("without Defence", "high", "beyond one contract")
    x_lo, x_mod = band("without Defence", "low"), band("without Defence", "moderate")
    large_value = float(ca.value.sum())
    top_seg = seg.iloc[0]
    building = seg[seg.segment == "72"].iloc[0]
    defence = ag[ag.agency == "Department of Defence"].iloc[0]
    hand = pd.read_csv(CATEGORIES, dtype=str, keep_default_na=False)
    hand = hand[hand.family_title_source == "derived from child codes"].drop_duplicates("family")

    L = [
        "# Spend cube: where the money goes, and who it goes to",
        "",
        "Generated by `scripts/spend_cube.py` from `sql/01_spend.sql` and `sql/spend.sql`. Every number",
        "below is computed from `data/releases.csv.gz` and `data/unspsc_categories.csv`.",
        "",
        "## Scope and rules",
        "",
        "| | |",
        "|---|---|",
        f"| Notices | {n(t.notices)} active contract notices first published in FY2024-25 "
        "(cancelled ones left out, as Part 1 decided) |",
        f"| Value | Each notice's latest amended value as of {as_of}: **committed contract value**, not "
        f"payments. {money(total)} in total ({money(t.value_at_award)} at award). |",
        f"| Suppliers | {n(t.suppliers)}, grouped by ABN; {n(t.notices_no_abn)} notices have no ABN "
        f"({n(t.notices_no_abn_overseas)} of them with overseas suppliers) and use the API's supplier id |",
        f"| Agencies | {n(t.agencies)}, grouped by ABN and labelled with their latest name |",
        f"| Categories | The AusTender Customised UNSPSC Codeset (1 July 2023, data.gov.au, CC BY 3.0 AU): "
        f"{n(t.codeset_codes)} codes in {n(t.codeset_families)} families. All {n(t.codes_used)} codes on these "
        f"notices are in it ({n(t.codes_not_in_codeset)} missing). |",
        f"| Coarse codes | {n(t.segment_only_notices)} notices ({money(t.segment_only_value)}, "
        f"{pct(t.segment_only_value, total)} of value) are coded to a segment only. They count in segment "
        "totals but not in family tables; Part 4 tries to place them. |",
        f"| Defence | The Department of Defence holds {pct(t.defence_value, total)} of value, so results "
        "are shown with and without it. Other defence bodies (e.g. ASD) are counted as other agencies. |",
        "",
        f"{n(t.families_titled_by_hand)} families in the codeset have codes under them but no family title of "
        "their own. Their titles were written from the codes under them and are marked "
        "`derived from child codes` in the CSV: "
        + ", ".join(f"{r.family} *{r.family_title}*" for r in hand.itertuples()) + ".",
        "",
        "## Where the money goes",
        "",
        table(r["goods_services"], money_cols=("value", "median_notice"), pct_cols=("value_share",),
              int_cols=("notices",)),
        "",
        f"Services hold {share(gs.loc['Services', 'value_share'])} of committed value. The largest segment, "
        f"*{top_seg.segment_title}*, holds {share(top_seg.value_share)} on its own. "
        f"Defence holds {share(building.defence_share)} of *{building.segment_title}* "
        f"({money(building.value)}).",
        "",
        "![Committed value by UNSPSC segment, Defence and other agencies](charts/03_spend_by_segment.png)",
        "",
        "Top 12 of " + n(t.segments_used) + " segments:",
        "",
        table(seg.head(12)[["segment", "segment_title", "notices", "value", "value_share", "defence_share",
                            "median_notice"]],
              money_cols=("value", "median_notice"), pct_cols=("value_share", "defence_share"),
              int_cols=("notices",)),
        "",
        f"The 15 largest of {n(t.families_used)} families:",
        "",
        table(fam.head(15)[["family", "family_title", "notices", "value", "value_share", "defence_share",
                            "agencies", "suppliers"]],
              money_cols=("value",), pct_cols=("value_share", "defence_share"),
              int_cols=("notices", "agencies", "suppliers")),
        "",
        "## Agencies",
        "",
        f"Defence holds {share(defence.value_share)} of value from {n(defence.notices)} notices, with a median "
        f"notice of {money(defence.median_notice)}. The 15 largest agencies:",
        "",
        table(ag.head(15)[["agency", "notices", "value", "value_share", "median_notice", "suppliers",
                           "top5_supplier_share", "top_family", "top_family_share"]],
              money_cols=("value", "median_notice"),
              pct_cols=("value_share", "top5_supplier_share", "top_family_share"),
              int_cols=("notices", "suppliers")),
        "",
        "`top5_supplier_share`: the share of the agency's value held by its 5 largest suppliers. "
        "`top_family`: its largest category family (segment-only notices left out).",
        "",
        "## Suppliers",
        "",
        f"- {n(base.suppliers)} suppliers. **{n(base.suppliers_for_50pct)} of them hold half the committed "
        f"value** and {n(base.suppliers_for_80pct)} hold 80%. The top 10 hold {share(base.top10_share)}, "
        f"the top 100 {share(base.top100_share)}.",
        f"- {n(base.one_notice_suppliers)} suppliers ({pct(base.one_notice_suppliers, base.suppliers)}) "
        f"won exactly one notice; together they hold {share(base.one_notice_value_share)} of value.",
        "- Big totals are often one contract: `largest_notice_share` below is the supplier's single largest "
        "notice as a share of its total.",
        "",
        table(sup.head(15)[["supplier", "notices", "value", "value_share", "agencies", "families", "names",
                            "defence_share", "largest_notice_share"]],
              money_cols=("value",), pct_cols=("value_share", "defence_share", "largest_notice_share"),
              int_cols=("notices", "agencies", "families", "names")),
        "",
        "`FMS ACCOUNT RESERVE BANK OF AUSTRALIA` has no ABN and its notices are missiles, military "
        "helicopters and the like: it appears to be the account Defence uses to pay for US Foreign Military "
        "Sales, so it stands for many purchases from the US government, not one company. `names` counts "
        "the spellings used for one ABN; `families` is 0 where every notice is coded to a segment only "
        "(the vaccine supply contracts, for example).",
        "",
        "## Supplier concentration by category",
        "",
        f"For every \"large\" family ({LARGE}; {len(ca)} families, {money(large_value)}, "
        f"{pct(large_value, total)} of value), the table gives the top supplier's share and the "
        "Herfindahl-Hirschman Index (HHI): the sum of squared supplier shares, from near 0 (many small "
        "suppliers) to 10,000 (one supplier). The bands (under 1,500 low, 1,500 to 2,500 moderate, over "
        "2,500 high) are the ones in the 2010 US merger guidelines, used here only as a familiar scale.",
        "",
        "One financial year of notices is lumpy: a single multi-year contract can make a category look "
        "owned by one supplier. So each family is also measured **without its single largest notice**. "
        "If the HHI then drops to 2,500 or below, the concentration is *one contract*; if it stays high, "
        "it goes *beyond one contract*.",
        "",
        table(bands, money_cols=("value",), int_cols=("families",)),
        "",
        f"- **All agencies:** {lo[0]} of {len(ca)} large families are low ({money(lo[1])}), {mod[0]} moderate "
        f"({money(mod[1])}) and {hi_one[0] + hi_beyond[0]} high. Of the high ones, {hi_one[0]} are one contract "
        f"and {hi_beyond[0]} go beyond one contract ({money(hi_beyond[1])}, "
        f"{pct(hi_beyond[1], large_value)} of large-family value).",
        f"- **Without Defence:** {len(cx)} large families: {x_lo[0]} low, {x_mod[0]} moderate, "
        f"{x_one[0] + x_beyond[0]} high ({x_one[0]} one contract, {x_beyond[0]} beyond one contract, "
        f"{money(x_beyond[1])}).",
        "",
        "![Top supplier share and largest notice share in the 20 largest families](charts/04_family_concentration.png)",
        "",
        "Large families that are moderately or highly concentrated, all agencies:",
        "",
        conc_table(ca[ca.hhi_band != "low"]),
        "",
        "Highly concentrated without Defence:",
        "",
        conc_table(cx[cx.hhi_band == "high"]),
        "",
        "## Spread thin: many agencies, many suppliers",
        "",
        f"The opposite pattern: large families that at least 20 agencies buy and where it takes 30 or more "
        f"suppliers to reach 80% of the value. {len(frag)} families, {money(frag.value.sum())}. Here a "
        "category manager's question is whether pooled demand would get better terms. The API has no panel "
        "or standing-offer flag, so some of this may already go through whole-of-government panels; it's a "
        "list to check, not a finding.",
        "",
        table(frag[["family", "family_title", "value", "notices", "agencies", "suppliers",
                    "suppliers_for_80pct", "median_notice", "top1_share"]],
              money_cols=("value", "median_notice"), pct_cols=("top1_share",),
              int_cols=("notices", "agencies", "suppliers", "suppliers_for_80pct")),
        "",
        "## Files",
        "",
        "- `spend_cube.csv`: agency x segment x family x goods/services, with notices, suppliers, committed "
        f"value and value at award ({n(len(r['cube']))} rows; it adds up to the totals above). Ready to load "
        "into Power BI or a spreadsheet pivot.",
        "- `family_concentration.csv` and `family_concentration_ex_defence.csv`: every family, not just the large ones.",
        "- `top_suppliers.csv` (top 200) and `agency_spend.csv` (all agencies).",
        "",
        "## Limits",
        "",
        "- **Committed value, not payments.** A notice records what a contract is worth over its life, "
        "and multi-year contracts are booked in the year their notice was published.",
        "- **Concentration is the buyer's view.** It shows how much of the government's own spend goes to "
        "a few suppliers, not market share in the economy.",
        "- **Codes are the agency's choice.** A contract can sit in an unexpected family (Part 4 looks at "
        "coding quality), and segment-only notices are missing from the family tables.",
        "- **No panel flag** in the API, so a repeat winner may be the supplier of a central arrangement "
        "chosen through open competition.",
        "",
    ]
    return "\n".join(L)


def write_csvs(r: dict[str, pd.DataFrame], con) -> None:
    r["cube"].to_csv(RESULTS / "spend_cube.csv", index=False)
    con.sql("SELECT * FROM family_concentration(false) ORDER BY value DESC, family").df() \
        .to_csv(RESULTS / "family_concentration.csv", index=False)
    con.sql("SELECT * FROM family_concentration(true) ORDER BY value DESC, family").df() \
        .to_csv(RESULTS / "family_concentration_ex_defence.csv", index=False)
    r["suppliers"].head(200).to_csv(RESULTS / "top_suppliers.csv", index=False)
    r["agencies"].to_csv(RESULTS / "agency_spend.csv", index=False)


def main() -> None:
    CHARTS.mkdir(parents=True, exist_ok=True)
    snap = json.loads(SNAPSHOT.read_text())
    con = spend_connection()
    r = results(con)
    chart_segments(r["segments"], CHARTS / "03_spend_by_segment.png")
    chart_concentration(r["concentration_all"], CHARTS / "04_family_concentration.png")
    write_csvs(r, con)
    (RESULTS / "SPEND_CUBE.md").write_text(write_report(r, snap))
    print(f"wrote {RESULTS / 'SPEND_CUBE.md'}")


if __name__ == "__main__":
    main()
