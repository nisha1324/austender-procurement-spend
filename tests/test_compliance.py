"""Part 3 queries on hand-written notices with answers worked out by hand, a synthetic bunching
check, then checks on the committed results."""
import json
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from scripts import build_snapshot as bs
from scripts import compliance as cp
from scripts.profile_releases import SQL_DIR, named_queries

from tests.test_spend import CATEGORIES

ROOT = Path(__file__).resolve().parent.parent
JULY_1 = "2024-06-30T14:00:00Z"  # 1 Jul 2024 in Canberra


def nt(release, cn, value, n=0, method="open", reason=None, exemption=None, published="2024-07-01T00:00:00Z",
       start=JULY_1, abn="11111111111", desc="Widgets", agency=None):
    rel = release(cn=cn, n=n, value=f"{value}.00", method=method, published=published, abn=abn,
                  supplier=f"Supplier {abn}")
    c = rel["contracts"][0]
    c["period"]["startDate"] = start
    c["description"] = desc
    if reason:
        rel["tender"]["limitedTenderReasonCode"] = reason
        rel["tender"]["limitedTenderReason"] = "a 10.3 condition"
    if exemption:
        rel["tender"]["limitedTenderExempt"] = "1"
        rel["tender"]["exemptionCode"] = exemption
        rel["tender"]["exemption"] = "an exemption"
    if agency:
        rel["parties"][1]["name"] = agency
        rel["parties"][1]["additionalIdentifiers"] = [{"id": "12345678901", "scheme": "AU-ABN"}]
    return rel


@pytest.fixture
def r(release, tmp_path):
    rels = [
        nt(release, "CN1", 100000),                                            # open, from $80k
        nt(release, "CN2", 200000, method="limited", reason="TR"),             # a 10.3 condition
        nt(release, "CN3", 150000, method="limited", exemption="GE"),          # an exemption
        nt(release, "CN4", 90000, method="limited"),                           # neither ...
        nt(release, "CN4", 50000, n=1, method="limited"),                      # ... then amended below $80k
        nt(release, "CN5", 70000, method="limited"),                           # under $80k at award ...
        nt(release, "CN5", 120000, n=1, method="limited"),                     # ... grew past it
        nt(release, "CN6", 10000),                                             # placeholder ...
        nt(release, "CN6", 200000, n=1),                                       # ... amended twentyfold
        nt(release, "CN13", 9000),                                             # under $10k: not a placeholder
        nt(release, "CN13", 12000, n=1),
        # Split group: same agency, supplier, description and start, 19 days apart, $100k together.
        nt(release, "CN7", 50000, method="limited", abn="22222222222", desc="Cleaning"),
        nt(release, "CN8", 50000, method="limited", abn="22222222222", desc="Cleaning",
           published="2024-07-20T00:00:00Z"),
        # Not a group: 40 days apart.
        nt(release, "CN9", 50000, method="limited", abn="22222222222", desc="Catering"),
        nt(release, "CN10", 50000, method="limited", abn="22222222222", desc="Catering",
           published="2024-08-10T00:00:00Z"),
        # Not a group: under $80k together.
        nt(release, "CN11", 30000, method="limited", abn="33333333333", desc="Repairs"),
        nt(release, "CN12", 30000, method="limited", abn="33333333333", desc="Repairs"),
        # Late: 10 on one day (a batch, 62 days after a 1 July start), then 1 on another day (50 days).
        *[nt(release, f"CN2{k}", 20000, agency="Department of Late", published="2024-09-01T00:00:00Z",
             abn=f"4444444444{k}", desc="Agreement") for k in range(10)],
        nt(release, "CN30", 20000, agency="Department of Late", published="2024-08-20T00:00:00Z"),
    ]
    # Fetched under its own Canberra publish day (all fixtures are published at 10:00 Canberra).
    rows = [bs.flatten_release(x, x["contracts"][0]["dateSigned"][:10]) for x in rels]
    df = bs.build(pd.DataFrame(rows, columns=bs.COLUMNS))
    path = tmp_path / "releases.csv.gz"
    df.to_csv(path, index=False, compression={"method": "gzip", "mtime": 0})
    cats = tmp_path / "cats.csv"
    CATEGORIES.to_csv(cats, index=False)
    return cp.results(cp.compliance_connection(path, cats))


def test_routes_and_the_80k_line_use_the_value_at_award(r):
    t = r["totals"].iloc[0]
    assert t.notices == 24  # CN1 to CN13, ten batch notices, CN30
    assert t.notices_80k == 4 and t.limited_80k == 3  # CN5 is $70k at award, CN4 $90k
    assert t.no_code_80k == 1 and t.no_code_80k_amended_below == 1
    routes = r["routes"].set_index("route").notices.to_dict()
    assert routes == {"1. Open tender": 1, "3. Limited: a 10.3 condition": 1, "4. Limited: an exemption": 1,
                      "5. Limited: no reason or exemption code": 1}
    codes = r["limited_codes"].set_index("code")
    assert codes.loc["TR", "kind"] == "10.3 condition" and codes.loc["GE", "kind"] == "exemption"


def test_crossed_threshold_and_placeholders(r):
    ct = r["crossed_threshold"].set_index("method")
    assert ct.loc["limited", "notices"] == 1 and float(ct.loc["limited", "current_value"]) == 120000
    assert ct.loc["open", "notices"] == 1 and ct.loc["open", "from_10000"] == 1
    ph = r["placeholders"]
    assert len(ph) == 1 and ph.notices.iloc[0] == 1 and ph.tenfold.iloc[0] == 1
    g = r["growth_totals"].iloc[0]
    assert g.grew == 3 and g.tenfold == 1
    assert float(g.net_added) == (120000 - 70000) + (200000 - 10000) + (12000 - 9000) - (90000 - 50000)


def test_split_groups(r):
    s = r["split_summary"].iloc[0]
    assert s.groups == 1 and s.notices == 2 and float(s.award_value) == 100000
    by = r["split_by_agency"]
    assert by.largest_group_description.tolist() == ["cleaning"]


def test_late_publication_and_batches(r):
    lt = r["late_totals"].iloc[0]
    assert lt.late == 11 and lt.late_43_90 == 11
    b = r["late_batches"].iloc[0]
    assert b.batch_days == 1 and b.late_in_batches == 10 and b.batch_share == pytest.approx(10 / 11)
    top = r["late_top_batches"].iloc[0]
    assert (top.agency, top.published, top.late, top.median_lag) == ("Department of Late", "2024-09-01", 10, 62)
    assert (top.main_start, top.main_start_notices) == ("2024-07-01", 10)


def test_bunching_arithmetic():
    """10 notices in each neighbouring bin, 30 in the last $1,000 before $80k (15 limited),
    and 50 at exactly $80,000 (the bin that starts at the amount, left out): ratio 3.0."""
    rows = [(b + 500.5, "open") for b in (75000, 76000, 77000, 78000, 81000, 82000, 83000, 84000)
            for _ in range(10)]
    rows += [(79500.5, "limited" if i < 15 else "open") for i in range(30)]
    rows += [(80000.0, "open")] * 50
    con = duckdb.connect()
    con.execute("CREATE TABLE comp (award_value DECIMAL(18, 2), method VARCHAR)")
    con.executemany("INSERT INTO comp VALUES (?, ?)", rows)
    q = named_queries(SQL_DIR / "compliance.sql")
    p = con.sql(q["bunching_points"]).df().set_index("amount").loc[80000]
    assert p.last_1k == 30 and p.neighbour_mean == 10 and p.ratio == 3.0 and p.ratio_not_round == 3.0
    assert p.last_1k_limited_share == 0.5 and p.neighbour_limited_share == 0
    scan = con.sql(q["bunching_scan"]).df().set_index("bin")
    assert scan.loc[79000, "ratio"] == 3.0 and scan.loc[79000, "same_value_max"] == 30
    # The $80k bin is all whole thousands, so it can't top the not-round ranking.
    assert scan.index[0] == 79000


# ---------- the committed results ----------
@pytest.fixture(scope="module")
def real():
    con = cp.compliance_connection()
    return con, cp.results(con)


def test_real_routes_add_up(real):
    _, r = real
    t = r["totals"].iloc[0]
    assert r["routes"].notices.sum() == t.notices_80k
    lim = r["routes"][r["routes"].route.str.startswith(("3.", "4.", "5."))]
    assert lim.notices.sum() == t.limited_80k
    coded = lim[~lim.route.str.startswith("5.")].notices.sum()
    assert r["limited_codes"].notices.sum() == coded
    assert t.notices_80k + t.notices_under_80k == t.notices


def test_real_bunching_recomputed_in_pandas(real):
    con, r = real
    v = con.sql("SELECT award_value::DOUBLE AS v FROM comp").df().v
    last = ((v >= 79000) & (v < 80000)).sum()
    nb = sum(((v >= lo) & (v < lo + 1000)).sum() for lo in (75000, 76000, 77000, 78000, 81000, 82000, 83000, 84000))
    p = r["bunching_points"].set_index("amount").loc[80000]
    assert p.last_1k == last and p.ratio == round(last / (nb / 8), 2)
    assert r["bunching_scan"].bin.iloc[0] == 79000


def test_real_late_batches_are_consistent(real):
    _, r = real
    la, lb = r["late_by_agency"], r["late_batches"].iloc[0]
    assert (la.late_in_batches <= la.late).all()
    assert la.late_in_batches.sum() <= lb.late_in_batches
    assert r["late_totals"].iloc[0].late == lb.late


def test_report_and_csvs_regenerate_identically(real, tmp_path, monkeypatch):
    con, r = real
    snap = json.loads(cp.SNAPSHOT.read_text())
    assert cp.write_report(r, snap) == (ROOT / "results" / "COMPLIANCE.md").read_text()
    monkeypatch.setattr(cp, "RESULTS", tmp_path)
    cp.write_csvs(con)
    for p in tmp_path.glob("*.csv"):
        assert p.read_text() == (ROOT / "results" / p.name).read_text(), p.name
