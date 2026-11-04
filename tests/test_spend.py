"""Part 2 queries on hand-written notices with answers worked out by hand, then checks on the
committed results."""
import json
from pathlib import Path

import pandas as pd
import pytest

from scripts import build_snapshot as bs
from scripts import spend_cube as sc

ROOT = Path(__file__).resolve().parent.parent

CATEGORIES = pd.DataFrame([
    # code, title, level, goods_services, segment, segment_title, family, family_title, source
    ("43211500", "Computers", "class", "Goods", "43", "IT", "4321", "Computer equipment", "codeset"),
    ("80111600", "Temporary personnel", "class", "Services", "80", "Management", "8011", "HR services", "codeset"),
    ("80000000", "Management", "segment", "Services", "80", "Management", "", "", ""),
], columns=["code", "title", "level", "goods_services", "segment", "segment_title", "family",
            "family_title", "family_title_source"])


def notice(release, cn, value, abn, supplier=None, code="43211500", n=0, agency=None, status="active"):
    rel = release(cn=cn, n=n, value=f"{value}.00", abn=abn, supplier=supplier or f"Supplier {abn}")
    rel["contracts"][0]["items"][0]["classification"]["id"] = code
    rel["contracts"][0]["status"] = status
    if agency:
        rel["parties"][1]["name"] = agency
        rel["parties"][1]["additionalIdentifiers"] = [{"id": "62950639680", "scheme": "AU-ABN"}]
    return rel


@pytest.fixture
def con(release, tmp_path):
    rels = [
        # Family 4321: one big contract (A, 600k) and eight suppliers with 50k each.
        # HHI = 10,000 x (0.6^2 + 8 x 0.05^2) = 3,800; without the 600k notice, 8 x 1/8^2 -> 1,250.
        notice(release, "CN1", 600000, "10000000001"),
        *[notice(release, f"CN1{k}", 50000, f"2000000000{k}") for k in range(8)],
        # Family 8011: E wins five 100k notices (one under another spelling), F one notice that was
        # 50k at award and amended to 100k. E = 5/6, F = 1/6: HHI 7,222. Without the largest notice
        # (all 100k; the first by cn_id, one of E's): E 0.8, F 0.2 -> 6,800.
        *[notice(release, f"CN2{k}", 100000, "30000000001", code="80111600") for k in range(4)],
        notice(release, "CN24", 100000, "30000000001", supplier="E PTY LTD (alt)", code="80111600"),
        notice(release, "CN25", 50000, "40000000001", code="80111600"),
        notice(release, "CN25", 100000, "40000000001", code="80111600", n=1),
        # Cancelled: never counts, however large.
        notice(release, "CN30", 9000000, "30000000001", code="80111600", status="cancelled"),
        # Coded to a segment only: counts in totals, not in families.
        notice(release, "CN40", 70000, "50000000001", code="80000000"),
    ]
    # One of the 50k suppliers in 4321 is a Defence notice.
    rels[1] = notice(release, "CN10", 50000, "20000000000", agency="Department of Defence")
    rows = [bs.flatten_release(r, "2024-07-01") for r in rels]
    df = bs.build(pd.DataFrame(rows, columns=bs.COLUMNS))
    path = tmp_path / "releases.csv.gz"
    df.to_csv(path, index=False, compression={"method": "gzip", "mtime": 0})
    cats = tmp_path / "cats.csv"
    CATEGORIES.to_csv(cats, index=False)
    return sc.spend_connection(path, cats)


def conc(con, leave_out_defence=False):
    return con.sql(f"SELECT * FROM family_concentration({str(leave_out_defence).lower()})").df() \
        .set_index("family")


def test_spend_view_applies_the_part1_rules(con):
    t = con.sql("SELECT count(*), sum(value_aud), count(DISTINCT supplier_key), "
                "count(*) FILTER (family IS NULL) FROM spend").fetchone()
    # 9 + 6 + 1 active notices (the cancelled one out), amended CN25 at its latest value.
    assert t[0] == 16
    assert float(t[1]) == 600000 + 8 * 50000 + 6 * 100000 + 70000
    assert t[2] == 1 + 8 + 2 + 1  # E's two spellings are one supplier
    assert t[3] == 1


def test_one_big_contract(con):
    f = conc(con).loc["4321"]
    assert f.value == 1_000_000 and f.notices == 9 and f.suppliers == 9
    assert f.hhi == 3800 and f.hhi_without_largest == 1250
    assert f.top1_share == pytest.approx(0.6) and f.top_supplier_largest_notice_share == pytest.approx(0.6)
    assert f.largest_notice_share == pytest.approx(0.6)
    assert (f.hhi_band, f.driver) == ("high", "one contract")
    assert f.top_supplier == "Supplier 10000000001"
    assert f.suppliers_for_80pct == 5  # 0.6 + 4 x 0.05


def test_concentration_beyond_one_contract(con):
    f = conc(con).loc["8011"]
    assert f.value == 600_000 and f.notices == 6 and f.suppliers == 2
    assert f.hhi == 7222 and f.hhi_without_largest == 6800
    assert f.top1_share == pytest.approx(5 / 6) and f.top_supplier_notices == 5
    assert (f.hhi_band, f.driver) == ("high", "beyond one contract")
    assert f.top_supplier == "Supplier 30000000001"  # the most used spelling


def test_leaving_out_defence(con):
    f = conc(con, True).loc["4321"]
    assert f.value == 950_000 and f.suppliers == 8
    expected = 10000 * ((600 / 950) ** 2 + 7 * (50 / 950) ** 2)
    assert f.hhi == round(expected)


def test_cube_adds_up(con):
    r = sc.results(con)
    cube, t = r["cube"], r["totals"].iloc[0]
    assert cube.notices.sum() == t.notices == 16
    assert float(cube.value.sum()) == float(t.value)
    assert float(cube.value_at_award.sum()) == float(t.value) - 50000
    assert set(cube.family_title) == {"Computer equipment", "HR services", "(segment only)"}
    assert t.defence_notices == 1 and t.segment_only_notices == 1


def test_agency_label_is_the_latest_name(con):
    labels = con.sql("SELECT agency_label FROM agency_labels ORDER BY 1").df().agency_label.tolist()
    assert labels == ["Department of Defence", "Department of Examples"]


# ---------- the committed results ----------
@pytest.fixture(scope="module")
def real():
    con = sc.spend_connection()
    return con, sc.results(con)


def test_every_code_is_in_the_codeset(real):
    t = real[1]["totals"].iloc[0]
    assert t.codes_not_in_codeset == 0
    active = real[0].sql("SELECT count(*) FROM notices WHERE status = 'active'").fetchone()[0]
    assert t.notices == active


def test_real_cube_and_families_add_up(real):
    con, r = real
    t = r["totals"].iloc[0]
    assert r["cube"].notices.sum() == t.notices
    assert float(r["cube"].value.sum()) == pytest.approx(float(t.value), abs=0.01)
    fam, seg_only, total = con.sql(
        "SELECT (SELECT sum(value) FROM family_concentration(false)), "
        "sum(value_aud) FILTER (family IS NULL), sum(value_aud) FROM spend").fetchone()
    assert fam + seg_only == total  # exact: DECIMAL sums
    assert r["agencies"].value.astype(float).sum() == pytest.approx(float(t.value), rel=1e-12)


def test_hhi_bounds(real):
    con, _ = real
    f = con.sql("SELECT * FROM family_concentration(false)").df()
    assert f.hhi.between(1, 10000).all() and f.hhi_without_largest.between(0, 10000).all()
    assert (f.top1_share >= f.top_supplier_largest_notice_share - 1e-12).all()
    assert (f.largest_notice_share >= f.top_supplier_largest_notice_share - 1e-12).all()


def test_report_and_csvs_regenerate_identically(real, tmp_path, monkeypatch):
    con, r = real
    snap = json.loads(sc.SNAPSHOT.read_text())
    assert sc.write_report(r, snap) == (ROOT / "results" / "SPEND_CUBE.md").read_text()
    monkeypatch.setattr(sc, "RESULTS", tmp_path)
    sc.write_csvs(r, con)
    for p in tmp_path.glob("*.csv"):
        assert p.read_text() == (ROOT / "results" / p.name).read_text(), p.name
