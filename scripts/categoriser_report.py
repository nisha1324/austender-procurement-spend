"""Part 4 report: what Education and Training spend buys, and how well each categoriser sorts it.

Writes `results/CATEGORISER.md`, `results/training_categories.csv` (every notice with its offline
label and the rule that fired), `results/training_category_mix.csv` and two charts. With
`--backend claude` (see `scripts/categorise.py`) it also writes the Claude labels and adds their score.

    python -m scripts.categorise
"""
from __future__ import annotations

import json
import math

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from scripts import categorise as cat  # noqa: E402
from scripts.draw_check_set import CHECK_DIR, LARGE_FROM, population, training_connection  # noqa: E402
from scripts.profile_releases import (  # noqa: E402
    BLUE, CHARTS, INK, INK_2, MUTED, ORANGE, RESULTS, SNAPSHOT, SURFACE, _style, money, n, table,
)
from scripts.training_taxonomy import GROUPS, KEYS, NAMES  # noqa: E402

LABELS = CHECK_DIR / "training_labels.csv"
SOURCE_NOTE = "Source: AusTender OCDS API (Department of Finance), CC BY 3.0 AU."
BASIS_ORDER = ["description", "supplier_name", "outside_knowledge", "none"]
BASIS_NAMES = {"description": "The description says it", "supplier_name": "The supplier's name says it",
               "outside_knowledge": "Needs knowledge of the supplier or program",
               "none": "Nothing says it (unspecified)"}
GROUP_ORDER = ["Program delivery, not staff training", "Military and operational",
               "Staff development, topic known", "Topic unknown", "Not training (miscoded)"]


def no_math(s: str) -> str:
    return s.replace("$", r"\$")


def load_labels() -> pd.DataFrame:
    return pd.read_csv(LABELS, dtype={"cn_id": str}, keep_default_na=False)


def wilson(k: int, m: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson interval for a proportion k/m."""
    if m == 0:
        return (0.0, 0.0)
    p = k / m
    den = 1 + z * z / m
    mid = (p + z * z / (2 * m)) / den
    half = z * math.sqrt(p * (1 - p) / m + z * z / (4 * m * m)) / den
    return (max(0.0, mid - half), min(1.0, mid + half))


# ---------- estimates from the hand labels ----------
def category_mix(pop: pd.DataFrame, gold: pd.DataFrame) -> pd.DataFrame:
    """Estimated notices and value per category for the whole population.

    Notices of $1m+ are a census, so their totals are exact. Under $1m, the random sample's
    category shares (by count and by value) are applied to that stratum's real totals.
    """
    v = pop.value_aud.astype(float)
    small_n, small_v = int((v < LARGE_FROM).sum()), float(v[v < LARGE_FROM].sum())
    large = gold[gold.stratum == "large"]
    rand = gold[gold.stratum == "random"]
    rows = []
    for k in KEYS:
        lg, rd = large[large.label == k], rand[rand.label == k]
        rows.append({
            "category": k, "name": NAMES[k], "group": GROUPS[k],
            "large_notices": len(lg), "large_value": float(lg.value_aud.sum()),
            "sample_notices": len(rd), "sample_value": float(rd.value_aud.sum()),
            "est_small_notices": small_n * len(rd) / len(rand),
            "est_small_value": small_v * float(rd.value_aud.sum()) / float(rand.value_aud.sum()),
        })
    mix = pd.DataFrame(rows)
    mix["est_notices"] = mix.large_notices + mix.est_small_notices
    mix["est_value"] = mix.large_value + mix.est_small_value
    mix["value_share"] = mix.est_value / mix.est_value.sum()
    mix["notice_share"] = mix.est_notices / mix.est_notices.sum()
    return mix


def group_mix(mix: pd.DataFrame) -> pd.DataFrame:
    g = mix.groupby("group", sort=False)[["est_notices", "est_value", "large_value", "est_small_value",
                                          "sample_notices"]].sum()
    g = g.reindex(GROUP_ORDER).reset_index()
    g["value_share"] = g.est_value / g.est_value.sum()
    g["notice_share"] = g.est_notices / g.est_notices.sum()
    return g


# ---------- scoring ----------
def score(gold: pd.DataFrame, pred: pd.DataFrame) -> dict:
    """Accuracy of `pred` (cn_id, label) against the hand labels, overall and by stratum and basis."""
    m = gold.merge(pred[["cn_id", "label"]].rename(columns={"label": "pred"}), on="cn_id", how="left")
    assert m.pred.notna().all(), "every check-set notice needs a prediction"
    m["ok"] = m.label == m.pred
    out = {"rows": m}
    for s in ("random", "large"):
        part = m[m.stratum == s]
        out[s] = {"n": len(part), "correct": int(part.ok.sum()),
                  "value_correct": float(part.value_aud[part.ok].sum()), "value": float(part.value_aud.sum())}
    out["by_basis"] = (m.groupby("basis").ok.agg(["sum", "count"]).reindex(BASIS_ORDER).fillna(0).astype(int))
    per = []
    for k in KEYS:
        tp = int(((m.pred == k) & m.ok).sum())
        n_pred, n_gold = int((m.pred == k).sum()), int((m.label == k).sum())
        per.append({"category": k, "gold": n_gold, "predicted": n_pred, "correct": tp,
                    "precision": tp / n_pred if n_pred else float("nan"),
                    "recall": tp / n_gold if n_gold else float("nan")})
    out["per_category"] = pd.DataFrame(per)
    errs = m[~m.ok]
    out["confusions"] = (errs.groupby(["label", "pred"]).size().rename("notices")
                         .sort_values(ascending=False).reset_index())
    return out


def fmt_pct(x: float) -> str:
    return "n/a" if x != x else f"{100 * x:.1f}%"


# ---------- context ----------
def segment_context(con) -> pd.DataFrame:
    return con.sql("""
        SELECT segment, segment_title, count(*) AS notices, sum(value_aud) AS value,
               count(*) FILTER (description ILIKE '%vaccine%') AS vaccine_notices,
               coalesce(sum(value_aud) FILTER (description ILIKE '%vaccine%'), 0) AS vaccine_value,
               (SELECT count(*) FROM categories c WHERE c.segment = s.segment AND c.level = 'family') AS family_codes,
               (SELECT count(*) FROM categories c WHERE c.segment = s.segment AND c.level <> 'segment') AS finer_codes
        FROM spend s WHERE category_level = 'segment'
        GROUP BY 1, 2 ORDER BY notices DESC
    """).df()


# ---------- charts ----------
def chart_mix(mix: pd.DataFrame, out) -> None:
    d = mix.sort_values("est_value", ascending=True)
    fig, ax = plt.subplots(figsize=(9.5, 5.8), dpi=150, facecolor=SURFACE)
    _style(ax)
    y = range(len(d))
    ax.barh(y, d.large_value / 1e6, height=0.66, color=BLUE, label="Notices of $1m or more (all labelled)")
    ax.barh(y, d.est_small_value / 1e6, left=d.large_value / 1e6, height=0.66, color=ORANGE,
            label="Notices under $1m (estimated from 200 labelled at random)")
    for i, r in enumerate(d.itertuples()):
        ax.text(r.est_value / 1e6 + 4, i, no_math(f"{money(r.est_value)}  ·  ~{r.est_notices:,.0f} notices"),
                va="center", fontsize=8.3, color=INK_2)
    ax.set_yticks(list(y), [no_math(x) for x in d.name], color=INK, fontsize=8.6)
    ax.set_xlim(0, d.est_value.max() / 1e6 * 1.42)
    ax.set_xlabel("Committed contract value, $ million", color=INK_2, fontsize=9)
    fig.suptitle(no_math(f"What {money(mix.est_value.sum())} of 'Education and Training Services' buys"),
                 x=0.01, y=0.985, ha="left", color=INK, fontsize=11.5)
    h, lab = ax.get_legend_handles_labels()
    fig.legend(h, [no_math(x) for x in lab], loc="upper left", bbox_to_anchor=(0.005, 0.96), ncol=1,
               frameon=False, fontsize=8.6, labelcolor=INK_2, handlelength=1.2)
    fig.text(0.01, 0.012, "Active FY2024-25 notices coded only to UNSPSC segment 86, latest value; categories "
             "from hand labels. " + SOURCE_NOTE, fontsize=7, color=MUTED)
    fig.tight_layout(rect=(0, 0.03, 1, 0.94))
    fig.savefig(out, facecolor=SURFACE)
    plt.close(fig)


def chart_basis(sc: dict, out) -> None:
    b = sc["by_basis"]
    labels = [BASIS_NAMES[k] for k in b.index]
    acc = 100 * b["sum"] / b["count"].where(b["count"] > 0)
    fig, ax = plt.subplots(figsize=(9, 3.6), dpi=150, facecolor=SURFACE)
    _style(ax)
    y = range(len(b))
    ax.barh(list(y), acc, height=0.6, color=BLUE)
    for i, (a, k, c) in enumerate(zip(acc, b["sum"], b["count"])):
        ax.text(a + 1.2, i, f"{a:.0f}%  ({k} of {c})", va="center", fontsize=8.6, color=INK_2)
    ax.set_yticks(list(y), labels, color=INK, fontsize=8.8)
    ax.invert_yaxis()
    ax.set_xlim(0, 118)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_xlabel("Keyword baseline agrees with the hand label, %", color=INK_2, fontsize=9)
    fig.suptitle("The keyword rules work when the text says it, and fail when the label needs outside knowledge",
                 x=0.01, y=0.975, ha="left", color=INK, fontsize=10.5)
    fig.text(0.01, 0.015, "All 288 check-set notices, by what the hand label rests on. " + SOURCE_NOTE,
             fontsize=7, color=MUTED)
    fig.tight_layout(rect=(0, 0.04, 1, 0.92))
    fig.savefig(out, facecolor=SURFACE)
    plt.close(fig)


# ---------- report ----------
def write_report(pop, gold, mix, sc_off, ctx, base_pop, snap, sc_claude=None) -> str:
    total_n, total_v = len(pop), float(pop.value_aud.sum())
    v = pop.value_aud.astype(float)
    large_n, large_v = int((v >= LARGE_FROM).sum()), float(v[v >= LARGE_FROM].sum())
    rand = gold[gold.stratum == "random"]
    g = group_mix(mix).set_index("group")
    m = mix.set_index("category")

    seg_all_n, seg_all_v = int(ctx.notices.sum()), float(ctx.value.sum())
    none_ctx = ctx[ctx.family_codes == 0]  # 86 (two commodity codes, no families), 27, 51
    some_ctx = ctx[ctx.family_codes > 0]
    vac = ctx.set_index("segment").loc["51"]
    edu = ctx.set_index("segment").loc["86"]

    see = gold[(gold.stratum == "large") & gold.description.str.contains("Skills for Education and Employment")]
    fms = gold[(gold.stratum == "large") & gold.supplier_name.str.startswith("FMS ACCOUNT")]
    unknown_k = int(rand.label.isin(["tertiary", "unspecified"]).sum())
    lo, hi = wilson(unknown_k, len(rand))
    staff = g.loc["Staff development, topic known"]
    unk = g.loc["Topic unknown"]
    ok_basis = sc_off["by_basis"]
    r_, l_ = sc_off["random"], sc_off["large"]
    ok_text = ok_basis.loc[["description", "supplier_name"]].sum()
    rows_ = sc_off["rows"]
    n_err = int((~rows_.ok).sum())
    n_fallback = int(((~rows_.ok) & (rows_.pred == "unspecified")).sum())
    outside = gold[gold.basis == "outside_knowledge"]
    est = cat.estimate_calls(total_n)
    base = base_pop.groupby("label").agg(notices=("cn_id", "size"), value=("value_aud", lambda s: float(s.sum())))
    as_of = snap["fetched_to"][:10]

    L = []
    w = L.append
    w("# Part 4: what 'Education and Training' spend buys, and can a categoriser tell?\n")
    w(f"Generated by `python -m scripts.categorise` from the snapshot (amendments to {as_of}) and the hand-labelled "
      "check set in `data/check_set/`. Active notices, latest value, as in Parts 2 and 3.\n")

    w("## 1. Which notices need a category\n")
    w(f"{n(seg_all_n)} active notices ({money(seg_all_v)}) are coded only to a UNSPSC segment. For most of them, "
      "the AusTender codeset offers nothing finer: an agency buying training can only pick *Education and Training "
      "Services*.\n")
    show = ctx[["segment", "segment_title", "notices", "value", "family_codes", "finer_codes",
                "vaccine_notices", "vaccine_value"]]
    show.columns = ["Segment", "Title", "Notices", "Value", "Family codes in the codeset", "All finer codes",
                    "Vaccine notices", "Vaccine value"]
    w(table(show, money_cols=("Value", "Vaccine value"), int_cols=("Notices", "Vaccine notices")) + "\n")
    w(f"- Segments with no family-level code ({', '.join(none_ctx.segment)}; segment 86 has only two narrow "
      f"commodity codes, for vocational rehabilitation and library services): **{n(none_ctx.notices.sum())} notices, "
      f"{money(none_ctx.value.sum())}** ({100 * none_ctx.notices.sum() / seg_all_n:.1f}% of segment-only notices). "
      "These aren't lazy coding; the codeset leaves no choice.")
    w(f"- Drugs and pharmaceuticals is {money(vac.value)}, but {n(vac.vaccine_notices)} vaccine notices "
      f"({money(vac.vaccine_value)}) are {100 * vac.vaccine_value / vac.value:.1f}% of it, and their descriptions "
      "already say what they are.")
    w(f"- Segments where agencies could have picked a family: {n(some_ctx.notices.sum())} notices, "
      f"{money(some_ctx.value.sum())}.")
    w(f"- **Education and Training is where a categoriser earns its keep:** {n(edu.notices)} notices, "
      f"{money(edu.value)}, with descriptions such as 'Training Services'. Part 4 sorts these.\n")

    w("## 2. The check set\n")
    w("The taxonomy (`scripts/training_taxonomy.py`) has 12 categories, in five groups, chosen for what a category "
      "manager would do with the spend. All {0} notices of $1m or more were labelled (a census, {1} of the value), "
      "plus 200 drawn at random from the {2} under $1m (seed 2025). One annotator labelled every row from the "
      "description, supplier and agency only, following `data/check_set/LABELLING_GUIDE.md`, and the labels were "
      "committed before the keyword rules were written.\n".format(
          n(large_n), f"{100 * large_v / total_v:.1f}%", n(total_n - large_n)))
    bb = gold.groupby(["basis", "stratum"]).size().unstack(fill_value=0).reindex(BASIS_ORDER).fillna(0).astype(int)
    tb = pd.DataFrame({"What the label rests on": [BASIS_NAMES[b] for b in bb.index],
                       "$1m+ notices": bb["large"].values, "Random sample": bb["random"].values})
    w(table(tb) + "\n")
    w(f"{len(outside)} of {len(gold)} labels ({100 * len(outside) / len(gold):.1f}%) needed knowledge that isn't in "
      "the notice: what SANS, Cubic, QinetiQ or Jeff Whalan Learning sell, or that *Be Connected* is a program for "
      "older Australians. No keyword rule can supply that.\n")

    w("## 3. What the money buys (from the hand labels)\n")
    w(f"Notices of $1m or more are exact. Under $1m, the random sample's shares (by count and by value) are applied "
      f"to that stratum's real totals, so those figures are estimates: for example, the share of small notices whose "
      f"topic is unknown is {100 * unknown_k / len(rand):.1f}% in the sample (95% interval {100 * lo:.1f}% to "
      f"{100 * hi:.1f}%).\n")
    gt = g.reset_index()[["group", "est_notices", "notice_share", "est_value", "value_share", "large_value"]]
    gt.columns = ["Group", "Notices (est.)", "Share of notices", "Value (est.)", "Share of value", "Of which $1m+ (exact)"]
    gt["Notices (est.)"] = gt["Notices (est.)"].round().astype(int)
    w(table(gt, money_cols=("Value (est.)", "Of which $1m+ (exact)"), pct_cols=("Share of notices", "Share of value"),
            int_cols=("Notices (est.)",)) + "\n")
    ct = mix[["name", "group", "large_notices", "sample_notices", "est_notices", "est_value", "value_share"]].copy()
    ct["est_notices"] = ct.est_notices.round().astype(int)
    ct.columns = ["Category", "Group", "$1m+ notices", "In random sample", "Notices (est.)", "Value (est.)",
                  "Share of value"]
    w(table(ct.sort_values("Value (est.)", ascending=False), money_cols=("Value (est.)",),
            pct_cols=("Share of value",), int_cols=("Notices (est.)",)) + "\n")
    w("![What Education and Training spend buys](charts/07_training_mix.png)\n")
    w(f"- **Over half the value isn't training staff at all.** Programs delivered to the public are "
      f"{money(g.loc['Program delivery, not staff training'].est_value)} "
      f"({100 * g.loc['Program delivery, not staff training'].value_share:.1f}%) in about "
      f"{g.loc['Program delivery, not staff training'].est_notices:,.0f} notices. The Skills for Education and "
      f"Employment program alone is {len(see)} notices and {money(see.value_aud.sum())}.")
    mil = g.loc["Military and operational"]
    w(f"- **Military and operational training** is {money(mil.est_value)} ({100 * mil.value_share:.1f}%), "
      f"{100 * mil.large_value / mil.est_value:.0f}% of it in notices of $1m or more. The largest is training bought "
      f"through what appears to be the US Foreign Military Sales account ({money(fms.value_aud.sum())}, "
      f"{len(fms)} notices); most of the rest is training systems (such as the P-8A's) and defence simulation and "
      "training firms such as Cubic, QinetiQ, Saab and Kongsberg.")
    w(f"- **Staff development with a known topic** is about {money(staff.est_value)} in about "
      f"{staff.est_notices:,.0f} notices ({100 * staff.notice_share:.1f}% of notices): professional and technical "
      "skills, IT and data, leadership and coaching, languages, safety, memberships.")
    w(f"- **A further {money(unk.est_value)}, in about {unk.est_notices:,.0f} notices ({100 * unk.notice_share:.1f}%), "
      "can't be placed at all:** the notice says only something like 'Training Services' and the supplier's name "
      "doesn't say what the training is (a university or TAFE, or an unknown firm). Together with the known "
      f"topics, that puts agencies' own staff development here at {money(staff.est_value + unk.est_value)} at most.")
    w(f"- **Not training:** about {money(g.loc['Not training (miscoded)'].est_value)} "
      f"({g.loc['Not training (miscoded)'].est_notices:,.0f} notices) is catering, venues, school fees, care "
      "services, quality assurance, consulting, internships and similar, coded as education.\n")

    w("## 4. How well the keyword baseline does\n")
    w("`scripts/categorise.py` applies ordered keyword rules to the description and supplier name. It records the "
      "rule that fired, so every label can be explained. It was scored once against the check set; the rules "
      "weren't changed after seeing the score.\n")
    sc_rows = pd.DataFrame([
        {"Check set": "Random sample (typical notice)", "Notices": r_["n"], "Agrees with hand label": r_["correct"],
         "Accuracy": r_["correct"] / r_["n"], "Accuracy by value": r_["value_correct"] / r_["value"]},
        {"Check set": "$1m+ notices (the money)", "Notices": l_["n"], "Agrees with hand label": l_["correct"],
         "Accuracy": l_["correct"] / l_["n"], "Accuracy by value": l_["value_correct"] / l_["value"]},
    ])
    w(table(sc_rows, pct_cols=("Accuracy", "Accuracy by value")) + "\n")
    bt = pd.DataFrame({"What the label rests on": [BASIS_NAMES[b] for b in ok_basis.index],
                       "Notices": ok_basis["count"].values, "Baseline agrees": ok_basis["sum"].values,
                       "Accuracy": (ok_basis["sum"] / ok_basis["count"]).values})
    w(table(bt, pct_cols=("Accuracy",)) + "\n")
    w("![Baseline accuracy by what the label rests on](charts/08_baseline_by_basis.png)\n")
    w(f"Where the notice's own words say the category, the rules agree with the hand label {ok_text['sum']} times out of "
      f"{ok_text['count']} ({100 * ok_text['sum'] / ok_text['count']:.1f}%). Where the label needs outside knowledge, "
      f"{ok_basis.loc['outside_knowledge', 'sum']} of {ok_basis.loc['outside_knowledge', 'count']}. Of the "
      f"{n_err} disagreements, {n_fallback} are the rules saying 'unspecified' where the hand label has a category; "
      f"only {n_err - n_fallback} put a notice in a different category. So the baseline is cautious rather than wrong:\n")
    pc = sc_off["per_category"].copy()
    pc["category"] = pc.category.map(NAMES)
    pc.columns = ["Category", "Hand labels", "Baseline labels", "Both agree", "Precision", "Recall"]
    pc["Precision"] = pc.Precision.map(fmt_pct)
    pc["Recall"] = pc.Recall.map(fmt_pct)
    w(table(pc) + "\n")
    named = sc_off["per_category"].query("category != 'unspecified' and predicted > 0")
    w(f"For {int((named.precision >= 0.85).sum())} of the {len(named)} named categories, at least 85% of the "
      "baseline's labels agree with the hand label. When the rules name a category, the label can usually be "
      "trusted; the work is in what they leave as 'unspecified'.\n")
    cf = sc_off["confusions"].head(8).copy()
    cf["label"], cf["pred"] = cf.label.map(NAMES), cf.pred.map(NAMES)
    cf.columns = ["Hand label", "Baseline label", "Notices"]
    w("Most common disagreements:\n")
    w(table(cf) + "\n")

    w("## 5. The baseline on every notice\n")
    bu, hu = base.loc["unspecified"], m.loc["unspecified"]
    w(f"Run on all notices, the baseline leaves {n(bu.notices)} notices ({money(bu.value)}) as 'unspecified', against "
      f"about {hu.est_notices:,.0f} ({money(hu.est_value)}) in the hand-label estimate: {bu.notices / hu.est_notices:.1f} "
      f"times by count and {bu.value / hu.est_value:.1f} times by value, because it can't use what suppliers are known "
      "for. Use its labels for the categories it names; treat its 'unspecified' as an upper bound.\n")
    cmp_ = pd.DataFrame({
        "Category": [NAMES[k] for k in KEYS],
        "Baseline notices": [int(base.notices.get(k, 0)) for k in KEYS],
        "Baseline value": [float(base.value.get(k, 0.0)) for k in KEYS],
        "Hand-label estimate, notices": [int(round(m.loc[k, "est_notices"])) for k in KEYS],
        "Hand-label estimate, value": [float(m.loc[k, "est_value"]) for k in KEYS],
    })
    w(table(cmp_, money_cols=("Baseline value", "Hand-label estimate, value"),
            int_cols=("Baseline notices", "Hand-label estimate, notices")) + "\n")

    w("## 6. The Claude backend\n")
    if sc_claude is None:
        w("**Not run: no `ANTHROPIC_API_KEY`.** The backend is built and tested with a fake client "
          "(`tests/test_categorise.py`): the same taxonomy and decision order as a prompt, a forced tool call with "
          "the category as an enum, batches of "
          f"{cat.BATCH_SIZE}, and any missing or invalid answer falls back to the baseline label and is counted. "
          f"One run over all {n(total_n)} notices is about {est['calls']} calls, ~{est['input_tokens'] // 1000}k "
          f"input and ~{est['output_tokens'] // 1000}k output tokens (model `{cat.MODEL}` by default; set "
          "`CLAUDE_MODEL` to change it). The check set shows where it could help: the "
          f"{len(outside)} labels that rest on outside knowledge, where the baseline gets "
          f"{ok_basis.loc['outside_knowledge', 'sum']} right.\n")
    else:
        cr_, cl_ = sc_claude["random"], sc_claude["large"]
        cb = sc_claude["by_basis"]
        w(f"Model `{cat.MODEL}`. Random sample: {cr_['correct']} of {cr_['n']} ({100 * cr_['correct'] / cr_['n']:.1f}%); "
          f"$1m+ notices: {cl_['correct']} of {cl_['n']} ({100 * cl_['value_correct'] / cl_['value']:.1f}% by value). "
          f"Outside-knowledge labels: {cb.loc['outside_knowledge', 'sum']} of {cb.loc['outside_knowledge', 'count']}.\n")
    return "\n".join(L)


def write_csvs(pop, base_pop, mix, claude=None) -> None:
    out = pop[["cn_id", "agency", "supplier_name", "description", "value_aud", "is_defence"]].merge(
        base_pop[["cn_id", "label", "rule"]].rename(columns={"label": "offline_label", "rule": "offline_rule"}),
        on="cn_id")
    if claude is not None:
        out = out.merge(claude.rename(columns={"label": "claude_label", "rule": "claude_rule"}), on="cn_id")
    out.sort_values("cn_id").to_csv(RESULTS / "training_categories.csv", index=False)
    mx = mix.copy()
    for c in ("est_notices", "est_small_notices"):
        mx[c] = mx[c].round(1)
    for c in ("est_value", "est_small_value", "large_value", "sample_value"):
        mx[c] = mx[c].round(2)
    for c in ("value_share", "notice_share"):
        mx[c] = mx[c].round(6)
    mx.to_csv(RESULTS / "training_category_mix.csv", index=False)


def main(backend: str = "offline") -> None:
    CHARTS.mkdir(parents=True, exist_ok=True)
    snap = json.loads(SNAPSHOT.read_text())
    con = training_connection()
    pop = population(con)
    gold = load_labels()
    base_pop = pop[["cn_id", "value_aud"]].merge(cat.label_offline(pop), on="cn_id")
    sc_off = score(gold, base_pop)
    mix = category_mix(pop, gold)
    claude, sc_claude = None, None
    if backend == "claude":
        claude = cat.label_claude(pop)
        sc_claude = score(gold, claude)
    chart_mix(mix, CHARTS / "07_training_mix.png")
    chart_basis(sc_off, CHARTS / "08_baseline_by_basis.png")
    write_csvs(pop, base_pop, mix, claude)
    report = write_report(pop, gold, mix, sc_off, segment_context(con), base_pop, snap, sc_claude)
    (RESULTS / "CATEGORISER.md").write_text(report)
    print(f"wrote {RESULTS / 'CATEGORISER.md'}")
