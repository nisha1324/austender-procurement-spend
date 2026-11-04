"""The UNSPSC codeset parser, on a hand-written sheet, and the committed lookup it produced."""
from pathlib import Path

import pandas as pd
import pytest

from scripts import build_categories as bc

ROOT = Path(__file__).resolve().parent.parent


def sheet(rows):
    return pd.DataFrame(rows, columns=["code", "title", "definition", "goods_services"])


GOOD = [
    (None, "Office Equipment", "A segment row has no code.", None),
    ("44100000", "Office machines", None, "Goods"),
    ("44101500", "Duplicating machines", None, "Goods"),
    ("50000000", "Food and Beverage Products", None, "Goods"),   # a segment with a code
    ("50190000", "Prepared foods", None, "Goods"),
    (None, "Management Services", None, None),
    ("80111600", "Temporary personnel services", None, "Services"),  # family 8011 has no row
    ("80111620", "Temporary clerical services", None, "Services"),
]


def test_parse_builds_the_hierarchy(monkeypatch):
    monkeypatch.setattr(bc, "FAMILY_TITLES_FROM_CHILDREN", {"8011": "Labour hire"})
    out = bc.parse(sheet(GOOD)).set_index("code")
    assert list(out.columns) == bc.COLUMNS[1:]
    assert out.loc["44101500", "segment_title"] == "Office Equipment"
    assert out.loc["44101500", "family_title"] == "Office machines"
    assert out.loc["44101500", "level"] == "class"
    assert out.loc["50000000", "level"] == "segment" and out.loc["50000000", "family"] == ""
    assert out.loc["50190000", "segment_title"] == "Food and Beverage Products"
    assert out.loc["80111620", "level"] == "commodity"
    assert out.loc["80111620", "family_title"] == "Labour hire"
    assert out.loc["80111620", "family_title_source"] == "derived from child codes"
    assert out.loc["44100000", "family_title_source"] == "codeset"


def test_parse_refuses_a_family_without_a_title(monkeypatch):
    monkeypatch.setattr(bc, "FAMILY_TITLES_FROM_CHILDREN", {})
    with pytest.raises(ValueError, match="no title"):
        bc.parse(sheet(GOOD))


def test_parse_refuses_a_hand_title_for_a_named_family(monkeypatch):
    monkeypatch.setattr(bc, "FAMILY_TITLES_FROM_CHILDREN", {"8011": "x", "4410": "y"})
    with pytest.raises(ValueError, match="codeset names"):
        bc.parse(sheet(GOOD))


@pytest.mark.parametrize("bad, match", [
    ([("4410000", "Short code", None, "Goods")], "8 digits"),
    ([(None, "Seg", None, None), ("44100000", "A", None, "Goods"), ("44100000", "B", None, "Goods")],
     "duplicate"),
    ([(None, "Seg A", None, None), (None, "Seg B", None, None), ("44100000", "A", None, "Goods")],
     "two segment rows"),
])
def test_parse_refuses_malformed_sheets(bad, match, monkeypatch):
    monkeypatch.setattr(bc, "FAMILY_TITLES_FROM_CHILDREN", {})
    with pytest.raises(ValueError, match=match):
        bc.parse(sheet(bad))


def test_download_checks_the_pinned_hash(tmp_path):
    fake = tmp_path / "codeset.xlsx"
    fake.write_bytes(b"not the codeset")
    with pytest.raises(SystemExit, match="SHA-256"):
        bc.download(fake)


@pytest.fixture(scope="module")
def committed():
    return pd.read_csv(bc.OUT, dtype=str, keep_default_na=False)


def test_committed_lookup_is_whole(committed):
    assert list(committed.columns) == bc.COLUMNS
    assert committed.code.is_unique and committed.code.str.fullmatch(r"\d{8}").all()
    assert (committed.segment_title != "").all()
    coded = committed[committed.level != "segment"]
    assert (coded.family_title != "").all()


def test_hand_titles_are_exactly_the_families_without_a_row(committed):
    family_rows = set(committed.code[committed.level == "family"].str[:4])
    derived = set(committed.family[committed.family_title_source == "derived from child codes"])
    used = set(committed.family[committed.family != ""])
    assert derived == set(bc.FAMILY_TITLES_FROM_CHILDREN)
    assert derived == used - family_rows


@pytest.mark.skipif(not bc.RAW.exists(), reason="raw codeset not downloaded (data/raw is not committed)")
def test_committed_lookup_matches_the_raw_codeset(committed):
    bc.download()  # checks the hash
    pd.testing.assert_frame_equal(bc.read_codeset().astype(str), committed)
